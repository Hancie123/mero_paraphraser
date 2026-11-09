"""Document structure helpers: reference lists, paragraphs and chunking."""

from __future__ import annotations

import re

from ..core.config import CHUNK_CHARS

_REF_HEADING = re.compile(
    r"^[ \t]*(?:#+[ \t]*)?(references|reference list|bibliography|works cited|literature cited|sources)[ \t]*:?[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)
_PARA_SPLIT = re.compile(r"(\n\s*\n)")
_SENTENCE_GAP = re.compile(r"(?<=[.!?…])(\s+)")


def split_references(text: str) -> tuple[str, str]:
    """Split off a trailing reference list (from its heading on), which is never rewritten."""
    matches = list(_REF_HEADING.finditer(text))
    if not matches:
        return text, ""
    m = matches[-1]
    # Only treat it as a reference list if it is in the second half and something follows it.
    if m.start() < len(text) * 0.3 or not text[m.end():].strip():
        return text, ""
    cut = m.start()
    # Keep the blank line(s) before the heading with the references.
    while cut > 0 and text[cut - 1] in " \t\n":
        cut -= 1
    return text[:cut], text[cut:]


def count_paragraphs(text: str) -> int:
    return sum(1 for p in _PARA_SPLIT.split(text)[::2] if p.strip())


def _split_long(para: str, limit: int) -> list[tuple[str, bool]]:
    """Split one oversized paragraph at sentence ends into chunks of at most ~limit chars."""
    parts = _SENTENCE_GAP.split(para)  # [sentence, gap, sentence, ...]
    out: list[tuple[str, bool]] = []
    cur, gap = "", ""
    for i, part in enumerate(parts):
        if i % 2:
            gap = part
            continue
        if cur and len(cur) + len(gap) + len(part) > limit:
            out += [(cur, True), (gap, False)]
            cur = part
        else:
            cur += gap + part
        gap = ""
    if cur:
        out.append((cur, True))
    return out


def chunk_text(text: str, limit: int = CHUNK_CHARS) -> list[tuple[str, bool]]:
    """Split ``text`` into ``(piece, should_rewrite)`` pieces that join back to ``text``.

    Whole paragraphs are grouped up to ``limit`` characters; a paragraph longer
    than that is split at sentence ends. Blank pieces are never rewritten.
    """
    parts = _PARA_SPLIT.split(text)  # [para, sep, para, sep, ...]
    out: list[tuple[str, bool]] = []
    cur, sep = "", ""
    for i, part in enumerate(parts):
        if i % 2:
            sep = part
            continue
        if len(part) > limit:
            if cur:
                out.append((cur, True))
            if sep:
                out.append((sep, False))
            out += _split_long(part, limit)
            cur, sep = "", ""
            continue
        if cur and len(cur) + len(sep) + len(part) > limit:
            out += [(cur, True), (sep, False)]
            cur = part
        else:
            cur += sep + part
        sep = ""
    if cur or sep:
        out.append((cur + sep, True))
    return [(p, rw and bool(p.strip())) for p, rw in out if p]
