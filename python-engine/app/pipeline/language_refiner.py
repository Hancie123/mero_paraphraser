"""Layer 5: language refinement - grammar, vocabulary, sentence flow and readability.

Deterministic clean-up after the rewrite: spacing and punctuation, doubled
words, sentence capitals, "a"/"an", stock filler phrases the author didn't
use, language-model wording ("delve into", "plays a pivotal role") wherever
it appears, and em dashes (clean_dashes).
With ``humanize`` it also breaks up structures AI detectors flag (see
humanizer.restructure): summary openers, "not only... but also", sentences of
even length, and missing contractions.
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
    "due to the fact that": "because",
    "in order to": "to",
    "it is essential to note that ": "",
    "it is crucial to note that ": "",
    "in today's digital age, ": "",
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
}
# AI-favoured verbs and adjectives -> plain words. Unlike STOCK_PHRASES these apply even when the
# source uses them: swapping "utilize" for "use" is good paraphrasing. (pattern, replacement, skip in academic)
PLAIN_WORDS: list[tuple[str, str, bool]] = [
    (r"utilize|utilization", "use", False),
    (r"utilizes", "uses", False),
    (r"utilized", "used", False),
    (r"utilizing", "using", False),
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
    (
        re.compile(
            r"\b(?:"
            + pat
            + r")\b"
            + (_NOT_AFTER_FOSTER if "foster" in pat else "")
            + (_LEVERAGE_OBJECT if "leverag" in pat else ""),
            re.IGNORECASE,
        ),
        repl,
        academic_skip,
    )
    for pat, repl, academic_skip in PLAIN_WORDS
]


def _plain_words(text: str, academic: bool) -> tuple[str, int]:
    count = 0

    for pattern, repl, skip_academic in _PLAIN_RES:
        if skip_academic and academic:
            continue

        def sub(m: re.Match) -> str:
            nonlocal count
            count += 1
            return repl[:1].upper() + repl[1:] if m.group()[:1].isupper() else repl

        text = pattern.sub(sub, text)
    return text, count


# Wording that marks text as written by a language model. Unlike STOCK_PHRASES these are
# replaced even when the source used them. Applied in order, longer phrases first.
# (pattern, replacement, skip in academic text). "\1" keeps the matched verb form.
SIGNATURES: list[tuple[str, str, bool]] = [
    (
        r"(play|plays|played|playing) an? (?:pivotal|crucial|vital|critical|key|instrumental|integral|significant) role",
        r"\1 a major part",
        False,
    ),
    (r"an? (?:pivotal|crucial|vital) role", "a central role", False),
    (r"delve deeper into", "look more closely at", False),
    (r"delves deeper into", "looks more closely at", False),
    (r"delve into", "look at", False),
    (r"delves into", "looks at", False),
    (r"delved into", "looked at", False),
    (r"delving into", "looking at", False),
    (r"delve", "dig", False),
    (r"delves", "digs", False),
    (r"delved", "dug", False),
    (r"delving", "digging", False),
    (r"(?:take|taking|took) a deep dive into", "look closely at", False),
    (r"a deep dive into", "a close look at", False),
    (r"(?:is|are|was|were|stands as|stand as|serves as|serve as) a testament to", "shows", False),
    (r"a testament to", "a sign of", False),
    (r"a (?:rich|vibrant|complex) tapestry of", "a wide mix of", False),
    (r"the tapestry of", "the mix of", False),
    (r"tapestry", "mix", False),
    (r"navigat(?:e|es) the (?:complexities|intricacies) of", "deal with", False),
    (r"navigating the (?:complexities|intricacies) of", "dealing with", False),
    (
        r"in today's (?:fast-paced|digital|modern|ever-changing|rapidly changing|interconnected) (?:world|age|era|landscape|society),\s*",
        "",
        False,
    ),
    (r"in the (?:ever-evolving|ever-changing|rapidly evolving) (?:landscape|world|field|realm) of", "in", False),
    (r"ever-evolving", "changing", False),
    (r"(?:with)?in the realm of", "in", False),
    (r"a (?:myriad|plethora) of", "many", False),
    (r"myriad", "many", False),
    (r"(?:harness|harnessing|harnesses) the (?:full )?power of", "use", False),
    (r"unlock(?:s|ing)? the (?:full )?potential of", "make the most of", False),
    (r"game-changer", "big change", False),
    (r"game-changing", "major", False),
    (r"underscores", "highlights", False),
    (r"underscored", "highlighted", False),
    (r"underscoring", "highlighting", False),
    (r"underscore", "highlight", False),
    (r"showcases", "shows", False),
    (r"showcased", "showed", False),
    (r"showcasing", "showing", False),
    (r"showcase", "show", False),
    (r"embarks on", "starts", False),
    (r"embarked on", "started", False),
    (r"embarking on", "starting", False),
    (r"embark on", "start", False),
    (r"seamlessly", "smoothly", False),
    (r"seamless", "smooth", False),
    (r"meticulously", "carefully", False),
    (r"meticulous", "careful", False),
    (r"intricacies", "details", False),
    (r"intricate", "complex", False),
    (r"multifaceted", "complex", False),
    (r"pivotal", "key", False),
    (r"crucial", "important", False),
    (r"unwavering", "steady", False),
    (r"commendable", "admirable", False),
    (r"noteworthy", "notable", False),
    (r"invaluable", "very useful", False),
    (r"bustling", "busy", False),
    (r"vibrant", "lively", True),
    (r"transformative", "far-reaching", False),
    (r"holistic", "overall", True),
    (r"endeavors|endeavours", "efforts", False),
    (r"endeavor|endeavour", "effort", True),
]
_SIGNATURE_RES = [(re.compile(r"\b" + pat + r"\b", re.IGNORECASE), repl, skip) for pat, repl, skip in SIGNATURES]


def _signatures(text: str, academic: bool) -> tuple[str, int]:
    count = 0
    for pattern, repl, skip_academic in _SIGNATURE_RES:
        if skip_academic and academic:
            continue

        def sub(m: re.Match) -> str:
            nonlocal count
            new = m.expand(repl)
            if new.lower() == m.group().lower():
                return m.group()
            count += 1
            if not new:
                return ""
            return new[:1].upper() + new[1:] if m.group()[:1].isupper() else new

        text = pattern.sub(sub, text)
    return text, count


# ---------------------------------------------------------------- em dashes

# An em dash, a spaced en dash or a spaced double hyphen used as a dash. Number ranges
# ("2010–2020", "pp. 4–7") have no spaces and are left alone.
_DASH = r"(?:\s*—\s*|\s+–\s+|\s+--\s+)"
_PAIR_RE = re.compile(_DASH + r"([^—–.!?\n]{1,120}?)" + _DASH)
_SINGLE_RE = re.compile(_DASH)
_SUBJECT = re.compile(
    r"(?:I|we|you|he|she|it|they|this|that|these|those|there|nobody|no one|everyone|"
    r"someone|people|nothing|everything)\b",
    re.IGNORECASE,
)


def clean_dashes(text: str) -> tuple[str, int]:
    """Replace em dashes with the punctuation a person would usually type.

    A pair around a short aside becomes commas (parentheses if the aside has a comma);
    a single dash becomes a colon before a short list, a full stop before a new
    clause, and a comma otherwise.
    """
    count = 0

    def pair(m: re.Match) -> str:
        nonlocal count
        aside = m.group(1).strip()
        if len(aside.split()) > 15:
            return m.group()
        count += 1
        return f" ({aside}) " if "," in aside else f", {aside}, "

    text = _PAIR_RE.sub(pair, text)

    def single(m: re.Match) -> str:
        nonlocal count
        right = re.match(r"[^.!?\n]*", m.string[m.end() :]).group()
        before = m.string[: m.start()].rstrip()
        count += 1
        if not right.strip() or not before or before[-1] in ".!?\n":
            return " " if before and right.strip() else ""
        n_right = len(right.split())
        if ("," in right or " and " in right) and n_right <= 14 and not _SUBJECT.match(right):
            return ": "
        if _SUBJECT.match(right) and n_right >= 3:
            return "\x00"  # a full stop; the next word is capitalised below
        return ", "

    text = _SINGLE_RE.sub(single, text)
    text = re.sub("\x00" r"(\W*)(\w)", lambda m: ". " + m.group(1) + m.group(2).upper(), text).replace("\x00", ". ")
    text = re.sub(r"\( ", "(", re.sub(r" \)", ")", text)) if count else text
    text = re.sub(r",\s*([.!?;:])", r"\1", text)  # "aside, ." at a sentence end
    return text, count


_KEEP_DOUBLES = {"had", "that", "is", "do", "very"}
_ABBREV_BEFORE = re.compile(r"\b(?:e\.g|i\.e|etc|al|vs|cf|approx|fig|no|vol|pp|p)\.$", re.IGNORECASE)


@dataclass
class Refined:
    text: str
    fixes: int  # spacing, punctuation and grammar corrections
    phrases: int  # stock phrases replaced
    restructured: int = 0  # edits against AI-typical structure (summary openers, even lengths...)
    dashes: int = 0  # em dashes replaced


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
    def refine(
        self, text: str, source: str, seed: int | None = None, *, humanize: bool = False, academic: bool = False
    ) -> Refined:
        """``academic``: the source reads as academic writing (Layer 2), so precise words stay."""
        fixes = 0
        restructured = 0
        if humanize:
            text, restructured = restructure(text, source, random.Random(seed))

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
        text, sig = _signatures(text, academic)
        text, plain = _plain_words(text, academic)
        phrases += plain + sig
        text, dashes = clean_dashes(text)
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
        return Refined(text, fixes, phrases, restructured, dashes)
