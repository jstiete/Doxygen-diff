"""Data model for parsed Doxygen documentation elements."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ImageRef:
    """An image referenced from a description (via \\image or markdown)."""
    name: str  # file name as referenced, e.g. "logo.png"
    owner_id: str  # identity of the element that references it


@dataclass
class MermaidRef:
    """A Mermaid diagram embedded via \\mermaid ... \\endmermaid."""
    key: str  # stable key used to match across old/new (owner id + index)
    source: str  # raw Mermaid diagram source text
    owner_label: str = ""  # human readable name of the owning compound/member
    owner_kind: str = ""  # "compound" or "member"
    owner_compound_kind: str = ""  # Compound.kind, for doclink resolution
    owner_refid: str = ""  # doxygen refid of the owner, for doclink resolution


@dataclass
class Member:
    """A documented member: function, variable, typedef, enum, define, ..."""
    kind: str  # function, variable, typedef, enum, define, enumvalue, ...
    name: str
    scope_id: str  # identity of the owning compound (class/namespace/file)
    argsstring: str = ""
    signature: str = ""  # human readable full signature/definition
    prot: str = ""  # public/protected/private
    static: bool = False
    brief: str = ""  # normalized text of briefdescription
    detailed: str = ""  # normalized text of detaileddescription
    file: str = ""
    line: int = 0
    refid: str = ""  # doxygen internal id, stable but not used as primary key
    images: list = field(default_factory=list)
    mermaids: list = field(default_factory=list)  # list[MermaidRef]

    type_sig: str = ""  # parameter types only, used for overload identity

    @property
    def identity(self) -> str:
        """Qualified identity used to match members across versions.

        Uses parameter *types* only (not parameter names) so that renaming a
        parameter does not look like a different overload.
        """
        return f"{self.scope_id}::{self.kind}:{self.name}({self.type_sig})"

    @property
    def name_only_identity(self) -> str:
        return f"{self.scope_id}::{self.kind}:{self.name}"

    @property
    def display_name(self) -> str:
        base = self.scope_id.split("::", 1)[-1] if "::" in self.scope_id else self.scope_id
        if base in ("<global>", ""):
            return f"{self.name}{self.argsstring}"
        return f"{base}::{self.name}{self.argsstring}"


def normalize_argsstring(argsstring: str) -> str:
    """Normalize an argsstring so that whitespace differences don't matter."""
    return " ".join((argsstring or "").split())


@dataclass
class Compound:
    """A documented compound: class, struct, namespace, file, page, group, dir."""
    kind: str  # class, struct, union, interface, namespace, file, page, group, dir, concept
    id: str  # qualified identity (e.g. "Calculator", "file:src/main.cpp", "page:mainpage")
    name: str  # display name / title
    refid: str = ""
    brief: str = ""
    detailed: str = ""
    title: str = ""  # for pages/groups
    file: str = ""
    members: dict = field(default_factory=dict)  # identity -> Member
    images: list = field(default_factory=list)  # list[ImageRef]
    mermaids: list = field(default_factory=list)  # list[MermaidRef]
    xml_path: str = ""


@dataclass
class Project:
    """All compounds parsed from one Doxygen XML output directory."""
    compounds: dict = field(default_factory=dict)  # id -> Compound
    xml_dir: str = ""
