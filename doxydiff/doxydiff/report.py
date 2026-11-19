"""Build the doxydiff HTML report: an overview of all differences plus
per-element git-diff style detail views, for members, compounds (incl.
pages/markdown), images and call/inheritance graphs.
"""
from __future__ import annotations

import html
import logging
import os
import shutil
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .matcher import CompoundDiff, MemberDiff, ProjectDiff, match_projects
from .xmlparse import parse_project
from .textdiff import inline_diff_html, line_diff_html, count_changed_lines
from .graphdiff import discover_graphs, diff_graphs, render_graph_diff_image
from .imagediff import diff_images, render_highlighted_image
from . import mermaiddiff
from . import doxylink

logger = logging.getLogger(__name__)



KIND_LABELS = {
    "class": "Class", "struct": "Struct", "union": "Union", "interface": "Interface",
    "namespace": "Namespace", "file": "File", "dir": "Directory", "page": "Page",
    "group": "Group", "concept": "Concept",
}


def _anchor(s: str) -> str:
    out = []
    for ch in s:
        out.append(ch if ch.isalnum() else "_")
    return "id_" + "".join(out)


@dataclass
class Stats:
    compounds_added: int = 0
    compounds_removed: int = 0
    compounds_modified: int = 0
    members_added: int = 0
    members_removed: int = 0
    members_modified: int = 0
    members_moved: int = 0
    images_changed: int = 0
    graphs_changed: int = 0
    mermaid_changed: int = 0
    lines_added: int = 0
    lines_removed: int = 0
    doc_lines_old_total: int = 0

    @property
    def lines_removed_pct(self) -> float:
        """Percentage of the OLD version's total documentation lines that
        were removed - useful as a CI regression signal (e.g. "more than
        10% of documentation disappeared")."""
        if not self.doc_lines_old_total:
            return 0.0
        return round(100.0 * self.lines_removed / self.doc_lines_old_total, 2)

    def as_dict(self) -> dict:
        d = {k: getattr(self, k) for k in (
            "compounds_added", "compounds_removed", "compounds_modified",
            "members_added", "members_removed", "members_modified", "members_moved",
            "images_changed", "graphs_changed", "mermaid_changed", "lines_added", "lines_removed",
            "doc_lines_old_total",
        )}
        d["lines_removed_pct"] = self.lines_removed_pct
        return d


@dataclass
class ReportResult:
    out_path: str
    stats: Stats


def _count_lines(*texts: str) -> int:
    total = 0
    for t in texts:
        if t:
            total += len(t.splitlines())
    return total


def _project_doc_line_total(project) -> int:
    total = 0
    for c in project.compounds.values():
        total += _count_lines(c.brief, c.detailed, c.title)
        for m in c.members.values():
            total += _count_lines(m.brief, m.detailed)
    return total


def _collect_stats(pdiff: ProjectDiff) -> Stats:
    s = Stats()
    for cd in pdiff.compound_diffs:
        if cd.status == "added":
            s.compounds_added += 1
        elif cd.status == "removed":
            s.compounds_removed += 1
        elif cd.status == "modified":
            s.compounds_modified += 1
        for md in cd.member_diffs:
            if md.status == "added":
                s.members_added += 1
            elif md.status == "removed":
                s.members_removed += 1
            elif md.status == "modified":
                s.members_modified += 1
                a, r = count_changed_lines(
                    (md.old.detailed if md.old else "") + "\n" + (md.old.brief if md.old else ""),
                    (md.new.detailed if md.new else "") + "\n" + (md.new.brief if md.new else ""),
                )
                s.lines_added += a
                s.lines_removed += r
            elif md.status == "moved":
                s.members_moved += 1
        if cd.status == "modified" and cd.old and cd.new:
            a, r = count_changed_lines(cd.old.detailed + "\n" + cd.old.brief, cd.new.detailed + "\n" + cd.new.brief)
            s.lines_added += a
            s.lines_removed += r
    return s


CSS = """
body { font-family: -apple-system, Segoe UI, Arial, sans-serif; margin: 0; background:#f6f8fa; color:#24292f; }
header { background:#24292f; color:white; padding: 16px 24px; }
header h1 { margin:0; font-size: 20px; }
.container { max-width: 1100px; margin: 0 auto; padding: 16px 24px 64px; }
.stats { display:flex; flex-wrap:wrap; gap:10px; margin: 16px 0; }
.stat-badge { background:white; border:1px solid #d0d7de; border-radius:6px; padding:8px 14px; font-size:13px; }
.stat-badge b { font-size:16px; display:block; }
table.overview { width:100%; border-collapse:collapse; background:white; border:1px solid #d0d7de; border-radius:6px; overflow:hidden;}
table.overview th, table.overview td { text-align:left; padding:6px 10px; border-bottom:1px solid #eaeef2; font-size:13px; }
table.overview th { background:#f6f8fa; }
.badge { display:inline-block; padding:1px 8px; border-radius:10px; font-size:11px; font-weight:600; color:white; }
.badge.added { background:#1a7f37; }
.badge.removed { background:#cf222e; }
.badge.modified { background:#9a6700; }
.badge.moved { background:#0969da; }
.badge.unchanged { background:#8c959f; }
a { color:#0969da; text-decoration:none; }
a:hover { text-decoration:underline; }
section.detail { background:white; border:1px solid #d0d7de; border-radius:6px; margin: 18px 0; padding: 14px 18px; }
section.detail h2 { margin-top:0; font-size:16px; }
section.detail h3 { font-size:14px; margin-bottom:4px; }
.del { background:#ffebe9; color:#82071e; text-decoration: line-through; }
.ins { background:#dafbe1; color:#116329; }
.line { font-family: Consolas, monospace; font-size: 12.5px; white-space: pre-wrap; padding: 1px 6px; border-radius: 2px;}
.line.del { background:#ffebe9; }
.line.ins { background:#dafbe1; }
.line.ctx { color:#57606a; }
.marker { display:inline-block; width:14px; color:#57606a; }
.subtle { color:#57606a; font-size:12px; }
img.diffimg { max-width: 100%; border:1px solid #d0d7de; border-radius:4px; }
.backlink { font-size:12px; }
.doclinks { margin: 4px 0 10px; }
.doclinks a { display:inline-block; font-size:12px; padding:2px 8px; margin-right:6px; border-radius:4px; border:1px solid #d0d7de; background:#f6f8fa; }
.doclinks a.v1 { border-color:#cf222e55; }
.doclinks a.v2 { border-color:#1a7f3755; }
hr { border:none; border-top:1px solid #eaeef2; margin: 10px 0; }
"""


def _doclinks_html(old_href: Optional[str], new_href: Optional[str]) -> str:
    if not old_href and not new_href:
        return ""
    parts = ['<div class="doclinks">']
    if old_href:
        parts.append(f'<a class="v1" href="{old_href}" target="_blank" rel="noopener">&#128194; view in v1 docs</a>')
    if new_href:
        parts.append(f'<a class="v2" href="{new_href}" target="_blank" rel="noopener">&#128194; view in v2 docs</a>')
    parts.append("</div>")
    return "".join(parts)


def _member_row_html(md: MemberDiff) -> Tuple[str, str]:
    anchor = _anchor(md.identity)
    name = (md.new or md.old).display_name if (md.new or md.old) else md.identity
    return anchor, name


def _render_member_detail(md: MemberDiff, rel_old_html: Optional[str], rel_new_html: Optional[str]) -> str:
    anchor, name = _member_row_html(md)
    parts = [f'<div id="{anchor}"></div>']
    parts.append(f'<h3>{html.escape(name)} <span class="badge {md.status}">{md.status}</span></h3>')
    old_href = doxylink.href(rel_old_html, doxylink.member_page_and_anchor(md.old.refid)) if md.old else None
    new_href = doxylink.href(rel_new_html, doxylink.member_page_and_anchor(md.new.refid)) if md.new else None
    parts.append(_doclinks_html(old_href, new_href))
    if md.status == "moved":
        parts.append(f'<p class="subtle">moved from <code>{html.escape(md.old_scope)}</code> to <code>{html.escape(md.new_scope)}</code></p>')
    if md.status in ("modified", "moved") and md.old and md.new:
        if md.old.brief != md.new.brief:
            parts.append("<p><b>Brief:</b><br/>" + inline_diff_html(md.old.brief, md.new.brief) + "</p>")
        if md.old.detailed != md.new.detailed:
            parts.append("<p><b>Description:</b></p>")
            parts.append(line_diff_html(md.old.detailed, md.new.detailed))
        if md.old.signature != md.new.signature:
            parts.append('<p><b>Signature:</b><br/>' + inline_diff_html(md.old.signature, md.new.signature) + "</p>")
    elif md.status == "added" and md.new:
        parts.append('<p class="subtle">' + html.escape(md.new.signature) + "</p>")
        if md.new.brief or md.new.detailed:
            parts.append(line_diff_html("", (md.new.brief + "\n\n" + md.new.detailed).strip()))
    elif md.status == "removed" and md.old:
        parts.append('<p class="subtle">' + html.escape(md.old.signature) + "</p>")
        if md.old.brief or md.old.detailed:
            parts.append(line_diff_html((md.old.brief + "\n\n" + md.old.detailed).strip(), ""))
    parts.append('<hr/>')
    return "\n".join(parts)


def _member_name_index(project) -> Dict[str, "object"]:
    """Map a graph node's label (e.g. 'Calculator::divide' or 'main') back
    to the Member it represents, so member-level graphs (call/caller
    graphs) can link to the *exact* anchor on the compound's HTML page
    instead of just the top of the page."""
    idx = {}
    for c in project.compounds.values():
        for m in c.members.values():
            key = m.name if m.scope_id == "<global>" else f"{m.scope_id}::{m.name}"
            idx[key] = m
    return idx


def build_report(
    old_xml: str,
    new_xml: str,
    out_dir: str,
    old_html: Optional[str] = None,
    new_html: Optional[str] = None,
    dot_exe: str = "dot",
    mmdc_cmd: str = "npx --yes @mermaid-js/mermaid-cli",
    project_name: str = "Project",
) -> ReportResult:
    os.makedirs(out_dir, exist_ok=True)
    assets_dir = os.path.join(out_dir, "assets")
    os.makedirs(assets_dir, exist_ok=True)

    rel_old_html = doxylink.relative_html_dir(out_dir, old_html)
    rel_new_html = doxylink.relative_html_dir(out_dir, new_html)

    logger.info("Parsing old Doxygen XML from %s", old_xml)
    old_project = parse_project(old_xml)
    logger.info("Parsing new Doxygen XML from %s", new_xml)
    new_project = parse_project(new_xml)
    logger.info("Matching compounds/members between old and new project")
    pdiff = match_projects(old_project, new_project)
    stats = _collect_stats(pdiff)
    stats.doc_lines_old_total = _project_doc_line_total(old_project)
    old_name_index = _member_name_index(old_project)
    new_name_index = _member_name_index(new_project)

    overview_rows = []
    detail_sections = []

    for cd in pdiff.compound_diffs:
        if cd.status == "unchanged":
            continue
        kind_label = KIND_LABELS.get(cd.kind, cd.kind)
        name = (cd.new or cd.old).name
        c_anchor = _anchor(cd.id)
        changed_member_count = sum(1 for md in cd.member_diffs if md.status != "unchanged")
        overview_rows.append(
            f'<tr><td><span class="badge {cd.status}">{cd.status}</span></td>'
            f'<td>{kind_label}</td><td><a href="#{c_anchor}">{html.escape(name)}</a></td>'
            f'<td>{html.escape(cd.id)}</td><td>{changed_member_count}</td></tr>'
        )

        section = [f'<section class="detail" id="{c_anchor}">']
        section.append(f'<h2>{kind_label}: {html.escape(name)} <span class="badge {cd.status}">{cd.status}</span></h2>')
        section.append(f'<p class="subtle">{html.escape(cd.id)} &middot; <a class="backlink" href="#overview">&uarr; back to overview</a></p>')
        old_page = doxylink.compound_page(cd.kind, cd.old.refid) if cd.old else None
        new_page = doxylink.compound_page(cd.kind, cd.new.refid) if cd.new else None
        section.append(_doclinks_html(doxylink.href(rel_old_html, old_page), doxylink.href(rel_new_html, new_page)))
        if cd.status == "modified" and cd.old and cd.new:
            if cd.old.title != cd.new.title:
                section.append("<p><b>Title:</b><br/>" + inline_diff_html(cd.old.title, cd.new.title) + "</p>")
            if cd.old.brief != cd.new.brief:
                section.append("<p><b>Brief:</b><br/>" + inline_diff_html(cd.old.brief, cd.new.brief) + "</p>")
            if cd.old.detailed != cd.new.detailed:
                section.append("<p><b>Description:</b></p>")
                section.append(line_diff_html(cd.old.detailed, cd.new.detailed))
        elif cd.status == "added" and cd.new:
            if cd.new.brief or cd.new.detailed:
                section.append(line_diff_html("", (cd.new.brief + "\n\n" + cd.new.detailed).strip()))
        elif cd.status == "removed" and cd.old:
            if cd.old.brief or cd.old.detailed:
                section.append(line_diff_html((cd.old.brief + "\n\n" + cd.old.detailed).strip(), ""))

        changed_members = [md for md in cd.member_diffs if md.status != "unchanged"]
        for md in changed_members:
            anchor, mname = _member_row_html(md)
            overview_rows.append(
                f'<tr><td><span class="badge {md.status}">{md.status}</span></td>'
                f'<td>member</td><td><a href="#{anchor}">{html.escape(mname)}</a></td>'
                f'<td>{html.escape(cd.id)}</td><td></td></tr>'
            )
            section.append(_render_member_detail(md, rel_old_html, rel_new_html))

        section.append("</section>")
        detail_sections.append("\n".join(section))

    # --- Images -----------------------------------------------------
    image_sections = []
    if True:
        logger.info("Comparing images referenced by old and new project")
        all_images: Dict[str, Tuple[Optional[str], Optional[str]]] = {}
        for c in old_project.compounds.values():
            for name in c.images:
                all_images.setdefault(name, [None, None])[0] = name
        for c in new_project.compounds.values():
            for name in c.images:
                all_images.setdefault(name, [None, None])[1] = name

        for name in sorted(all_images):
            old_path = os.path.join(old_xml, name)
            new_path = os.path.join(new_xml, name)
            old_exists = os.path.isfile(old_path)
            new_exists = os.path.isfile(new_path)
            anchor = _anchor("image:" + name)
            if old_exists and new_exists:
                try:
                    result = diff_images(old_path, new_path)
                except FileNotFoundError:
                    continue
                if result.identical:
                    continue
                stats.images_changed += 1
                out_name = f"img_{len(image_sections)}_{os.path.basename(name)}"
                out_path = os.path.join(assets_dir, out_name)
                render_highlighted_image(new_path, result.bbox, out_path)
                overview_rows.append(
                    f'<tr><td><span class="badge modified">modified</span></td><td>image</td>'
                    f'<td><a href="#{anchor}">{html.escape(name)}</a></td><td></td><td></td></tr>'
                )
                pct = round(result.changed_pixel_ratio * 100, 1)
                image_sections.append(
                    f'<section class="detail" id="{anchor}"><h2>Image: {html.escape(name)} '
                    f'<span class="badge modified">modified</span></h2>'
                    f'<p class="subtle">{pct}% of pixels changed'
                    + (" &middot; size changed" if result.size_changed else "")
                    + f' &middot; <a class="backlink" href="#overview">&uarr; back to overview</a></p>'
                    + _doclinks_html(doxylink.href(rel_old_html, name), doxylink.href(rel_new_html, name))
                    + f'<p><b>New version (changed region outlined in red):</b><br/>'
                    f'<img class="diffimg" src="assets/{out_name}"/></p>'
                    f'</section>'
                )
            elif old_exists and not new_exists:
                stats.images_changed += 1
                overview_rows.append(
                    f'<tr><td><span class="badge removed">removed</span></td><td>image</td>'
                    f'<td><a href="#{anchor}">{html.escape(name)}</a></td><td></td><td></td></tr>'
                )
                image_sections.append(
                    f'<section class="detail" id="{anchor}"><h2>Image: {html.escape(name)} '
                    f'<span class="badge removed">removed</span></h2></section>'
                )
            elif new_exists and not old_exists:
                stats.images_changed += 1
                overview_rows.append(
                    f'<tr><td><span class="badge added">added</span></td><td>image</td>'
                    f'<td><a href="#{anchor}">{html.escape(name)}</a></td><td></td><td></td></tr>'
                )
                image_sections.append(
                    f'<section class="detail" id="{anchor}"><h2>Image: {html.escape(name)} '
                    f'<span class="badge added">added</span></h2></section>'
                )

    # --- Graphs -------------------------------------------------------
    graph_sections = []
    if old_html and new_html:
        logger.info("Comparing call/inheritance graphs between old and new html output")
        old_graphs = discover_graphs(old_html)
        new_graphs = discover_graphs(new_html)
        all_keys = set(old_graphs) | set(new_graphs)
        for key in sorted(all_keys, key=lambda k: (k[0], k[1], k[2] or "")):
            old_g = old_graphs.get(key)
            new_g = new_graphs.get(key)
            gd = diff_graphs(old_g, new_g, key)
            if not gd.changed:
                continue
            scope, gtype, subject = key
            status = "added" if old_g is None else "removed" if new_g is None else "modified"
            stats.graphs_changed += 1
            anchor = _anchor("graph:" + scope + gtype + str(subject))

            old_gh = new_gh = None
            if gtype in ("cgraph", "icgraph") and subject:
                old_m = old_name_index.get(subject)
                new_m = new_name_index.get(subject)
                if old_g is not None and old_m:
                    old_gh = doxylink.href(rel_old_html, doxylink.member_page_and_anchor(old_m.refid))
                if new_g is not None and new_m:
                    new_gh = doxylink.href(rel_new_html, doxylink.member_page_and_anchor(new_m.refid))
            else:
                refid = doxylink.graph_scope_to_refid(scope, gtype)
                if old_g is not None:
                    old_gh = doxylink.href(rel_old_html, doxylink.compound_page("", refid))
                if new_g is not None:
                    new_gh = doxylink.href(rel_new_html, doxylink.compound_page("", refid))

            overview_rows.append(
                f'<tr><td><span class="badge {status}">{status}</span></td><td>graph ({gtype})</td>'
                f'<td><a href="#{anchor}">{html.escape(str(subject))}</a></td><td>{html.escape(scope)}</td><td></td></tr>'
            )
            img_tag = ""
            if new_g is not None:
                out_name = f"graph_{len(graph_sections)}_{scope}_{gtype}.png"
                out_path = os.path.join(assets_dir, out_name)
                try:
                    render_graph_diff_image(new_g.path, gd.added_nodes, out_path, dot_exe=dot_exe)
                    img_tag = f'<img class="diffimg" src="assets/{out_name}"/>'
                except Exception as e:  # pragma: no cover - graphviz optional at runtime
                    img_tag = f'<p class="subtle">(could not render graph image: {html.escape(str(e))})</p>'
            details = []
            if gd.added_nodes:
                details.append("<b>New nodes:</b> " + ", ".join(f"<code>{html.escape(n)}</code>" for n in sorted(gd.added_nodes)))
            if gd.removed_nodes:
                details.append("<b>Removed nodes:</b> " + ", ".join(f"<code>{html.escape(n)}</code>" for n in sorted(gd.removed_nodes)))
            if gd.added_edges:
                details.append("<b>New edges:</b> " + ", ".join(f"<code>{html.escape(a)} &rarr; {html.escape(b)}</code>" for a, b in sorted(gd.added_edges)))
            if gd.removed_edges:
                details.append("<b>Removed edges:</b> " + ", ".join(f"<code>{html.escape(a)} &rarr; {html.escape(b)}</code>" for a, b in sorted(gd.removed_edges)))
            graph_sections.append(
                f'<section class="detail" id="{anchor}"><h2>Graph ({html.escape(gtype)}): {html.escape(str(subject))} '
                f'<span class="badge {status}">{status}</span></h2>'
                f'<p class="subtle">in {html.escape(scope)} &middot; <a class="backlink" href="#overview">&uarr; back to overview</a></p>'
                + _doclinks_html(old_gh, new_gh)
                + "<p>" + "<br/>".join(details) + "</p>"
                + f"<p>{img_tag}</p></section>"
            )

    # --- Mermaid diagrams ----------------------------------------------
    mermaid_sections = []
    logger.info("Comparing Mermaid diagrams referenced by old and new project")
    all_mermaids: Dict[str, List[Optional["object"]]] = {}

    def _collect_mermaids(project, idx):
        for c in project.compounds.values():
            for mm in c.mermaids:
                all_mermaids.setdefault(mm.key, [None, None])[idx] = mm
            for m in c.members.values():
                for mm in m.mermaids:
                    all_mermaids.setdefault(mm.key, [None, None])[idx] = mm

    _collect_mermaids(old_project, 0)
    _collect_mermaids(new_project, 1)

    def _mermaid_doclink(mm, rel_html):
        if mm is None:
            return None
        if mm.owner_kind == "member":
            return doxylink.href(rel_html, doxylink.member_page_and_anchor(mm.owner_refid))
        return doxylink.href(rel_html, doxylink.compound_page(mm.owner_compound_kind, mm.owner_refid))

    for key in sorted(all_mermaids):
        old_mm, new_mm = all_mermaids[key]
        old_src = old_mm.source if old_mm else None
        new_src = new_mm.source if new_mm else None
        if old_src == new_src:
            continue
        stats.mermaid_changed += 1
        anchor = _anchor("mermaid:" + key)
        status = "added" if old_mm is None else "removed" if new_mm is None else "modified"
        ref = new_mm or old_mm
        kind = mermaiddiff.diagram_kind(new_src or old_src or "")

        overview_rows.append(
            f'<tr><td><span class="badge {status}">{status}</span></td><td>mermaid ({html.escape(kind or "diagram")})</td>'
            f'<td><a href="#{anchor}">{html.escape(ref.owner_label)}</a></td><td></td><td></td></tr>'
        )

        img_tag = ""
        details_html = ""
        try:
            out_name = f"mermaid_{len(mermaid_sections)}.png"
            out_path = os.path.join(assets_dir, out_name)
            if kind in mermaiddiff.FLOWCHART_KINDS and new_src:
                # Flowchart/graph: structural node/edge diff + Mermaid-native
                # red highlighting of added nodes (no bounding-box math).
                gd = mermaiddiff.diff_flowcharts(old_src, new_src)
                mermaiddiff.render_flowchart_diff_image(new_src, gd.added_nodes, out_path, mmdc_cmd=mmdc_cmd)
                img_tag = f'<img class="diffimg" src="assets/{out_name}"/>'
                details = []
                if gd.added_nodes:
                    details.append("<b>New nodes:</b> " + ", ".join(f"<code>{html.escape(n)}</code>" for n in sorted(gd.added_nodes)))
                if gd.removed_nodes:
                    details.append("<b>Removed nodes:</b> " + ", ".join(f"<code>{html.escape(n)}</code>" for n in sorted(gd.removed_nodes)))
                if gd.added_edges:
                    details.append("<b>New edges:</b> " + ", ".join(f"<code>{html.escape(a)} &rarr; {html.escape(b)}</code>" for a, b in sorted(gd.added_edges)))
                if gd.removed_edges:
                    details.append("<b>Removed edges:</b> " + ", ".join(f"<code>{html.escape(a)} &rarr; {html.escape(b)}</code>" for a, b in sorted(gd.removed_edges)))
                if details:
                    details_html = "<p>" + "<br/>".join(details) + "</p>"
            elif new_src and old_src:
                # Any other Mermaid diagram kind (sequence/class/state/ER/
                # pie/timeline/gantt/...): no structural model, so fall back
                # to a generic rendered pixel diff, same as for plain images.
                old_png = os.path.join(assets_dir, f"mermaid_{len(mermaid_sections)}_old.png")
                new_png = os.path.join(assets_dir, f"mermaid_{len(mermaid_sections)}_new.png")
                try:
                    mermaiddiff.render_mermaid(old_src, old_png, mmdc_cmd=mmdc_cmd)
                    mermaiddiff.render_mermaid(new_src, new_png, mmdc_cmd=mmdc_cmd)
                    result = diff_images(old_png, new_png)
                    render_highlighted_image(new_png, result.bbox, out_path)
                    img_tag = f'<img class="diffimg" src="assets/{out_name}"/>'
                finally:
                    for p in (old_png, new_png):
                        if os.path.isfile(p):
                            os.remove(p)
            elif new_src:
                mermaiddiff.render_mermaid(new_src, out_path, mmdc_cmd=mmdc_cmd)
                img_tag = f'<img class="diffimg" src="assets/{out_name}"/>'
            elif old_src:
                mermaiddiff.render_mermaid(old_src, out_path, mmdc_cmd=mmdc_cmd)
                img_tag = f'<img class="diffimg" src="assets/{out_name}"/>'
        except Exception as e:  # pragma: no cover - mermaid-cli/Node.js optional at runtime
            img_tag = f'<p class="subtle">(could not render mermaid diagram: {html.escape(str(e))})</p>'

        mermaid_sections.append(
            f'<section class="detail" id="{anchor}"><h2>Mermaid diagram ({html.escape(kind or "diagram")}): {html.escape(ref.owner_label)} '
            f'<span class="badge {status}">{status}</span></h2>'
            f'<p class="subtle"><a class="backlink" href="#overview">&uarr; back to overview</a></p>'
            + _doclinks_html(_mermaid_doclink(old_mm, rel_old_html), _mermaid_doclink(new_mm, rel_new_html))
            + details_html
            + line_diff_html(old_src or "", new_src or "")
            + f"<p>{img_tag}</p></section>"
        )


    summary_html = f"""
    <div class="stats">
      <div class="stat-badge"><b>{stats.compounds_modified}</b>Compounds modified</div>
      <div class="stat-badge"><b>{stats.compounds_added}</b>Compounds added</div>
      <div class="stat-badge"><b>{stats.compounds_removed}</b>Compounds removed</div>
      <div class="stat-badge"><b>{stats.members_added}</b>Members added</div>
      <div class="stat-badge"><b>{stats.members_removed}</b>Members removed</div>
      <div class="stat-badge"><b>{stats.members_modified}</b>Members modified</div>
      <div class="stat-badge"><b>{stats.members_moved}</b>Members moved</div>
      <div class="stat-badge"><b>{stats.images_changed}</b>Images changed</div>
      <div class="stat-badge"><b>{stats.graphs_changed}</b>Graphs changed</div>
      <div class="stat-badge"><b>{stats.mermaid_changed}</b>Mermaid diagrams changed</div>
      <div class="stat-badge"><b>+{stats.lines_added}</b>Doc lines added</div>
      <div class="stat-badge"><b>-{stats.lines_removed}</b>Doc lines removed</div>
      <div class="stat-badge"><b>{stats.lines_removed_pct}%</b>of old doc lines removed</div>
    </div>
    """

    html_doc = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/>
<title>doxydiff report: {html.escape(project_name)}</title>
<style>{CSS}</style></head>
<body>
<header><h1>doxydiff &middot; {html.escape(project_name)}</h1>
<div class="subtle" style="color:#c9d1d9;">old: {html.escape(old_xml)}<br/>new: {html.escape(new_xml)}</div></header>
<div class="container">
{summary_html}
<h2 id="overview">Overview of all differences</h2>
<table class="overview">
<tr><th>Status</th><th>Kind</th><th>Name</th><th>Location / Scope</th><th>Changed members</th></tr>
{''.join(overview_rows) if overview_rows else '<tr><td colspan="5">No differences found.</td></tr>'}
</table>

<h2>Details</h2>
{''.join(detail_sections)}
{''.join(image_sections)}
{''.join(graph_sections)}
{''.join(mermaid_sections)}
</div>
</body></html>
"""

    out_path = os.path.join(out_dir, "index.html")
    logger.info("Writing HTML report to %s", out_path)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_doc)
    return ReportResult(out_path=out_path, stats=stats)
