"""Match compounds and members between an old and a new Doxygen XML project."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .model import Compound, Member, Project


@dataclass
class MemberDiff:
    status: str  # added, removed, modified, moved, unchanged
    identity: str
    old: Optional[Member]
    new: Optional[Member]
    old_scope: str = ""
    new_scope: str = ""


@dataclass
class CompoundDiff:
    status: str  # added, removed, modified, unchanged
    id: str
    kind: str
    old: Optional[Compound]
    new: Optional[Compound]
    member_diffs: List[MemberDiff] = field(default_factory=list)


@dataclass
class ProjectDiff:
    compound_diffs: List[CompoundDiff] = field(default_factory=list)


def _name_argtype_key(identity: str) -> Tuple[str, str]:
    # identity looks like "<scope>::<kind>:<name>(<types>)"
    # return (kind:name, types) ignoring scope, used for moved-detection
    scope, rest = identity.split("::", 1) if "::" in identity else ("", identity)
    return rest


def match_members(old_members: Dict[str, Member], new_members: Dict[str, Member]) -> List[MemberDiff]:
    diffs: List[MemberDiff] = []
    old_keys = set(old_members)
    new_keys = set(new_members)

    common = old_keys & new_keys
    only_old = old_keys - new_keys
    only_new = new_keys - old_keys

    for key in sorted(common):
        old_m, new_m = old_members[key], new_members[key]
        if old_m.brief == new_m.brief and old_m.detailed == new_m.detailed and old_m.signature == new_m.signature:
            diffs.append(MemberDiff("unchanged", key, old_m, new_m))
        else:
            diffs.append(MemberDiff("modified", key, old_m, new_m))

    # Try to detect moves: same kind+name+argtypes, different scope.
    old_by_namekey: Dict[str, List[str]] = {}
    for key in only_old:
        old_by_namekey.setdefault(_name_argtype_key(key), []).append(key)
    new_by_namekey: Dict[str, List[str]] = {}
    for key in only_new:
        new_by_namekey.setdefault(_name_argtype_key(key), []).append(key)

    moved_old = set()
    moved_new = set()
    for namekey, old_candidates in old_by_namekey.items():
        new_candidates = new_by_namekey.get(namekey)
        if not new_candidates:
            continue
        # Only treat as an unambiguous move if there's exactly one candidate
        # on each side; otherwise fall back to add/remove to avoid guessing.
        if len(old_candidates) == 1 and len(new_candidates) == 1:
            old_key, new_key = old_candidates[0], new_candidates[0]
            old_m, new_m = old_members[old_key], new_members[new_key]
            diffs.append(MemberDiff(
                "moved", f"{old_key} -> {new_key}", old_m, new_m,
                old_scope=old_m.scope_id, new_scope=new_m.scope_id,
            ))
            moved_old.add(old_key)
            moved_new.add(new_key)

    for key in sorted(only_old - moved_old):
        diffs.append(MemberDiff("removed", key, old_members[key], None))
    for key in sorted(only_new - moved_new):
        diffs.append(MemberDiff("added", key, None, new_members[key]))

    return diffs


def compound_unchanged(old: Compound, new: Compound, member_diffs: List[MemberDiff]) -> bool:
    if old.brief != new.brief or old.detailed != new.detailed or old.title != new.title:
        return False
    return all(d.status == "unchanged" for d in member_diffs)


def _global_move_detection(result: ProjectDiff) -> None:
    """Reclassify removed+added member pairs across *different* compounds as
    'moved' if they share the same kind/name/argument-types and the pairing
    is unambiguous. This complements match_members(), which only looks for
    moves within members that ended up in the same compound.
    """
    removed_index: Dict[str, List[Tuple[CompoundDiff, MemberDiff]]] = {}
    added_index: Dict[str, List[Tuple[CompoundDiff, MemberDiff]]] = {}

    for cd in result.compound_diffs:
        for md in cd.member_diffs:
            if md.status == "removed":
                removed_index.setdefault(_name_argtype_key(md.identity), []).append((cd, md))
            elif md.status == "added":
                added_index.setdefault(_name_argtype_key(md.identity), []).append((cd, md))

    touched_compounds = set()
    for namekey, removed_list in removed_index.items():
        added_list = added_index.get(namekey)
        if not added_list or len(removed_list) != 1 or len(added_list) != 1:
            continue
        old_cd, old_md = removed_list[0]
        new_cd, new_md = added_list[0]
        if old_cd is new_cd:
            continue  # already handled as an in-compound move
        old_cd.member_diffs.remove(old_md)
        new_cd.member_diffs.remove(new_md)
        moved = MemberDiff(
            "moved", f"{old_md.identity} -> {new_md.identity}", old_md.old, new_md.new,
            old_scope=old_md.old.scope_id if old_md.old else "",
            new_scope=new_md.new.scope_id if new_md.new else "",
        )
        new_cd.member_diffs.append(moved)
        touched_compounds.add(old_cd.id)
        touched_compounds.add(new_cd.id)

    # Recompute status for compounds that are not wholly added/removed and
    # whose member list changed as a result of move detection.
    for cd in result.compound_diffs:
        if cd.id not in touched_compounds:
            continue
        if cd.status in ("added", "removed"):
            continue
        if cd.old is not None and cd.new is not None:
            cd.status = "unchanged" if compound_unchanged(cd.old, cd.new, cd.member_diffs) else "modified"


def match_projects(old: Project, new: Project) -> ProjectDiff:
    result = ProjectDiff()
    old_ids = set(old.compounds)
    new_ids = set(new.compounds)

    for cid in sorted(old_ids & new_ids):
        old_c, new_c = old.compounds[cid], new.compounds[cid]
        member_diffs = match_members(old_c.members, new_c.members)
        status = "unchanged" if compound_unchanged(old_c, new_c, member_diffs) else "modified"
        result.compound_diffs.append(CompoundDiff(status, cid, new_c.kind, old_c, new_c, member_diffs))

    for cid in sorted(old_ids - new_ids):
        old_c = old.compounds[cid]
        member_diffs = [MemberDiff("removed", k, m, None) for k, m in sorted(old_c.members.items())]
        result.compound_diffs.append(CompoundDiff("removed", cid, old_c.kind, old_c, None, member_diffs))

    for cid in sorted(new_ids - old_ids):
        new_c = new.compounds[cid]
        member_diffs = [MemberDiff("added", k, None, m) for k, m in sorted(new_c.members.items())]
        result.compound_diffs.append(CompoundDiff("added", cid, new_c.kind, None, new_c, member_diffs))

    _global_move_detection(result)
    return result
