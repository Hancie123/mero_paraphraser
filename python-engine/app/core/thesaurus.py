"""Similar words for the picker: click any word in the result to see them.

Sources, best first:

1. the hand-written groups in lexicon.py (reviewed, also used by the rewrite);
2. app/data/thesaurus.json (built by tools/build_thesaurus.py from WordNet),
   grouped by meaning with a short gloss, so the user can pick the right sense.

Inflected words are looked up by their base form and the suggestions are put
back in the same form: "problems" -> "issues", "analysed" -> "examined".
Senses whose part of speech matches the word's use in the sentence come first
("a show" lists the noun senses first, "they show" the verb senses).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from ..utils.text_utils import match_case
from . import lexicon as lx
from . import pos

DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "thesaurus.json"
_POS_NAMES = {"n": "noun", "v": "verb", "a": "adjective", "r": "adverb"}
_TAG_POS = {"NN": "n", "NNS": "n", "NNP": "n", "VB": "v", "VBZ": "v", "VBD": "v", "VBN": "v", "VBG": "v",
            "JJ": "a", "RB": "r"}  # fmt: skip


@dataclass
class Sense:
    pos: str  # noun | verb | adjective | adverb | "" for the hand-written group
    gloss: str
    words: list[str]

    def to_dict(self) -> dict:
        return {"pos": self.pos, "gloss": self.gloss, "words": self.words}


@cache
def _data() -> dict[str, list]:
    try:
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))["words"]
    except (OSError, ValueError, KeyError):
        return {}


def _plural(word: str) -> str:
    head, _, last = word.rpartition(" ")
    if last.endswith(("s", "x", "z", "ch", "sh")):
        last += "es"
    elif last.endswith("y") and last[-2:-1] not in "aeiou":
        last = last[:-1] + "ies"
    else:
        last += "s"
    return f"{head} {last}" if head else last


def _verb_form(word: str, form: str) -> str:
    """Inflect the first word of a (possibly two-word) verb: "break down" -> "broke down"."""
    first, _, rest = word.partition(" ")
    first = {"third": pos.third, "past": pos.past, "pp": pos.participle, "gerund": pos.gerund}[form](first)
    return f"{first} {rest}" if rest else first


def _forms(word: str) -> list[tuple[str, str, str]]:
    """(base, part of speech, form) readings of ``word``: "problems" -> [("problem", "n", "plural")]."""
    w = word.lower()
    out: list[tuple[str, str, str]] = []
    data = _data()
    if w in data:
        out.append((w, "", "base"))
    lemma = pos.lemma(w)
    if lemma and lemma != w and lemma in data:
        if w.endswith("ing"):
            out.append((lemma, "v", "gerund"))
        elif w.endswith("s") and not w.endswith("ss"):
            out.append((lemma, "v", "third"))
        else:
            past, pp = pos.past(lemma), pos.participle(lemma)
            out.append((lemma, "v", "pp" if w == pp and w != past else "past"))
    if w.endswith("s") and not w.endswith("ss"):
        for base in (w[:-3] + "y" if w.endswith("ies") else None, w[:-2] if w.endswith("es") else None, w[:-1]):
            if base and base in data:
                out.append((base, "n", "plural"))
                break
    return out


def _inflect(cand: str, sense_pos: str, form: str) -> str | None:
    if form == "base":
        return cand
    if form == "plural":
        return _plural(cand) if sense_pos == "n" else None
    return _verb_form(cand, form) if sense_pos == "v" else None


# Shown above the list when the word sets how sure or how strong a claim is.
FROZEN_NOTE = "This word sets how certain or strong the claim is; a swap can change the meaning."


def is_risky(word: str) -> bool:
    """A hedge, negation or reporting verb ("suggest", "may", "not"), in any form."""
    low = word.lower()
    return lx.is_frozen(low) or any(lx.is_frozen(base) for base, _, _ in _forms(low))


def senses_for(word: str, context: str = "") -> list[Sense]:
    """Similar words for ``word``, grouped by meaning. ``context`` is the sentence it is in.

    Unlike the rewrite, this also lists words for hedges and reporting verbs, since the
    user picks one; check ``is_risky`` to warn them.
    """
    low = word.lower()
    if not low.replace("'", "").replace("’", "").isalpha():
        return []
    want = _context_pos(word, context)
    out: list[Sense] = []
    seen = {low}

    curated = lx.suggestions_for(low) or []
    curated = [c for c in curated if c.lower() not in seen]
    if curated:
        out.append(Sense("", "", [match_case(word, c) for c in curated]))
        seen.update(c.lower() for c in curated)

    groups: list[tuple[int, Sense]] = []
    for base, form_pos, form in _forms(low):
        for k, (sense_pos, gloss, cands) in enumerate(_data().get(base, [])):
            if form_pos and sense_pos != form_pos and not (form_pos == "v" and sense_pos == "a" and form == "pp"):
                continue
            words = []
            for cand in cands:
                new = _inflect(cand, sense_pos, form)
                if new and new.lower() not in seen and not lx.opposed(low, new.lower()):
                    words.append(match_case(word, new))
                    seen.add(new.lower())
            if words:
                rank = (0 if not want or sense_pos == want else 1) * 100 + k
                groups.append((rank, Sense(_POS_NAMES[sense_pos], gloss, words)))
    out += [s for _, s in sorted(groups, key=lambda g: g[0])]
    return out


def _context_pos(word: str, context: str) -> str:
    """The word's part of speech in ``context`` ("n", "v", "a", "r"), or "" if unknown."""
    if not context:
        return ""
    words = [w.strip('.,;:!?"“”()') for w in context.split()]
    words = [w for w in words if w]
    for i, w in enumerate(words):
        if w.lower() == word.lower():
            return _TAG_POS.get(pos.tag(words)[i], "")
    return ""
