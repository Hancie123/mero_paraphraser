"""Word, sentence and readability helpers shared by the pipeline layers."""

from __future__ import annotations

import json
import re
from pathlib import Path

WORD_RE = re.compile(r"[^\W_]+(?:['’][^\W_]+)*")
# Diff tokens: a word or symbol plus the whitespace after it.
TOKEN_RE = re.compile(r"[^\W_]+(?:['’][^\W_]+)*\s*|[^\w\s]\s*|_+\s*|\s+")
PLACEHOLDER_RE = re.compile(r"\[\[\s*(\d+)\s*\]\]")

# A "." after one of these does not end a sentence. Dotted initials ("U.S.", "e.g.",
# "p.m.", "J. Smith") are caught by shape in ``ends_with_abbreviation``.
ABBREVIATIONS = frozenset(
    "e.g i.e etc al vs cf approx fig no vol pp p dr mr mrs ms prof st jr sr inc ltd co corp dept est "
    "gen gov sen rep rev mt ft jan feb mar apr jun jul aug sep sept oct nov dec".split()
)
_LAST_WORD_DOT = re.compile(r"(\w+(?:\.\w+)*)\.$")
_SENTENCE_END = re.compile(r"(?<=[.!?…])[\"”’)\]]*\s+(?=[\"“‘(\[]*[A-Z0-9\[])")


def words(text: str) -> list[str]:
    return WORD_RE.findall(text)


def word_count(text: str) -> int:
    return len(WORD_RE.findall(text))


def tokens(text: str) -> list[str]:
    return TOKEN_RE.findall(text)


def _trimmed(text: str, a: int, b: int) -> tuple[int, int]:
    while a < b and text[a].isspace():
        a += 1
    while b > a and text[b - 1].isspace():
        b -= 1
    return a, b


def ends_with_abbreviation(text: str) -> bool:
    """True if ``text`` ends with an abbreviation's ".": "Dr.", "et al.", "U.S.", "e.g.", "J."."""
    last = _LAST_WORD_DOT.search(text.rstrip())
    if not last:
        return False
    word = last.group(1)
    if word.lower() in ABBREVIATIONS:
        return True
    if len(word) == 1 and word.isupper():  # initials: "J. Smith"
        return True
    return "." in word and all(len(part) == 1 for part in word.split("."))  # "U.S.", "e.g.", "p.m."


def sentence_spans(text: str) -> list[tuple[int, int]]:
    """``(start, end)`` of each sentence, ignoring abbreviations like "e.g.", "U.S." and "et al."."""
    spans: list[tuple[int, int]] = []
    start = 0
    for m in _SENTENCE_END.finditer(text):
        if ends_with_abbreviation(text[start : m.start()].rstrip('"”’)]')):
            continue
        spans.append(_trimmed(text, start, m.start()))
        start = m.end()
    spans.append(_trimmed(text, start, len(text)))
    return [(a, b) for a, b in spans if WORD_RE.search(text[a:b])]


def split_sentences(text: str) -> list[str]:
    """Split prose into sentences, ignoring common abbreviations like "e.g." and "et al."."""
    return [text[a:b] for a, b in sentence_spans(text)]


def match_case(original: str, replacement: str) -> str:
    """Give ``replacement`` the capitalisation style of ``original``."""
    letters = [c for c in original if c.isalpha()]
    if len(letters) > 1 and all(c.isupper() for c in letters):
        return replacement.upper()
    if original[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


# Prefixes that override the vowel rule; shared with the UI (src/text.ts).
_ARTICLES = json.loads((Path(__file__).resolve().parents[1] / "data" / "articles.json").read_text(encoding="utf-8"))
_AN_EXCEPTIONS = tuple(_ARTICLES["an"])
_A_EXCEPTIONS = tuple(_ARTICLES["a"])


def wants_an(word: str) -> bool:
    w = word.lower()
    if w.startswith(_AN_EXCEPTIONS):
        return True
    if w.startswith(_A_EXCEPTIONS):
        return False
    return w[:1] in "aeiou"


def _syllables(word: str) -> int:
    w = word.lower()
    groups = re.findall(r"[aeiouy]+", w)
    n = len(groups)
    if w.endswith("e") and not w.endswith(("le", "ee")) and n > 1:
        n -= 1
    return max(1, n)


def reading_ease(text: str) -> float | None:
    """Flesch reading ease (higher is easier); None for very short text."""
    ws = words(text)
    sents = split_sentences(text)
    if len(ws) < 10 or not sents:
        return None
    syllables = sum(_syllables(w) for w in ws)
    return 206.835 - 1.015 * (len(ws) / len(sents)) - 84.6 * (syllables / len(ws))


def avg_sentence_length(text: str) -> float:
    sents = split_sentences(text)
    return word_count(text) / len(sents) if sents else 0.0


STOPWORDS = frozenset(
    """a about above after again against all also am an and any are as at be because been before being
    below between both but by can could did do does doing down during each few for from further had has
    have having he her here hers herself him himself his how i if in into is it its itself just me more
    most my myself no nor not now of off on once only or other our ours ourselves out over own same she
    should so some such than that the their theirs them themselves then there these they this those
    through to too under until up very was we were what when where which while who whom why will with
    would you your yours yourself yourselves may might must shall within without however therefore thus
    although though whereas yet also many much one two three first second new used using use""".split()
)
