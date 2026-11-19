"""Structural diff of Doxygen/Graphviz call- and inheritance-graphs.

Doxygen (with ``DOT_CLEANUP = NO``) leaves the raw ``.dot`` sources of every
graph next to the generated HTML. Graph layouts are not stable: adding a
single new node can shift every other node's coordinates. Comparing the
rendered images pixel-by-pixel would therefore flag almost the whole image
as "changed" whenever a graph gains or loses a single element.

Instead we:
 1. Parse the ``.dot`` source and identify nodes by their *label* (which
    doxygen sets to the human readable, qualified function/class name) - not
    by their positional ``NodeN`` id, which is meaningless across versions.
 2. Diff the node/edge *sets* (added / removed / common) - a pure structural,
    layout-independent diff.
 3. Render the *new* graph via Graphviz ourselves (``dot -Tpng`` /
    ``dot -Tcmapx``) to get the exact pixel bounding box of every node in the
    new layout, and draw a red rectangle only around genuinely new nodes.
"""
from __future__ import annotations

import glob
import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

NODE_RE = re.compile(r'^\s*(Node\d+)\s*\[(.*)\]\s*;\s*$')
EDGE_RE = re.compile(r'^\s*(Node\d+)\s*->\s*(Node\d+)\s*\[(.*)\]\s*;\s*$')
ATTR_RE = re.compile(r'(\w+)\s*=\s*"((?:[^"\\]|\\.)*)"')
DIGRAPH_TITLE_RE = re.compile(r'^\s*digraph\s+"([^"]*)"')


_COMMON_WINDOWS_GRAPHVIZ_DIRS = [
    r"C:\Program Files\Graphviz\bin",
    r"C:\Program Files (x86)\Graphviz\bin",
]


def _resolve_dot_exe(dot_exe: str) -> str:
    """Resolve the 'dot' executable to an absolute, runnable path.

    On Windows, ``subprocess.run(["dot", ...])`` (without ``shell=True``)
    does *not* reliably search ``PATH`` the way a shell would, so a bare
    ``"dot"`` can fail with ``WinError 2`` even though Graphviz is installed
    and ``dot`` works fine from a terminal. ``shutil.which`` performs the
    same search a shell would (including ``PATHEXT``); if that still finds
    nothing (e.g. Graphviz's ``bin`` directory was never added to ``PATH``
    at all), fall back to probing a couple of common Windows install
    locations before giving up and returning the original value unchanged
    (so the original, clearer "file not found" error still surfaces).
    """
    found = shutil.which(dot_exe)
    if found:
        return found
    if os.name == "nt" and os.path.basename(dot_exe).lower() in ("dot", "dot.exe"):
        for d in _COMMON_WINDOWS_GRAPHVIZ_DIRS:
            candidate = os.path.join(d, "dot.exe")
            if os.path.isfile(candidate):
                return candidate
    return dot_exe

# Filename pattern used by Doxygen for member call/caller graphs, e.g.
# "class_calculator_a7d50f9c...42_icgraph.dot" or "main_8cpp_ae66...4_cgraph.dot"
MEMBER_GRAPH_RE = re.compile(r'^(?P<scope>.+)_(?P<hash>[0-9a-f]{16,40})_(?P<gtype>cgraph|icgraph)\.dot$')
# Other structural graphs: inheritance / collaboration / include / dependency
OTHER_GRAPH_RE = re.compile(
    r'^(?P<scope>.+?)__?(?P<gtype>inherit__graph|coll__graph|incl|dep)\.dot$'
)


def _parse_attrs(attr_str: str) -> Dict[str, str]:
    return {k: v for k, v in ATTR_RE.findall(attr_str)}


@dataclass
class DotGraph:
    path: str
    title: str = ""
    nodes: Dict[str, Dict[str, str]] = field(default_factory=dict)  # var name (Node1) -> attrs
    edges: List[Tuple[str, str]] = field(default_factory=list)  # (var_src, var_dst)

    def node_labels(self) -> Set[str]:
        return {a.get("label", n) for n, a in self.nodes.items()}

    def label_of(self, var: str) -> str:
        return self.nodes.get(var, {}).get("label", var)

    def edge_labels(self) -> Set[Tuple[str, str]]:
        return {(self.label_of(s), self.label_of(d)) for s, d in self.edges}

    def subject_label(self) -> Optional[str]:
        """The node representing the 'current' item the graph is drawn for
        (Doxygen fills it with fillcolor="grey60")."""
        for attrs in self.nodes.values():
            if attrs.get("fillcolor") == "grey60":
                return attrs.get("label")
        return None


def parse_dot(path: str) -> DotGraph:
    graph = DotGraph(path=path)
    logger.debug("Parsing dot file: %s", path)
    # Doxygen does not always write .dot files as pure UTF-8 (e.g. umlauts in
    # source comments can end up as Windows-1252/Latin-1 bytes). Rather than
    # crashing the whole report generation on a single stray byte, decode
    # leniently and just warn so the user can fix the source encoding.
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    if any("\ufffd" in line for line in lines):
        logger.warning(
            "Dot file %s contains bytes that are not valid UTF-8; "
            "offending characters were replaced with '\ufffd'. "
            "Check the encoding of the corresponding source file.",
            path,
        )
    for line in lines:
        m = DIGRAPH_TITLE_RE.match(line)
        if m:
            graph.title = m.group(1)
            break
    for line in lines:
        m = NODE_RE.match(line)
        if m:
            graph.nodes[m.group(1)] = _parse_attrs(m.group(2))
            continue
        m = EDGE_RE.match(line)
        if m:
            graph.edges.append((m.group(1), m.group(2)))
    return graph


def classify_graph_file(filename: str) -> Optional[Tuple[str, str, str]]:
    """Return (scope, gtype, key_hint) for a graph filename, or None if it
    should be ignored (e.g. the static graph_legend.dot)."""
    if filename == "graph_legend.dot":
        return None
    m = MEMBER_GRAPH_RE.match(filename)
    if m:
        return m.group("scope"), m.group("gtype"), ""
    m = OTHER_GRAPH_RE.match(filename)
    if m:
        return m.group("scope"), m.group("gtype"), ""
    return None


def discover_graphs(html_dir: str) -> Dict[Tuple[str, str, str], DotGraph]:
    """Discover graphs in a doxygen html output dir, keyed by a stable
    (scope, gtype, subject_label) tuple so that graphs can be matched across
    two versions even though the hash in the filename changes."""
    result: Dict[Tuple[str, str, str], DotGraph] = {}
    dot_files = glob.glob(os.path.join(html_dir, "*.dot"))
    logger.info("Discovering graphs in %s (%d .dot files found)", html_dir, len(dot_files))
    for path in dot_files:
        filename = os.path.basename(path)
        classified = classify_graph_file(filename)
        if classified is None:
            continue
        scope, gtype, _ = classified
        graph = parse_dot(path)
        subject = graph.subject_label() or graph.title
        key = (scope, gtype, subject)
        result[key] = graph
    return result


@dataclass
class GraphDiff:
    key: Tuple[str, str, str]
    added_nodes: Set[str]
    removed_nodes: Set[str]
    common_nodes: Set[str]
    added_edges: Set[Tuple[str, str]]
    removed_edges: Set[Tuple[str, str]]
    old_graph: Optional[DotGraph]
    new_graph: Optional[DotGraph]

    @property
    def changed(self) -> bool:
        return bool(self.added_nodes or self.removed_nodes or self.added_edges or self.removed_edges)


def diff_graphs(old: Optional[DotGraph], new: Optional[DotGraph], key) -> GraphDiff:
    old_labels = old.node_labels() if old else set()
    new_labels = new.node_labels() if new else set()
    old_edges = old.edge_labels() if old else set()
    new_edges = new.edge_labels() if new else set()
    return GraphDiff(
        key=key,
        added_nodes=new_labels - old_labels,
        removed_nodes=old_labels - new_labels,
        common_nodes=old_labels & new_labels,
        added_edges=new_edges - old_edges,
        removed_edges=old_edges - new_edges,
        old_graph=old,
        new_graph=new,
    )


def render_dot_with_map(dot_path: str, out_png: str, dot_exe: str = "dot") -> Dict[str, Tuple[int, int, int, int]]:
    """Render a .dot file to PNG and return a dict mapping each node's dot
    'id' attribute (e.g. "Node000001") to its pixel bounding box
    (x1, y1, x2, y2), obtained from Graphviz's own client-side image map
    (cmapx) - so the coordinates are guaranteed pixel-accurate for out_png.
    """
    dot_exe = _resolve_dot_exe(dot_exe)
    try:
        subprocess.run([dot_exe, "-Tpng", dot_path, "-o", out_png], check=True, capture_output=True)
        map_result = subprocess.run(
            [dot_exe, "-Tcmapx", dot_path], check=True, capture_output=True, encoding="utf-8", errors="replace"
        )
    except FileNotFoundError as e:
        raise FileNotFoundError(
            f"Graphviz 'dot' executable not found ({dot_exe!r}). Install Graphviz and make sure its "
            "'bin' directory is on PATH, or pass its full path via --dot <path-to-dot.exe>."
        ) from e
    boxes: Dict[str, Tuple[int, int, int, int]] = {}
    area_re = re.compile(r'<area shape="rect" id="([^"]+)"[^>]*coords="(\d+),(\d+),(\d+),(\d+)"')
    for m in area_re.finditer(map_result.stdout):
        node_id, x1, y1, x2, y2 = m.groups()
        boxes[node_id] = (int(x1), int(y1), int(x2), int(y2))
    return boxes


def render_graph_diff_image(
    new_dot_path: str,
    added_labels: Set[str],
    out_png: str,
    dot_exe: str = "dot",
) -> str:
    """Render the *new* graph to PNG and draw a red rectangle around every
    node whose label is in ``added_labels``. Returns out_png path."""
    from PIL import Image, ImageDraw

    graph = parse_dot(new_dot_path)
    boxes = render_dot_with_map(new_dot_path, out_png, dot_exe=dot_exe)
    # map label -> dot "id" attribute (e.g. Node000002)
    label_to_dotid = {attrs.get("label"): attrs.get("id") for attrs in graph.nodes.values()}

    raw = Image.open(out_png)
    if raw.mode in ("RGBA", "LA") or (raw.mode == "P" and "transparency" in raw.info):
        raw = raw.convert("RGBA")
        background = Image.new("RGBA", raw.size, (255, 255, 255, 255))
        img = Image.alpha_composite(background, raw).convert("RGB")
    else:
        img = raw.convert("RGB")
    draw = ImageDraw.Draw(img)
    pad = 4
    for label in added_labels:
        dot_id = label_to_dotid.get(label)
        if not dot_id or dot_id not in boxes:
            continue
        x1, y1, x2, y2 = boxes[dot_id]
        draw.rectangle([x1 - pad, y1 - pad, x2 + pad, y2 + pad], outline=(220, 20, 60), width=3)
    img.save(out_png)
    return out_png
