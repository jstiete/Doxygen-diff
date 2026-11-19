"""Parse a Doxygen XML output directory into the doxydiff data model."""
from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from typing import Optional

from .model import Compound, Member, MermaidRef, Project
from .render import RenderContext, render_description

SKIP_FILES = {"index.xml", "Doxyfile.xml"}
SKIP_SUFFIXES = (".xsd", ".xslt")


def _first_text(elem: Optional[ET.Element]) -> str:
    if elem is None:
        return ""
    return "".join(elem.itertext()).strip()


def _compound_identity(kind: str, compoundname: str, location_file: str) -> str:
    if kind == "file":
        return f"file:{location_file or compoundname}"
    if kind == "dir":
        return f"dir:{location_file or compoundname}"
    if kind == "page":
        return f"page:{compoundname}"
    if kind == "group":
        return f"group:{compoundname}"
    return compoundname  # class/struct/union/interface/namespace/concept: already qualified


def parse_member(memberdef: ET.Element, owner_compound_id: str) -> Member:
    kind = memberdef.get("kind", "")
    name = _first_text(memberdef.find("name"))
    qualifiedname_elem = memberdef.find("qualifiedname")
    qualifiedname = _first_text(qualifiedname_elem) if qualifiedname_elem is not None else name
    argsstring = _first_text(memberdef.find("argsstring"))
    definition = _first_text(memberdef.find("definition"))
    type_text = _first_text(memberdef.find("type"))
    prot = memberdef.get("prot", "")
    static = memberdef.get("static", "no") == "yes"
    refid = memberdef.get("id", "")

    ctx = RenderContext()
    brief = render_description(memberdef.find("briefdescription"), ctx)
    detailed = render_description(memberdef.find("detaileddescription"), ctx)
    inbody = render_description(memberdef.find("inbodydescription"), ctx)
    if inbody:
        detailed = (detailed + "\n\n" + inbody).strip() if detailed else inbody

    loc = memberdef.find("location")
    file_ = loc.get("file", "") if loc is not None else ""
    line = int(loc.get("line", 0)) if loc is not None and loc.get("line") else 0

    signature = f"{type_text} {definition}{argsstring}".strip() if definition else f"{name}{argsstring}"

    # scope_id used for grouping/moved-detection is the owner (namespace/class)
    # part of the qualified name if present. Free functions/variables at file
    # scope have no qualifiedname prefix in Doxygen's XML; they are treated as
    # globally scoped so that moving one between files is detected as a move
    # instead of a delete+add.
    if "::" in qualifiedname:
        scope_id = qualifiedname.rsplit("::", 1)[0]
    else:
        scope_id = "<global>"

    type_sig = ", ".join(
        _first_text(p.find("type")) for p in memberdef.findall("param")
    )

    m = Member(
        kind=kind,
        name=name if "::" not in qualifiedname else qualifiedname.rsplit("::", 1)[-1],
        scope_id=scope_id,
        argsstring=argsstring,
        type_sig=type_sig,
        signature=signature,
        prot=prot,
        static=static,
        brief=brief,
        detailed=detailed,
        file=file_,
        line=line,
        refid=refid,
    )
    m.images = list(ctx.images)
    m.mermaids = [
        MermaidRef(
            key=f"{m.identity}#{i}",
            source=src,
            owner_label=m.display_name,
            owner_kind="member",
            owner_refid=refid,
        )
        for i, src in enumerate(ctx.mermaids)
    ]
    return m


def parse_compound_file(path: str) -> Optional[Compound]:
    try:
        tree = ET.parse(path)
    except ET.ParseError:
        return None
    root = tree.getroot()
    compounddef = root.find("compounddef")
    if compounddef is None:
        return None

    kind = compounddef.get("kind", "")
    refid = compounddef.get("id", "")
    compoundname = _first_text(compounddef.find("compoundname"))
    title = _first_text(compounddef.find("title"))

    loc = compounddef.find("location")
    location_file = loc.get("file", "") if loc is not None else ""

    cid = _compound_identity(kind, compoundname, location_file)

    ctx = RenderContext()
    brief = render_description(compounddef.find("briefdescription"), ctx)
    detailed = render_description(compounddef.find("detaileddescription"), ctx)

    display_name = title or compoundname

    compound = Compound(
        kind=kind,
        id=cid,
        name=display_name,
        refid=refid,
        brief=brief,
        detailed=detailed,
        title=title,
        file=location_file,
        xml_path=path,
    )
    compound.images = list(ctx.images)
    compound.mermaids = [
        MermaidRef(
            key=f"{cid}#{i}",
            source=src,
            owner_label=display_name,
            owner_kind="compound",
            owner_compound_kind=kind,
            owner_refid=refid,
        )
        for i, src in enumerate(ctx.mermaids)
    ]

    for sectiondef in compounddef.findall("sectiondef"):
        for memberdef in sectiondef.findall("memberdef"):
            member = parse_member(memberdef, cid)
            compound.members[member.identity] = member

    return compound


def parse_project(xml_dir: str) -> Project:
    project = Project(xml_dir=xml_dir)
    for entry in sorted(os.listdir(xml_dir)):
        if entry in SKIP_FILES or entry.endswith(SKIP_SUFFIXES) or not entry.endswith(".xml"):
            continue
        path = os.path.join(xml_dir, entry)
        compound = parse_compound_file(path)
        if compound is None:
            continue
        if compound.id in project.compounds:
            # Merge members if the same identity appears in multiple files
            # (should not normally happen, but be defensive).
            project.compounds[compound.id].members.update(compound.members)
        else:
            project.compounds[compound.id] = compound
    return project
