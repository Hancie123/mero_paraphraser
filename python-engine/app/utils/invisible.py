"""Removal of invisible and look-alike Unicode characters.

Zero-width spaces, word joiners, BOMs, soft hyphens, bidi overrides, tag
characters and stray variation selectors usually arrive by copy-paste from web
pages, PDFs and chat apps. They break search, word counts and code (a
U+200B inside an identifier is a syntax error that you can't see).

Joiners that carry meaning are kept:
- ZWJ / ZWNJ between letters of scripts that need them (Devanagari, Bengali,
  Arabic, Persian, Sinhala, Myanmar...), e.g. Nepali "क्‍ष" vs "क्ष";
- ZWJ inside emoji sequences (👩‍💻), variation selectors after emoji and
  keycaps, and tag characters inside subdivision flags (🏴 + tags);
- bidi marks in text that contains right-to-left letters.
"""

from __future__ import annotations

import unicodedata

ZWSP, ZWNJ, ZWJ = "​", "‌", "‍"

# Always removed.
_ALWAYS = set(
    "​"  # zero width space
    "⁠"  # word joiner
    "﻿"  # BOM / zero width no-break space
    "­"  # soft hyphen
    "᠎"  # Mongolian vowel separator
    "⁡⁢⁣⁤"  # invisible math operators
    "￹￺￻"  # interlinear annotation
    "ㅤﾠ"  # Hangul fillers (often used as "blank" characters)
)
_BIDI = set("‎‏‪‫‬‭‮⁦⁧⁨⁩؜")
# Unusual spaces -> a normal space.
_SPACES = set("               ")

# Scripts whose spelling uses ZWJ / ZWNJ.
_JOINING_RANGES = (
    (0x0590, 0x08FF),  # Hebrew, Arabic, Syriac, Thaana, N'Ko...
    (0x0900, 0x0DFF),  # Indic: Devanagari ... Sinhala
    (0x1000, 0x109F),  # Myanmar
    (0x1780, 0x17FF),  # Khmer
    (0xA8E0, 0xA8FF),  # Devanagari extended
    (0xFB50, 0xFDFF), (0xFE70, 0xFEFF),  # Arabic presentation forms
)


def _joining_script(ch: str) -> bool:
    cp = ord(ch)
    return any(lo <= cp <= hi for lo, hi in _JOINING_RANGES)


def _emoji_like(ch: str) -> bool:
    cp = ord(ch)
    return (cp >= 0x1F000 or 0x2190 <= cp <= 0x2BFF or 0x1F3FB <= cp <= 0x1F3FF
            or cp in (0xFE0F, 0x20E3, 0x00A9, 0x00AE, 0x2122) or unicodedata.category(ch) == "So")


def _has_rtl(text: str) -> bool:
    return any(unicodedata.bidirectional(c) in ("R", "AL") for c in text)


def purge(text: str) -> tuple[str, int]:
    """Returns (cleaned text, number of characters removed or replaced)."""
    if text.isascii():
        return text, 0
    rtl = _has_rtl(text)
    out: list[str] = []
    removed = 0
    in_flag = False  # inside a 🏴 + tag sequence
    n = len(text)
    for i, ch in enumerate(text):
        cp = ord(ch)
        prev = out[-1] if out else ""
        nxt = text[i + 1] if i + 1 < n else ""
        keep = True
        if ch in _ALWAYS:
            keep = False
        elif ch in _SPACES:
            out.append(" ")
            removed += 1
            continue
        elif ch in _BIDI:
            keep = rtl
        elif ch in (ZWJ, ZWNJ):
            keep = bool(prev and nxt) and (
                (_joining_script(prev) and _joining_script(nxt))
                or (ch == ZWJ and _emoji_like(prev) and _emoji_like(nxt))
            )
        elif 0xE0000 <= cp <= 0xE007F:  # tag characters: only inside 🏴 subdivision flags
            keep = in_flag
            if cp == 0xE007F:  # cancel tag ends the flag
                in_flag = False
        elif 0xFE00 <= cp <= 0xFE0F:  # variation selectors
            keep = bool(prev) and (_emoji_like(prev) or prev in "0123456789#*" or unicodedata.category(prev) == "Lo")
        elif 0xE0100 <= cp <= 0xE01EF:  # ideographic variation selectors
            keep = bool(prev) and unicodedata.category(prev) == "Lo"
        if not 0xE0000 <= cp <= 0xE007F:
            in_flag = cp == 0x1F3F4
        if keep:
            out.append(ch)
        else:
            removed += 1
    return "".join(out), removed
