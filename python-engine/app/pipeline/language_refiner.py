"""Layer 5: language refinement - grammar, vocabulary, sentence flow and readability.

Deterministic clean-up after the model: spacing and punctuation, doubled
words, sentence capitals, "a"/"an", and stock AI phrases the author didn't use.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..utils.text_utils import wants_an

# Stock phrases -> plainer wording ("" removes the phrase). Only applied when the source didn't use them.
STOCK_PHRASES: dict[str, str] = {
    "in today's fast-paced world, ": "",
    "in today's world, ": "",
    "it is important to note that ": "",
    "it's important to note that ": "",
    "it is worth noting that ": "",
    "it's worth noting that ": "",
    "delve into": "explore",
    "delves into": "explores",
    "delved into": "explored",
    "delving into": "exploring",
    "a testament to": "a sign of",
    "plays a crucial role in": "is central to",
    "play a crucial role in": "are central to",
    "navigate the complexities of": "deal with",
    "a rich tapestry of": "a wide range of",
    "seamlessly": "smoothly",
    "seamless": "smooth",
}
_KEEP_DOUBLES = {"had", "that", "is", "do", "very"}
_ABBREV_BEFORE = re.compile(r"\b(?:e\.g|i\.e|etc|al|vs|cf|approx|fig|no|vol|pp|p)\.$", re.IGNORECASE)


@dataclass
class Refined:
    text: str
    fixes: int  # spacing, punctuation and grammar corrections
    phrases: int  # stock phrases replaced


def _replace_phrases(text: str, source: str) -> tuple[str, int]:
    count = 0
    src = source.lower()
    for phrase, repl in STOCK_PHRASES.items():
        if phrase.strip(", ") in src:
            continue  # the author wrote it; leave it alone

        def sub(m: re.Match) -> str:
            nonlocal count
            count += 1
            if not repl:
                return ""
            return repl[:1].upper() + repl[1:] if m.group()[:1].isupper() else repl

        text = re.sub(re.escape(phrase), sub, text, flags=re.IGNORECASE)
    return text, count  # a removed opener's lowercase start is fixed by the capitals pass


def _article(m: re.Match) -> str:
    art, space, word = m.group(1), m.group(2), m.group(3)
    want = "an" if wants_an(word) else "a"
    if art.lower() == want:
        return m.group(0)
    return (want.capitalize() if art[0].isupper() else want) + space + word


def _dedupe(m: re.Match) -> str:
    return m.group(0) if m.group(1).lower() in _KEEP_DOUBLES else m.group(1)


class LanguageRefiner:
    def refine(self, text: str, source: str) -> Refined:
        fixes = 0

        def apply(pattern: str, repl, flags: int = 0) -> None:
            """Substitute, counting only matches whose replacement actually differs."""
            nonlocal text, fixes
            current = text

            def wrapped(m: re.Match) -> str:
                nonlocal fixes
                new = repl(m, current) if callable(repl) else m.expand(repl)
                if new != m.group(0):
                    fixes += 1
                return new

            text = re.sub(pattern, wrapped, current, flags=flags)

        text, phrases = _replace_phrases(text, source)
        if "  " not in source:
            apply(r"(?<=\S) {2,}(?=\S)", " ")
        apply(r" +([,.;:!?])(?=\s|$)", r"\1")  # no space before punctuation
        apply(r"([(\[“]) +", r"\1")
        apply(r" +([)\]”])", r"\1")
        apply(r",{2,}", ",")
        apply(r"(?<!\.)\.\.(?!\.)", ".")  # ".." but not "..."
        apply(r"\b(\w+)\s+\1\b", lambda m, _: _dedupe(m), re.IGNORECASE)  # "the the"
        apply(r"\b([Aa]n?)(\s+)([a-z][a-z-]*)", lambda m, _: _article(m))  # a/an before lowercase words

        def capital(m: re.Match, current: str) -> str:
            if _ABBREV_BEFORE.search(current[: m.start(2)].rstrip()):
                return m.group(0)
            return m.group(1) + m.group(2).upper()

        if not source.lstrip()[:1].islower():  # some writers never capitalise; respect that
            apply(r"(^|(?<=[.!?])\s+)([a-z])", capital)
        return Refined(text, fixes, phrases)
