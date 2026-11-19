"""Render Doxygen description XML (briefdescription/detaileddescription and
similar "docCmdGroup" content) into normalized, diff-friendly plain text.

The rendering is intentionally lossy (it is not meant to reproduce HTML) but
stable and readable, so that two renderings of semantically-equal XML always
produce the same text, while any real content change shows up as a text
change that ``difflib`` can highlight in a git-diff style.
"""
from __future__ import annotations

from typing import List
import xml.etree.ElementTree as ET


class RenderContext:
    def __init__(self):
        self.images: List[str] = []  # image file names referenced in this description
        self.mermaids: List[str] = []  # raw \mermaid ... \endmermaid diagram sources


def _text(s):
    return s if s else ""


def render_children(elem: ET.Element, ctx: RenderContext) -> str:
    parts = []
    if elem.text:
        parts.append(elem.text)
    for child in elem:
        parts.append(render_element(child, ctx))
        if child.tail:
            parts.append(child.tail)
    return "".join(parts)


def render_element(elem: ET.Element, ctx: RenderContext) -> str:
    tag = elem.tag
    inner = render_children(elem, ctx)

    if tag == "para":
        return inner.strip() + "\n\n"
    if tag == "sp":
        return " "
    if tag == "linebreak":
        return "\n"
    if tag in ("bold", "b"):
        return f"**{inner.strip()}**"
    if tag in ("emphasis", "i"):
        return f"*{inner.strip()}*"
    if tag == "computeroutput":
        return f"`{inner.strip()}`"
    if tag == "ref":
        return inner.strip()
    if tag == "ulink":
        url = elem.get("url", "")
        return f"{inner.strip()} ({url})"
    if tag == "anchor":
        return ""
    if tag in ("itemizedlist",):
        items = []
        for li in elem.findall("listitem"):
            items.append("- " + render_children(li, ctx).strip())
        return "\n".join(items) + "\n"
    if tag == "orderedlist":
        items = []
        for i, li in enumerate(elem.findall("listitem"), 1):
            items.append(f"{i}. " + render_children(li, ctx).strip())
        return "\n".join(items) + "\n"
    if tag == "listitem":
        return inner
    if tag in ("sect1", "sect2", "sect3", "sect4"):
        return inner
    if tag == "title":
        return "\n## " + inner.strip() + "\n\n"
    if tag == "simplesect":
        kind = elem.get("kind", "")
        prefix = {
            "return": "Returns: ",
            "see": "See also: ",
            "note": "Note: ",
            "warning": "Warning: ",
            "author": "Author: ",
            "since": "Since: ",
            "pre": "Precondition: ",
            "post": "Postcondition: ",
        }.get(kind, f"{kind.capitalize()}: " if kind else "")
        return prefix + inner.strip() + "\n"
    if tag == "parameterlist":
        kind = elem.get("kind", "param")
        header = {"param": "Parameters", "retval": "Return values", "exception": "Exceptions"}.get(kind, "Parameters")
        lines = [f"{header}:"]
        for item in elem.findall("parameteritem"):
            names = []
            namelist = item.find("parameternamelist")
            if namelist is not None:
                for pn in namelist.findall("parametername"):
                    names.append("".join(pn.itertext()).strip())
            desc_elem = item.find("parameterdescription")
            desc = render_children(desc_elem, ctx).strip() if desc_elem is not None else ""
            lines.append(f"  - {', '.join(names)}: {desc}")
        return "\n".join(lines) + "\n"
    if tag == "image":
        name = elem.get("name", "")
        img_type = elem.get("type", "")
        if name and img_type in ("", "html"):
            ctx.images.append(name)
        return f"[image: {name}]"
    if tag in ("programlisting",):
        lines = []
        for codeline in elem.findall("codeline"):
            lines.append("".join(codeline.itertext()))
        return "```\n" + "\n".join(lines) + "\n```\n"
    if tag == "verbatim":
        return "```\n" + inner + "\n```\n"
    if tag in ("highlight", "codeline"):
        return inner
    if tag in ("dot", "msc", "plantuml", "mermaid"):
        # Inline diagram source blocks (\dot, \msc, \startuml, \mermaid ...
        # \enddot/\endmsc/\enduml/\endmermaid). Doxygen puts the raw diagram
        # source as the element text; render it as a labelled fenced code
        # block so it diffs cleanly like any other text (e.g. a changed
        # mermaid flowchart shows up as normal added/removed lines).
        if tag == "mermaid":
            # Also keep the raw source around so report.py can render/diff
            # the diagram graphically (see mermaiddiff.py), not just as text.
            ctx.mermaids.append(inner.strip())
        return f"```{tag}\n" + inner.strip() + "\n```\n"
    if tag in ("dotfile", "mscfile", "diafile", "plantumlfile", "mermaidfile"):
        # References to an external diagram file (\dotfile, \mermaidfile, ...).
        name = elem.get("name", "")
        return f"[{tag}: {name}]"

    # Unknown / structural tags: just return concatenated inner text.
    return inner


def render_description(elem, ctx: RenderContext) -> str:
    """Render a briefdescription/detaileddescription element to plain text."""
    if elem is None:
        return ""
    text = render_children(elem, ctx)
    # normalize excessive blank lines while keeping paragraph breaks
    lines = [ln.rstrip() for ln in text.splitlines()]
    out = []
    blank = False
    for ln in lines:
        if ln.strip() == "":
            if not blank:
                out.append("")
            blank = True
        else:
            out.append(ln)
            blank = False
    return "\n".join(out).strip()
