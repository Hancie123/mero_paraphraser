"""Rule-based paraphrasing for Humanize mode: phrase rewrites, synonym swaps and contractions.

Used by the rewriting layer (Layer 4).

The engine works on tokens so it can report exactly which spans changed.
Each changed span carries its original text and the other candidates, which
the UI uses to highlight edits and let the user pick an alternative.

Meaning safety:

* hedges, negations and reporting verbs (lexicon.FROZEN) are never swapped;
* a synonym that is the opposite of the word it replaces, or of another word
  in the sentence (lexicon.opposed), is never used or offered, and a word
  whose opposite is in the same sentence ("strong and weak") is kept;
* the user's preferences (core/preferences.py): locked terms never change,
  a preferred replacement is the one used, a banned word is never put in;
* a cheap part-of-speech check (``Paraphraser._fits``) looks at the words
  around a candidate so "the increase" (noun) is not handled like a verb,
  and "issue the statement" (verb) not like a noun;
* names are protected: capitalised mid-sentence, after "Dr." / "e.g." /
  initials, or anywhere once seen capitalised mid-sentence.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field

from ..schemas.paraphrase import ParaphraseError
from ..utils.text_utils import ABBREVIATIONS as TEXT_ABBREVIATIONS
from ..utils.text_utils import match_case, wants_an
from . import lexicon as lx
from .config import MAX_CHARS
from .preferences import NONE, Preferences


@dataclass(frozen=True)
class PhraseRule:
    table: dict[tuple[str, ...], list[str]]
    needs_next_word: bool = False  # only rewrite when another word follows


# Humanize: natural, everyday wording with contractions where they read naturally.
BASE_P = 0.10  # replacement probability at strength 0
SPAN_P = 0.80  # extra probability added at strength 100
# From this strength on, a sentence the normal pass left unchanged gets a second
# pass that makes one safe edit in it (two from strength 75), so most sentences change.
FORCE_FROM = 40
# Zipf points (lexicon.WORD_FREQ): a synonym this much rarer than the word it replaces is
# down-ranked; one HARD_RARE_GAP rarer is never used ("utilize" for "use").
RARE_GAP = 1.0
HARD_RARE_GAP = 2.0
RULES: tuple[PhraseRule, ...] = (
    PhraseRule(lx.GENERAL_PHRASES),
    PhraseRule(lx.CONTRACT_PHRASES, needs_next_word=True),
)
_CONTRACTIONS = RULES[1]  # keeps negations ("do not" -> "don't"), so frozen words are fine here

_TOKEN_RE = re.compile(
    r"(?P<protected>https?://\S+|www\.\S+|[\w.+-]+@[\w-]+\.[\w.-]+|`[^`\n]*`)"
    r"|(?P<word>[^\W\d_]+(?:['’][^\W\d_]+)*)"
    r"|(?P<space>\s+)"
    r"|(?P<other>.)",
    re.DOTALL,
)
_WORD_RE = re.compile(r"[^\W_]+(?:['’][^\W_]+)*")
_MAX_PHRASE = max(len(key) for rule in RULES for key in rule.table)


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


_SUFFIXES = (
    "ization", "ational", "fulness", "iveness", "ically", "ations", "ation", "nesses", "ments", "ment",
    "ness", "ingly", "ings", "ing", "ities", "ity", "ies", "ied", "edly", "ers", "er", "ed", "ly",
    "ance", "ence", "ant", "ent", "ive", "ous", "ful", "al", "ic", "es", "s", "y", "e",
)  # fmt: skip


def _stem(word: str) -> str:
    """Crude suffix-stripping stem: "challenge"/"challenging", "happy"/"happiness" share one.

    Two rounds, each leaving at least four letters, so "significantly" ->
    "significant" -> "signific", while "consider" and "consistent" stay apart.
    """
    w = _norm(word)
    for _ in range(2):
        for suf in _SUFFIXES:
            if w.endswith(suf) and len(w) - len(suf) >= 4:
                w = w[: -len(suf)]
                break
        else:
            break
        if w.endswith("i"):
            w = w[:-1]
    return w


# --- context cues for the part-of-speech check -------------------------------

DETERMINERS = frozenset(
    "a an the this these those my your his its our their each every some any no another such "
    "much many several few more most".split()
)
# Before an adjective with nothing after it, these make it a noun ("the whole of"); "more" does not.
ARTICLES = frozenset("a an the this these those my your his its our their".split())
# Words before a verb, never before a noun: "to issue", "they challenge", "will impact".
VERB_CUES = frozenset("will would can could should must might may shall do does did i you we they he she who".split())
# Words that start an object: "issue the statement", "challenge their view".
OBJECT_START = frozenset("the a an his their our my your its them him us me".split())
PREPOSITIONS = frozenset("of in on at for with from without into about".split())
# Words after an adjective that is being used as a noun: "the whole of", "the chief said".
FUNCTION_AFTER = frozenset(
    "of in on at is are was were and or to for with by from as who that which has have had "
    "will would can could said".split()
)
LINKING = frozenset(
    "is are was were be been being am seem seems seemed become becomes became remain remains stay stays "
    "very so too quite rather really extremely more most less feel feels felt look looks looked get gets got".split()
)
# Adjectives that are also adverbs: "they ran fast." must not become "they ran rapid."
ADVERBIAL = frozenset({"fast", "quick", "quiet", "slow", "hard", "late", "early", "straight"})
# Idioms where a word must stay: "take advantage of", "on purpose", "in place".
_TAKE = ("take", "takes", "took", "taken", "taking")
IDIOM_PREV = frozenset(
    {(t, "advantage") for t in _TAKE}
    | {(t, "place") for t in _TAKE}
    | {("on", "purpose"), ("by", "mistake"), ("in", "place"), ("first", "place"), ("in", "common"),
       ("in", "part"), ("at", "present"), ("for", "good"), ("in", "general"), ("on", "end")}
)  # fmt: skip
IDIOM_NEXT = frozenset({("problem", "solving"), ("whole", "lot"), ("job", "done"), ("end", "up")})

# A "." after these (or after a single letter: "U.S.", "e.g.", "J. Smith") does not end a sentence.
ABBREVIATIONS = frozenset(w for w in TEXT_ABBREVIATIONS if "." not in w)


_ADJ_SUFFIXES = ("al", "ant", "ent", "ive", "ous", "ful", "ic", "able", "ible", "less", "ary")


def _adjective_like(word: str | None) -> bool:
    """An adjective from the lexicon, or a word with a typical adjective ending ("sharp" is missed)."""
    if not word or word in VERB_CUES or word in PREPOSITIONS or word in DETERMINERS:
        return False
    found = lx.lookup(word)
    if found:
        return found[0] == lx.A
    return len(word) > 4 and word.endswith(_ADJ_SUFFIXES)


def _casual(option: str) -> bool:
    """Slang, including its plural ("pals", "kids")."""
    low = option.lower()
    return low in lx.CASUAL or (low.endswith("s") and low[:-1] in lx.CASUAL)


class Paraphraser:
    def __init__(self, text: str, strength: int, rng: random.Random, prefs: Preferences = NONE):
        self.rng = rng
        self.strength = strength
        self.prefs = prefs
        self.p = min(BASE_P + SPAN_P * strength / 100, 0.95)
        matches = list(_TOKEN_RE.finditer(text))
        self.tokens = [(m.lastgroup, m.group()) for m in matches]
        self.locked = self._locked(text, matches)
        self.near: set[str] = set()  # words of the sentence being rewritten (for the opposites check)
        # Word stems already in the text; avoids "the challenge was challenging".
        self.stems = {_stem(t) for k, t in self.tokens if k == "word"}
        self.allowed: set[int] | None = None  # forced pass: only these token positions may change
        self._scan()

    def _locked(self, text: str, matches: list[re.Match]) -> set[int]:
        """Token positions inside one of the user's locked terms."""
        pattern = self.prefs.locked_re()
        if pattern is None:
            return set()
        spans = [(m.start(), m.end()) for m in pattern.finditer(text)]
        return {i for i, m in enumerate(matches) if any(s < m.end() and m.start() < e for s, e in spans)}

    # -- token helpers --------------------------------------------------
    def _kind(self, i: int) -> str | None:
        return self.tokens[i][0] if 0 <= i < len(self.tokens) else None

    def _next_is_word(self, i: int) -> bool:
        """True if token i is followed by a single inline gap and a word."""
        return self._kind(i + 1) == "space" and "\n" not in self.tokens[i + 1][1] and self._kind(i + 2) == "word"

    def _in_compound(self, i: int) -> bool:
        """Part of a hyphenated or slashed compound like ``well-known``."""
        before = self.tokens[i - 1][1] if i > 0 else ""
        after = self.tokens[i + 1][1] if i + 1 < len(self.tokens) else ""
        return before in ("-", "/") or after in ("-", "/")

    def _prev(self, i: int) -> str | None:
        """The word before token i (lowercase), "#" right after a number, else None."""
        j = i - 1
        if self._kind(j) == "space":
            if "\n" in self.tokens[j][1]:
                return None
            j -= 1
        kind = self._kind(j)
        if kind == "word":
            return _norm(self.tokens[j][1])
        if kind == "other" and (self.tokens[j][1].isdigit() or self.tokens[j][1] == "%"):
            return "#"
        return None

    def _next(self, i: int) -> str | None:
        """The word after token i (lowercase), or None at punctuation or a line break."""
        return _norm(self.tokens[i + 2][1]) if self._next_is_word(i) else None

    # -- sentences and names ----------------------------------------------
    def _abbreviation(self, i: int) -> bool:
        """True if the "." at token i ends an abbreviation or an initial, not a sentence."""
        if self._kind(i - 1) != "word":
            return False
        word = self.tokens[i - 1][1]
        return len(word) == 1 or _norm(word) in ABBREVIATIONS

    def _scan(self) -> None:
        """Mark sentence starts and quoted words, find sentence spans, and collect names.

        A word capitalised mid-sentence anywhere in the text counts as a name
        everywhere, including when it opens a sentence.
        """
        n = len(self.tokens)
        self.starts = [False] * n
        self.quoted = [False] * n
        self.sentences: list[tuple[int, int]] = []
        self.names: set[str] = set()
        sentence_start, in_quote, begin = True, False, 0
        for i, (kind, tok) in enumerate(self.tokens):
            if kind == "word":
                self.starts[i], self.quoted[i] = sentence_start, in_quote
                lower = _norm(tok)
                if tok[0].isupper() and not sentence_start and lower != "i" and not lower.startswith("i'"):
                    self.names.add(lower)
                sentence_start = False
            elif kind == "other":
                if tok == '"':
                    in_quote = not in_quote
                elif tok in "“”":
                    in_quote = tok == "“"
                elif tok in "!?" or (tok == "." and not self._abbreviation(i)):
                    sentence_start = True
            elif kind == "space":
                if "\n" in tok:
                    sentence_start = True
                if sentence_start and i >= begin:
                    self.sentences.append((begin, i + 1))
                    begin = i + 1
        if begin < n:
            self.sentences.append((begin, n))

    # -- part-of-speech check ---------------------------------------------
    def _fits(self, pos: str, lower: str, i: int) -> bool:
        """Cheap context check that the word is used in its group's part of speech."""
        prev, nxt = self._prev(i), self._next(i)
        if (prev, lower) in IDIOM_PREV or (lower, nxt) in IDIOM_NEXT:
            return False
        if pos == lx.N:
            if prev in VERB_CUES or (prev and prev.endswith(("n't", "'ll", "'d"))):
                return False  # "they challenge", "will impact"
            if nxt in OBJECT_START and prev not in DETERMINERS:
                return False  # "issue the statement", "to target their"
        elif pos == lx.V:
            if prev in DETERMINERS or prev == "#" or _adjective_like(prev):
                return False  # "the increase", "a 5% increase", "a significant increase"
            if prev and prev not in VERB_CUES and self._prev(i - 2) in ("a", "an", "the"):
                return False  # "a sharp increase", "the final finish"
            if not lower.endswith("ing") and prev in PREPOSITIONS:
                return False  # "in need of", "with increased risk"
        elif pos == lx.A:
            nounish_end = nxt is None or nxt in FUNCTION_AFTER
            if prev in ARTICLES and nounish_end:
                return False  # "the whole of", "a grave.", "the chief said"
            if prev in PREPOSITIONS and nounish_end:
                return False  # "in common", "for real"
            if lower in ADVERBIAL and prev not in LINKING and prev not in DETERMINERS and nounish_end:
                return False  # "they ran fast."
        return True

    # -- choosing a replacement -----------------------------------------
    def _ok(self, candidate: str, original: str) -> bool:
        """Not banned, and not the opposite of the original or of another word in the sentence."""
        if not self.prefs.allows(candidate):
            return False
        others = self.near - {original}
        return not any(lx.opposed(w, original) or any(lx.opposed(w, n) for n in others) for w in candidate.split())

    def _pick(self, options: list[str], original: str) -> str | None:
        """One of the two most common candidates, skipping slang and down-ranking rare words.

        A candidate much rarer than the original ("weary" for "tired") is used only when
        nothing more common fits, and never when it is very much rarer.
        """
        opts = [o for o in options if o.lower() != original and not _casual(o)]
        common = [o for o in opts if not lx.much_rarer(o, original, RARE_GAP)]
        opts = (common or [o for o in opts if not lx.much_rarer(o, original, HARD_RARE_GAP)])[:2]
        return self.rng.choice(opts) if opts else None

    def _phrase(self, i: int) -> tuple[Segment, int] | None:
        words: list[str] = []
        positions: list[int] = []
        j = i
        while len(words) < _MAX_PHRASE and self._kind(j) == "word" and j not in self.locked:
            words.append(_norm(self.tokens[j][1]))
            positions.append(j)
            if not self._next_is_word(j):
                break
            j += 2
        for length in range(len(words), 0, -1):
            key = tuple(words[:length])
            end = positions[length - 1] + 1
            preferred = self.prefs.preferred.get(" ".join(key))
            if preferred:
                if length == 1:
                    break  # a single word: _synonym applies the preference
                if self.rng.random() >= self.p:
                    continue
                original = "".join(t for _, t in self.tokens[i:end])
                return Segment(match_case(original, preferred), "word", original, [original]), end - i
            for rule in RULES:
                options = rule.table.get(key)
                if not options:
                    continue
                if rule is not _CONTRACTIONS:
                    if lx.is_frozen(" ".join(key)):
                        continue
                    options = [o for o in options if not lx.is_frozen(o)]
                options = [o for o in options if self._ok(o, " ".join(key))]
                if not options:
                    continue
                if rule.needs_next_word and not self._next_is_word(end - 1):
                    continue
                if self.rng.random() >= self.p:
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

    def _synonym(self, token: str, i: int) -> Segment | None:
        lower = _norm(token)
        found = lx.lookup(lower)
        preferred = self.prefs.preferred.get(lower)
        if preferred:  # the user's choice wins over the built-in groups and the frozen words
            if self.rng.random() >= self.p or (found and not self._fits(found[0], lower, i)):
                return None
            self.stems.add(_stem(preferred.split(" ")[0]))
            others = [c for c in (found[1] if found else []) if c.lower() != preferred.lower() and self._ok(c, lower)]
            return Segment(
                match_case(token, preferred), "word", token, [match_case(token, c) for c in others] + [token]
            )
        if lower in lx.FROZEN:  # hedges, negations, reporting verbs: never swapped
            return None
        if not found or any(lx.opposed(lower, n) for n in self.near - {lower}):
            return None  # one side of a contrast ("strong and weak") stays as written
        pos, candidates = found
        candidates = [c for c in candidates if not lx.is_frozen(c) and self._ok(c, lower)]
        if not candidates or self.rng.random() >= self.p or not self._fits(pos, lower, i):
            return None
        fresh = [c for c in candidates if _stem(c.split(" ")[0]) not in self.stems]
        choice = self._pick(fresh, lower)
        if choice is None:
            return None
        self.stems.add(_stem(choice.split(" ")[0]))
        text = match_case(token, choice)
        alts = [match_case(token, c) for c in candidates if c != choice]
        return Segment(text, "word", token, alts + [token])

    # -- main pass -------------------------------------------------------
    def _span(self, lo: int, hi: int) -> list[tuple[int, Segment]]:
        """Rewrite tokens lo..hi-1; returns (token index, segment) pairs."""
        out: list[tuple[int, Segment]] = []
        self.near = {_norm(t) for k, t in self.tokens[lo:hi] if k == "word"}
        i = lo
        while i < hi:
            kind, tok = self.tokens[i]
            if kind != "word":
                out.append((i, Segment(tok, kind)))
                i += 1
                continue
            lower = _norm(tok)
            is_i = lower == "i" or lower.startswith("i'")
            name = tok[0].isupper() and not is_i and (not self.starts[i] or lower in self.names)
            seg, consumed = None, 1
            may_change = (self.allowed is None or i in self.allowed) and i not in self.locked
            if may_change and not (self.quoted[i] or name or self._in_compound(i)):
                hit = self._phrase(i)
                if hit and i + hit[1] <= hi:
                    seg, consumed = hit
                else:
                    seg = self._synonym(tok, i)
            out.append((i, seg or Segment(tok, "word")))
            i += consumed
        return out

    def _forced(self, lo: int, hi: int) -> list[tuple[int, Segment]] | None:
        """Second pass over an unchanged sentence: a few safe edits at random spots."""
        stems, p = set(self.stems), self.p
        self.p = 1.0
        spots = [i for i, seg in self._span(lo, hi) if seg.changed]  # every place an edit fits
        self.stems = set(stems)
        result = None
        if spots:
            self.allowed = set(self.rng.sample(spots, min(len(spots), 1 if self.strength < 75 else 2)))
            result = self._span(lo, hi)
            self.allowed = None
        self.p = p
        return result

    def run(self) -> list[Segment]:
        out: list[Segment] = []
        for lo, hi in self.sentences:
            span = self._span(lo, hi)
            words = sum(1 for _, seg in span if seg.kind == "word")
            if self.strength >= FORCE_FROM and words >= 4 and not any(seg.changed for _, seg in span):
                span = self._forced(lo, hi) or span
            out.extend(seg for _, seg in span)
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
            merged.append(
                {
                    "text": seg.text,
                    "original": seg.original,
                    "alternatives": list(dict.fromkeys(a for a in seg.alternatives if a != seg.text)),
                }
            )
        elif merged and "original" not in merged[-1]:
            merged[-1]["text"] += seg.text
        else:
            merged.append({"text": seg.text})
    return merged


def paraphrase(text: str, strength: int = 50, seed: int | None = None, prefs: Preferences = NONE) -> dict:
    """Paraphrase ``text``. Same text, strength, seed and preferences give the same output."""
    if not isinstance(text, str):
        raise ParaphraseError("text must be a string")
    if len(text) > MAX_CHARS:
        raise ParaphraseError(f"text is too long ({len(text):,} characters, max {MAX_CHARS:,})")
    strength = max(0, min(100, int(strength)))

    segments = Paraphraser(text, strength, random.Random(seed), prefs).run()
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
