"""Structural + visual diff of Mermaid diagrams embedded via Doxygen's
``\\mermaid`` / ``\\endmermaid`` command (Doxygen >= ~1.17).

Unlike Graphviz call/inheritance graphs, Doxygen does **not** pre-render
Mermaid diagrams at generation time: the raw Mermaid source text is stored
verbatim in the XML (`<mermaid>...</mermaid>`) and in the HTML output it is
rendered *client-side* in the browser via mermaid.js. There is no `.dot`-like
intermediate file and no server-side layout we can reuse.

To still get a git-diff-style graphical comparison we:
 1. Parse the Mermaid source ourselves and, for ``flowchart``/``graph``
    diagrams (the most common kind and structurally similar to the Graphviz
    call graphs), extract the node/edge sets - a pure structural, purely
    textual diff (no layout involved, so it is 100% stable across renders).
 2. Render diagrams via the Mermaid CLI (``mmdc``, from the npm package
    ``@mermaid-js/mermaid-cli``), which drives a headless Chromium through
    Puppeteer to produce a real PNG.
 3. For flowcharts, inject a Mermaid ``classDef``/``class`` styling directive
    for every *added* node directly into the new diagram's source before
    rendering, so Mermaid itself highlights the new nodes in red - no manual
    bounding-box math required (unlike the Graphviz path in graphdiff.py).
 4. For every other diagram kind (sequence, class, state, ER, pie, timeline,
    gantt, mindmap, ...) - where we do not attempt to parse a node/edge model
    - we still render both versions to PNG and fall back to the same
    pixel-level bounding-box diff used for plain images (imagediff.py), so a
    "changed" diagram is still visually flagged even though it is not
    structurally understood.
"""
from __future__ import annotations

import logging
import os
import re
import shlex
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# Diagram kinds with a flowchart-like node/edge grammar we can structurally
# parse and highlight via injected ``class`` directives.
FLOWCHART_KINDS = {"flowchart", "graph"}

_KIND_RE = re.compile(r'^\s*([A-Za-z][A-Za-z0-9_-]*)')

# Statements that are not node/edge declarations and must be ignored while
# scanning a flowchart body.
_IGNORED_STATEMENT_RE = re.compile(
    r'^\s*(subgraph\b|end\s*$|classDef\b|class\b|click\b|style\b|linkStyle\b|'
    r'direction\b|%%|$)',
    re.IGNORECASE,
)

_INLINE_EDGE_LABEL_RE = re.compile(r'(--|==|-\.)\s+[^\n|]+?\s+(--|==|\.-)')
_PIPE_LABEL_RE = re.compile(r'\|[^|]*\|')
_ARROW_RE = re.compile(r'(-\.+->|-\.+-|={2,}>|={3,}|-{2,}>|-{2,}|~{2,})')
_NODE_ID_RE = re.compile(r'^\s*([A-Za-z0-9_\-.]+)')


def diagram_kind(source: str) -> str:
    """Return the Mermaid diagram kind (e.g. "flowchart", "sequenceDiagram",
    "pie", ...) based on the first keyword of the diagram source."""
    for line in source.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("%%"):
            continue
        m = _KIND_RE.match(stripped)
        return m.group(1) if m else ""
    return ""


@dataclass
class MermaidFlowchart:
    nodes: Set[str] = field(default_factory=set)
    edges: Set[Tuple[str, str]] = field(default_factory=set)


def _split_statements(source: str) -> List[str]:
    # Drop the diagram header line (e.g. "flowchart TD") and split the rest
    # into individual statements on both newlines and ';'.
    lines = source.splitlines()[1:]
    body = "\n".join(lines)
    return [s.strip() for s in re.split(r'[\n;]', body) if s.strip()]


def _node_id(token: str) -> Optional[str]:
    m = _NODE_ID_RE.match(token)
    return m.group(1) if m else None


def parse_flowchart(source: str) -> MermaidFlowchart:
    """Best-effort structural parse of a Mermaid ``flowchart``/``graph``
    diagram: extract the set of node ids and (source_id, dest_id) edges.

    This purposely only supports the common subset of Mermaid's flowchart
    grammar (arrows ``-->``, ``---``, ``-.->``, ``==>``, optional ``|label|``
    or inline ``-- label -->`` edge labels, and node shapes ``[...]``,
    ``(...)``, ``{...}``, ``((...))``, ``([...])``, ...). Anything it can't
    make sense of is simply skipped rather than raising, since this is a
    diagnostic diff, not a Mermaid parser/validator.
    """
    result = MermaidFlowchart()
    for stmt in _split_statements(source):
        if _IGNORED_STATEMENT_RE.match(stmt):
            continue
        stmt = _INLINE_EDGE_LABEL_RE.sub(lambda m: m.group(1) + m.group(2), stmt)
        stmt = _PIPE_LABEL_RE.sub("", stmt)
        parts = _ARROW_RE.split(stmt)
        # parts alternates node-token, arrow, node-token, arrow, ... for chained edges
        node_tokens = parts[0::2]
        ids = [_node_id(t) for t in node_tokens]
        ids = [i for i in ids if i]
        for i in ids:
            result.nodes.add(i)
        for a, b in zip(ids, ids[1:]):
            result.edges.add((a, b))
    return result


@dataclass
class MermaidGraphDiff:
    added_nodes: Set[str]
    removed_nodes: Set[str]
    added_edges: Set[Tuple[str, str]]
    removed_edges: Set[Tuple[str, str]]

    @property
    def changed(self) -> bool:
        return bool(self.added_nodes or self.removed_nodes or self.added_edges or self.removed_edges)


def diff_flowcharts(old_source: Optional[str], new_source: Optional[str]) -> MermaidGraphDiff:
    old_g = parse_flowchart(old_source) if old_source else MermaidFlowchart()
    new_g = parse_flowchart(new_source) if new_source else MermaidFlowchart()
    return MermaidGraphDiff(
        added_nodes=new_g.nodes - old_g.nodes,
        removed_nodes=old_g.nodes - new_g.nodes,
        added_edges=new_g.edges - old_g.edges,
        removed_edges=old_g.edges - new_g.edges,
    )


# Common Windows Node.js install locations to probe as a last resort if the
# executable isn't found on PATH at all (e.g. Node.js installed but its
# install directory was never added to PATH).
_COMMON_WINDOWS_NODE_DIRS = [
    r"C:\Program Files\nodejs",
    r"C:\Program Files (x86)\nodejs",
    os.path.expandvars(r"%APPDATA%\npm"),
]


def _resolve_mmdc(mmdc_cmd: str) -> List[str]:
    parts = shlex.split(mmdc_cmd)
    if not parts:
        raise ValueError("empty --mmdc command")
    exe = parts[0]
    resolved = shutil.which(exe)
    if not resolved and os.name == "nt":
        for d in _COMMON_WINDOWS_NODE_DIRS:
            for candidate in (os.path.join(d, exe), os.path.join(d, exe + ".cmd"), os.path.join(d, exe + ".exe")):
                if os.path.isfile(candidate):
                    resolved = candidate
                    break
            if resolved:
                break
    if not resolved:
        raise FileNotFoundError(
            f"'{exe}' not found. Install Node.js (https://nodejs.org, includes npm/npx) and make sure its "
            f"install directory is on PATH, or pass a full command via --mmdc \"<path-to-mmdc-or-npx> ...\"."
        )
    parts[0] = resolved
    return parts


def render_mermaid(source: str, out_png: str, mmdc_cmd: str = "npx --yes @mermaid-js/mermaid-cli") -> str:
    """Render Mermaid ``source`` to a PNG file at ``out_png`` using the
    Mermaid CLI (``mmdc``). Requires Node.js; ``mmdc_cmd`` defaults to
    invoking the CLI on-demand via ``npx`` so a global install isn't
    required."""
    cmd = _resolve_mmdc(mmdc_cmd)
    with tempfile.NamedTemporaryFile(suffix=".mmd", delete=False, mode="w", encoding="utf-8") as f:
        f.write(source)
        in_path = f.name
    try:
        result = subprocess.run(
            cmd + ["-i", in_path, "-o", out_png, "-b", "white"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if result.returncode != 0 or not os.path.isfile(out_png):
            raise RuntimeError(
                f"mmdc failed (exit {result.returncode}): {result.stderr.strip() or result.stdout.strip()}"
            )
    finally:
        os.remove(in_path)
    return out_png


def render_flowchart_diff_image(
    new_source: str,
    added_nodes: Set[str],
    out_png: str,
    mmdc_cmd: str = "npx --yes @mermaid-js/mermaid-cli",
) -> str:
    """Render the *new* flowchart, highlighting every added node in red by
    injecting a Mermaid ``classDef``/``class`` directive - Mermaid does the
    highlighting itself, so no pixel-level bounding-box math is needed."""
    src = new_source.rstrip("\n")
    if added_nodes:
        src += "\nclassDef ddiffAdded fill:#ffd7d7,stroke:#cc0000,stroke-width:3px,color:#600;\n"
        for node_id in sorted(added_nodes):
            src += f"class {node_id} ddiffAdded;\n"
    return render_mermaid(src, out_png, mmdc_cmd=mmdc_cmd)
