"""Derive links into Doxygen's own generated HTML output.

Doxygen's HTML file/anchor naming is a documented, stable convention:
- a compound's page is simply ``{refid}.html`` (the page compound's special
  "main page" is the one exception: refid ``indexpage`` maps to
  ``index.html``).
- a member's anchor on its owning compound's page is the memberdef's
  ``id`` attribute with the *compound* prefix (``{compound_refid}_1``)
  stripped off, e.g. ``class_calculator_1a7d50...`` -> anchor
  ``a7d50...`` on page ``class_calculator.html``.
"""
from __future__ import annotations

import os
import re
from typing import Optional

_MEMBER_ID_RE = re.compile(r'^(?P<compound_refid>.+)_1(?P<anchor>[0-9a-fA-F]{16,40})$')


def compound_page(kind: str, refid: str) -> Optional[str]:
    """HTML filename (relative to the html output dir) for a compound."""
    if not refid:
        return None
    if kind == "page" and refid == "indexpage":
        return "index.html"
    return f"{refid}.html"


def member_page_and_anchor(refid: str) -> Optional[str]:
    """Return 'compoundpage.html#anchor' for a memberdef refid, or None."""
    if not refid:
        return None
    m = _MEMBER_ID_RE.match(refid)
    if not m:
        return None
    return f"{m.group('compound_refid')}.html#{m.group('anchor')}"


def graph_scope_to_refid(scope: str, gtype: str) -> str:
    """The graph filename 'scope' component sometimes includes an extra
    '__dep' qualifier (for "included by" dependency graphs) that is not
    part of the actual compound refid the graph is displayed on."""
    if gtype == "incl" and scope.endswith("__dep"):
        return scope[: -len("__dep")]
    return scope


def relative_html_dir(out_dir: str, html_dir: Optional[str]) -> Optional[str]:
    """Relative path from the report's out_dir to a Doxygen html dir, using
    forward slashes so it works as a URL/href. Falls back to an absolute
    file:// URI if the two paths are on different drives (Windows) and no
    relative path can be computed."""
    if not html_dir:
        return None
    html_dir = os.path.abspath(html_dir)
    out_dir = os.path.abspath(out_dir)
    try:
        rel = os.path.relpath(html_dir, out_dir)
        return rel.replace(os.sep, "/")
    except ValueError:
        # different drives on Windows: fall back to an absolute file:// URI
        return "file:///" + html_dir.replace("\\", "/").lstrip("/")


def href(base: Optional[str], page_and_anchor: Optional[str]) -> Optional[str]:
    if not base or not page_and_anchor:
        return None
    return f"{base}/{page_and_anchor}"
