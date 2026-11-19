"""Human-like output: score drafts the way AI detectors do, and fix what they flag.

Detectors such as GPTZero look at, among other things:

* burstiness: how much sentence length varies,
* patterns: structures models overuse ("not only... but also", a summary
  opener on the last sentence, lists of three, sentences of even length).

Layer 4 uses ``human_score`` to choose between drafts. Layer 5 calls
``restructure``, which only makes edits that keep the meaning: it drops summary
openers, unrolls "not only... but also", splits a long sentence when the
lengths are too even, and uses contractions.
"""

from __future__ import annotations

import random
import re
import statistics
from dataclasses import dataclass, field

from ..core import lexicon as lx
from ..utils.text_utils import STOPWORDS, WORD_RE, match_case, split_sentences, word_count

# ---------------------------------------------------------------- patterns

_OPENERS = (
    "overall",
    "ultimately",
    "in essence",
    "in summary",
    "in conclusion",
    "in short",
    "all in all",
    "taken together",
    "to sum up",
    "in the end",
)
_OPENER_RE = re.compile(
    r"(^|[.!?][\"”’)\]]*\s+|\n\s*)(" + "|".join(o.replace(" ", r"\s") for o in _OPENERS) + r"),\s+(\S)",
    re.IGNORECASE,
)
_NOT_ONLY_RE = re.compile(r"\bnot only ((?:[\w'’-]+ ){0,5}?[\w'’-]+),? but also\b")
_NOT_ONLY_ANY = re.compile(r"\bnot only\b[^.!?]{1,80}?\bbut\b", re.IGNORECASE)
_NOT_JUST_RE = re.compile(
    r"\b(?:isn't|is not|it's not|aren't|are not|wasn't|was not)\s+(?:just|only|merely|simply)\b"
    r"[^.!?;]{1,60}[,;]\s*(?:it's|it is|they're|they are|but)\b",
    re.IGNORECASE,
)
_TRIPLET_RE = re.compile(
    r"\b[\w-]+(?: [\w-]+){0,2}, [\w-]+(?: [\w-]+){0,2}, (?:and|or) [\w-]+"
    r"|\b[\w-]+, [\w-]+ (?:and|or) [\w-]+\b"
)
_PARTICIPLE_RE = re.compile(r"^[A-Z][a-z]{2,}ing\b[^,.]{0,60},")
_TRANSITIONS = (
    "however",
    "additionally",
    "furthermore",
    "moreover",
    "consequently",
    "therefore",
    "thus",
    "notably",
    "importantly",
    "indeed",
    "similarly",
    "in addition",
)
_TRANSITION_RE = re.compile(r"^(?:" + "|".join(_TRANSITIONS) + r"),", re.IGNORECASE)


def burstiness(text: str) -> float:
    """Coefficient of variation of sentence lengths (human prose is usually 0.5 or more)."""
    lengths = [word_count(s) for s in split_sentences(text)]
    if len(lengths) < 2:
        return 0.5  # nothing to compare: neutral
    mean = statistics.fmean(lengths)
    return statistics.pstdev(lengths) / mean if mean else 0.0


def ai_patterns(text: str) -> list[str]:
    """Names of the AI-typical structures found in ``text``."""
    found: list[str] = []
    sentences = split_sentences(text)
    if _NOT_ONLY_ANY.search(text):
        found.append("not only... but also")
    if _NOT_JUST_RE.search(text):
        found.append("it's not X, it's Y")
    if _OPENER_RE.search(text):
        found.append("summary opener")
    if len(_TRIPLET_RE.findall(text)) >= 2:
        found.append("lists of three")
    if sum(1 for s in sentences if _PARTICIPLE_RE.match(s)) >= 2:
        found.append("participle openers")
    transitions = sum(1 for s in sentences if _TRANSITION_RE.match(s))
    if transitions >= 2 and transitions >= len(sentences) / 3:
        found.append("transition-word openers")
    firsts = [(WORD_RE.findall(s) or [""])[0].lower() for s in sentences]
    if any(a and a == b for a, b in zip(firsts, firsts[1:])):
        found.append("repeated sentence openers")
    if len(sentences) >= 4 and burstiness(text) < 0.3:
        found.append("even sentence lengths")
    return found


# ---------------------------------------------------------------- scoring


@dataclass
class HumanScore:
    burstiness: float  # sentence-length variation
    patterns: list[str] = field(default_factory=list)

    @property
    def total(self) -> float:
        """Higher reads more human. Burstiness is capped so it can't outweigh the patterns."""
        return round(0.8 * min(self.burstiness, 0.9) - 0.15 * len(self.patterns), 3)


def human_score(text: str) -> HumanScore:
    return HumanScore(burstiness(text), ai_patterns(text))


# ---------------------------------------------------------------- Layer 5 restructuring

_CONTRACT = {" ".join(k): v[0] for k, v in lx.CONTRACT_PHRASES.items()}
_CONTRACT_RE = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in sorted(_CONTRACT, key=len, reverse=True)) + r")\b(?=\s+[\w\[])",
    re.IGNORECASE,
)
_SUBJECT = r"(?:the|this|that|these|those|it|its|they|their|we|our|he|she|his|her|there|many|most|some|such|[A-Z][\w-]*|\[\[\d+\]\])"
_SPLIT_RE = re.compile(r"(,\s+(and|but|so|yet)|;)\s+(?=" + _SUBJECT + r"\b)")


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:]


def _split_long(sentence: str, rng: random.Random) -> str | None:
    """Split one long sentence at a clause boundary near its middle, or None."""
    n = word_count(sentence)
    best = None
    for m in _SPLIT_RE.finditer(sentence):
        conj = (m.group(2) or ";").lower()
        left, right = word_count(sentence[: m.start()]), word_count(sentence[m.end() :])
        if left >= 6 and right >= 6:
            dist = abs(left - n / 2)
            if best is None or dist < best[0]:
                best = (dist, m, conj)
    if best is None:
        return None
    _, m, conj = best
    rest = sentence[m.end() :]
    if conj in ("but", "so", "yet") or (conj == "and" and rng.random() < 0.4):
        rest = conj + " " + rest
    return sentence[: m.start()] + ". " + _cap(rest)


# Stiff connectors -> natural ones with the same meaning (addition stays addition, contrast stays
# contrast). "But"/"So" take no comma.
_TRANSITION_SWAPS: dict[str, list[str]] = {
    "furthermore": ["On top of that,", "Plus,", "Also,", "What's more,"],
    "moreover": ["On top of that,", "Plus,", "What's more,"],
    "additionally": ["Also,", "Plus,", "On top of that,"],
    "in addition": ["Also,", "Plus,"],
    "however": ["That said,", "Still,", "But"],
    "nevertheless": ["Even so,", "Still,"],
    "nonetheless": ["Even so,", "Still,"],
    "consequently": ["So", "Because of that,"],
    "therefore": ["So", "Because of that,"],
    "thus": ["So"],
    "similarly": ["In the same way,", "Likewise,"],
}
_TRANSITION_SWAP_RE = re.compile(
    r"(^|[.!?][\"”’)\]]*\s+|\n\s*)(" + "|".join(k.replace(" ", r"\s") for k in _TRANSITION_SWAPS) + r"),\s+(\S)",
    re.IGNORECASE,
)
_THIS_RE = re.compile(
    r"([^.!?\n]{10,}?)\.\s+(?:This|That)\s+(shows|means|suggests|indicates|highlights|demonstrates|reflects|"
    r"explains|helps|allows|makes|leads|creates|is|was)\b"
)
_SUMMARY_START = re.compile(r"^(?:" + "|".join(o.replace(" ", r"\s") for o in _OPENERS) + r"),", re.IGNORECASE)


def _swap_transitions(text: str, src: str, rng: random.Random) -> tuple[str, int]:
    """Replace stiff sentence-opening connectors, never with the same one twice in a part."""
    used: set[str] = set()
    count = 0

    def sub(m: re.Match) -> str:
        nonlocal count
        key = re.sub(r"\s+", " ", m.group(2).lower())
        if key in src or rng.random() < 0.3:  # the author's own words, or leave some as they are
            return m.group(0)
        options = [o for o in _TRANSITION_SWAPS[key] if o not in used]
        if not options:
            return m.group(0)
        choice = rng.choice(options)
        used.add(choice)
        count += 1
        nxt = m.group(3)  # first character of the next word
        word = WORD_RE.match(m.string, m.start(3))
        if word and word.group().lower() in STOPWORDS and word.group() != "I":
            nxt = nxt.lower()  # "Plus, the..." not "Plus, The..."; names keep their capital
        return m.group(1) + choice + " " + nxt

    return _TRANSITION_SWAP_RE.sub(sub, text), count


def _merge_this_openers(text: str) -> tuple[str, int]:
    """ "X. This shows Y." -> "X, which shows Y." when X is short enough to carry a clause."""
    count = 0

    def sub(m: re.Match) -> str:
        nonlocal count
        if word_count(m.group(1)) > 22 or m.group(1).rstrip().endswith((",", ";", ":")):
            return m.group(0)
        count += 1
        return m.group(1) + ", which " + m.group(2)

    return _THIS_RE.sub(sub, text, count=1), count  # once per part, or it becomes its own tic


def _drop_added_summary(text: str, source: str) -> tuple[str, int]:
    """Drop a closing "Overall, ..." sentence the rewrite added (the source has no such sentence)."""
    out_sents, src_sents = split_sentences(text), split_sentences(source)
    if len(out_sents) <= len(src_sents) or len(out_sents) < 3 or not out_sents:
        return text, 0
    last = out_sents[-1]
    if not _SUMMARY_START.match(last) or any(_SUMMARY_START.match(s) for s in src_sents):
        return text, 0
    i = text.rfind(last)
    return text[:i].rstrip() + text[i + len(last) :], 1


# Elliptical phrasing: drop words the reader fills in ("If it is possible" -> "If possible").
_ELLIPSES: list[tuple[re.Pattern, str]] = [
    (
        re.compile(
            r"\b(if|when|where|unless|whenever) it is (possible|necessary|needed|required|appropriate|available)\b",
            re.IGNORECASE,
        ),
        r"\1 \2",
    ),
    (
        re.compile(
            r"\b(as) (?:it is|it was|was|is) (shown|mentioned|noted|described|discussed|expected)\b", re.IGNORECASE
        ),
        r"\1 \2",
    ),
    (
        re.compile(r"\b(when|if) (?:it is|they are) (compared|combined|used|applied) (with|to)\b", re.IGNORECASE),
        r"\1 \2 \3",
    ),
    (re.compile(r"\bif you are able to\b", re.IGNORECASE), "if you can"),
    # reduced relative clause: "the method that was used" -> "the method used"
    (
        re.compile(
            r"(?<=[a-z]) that (?:is|are|was|were) ((?:[a-z]+ed|built|made|done|given|known|seen|shown|taken|written))\b"
        ),
        r" \1",
    ),
]
_WHICH_ASIDE = re.compile(r"(\w), (which|who) ([^,.;:!?()\[\]]{8,70}), (?=[a-z])")


def _ellipsis(text: str, src: str) -> tuple[str, int]:
    count = 0
    for pattern, repl in _ELLIPSES:

        def sub(m: re.Match) -> str:
            nonlocal count
            if m.group(0).lower() in src:
                return m.group(0)  # the author's own phrasing
            count += 1
            out = m.expand(repl)
            return out[:1].upper() + out[1:] if m.group(0)[:1].isupper() else out

        text = pattern.sub(sub, text)
    return text, count


def _parenthetical(text: str, rng: random.Random) -> tuple[str, int]:
    """Set one existing aside apart: "X, which Y, Z" -> "X (which Y) Z"."""
    m = _WHICH_ASIDE.search(text)
    if not m or "(" in text or rng.random() < 0.6:
        return text, 0
    return text[: m.start()] + f"{m.group(1)} ({m.group(2)} {m.group(3)}) " + text[m.end() :], 1


def restructure(text: str, source: str, rng: random.Random) -> tuple[str, int]:
    """Meaning-preserving edits against the structures detectors flag. Returns (text, edits)."""
    edits = 0
    src = source.lower()

    def opener(m: re.Match) -> str:
        nonlocal edits
        if m.group(2).lower() in src:
            return m.group(0)  # the author wrote it
        edits += 1
        return m.group(1) + _cap(m.group(3))

    text, n = _drop_added_summary(text, source)
    edits += n
    text = _OPENER_RE.sub(opener, text)

    # Em dashes are replaced by language_refiner.clean_dashes.

    if "not only" not in src:
        text, n = _NOT_ONLY_RE.subn(r"\1 and", text)
        edits += n

    text, n = _swap_transitions(text, src, rng)
    edits += n
    text, n = _merge_this_openers(text)
    edits += n
    text, n = _ellipsis(text, src)
    edits += n
    text, n = _parenthetical(text, rng)
    edits += n

    def contract(m: re.Match) -> str:
        nonlocal edits
        if rng.random() > 0.75:
            return m.group(0)  # people aren't fully consistent
        edits += 1
        return match_case(m.group(1), _CONTRACT[m.group(1).lower()])

    text = _CONTRACT_RE.sub(contract, text)

    sentences = split_sentences(text)
    if len(sentences) >= 3 and burstiness(text) < 0.45:
        budget = max(1, len(sentences) // 4)
        for s in sorted(sentences, key=word_count, reverse=True):
            if budget == 0 or word_count(s) < 20:
                break
            new = _split_long(s, rng)
            if new and s in text:
                text = text.replace(s, new, 1)
                edits += 1
                budget -= 1
    return text, edits
