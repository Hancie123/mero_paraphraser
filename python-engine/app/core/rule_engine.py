"""Rule-based paraphrasing: phrase rewrites, synonym swaps and register shifts.

Used by the rewriting layer when the AI model isn't installed yet.

The engine works on tokens so it can report exactly which spans changed.
Each changed span carries its original text and the other candidates, which
the UI uses to highlight edits and let the user pick an alternative.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field

from ..schemas.paraphrase import ParaphraseError
from . import lexicon as lx
from .config import MAX_CHARS


@dataclass(frozen=True)
class PhraseRule:
    table: dict[tuple[str, ...], list[str]]
    forced: bool  # always apply (the point of the mode) vs. roll against strength
    needs_next_word: bool = False  # only rewrite when another word follows


@dataclass(frozen=True)
class ModeConfig:
    label: str
    description: str
    base_p: float  # replacement probability at strength 0
    span_p: float  # extra probability added at strength 100
    picker: str  # how a candidate is chosen, see Paraphraser._pick
    rules: tuple[PhraseRule, ...] = ()
    only_shorter: bool = False
    remove_fillers: bool = False


MODES: dict[str, ModeConfig] = {
    "standard": ModeConfig(
        "Standard", "Balanced rewording that keeps the meaning.",
        0.10, 0.60, "random", (PhraseRule(lx.GENERAL_PHRASES, False),),
    ),
    "fluent": ModeConfig(
        "Fluent", "Natural, everyday wording that reads smoothly.",
        0.08, 0.50, "common",
        (PhraseRule(lx.GENERAL_PHRASES, False),
         PhraseRule(lx.CONTRACT_PHRASES, False, needs_next_word=True)),
    ),
    "formal": ModeConfig(
        "Formal", "Professional tone: no contractions, formal vocabulary.",
        0.10, 0.50, "formal",
        (PhraseRule(lx.EXPAND_CONTRACTIONS, True),
         PhraseRule(lx.FORMAL_PHRASES, True),
         PhraseRule(lx.GENERAL_PHRASES, False)),
    ),
    "simple": ModeConfig(
        "Simple", "Plain words and shorter phrases that are easy to read.",
        0.15, 0.55, "simple", (PhraseRule(lx.SIMPLE_PHRASES, True),),
        only_shorter=True,
    ),
    "creative": ModeConfig(
        "Creative", "Bolder rewording with more varied vocabulary.",
        0.35, 0.60, "wild",
        (PhraseRule(lx.GENERAL_PHRASES, False),
         PhraseRule(lx.CONTRACT_PHRASES, False, needs_next_word=True)),
    ),
    "shorten": ModeConfig(
        "Shorten", "Cuts wordy phrases and filler words.",
        0.05, 0.30, "simple", (PhraseRule(lx.SHORTEN_PHRASES, True),),
        only_shorter=True, remove_fillers=True,
    ),
}

_TOKEN_RE = re.compile(
    r"(?P<protected>https?://\S+|www\.\S+|[\w.+-]+@[\w-]+\.[\w.-]+|`[^`\n]*`)"
    r"|(?P<word>[^\W\d_]+(?:['’][^\W\d_]+)*)"
    r"|(?P<space>\s+)"
    r"|(?P<other>.)",
    re.DOTALL,
)
_WORD_RE = re.compile(r"[^\W_]+(?:['’][^\W_]+)*")
_MAX_PHRASE = max(
    len(key) for cfg in MODES.values() for rule in cfg.rules for key in rule.table
)
_AN_EXCEPTIONS = ("hour", "honest", "honor", "honour", "heir")
_A_EXCEPTIONS = (
    "unique", "unit", "univ", "unif", "union", "unicorn", "usual", "use", "usa",
    "utili", "utop", "euro", "eu", "one", "once", "ufo",
)


@dataclass
class Segment:
    text: str
    kind: str = "other"
    original: str | None = None
    alternatives: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return self.original is not None


def _norm(word: str) -> str:
    return word.lower().replace("’", "'")


def _stem(word: str) -> str:
    return _norm(word)[:5]


def match_case(original: str, replacement: str) -> str:
    """Give ``replacement`` the capitalisation style of ``original``."""
    letters = [c for c in original if c.isalpha()]
    if len(letters) > 1 and all(c.isupper() for c in letters):
        return replacement.upper()
    if original[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def wants_an(word: str) -> bool:
    w = word.lower()
    if w.startswith(_AN_EXCEPTIONS):
        return True
    if w.startswith(_A_EXCEPTIONS):
        return False
    return w[:1] in "aeiou"


class Paraphraser:
    def __init__(self, text: str, cfg: ModeConfig, strength: int, rng: random.Random):
        self.cfg = cfg
        self.rng = rng
        self.p = min(cfg.base_p + cfg.span_p * strength / 100, 0.95)
        self.tokens = [(m.lastgroup, m.group()) for m in _TOKEN_RE.finditer(text)]
        # Word stems already in the text; avoids "the challenge was challenging".
        self.stems = {_stem(t) for k, t in self.tokens if k == "word"}

    # -- token helpers --------------------------------------------------
    def _kind(self, i: int) -> str | None:
        return self.tokens[i][0] if 0 <= i < len(self.tokens) else None

    def _next_is_word(self, i: int) -> bool:
        """True if token i is followed by a single inline gap and a word."""
        return (
            self._kind(i + 1) == "space"
            and "\n" not in self.tokens[i + 1][1]
            and self._kind(i + 2) == "word"
        )

    def _in_compound(self, i: int) -> bool:
        """Part of a hyphenated or slashed compound like ``well-known``."""
        before = self.tokens[i - 1][1] if i > 0 else ""
        after = self.tokens[i + 1][1] if i + 1 < len(self.tokens) else ""
        return before in ("-", "/") or after in ("-", "/")

    # -- choosing a replacement -----------------------------------------
    def _pick(self, options: list[str], original: str) -> str | None:
        opts = [o for o in options if o.lower() != original]
        if not opts:
            return None
        picker = self.cfg.picker
        if picker == "formal":
            preferred = [o for o in opts if o in lx.FORMAL_PREF]
            opts = preferred or [o for o in opts if o not in lx.CASUAL]
        elif picker == "simple":
            plain = [o for o in opts if o not in lx.FORMAL_PREF] or opts
            shortest = min(len(o) for o in plain)
            opts = [o for o in plain if len(o) <= shortest + 1]
        elif picker == "common":
            opts = [o for o in opts if o not in lx.CASUAL][:2]
        elif picker == "random":
            opts = [o for o in opts if o not in lx.CASUAL]
        return self.rng.choice(opts) if opts else None

    def _phrase(self, i: int) -> tuple[Segment, int] | None:
        words: list[str] = []
        positions: list[int] = []
        j = i
        while len(words) < _MAX_PHRASE and self._kind(j) == "word":
            words.append(_norm(self.tokens[j][1]))
            positions.append(j)
            if not self._next_is_word(j):
                break
            j += 2
        for length in range(len(words), 0, -1):
            key = tuple(words[:length])
            end = positions[length - 1] + 1
            for rule in self.cfg.rules:
                options = rule.table.get(key)
                if not options:
                    continue
                if rule.needs_next_word and not self._next_is_word(end - 1):
                    continue
                if not rule.forced and self.rng.random() >= self.p:
                    continue
                original = "".join(t for _, t in self.tokens[i:end])
                choice = self._pick(options, original.lower())
                if choice is None:
                    continue
                # "it's been" -> "it has been", not "it is been"
                if key[-1].endswith("'s") and choice.endswith(" is"):
                    nxt = self.tokens[end + 1][1].lower() if self._next_is_word(end - 1) else ""
                    if nxt == "been":
                        choice = choice[:-3] + " has"
                text = match_case(original, choice)
                alts = [match_case(original, o) for o in options if o != choice]
                return Segment(text, "word", original, alts + [original]), end - i
        return None

    def _synonym(self, token: str) -> Segment | None:
        lower = _norm(token)
        candidates = lx.synonyms_for(lower)
        if not candidates or self.rng.random() >= self.p:
            return None
        fresh = [c for c in candidates if _stem(c.split(" ")[0]) not in self.stems]
        choice = self._pick(fresh, lower)
        if choice is None or (self.cfg.only_shorter and len(choice) >= len(lower)):
            return None
        self.stems.add(_stem(choice.split(" ")[0]))
        text = match_case(token, choice)
        alts = [match_case(token, c) for c in candidates if c != choice]
        return Segment(text, "word", token, alts + [token])

    # -- main pass -------------------------------------------------------
    def run(self) -> list[Segment]:
        out: list[Segment] = []
        sentence_start, in_quote, cap_next = True, False, False
        i, n = 0, len(self.tokens)
        while i < n:
            kind, tok = self.tokens[i]
            if kind != "word":
                out.append(Segment(tok, kind))
                if kind == "other":
                    if tok == '"':
                        in_quote = not in_quote
                    elif tok in "“”":
                        in_quote = tok == "“"
                    elif tok in ".!?":
                        sentence_start = True
                elif kind == "space" and "\n" in tok:
                    sentence_start = True
                i += 1
                continue

            lower = _norm(tok)
            is_i = lower == "i" or lower.startswith("i'")
            proper_noun = tok[0].isupper() and not sentence_start and not is_i
            seg, consumed = None, 1
            if not (in_quote or proper_noun or self._in_compound(i)):
                if self.cfg.remove_fillers and lower in lx.FILLERS and self._next_is_word(i):
                    cap_next = cap_next or tok[0].isupper()
                    i += 2  # drop the filler and the space after it
                    continue
                hit = self._phrase(i)
                if hit:
                    seg, consumed = hit
                else:
                    seg = self._synonym(tok)
            if seg is None:
                seg = Segment(tok, "word")
            if cap_next:
                seg.text = seg.text[:1].upper() + seg.text[1:]
                cap_next = False
            out.append(seg)
            sentence_start = False
            i += consumed
        _fix_articles(out)
        return out


def _fix_articles(segments: list[Segment]) -> None:
    """Repair "a"/"an" in front of words that were changed."""
    for idx in range(len(segments) - 2):
        art, gap, nxt = segments[idx], segments[idx + 1], segments[idx + 2]
        low = art.text.lower()
        if low not in ("a", "an") or gap.kind != "space" or "\n" in gap.text:
            continue
        if nxt.kind != "word" or not (art.changed or nxt.changed):
            continue
        want = "an" if wants_an(nxt.text) else "a"
        if low == want:
            continue
        if not art.changed:
            art.original, art.alternatives = art.text, [art.text]
        art.text = match_case(art.text, want)


def _merge(segments: list[Segment]) -> list[dict]:
    """Collapse runs of unchanged text into single segments for the UI."""
    merged: list[dict] = []
    for seg in segments:
        if seg.changed:
            merged.append({
                "text": seg.text,
                "original": seg.original,
                "alternatives": list(dict.fromkeys(a for a in seg.alternatives if a != seg.text)),
            })
        elif merged and "original" not in merged[-1]:
            merged[-1]["text"] += seg.text
        else:
            merged.append({"text": seg.text})
    return merged


def paraphrase(text: str, mode: str = "standard", strength: int = 50, seed: int | None = None) -> dict:
    """Paraphrase ``text``. Same text, mode, strength and seed give the same output."""
    if not isinstance(text, str):
        raise ParaphraseError("text must be a string")
    if len(text) > MAX_CHARS:
        raise ParaphraseError(f"text is too long ({len(text):,} characters, max {MAX_CHARS:,})")
    cfg = MODES.get(mode)
    if cfg is None:
        raise ParaphraseError(f"unknown mode {mode!r}; choose one of {', '.join(MODES)}")
    strength = max(0, min(100, int(strength)))

    segments = Paraphraser(text, cfg, strength, random.Random(seed)).run()
    output = "".join(s.text for s in segments)
    words_in = len(_WORD_RE.findall(text))
    changed_words = sum(len(_WORD_RE.findall(s.original)) for s in segments if s.changed)
    return {
        "text": output,
        "segments": _merge(segments),
        "stats": {
            "words_in": words_in,
            "words_out": len(_WORD_RE.findall(output)),
            "changes": sum(1 for s in segments if s.changed),
            "change_pct": round(100 * changed_words / words_in) if words_in else 0,
        },
    }
