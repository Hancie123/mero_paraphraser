"""Layer 5: language refinement - grammar, vocabulary, sentence flow and readability.

Deterministic clean-up after the model: spacing and punctuation, doubled
words, sentence capitals, "a"/"an", and stock AI phrases the author didn't use.
Given the mode, it also breaks up structures AI detectors flag (see
humanizer.restructure): summary openers, "not only... but also", sentences of
even length, and missing contractions in casual modes.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass

from ..utils.text_utils import wants_an
from .humanizer import restructure

# Stock phrases -> plainer wording ("" removes the phrase). Only applied when the source didn't use them.
STOCK_PHRASES: dict[str, str] = {
    "in today's fast-paced world, ": "",
    "in today's world, ": "",
    "it is important to note that ": "",
    "it's important to note that ": "",
    "it is worth noting that ": "",
    "it's worth noting that ": "",
    "delve into": "look at",
    "delves into": "looks at",
    "delved into": "looked at",
    "delving into": "looking at",
    "a testament to": "a sign of",
    "plays a crucial role in": "is central to",
    "play a crucial role in": "are central to",
    "navigate the complexities of": "deal with",
    "a rich tapestry of": "a wide range of",
    "seamlessly": "smoothly",
    "seamless": "smooth",
    "in the realm of": "in",
    "a myriad of": "many",
    "a plethora of": "many",
    "plays a pivotal role in": "is central to",
    "play a pivotal role in": "are central to",
    "plays a vital role in": "is central to",
    "play a vital role in": "are central to",
    "serves as a testament to": "shows",
    "stands as a testament to": "shows",
    "due to the fact that": "because",
    "in order to": "to",
    "it is essential to note that ": "",
    "it is crucial to note that ": "",
    "in today's digital age, ": "",
    "in the ever-evolving landscape of": "in",
    "ever-evolving": "changing",
    "game-changer": "big change",
    # filler that only restates or announces (removed)
    "as mentioned earlier, ": "",
    "as previously mentioned, ": "",
    "as mentioned above, ": "",
    "it should be noted that ": "",
    "it goes without saying that ": "",
    "needless to say, ": "",
    "it is worth mentioning that ": "",
    "it's worth mentioning that ": "",
    "it is interesting to note that ": "",
    "unlock the potential of": "make the most of",
    "harness the power of": "use",
}
# AI-favoured verbs and adjectives -> plain words. Unlike STOCK_PHRASES these apply even when the
# source uses them: swapping "utilize" for "use" is good paraphrasing. (pattern, replacement, skip in academic)
PLAIN_WORDS: list[tuple[str, str, bool]] = [
    (r"utilize|utilization", "use", False),
    (r"utilizes", "uses", False),
    (r"utilized", "used", False),
    (r"utilizing", "using", False),
    (r"delve into|delves into", "look at", False),
    (r"foster", "encourage", False),
    (r"fosters", "encourages", False),
    (r"fostered", "encouraged", False),
    (r"fostering", "encouraging", False),
    (r"elevate", "improve", False),  # "elevated" is left alone: "elevated blood pressure"
    (r"elevates", "improves", False),
    (r"elevating", "improving", False),
    (r"is paramount", "matters most", False),
    (r"are paramount", "matter most", False),
    (r"of paramount importance", "very important", False),
    (r"robust", "solid", True),  # statistics: "robust to outliers"
    (r"leverage", "use", True),
    (r"leverages", "uses", True),
    (r"leveraged", "used", True),
    (r"leveraging", "using", True),
]
_NOT_AFTER_FOSTER = r"(?!\s+(?:care|parents?|child|children|famil\w*|homes?|kids?)\b)"
_LEVERAGE_OBJECT = r"(?=\s+(?:the|our|their|its|this|these|existing|data|AI|new|your|his|her|a|an)\b)"
_PLAIN_RES = [
    (re.compile(r"\b(?:" + pat + r")\b" + (_NOT_AFTER_FOSTER if "foster" in pat else "")
                + (_LEVERAGE_OBJECT if "leverag" in pat else ""), re.IGNORECASE), repl, academic_skip)
    for pat, repl, academic_skip in PLAIN_WORDS
]


def _plain_words(text: str, mode: str | None) -> tuple[str, int]:
    count = 0

    for pattern, repl, skip_academic in _PLAIN_RES:
        if skip_academic and mode == "academic":
            continue

        def sub(m: re.Match) -> str:
            nonlocal count
            count += 1
            return repl[:1].upper() + repl[1:] if m.group()[:1].isupper() else repl

        text = pattern.sub(sub, text)
    return text, count


_KEEP_DOUBLES = {"had", "that", "is", "do", "very"}
_ABBREV_BEFORE = re.compile(r"\b(?:e\.g|i\.e|etc|al|vs|cf|approx|fig|no|vol|pp|p)\.$", re.IGNORECASE)


@dataclass
class Refined:
    text: str
    fixes: int  # spacing, punctuation and grammar corrections
    phrases: int  # stock phrases replaced
    restructured: int = 0  # edits against AI-typical structure (summary openers, even lengths...)


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
    def refine(self, text: str, source: str, mode: str | None = None, seed: int | None = None) -> Refined:
        fixes = 0
        restructured = 0
        if mode is not None:
            text, restructured = restructure(text, source, mode, random.Random(seed))

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
        text, plain = _plain_words(text, mode)
        phrases += plain
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
        return Refined(text, fixes, phrases, restructured)
