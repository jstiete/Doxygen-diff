"""Git-diff style HTML rendering of text differences."""
from __future__ import annotations

import difflib
import html
import re
from typing import List

_TOKEN_RE = re.compile(r"\s+|\w+|[^\w\s]", re.UNICODE)


def _tokenize(text: str) -> List[str]:
    return _TOKEN_RE.findall(text)


def inline_diff_html(old_text: str, new_text: str) -> str:
    """Render a word-level, git-diff-style inline HTML diff of two texts.

    Deleted tokens are wrapped in <span class="del">, inserted tokens in
    <span class="ins">, matching the git-diff red/green convention.
    """
    old_tokens = _tokenize(old_text or "")
    new_tokens = _tokenize(new_text or "")
    sm = difflib.SequenceMatcher(a=old_tokens, b=new_tokens, autojunk=False)
    out = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            out.append(html.escape("".join(old_tokens[i1:i2])))
        elif tag == "delete":
            chunk = html.escape("".join(old_tokens[i1:i2]))
            if chunk.strip():
                out.append(f'<span class="del">{chunk}</span>')
        elif tag == "insert":
            chunk = html.escape("".join(new_tokens[j1:j2]))
            if chunk.strip():
                out.append(f'<span class="ins">{chunk}</span>')
        elif tag == "replace":
            chunk_del = html.escape("".join(old_tokens[i1:i2]))
            chunk_ins = html.escape("".join(new_tokens[j1:j2]))
            if chunk_del.strip():
                out.append(f'<span class="del">{chunk_del}</span>')
            if chunk_ins.strip():
                out.append(f'<span class="ins">{chunk_ins}</span>')
    html_out = "".join(out).replace("\n", "<br/>\n")
    return html_out


def line_diff_html(old_text: str, new_text: str) -> str:
    """Render a git-diff-style line-based HTML diff (whole line red/green)."""
    old_lines = (old_text or "").splitlines()
    new_lines = (new_text or "").splitlines()
    sm = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)
    out = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for line in old_lines[i1:i2]:
                out.append(f'<div class="line ctx"><span class="marker"> </span>{html.escape(line)}</div>')
        elif tag == "delete":
            for line in old_lines[i1:i2]:
                out.append(f'<div class="line del"><span class="marker">-</span>{html.escape(line)}</div>')
        elif tag == "insert":
            for line in new_lines[j1:j2]:
                out.append(f'<div class="line ins"><span class="marker">+</span>{html.escape(line)}</div>')
        elif tag == "replace":
            for line in old_lines[i1:i2]:
                out.append(f'<div class="line del"><span class="marker">-</span>{html.escape(line)}</div>')
            for line in new_lines[j1:j2]:
                out.append(f'<div class="line ins"><span class="marker">+</span>{html.escape(line)}</div>')
    return "\n".join(out)


def count_changed_lines(old_text: str, new_text: str):
    """Return (added_lines, removed_lines) counts, git --stat style."""
    old_lines = (old_text or "").splitlines()
    new_lines = (new_text or "").splitlines()
    sm = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)
    added = removed = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "delete":
            removed += i2 - i1
        elif tag == "insert":
            added += j2 - j1
        elif tag == "replace":
            removed += i2 - i1
            added += j2 - j1
    return added, removed
