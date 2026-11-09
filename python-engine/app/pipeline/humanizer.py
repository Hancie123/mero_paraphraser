"""Human-like output: score drafts the way AI detectors do, and fix what they flag.

Detectors such as GPTZero look at three things:

* perplexity: how predictable each word is to a language model,
* burstiness: how much sentence length and predictability vary,
* patterns: structures models overuse ("not only... but also", a summary
  opener on the last sentence, lists of three, sentences of even length).

Layer 4 uses ``human_score`` to choose between drafts, ``flattest_sentence`` to
pick one sentence to rewrite, and ``swap_predictable`` to replace a few words
the model was sure of. Layer 5 calls ``restructure``, which only makes edits
that keep the meaning: it drops summary openers, unrolls "not only... but
also", splits a long sentence when the lengths are too even, and uses
contractions in casual modes. ``record_preference`` saves good/bad draft pairs
for fine-tuning (tools/train_dpo.py).
"""

from __future__ import annotations

import json
import math
import os
import random
import re
import statistics
import threading
from dataclasses import dataclass, field
from pathlib import Path

from ..core import lexicon as lx
from ..core.config import (
    AVOID_WORDS,
    CASUAL_MODES,
    FLAT_SENTENCE,
    MAX_SWAPS,
    STYLE_SAMPLE_CHARS,
    SWAP_MIN_PROB,
    SWAP_RATE,
    style_dirs,
)
from ..utils.text_utils import PLACEHOLDER_RE, STOPWORDS, WORD_RE, match_case, split_sentences, word_count

# (start, end, logprob, alternatives) of each generated token in the text; alternatives are the
# other tokens the model rated likely at that point
Tokens = list[tuple[int, int, float, tuple[str, ...]]]

# ---------------------------------------------------------------- patterns

_OPENERS = ("overall", "ultimately", "in essence", "in summary", "in conclusion", "in short",
            "all in all", "taken together", "to sum up", "in the end")
_OPENER_RE = re.compile(
    r"(^|[.!?][\"”’)\]]*\s+|\n\s*)(" + "|".join(o.replace(" ", r"\s") for o in _OPENERS) + r"),\s+(\S)",
    re.IGNORECASE,
)
_NOT_ONLY_RE = re.compile(r"\bnot only ((?:[\w'’-]+ ){0,5}?[\w'’-]+),? but also\b")
_NOT_ONLY_ANY = re.compile(r"\bnot only\b[^.!?]{1,80}?\bbut\b", re.IGNORECASE)
_NOT_JUST_RE = re.compile(
    r"\b(?:isn't|is not|it's not|aren't|are not|wasn't|was not)\s+(?:just|only|merely|simply)\b"
    r"[^.!?;]{1,60}[,;]\s*(?:it's|it is|they're|they are|but)\b", re.IGNORECASE)
_TRIPLET_RE = re.compile(r"\b[\w-]+(?: [\w-]+){0,2}, [\w-]+(?: [\w-]+){0,2}, (?:and|or) [\w-]+"
                         r"|\b[\w-]+, [\w-]+ (?:and|or) [\w-]+\b")
_EM_DASH_RE = re.compile(r"\s*—\s*")
_PARTICIPLE_RE = re.compile(r"^[A-Z][a-z]{2,}ing\b[^,.]{0,60},")
_TRANSITIONS = ("however", "additionally", "furthermore", "moreover", "consequently", "therefore",
                "thus", "notably", "importantly", "indeed", "similarly", "in addition")
_TRANSITION_RE = re.compile(r"^(?:" + "|".join(_TRANSITIONS) + r"),", re.IGNORECASE)


def sentence_spans(text: str) -> list[tuple[int, int]]:
    """Character spans of the sentences in ``text``."""
    spans, pos = [], 0
    for s in split_sentences(text):
        i = text.find(s, pos)
        if i >= 0:
            spans.append((i, i + len(s)))
            pos = i + len(s)
    return spans


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


def _word_surprisals(raw: str, tokens: Tokens, span: tuple[int, int] | None = None) -> list[float]:
    """Surprisal (-logprob) of each token that contains a letter, optionally inside ``span``."""
    out = []
    for a, b, lp, _ in tokens:
        if span and not (span[0] <= a < span[1]):
            continue
        piece = raw[a:b]
        if any(c.isalpha() for c in piece) and not PLACEHOLDER_RE.search(raw[max(0, a - 3):b + 3]):
            out.append(-lp)
    return out


@dataclass
class HumanScore:
    surprisal: float | None  # mean nats per token (None: no token data)
    spread: float | None  # how much the sentences' surprisal varies
    burstiness: float  # sentence-length variation
    patterns: list[str] = field(default_factory=list)

    @property
    def total(self) -> float:
        """Higher reads more human. Each part is capped so no single signal can win alone."""
        s = min(self.surprisal or 0.0, 2.5) + min(self.spread or 0.0, 1.0)
        return round(s + 0.8 * min(self.burstiness, 0.9) - 0.15 * len(self.patterns), 3)


def human_score(text: str, raw: str = "", tokens: Tokens | None = None) -> HumanScore:
    """Score ``text`` (the refined draft); ``raw``/``tokens`` are the model's reply and its token data."""
    surprisal = spread = None
    if tokens:
        values = _word_surprisals(raw, tokens)
        if values:
            surprisal = statistics.fmean(values)
            per_sentence = [statistics.fmean(v) for v in
                            (_word_surprisals(raw, tokens, s) for s in sentence_spans(raw)) if v]
            spread = statistics.pstdev(per_sentence) if len(per_sentence) > 1 else 0.0
    return HumanScore(surprisal, spread, burstiness(text), ai_patterns(text))


def flattest_sentence(raw: str, tokens: Tokens) -> tuple[int, int] | None:
    """The most predictable sentence of 8+ words, if it is far below the part's average."""
    if not tokens:
        return None
    overall = _word_surprisals(raw, tokens)
    if not overall:
        return None
    mean = statistics.fmean(overall)
    scored = []
    for span in sentence_spans(raw):
        values = _word_surprisals(raw, tokens, span)
        if values and word_count(raw[span[0]:span[1]]) >= 8:
            scored.append((statistics.fmean(values), span))
    if len(scored) < 2:
        return None
    low, span = min(scored)
    return span if low < FLAT_SENTENCE * mean else None


def splice_tokens(tokens: Tokens, start: int, end: int, new_len: int) -> Tokens:
    """Token data after ``text[start:end]`` is replaced by ``new_len`` characters (the new part has none)."""
    shift = new_len - (end - start)
    out = []
    for a, b, lp, alts in tokens:
        if b <= start:
            out.append((a, b, lp, alts))
        elif a >= end:
            out.append((a + shift, b + shift, lp, alts))
    return out


# ---------------------------------------------------------------- word swaps

_NO_SWAP_TO = {"significant", "significantly", "crucial", "essential", "definitive", "substantial"}


def swap_predictable(raw: str, tokens: Tokens, keep: set[str], strength: int, formal: bool,
                     rng: random.Random, skip: tuple[int, int] | None = None) -> tuple[str, Tokens, int]:
    """Swap the words the model was surest of for lexicon synonyms.

    Model text is predictable word by word; a few less expected (but correct)
    words lift perplexity the way a human's choices do. ``keep`` holds names
    and key terms that must not change; ``skip`` is a span left alone.
    """
    if not tokens:
        return raw, tokens, 0
    budget = min(MAX_SWAPS, round(SWAP_RATE * strength / 100 * word_count(raw)))
    if budget <= 0:
        return raw, tokens, 0
    stems = {w.lower()[:5] for w in WORD_RE.findall(raw)}
    options = []
    for m in WORD_RE.finditer(raw):
        word, (a, b) = m.group(), m.span()
        lower = word.lower()
        entry = lx.swap_entry(lower)
        if (len(word) < 4 or not word.islower() or lower in STOPWORDS or lower in keep
                # adjectives and adverbs only: swapping a verb or noun can break the grammar
                # ("helping doctors diagnose" -> "supporting doctors diagnose")
                or not entry or entry[0] not in (lx.A, lx.R)
                or (skip and skip[0] <= a < skip[1]) or PLACEHOLDER_RE.search(raw[max(0, a - 3):b + 3])
                or (b < len(raw) and raw[b] in "-/") or (a > 0 and raw[a - 1] in "-/")):
            continue
        covering = [t for t in tokens if t[0] < b and t[1] > a]
        lp = sum(t[2] for t in covering)
        if not covering or math.exp(lp) < SWAP_MIN_PROB:
            continue
        # Contextual check: only synonyms the model itself rated likely here (its top 10
        # alternatives for the word's first token), so "feline" fits a report and "kitty" a chat.
        alts = {x.strip().lower() for x in covering[0][3]}
        alts = {x for x in alts if len(x) >= 3 and x != lower[:len(x)]}
        synonyms = [s for s in (lx.suggestions_for(lower) or []) if s != lower and s not in AVOID_WORDS
                    and s not in _NO_SWAP_TO and s.split()[0][:5] not in stems
                    and not (formal and s in lx.CASUAL) and not (not formal and s in lx.FORMAL_PREF)
                    and any(s.startswith(x) for x in alts)]
        if synonyms:
            options.append((lp, a, b, word, synonyms[:2]))
    options.sort(key=lambda o: -o[0])
    chosen: list[tuple[int, int, str]] = []
    for _, a, b, word, synonyms in options:
        if len(chosen) >= budget:
            break
        if any(abs(a - c[0]) < 20 for c in chosen):
            continue  # spread the swaps out
        chosen.append((a, b, match_case(word, rng.choice(synonyms))))
    for a, b, new in sorted(chosen, reverse=True):
        raw = raw[:a] + new + raw[b:]
        tokens = splice_tokens(tokens, a, b, len(new))
    return raw, tokens, len(chosen)


# ---------------------------------------------------------------- Layer 5 restructuring

_CONTRACT = {" ".join(k): v[0] for k, v in lx.CONTRACT_PHRASES.items()}
_CONTRACT_RE = re.compile(r"\b(" + "|".join(re.escape(k) for k in sorted(_CONTRACT, key=len, reverse=True))
                          + r")\b(?=\s+[\w\[])", re.IGNORECASE)
_HAS_CONTRACTION = re.compile(r"\b\w+['’](?:t|s|re|ve|ll|d|m)\b", re.IGNORECASE)
_SUBJECT = r"(?:the|this|that|these|those|it|its|they|their|we|our|he|she|his|her|there|many|most|some|such|[A-Z][\w-]*|\[\[\d+\]\])"
_SPLIT_RE = re.compile(r"(,\s+(and|but|so|yet)|;)\s+(?=" + _SUBJECT + r"\b)")


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:]


def _split_long(sentence: str, casual: bool, rng: random.Random) -> str | None:
    """Split one long sentence at a clause boundary near its middle, or None."""
    n = word_count(sentence)
    best = None
    for m in _SPLIT_RE.finditer(sentence):
        conj = (m.group(2) or ";").lower()
        if conj != ";" and conj != "and" and not casual:
            continue  # formal text: no sentence starting with "But"/"So"
        left, right = word_count(sentence[:m.start()]), word_count(sentence[m.end():])
        if left >= 6 and right >= 6:
            dist = abs(left - n / 2)
            if best is None or dist < best[0]:
                best = (dist, m, conj)
    if best is None:
        return None
    _, m, conj = best
    rest = sentence[m.end():]
    if conj in ("but", "so", "yet") or (conj == "and" and casual and rng.random() < 0.4):
        rest = conj + " " + rest
    return sentence[:m.start()] + ". " + _cap(rest)


# Stiff connectors -> natural ones with the same meaning (addition stays addition, contrast stays
# contrast). "But"/"So"/"Yet" take no comma. Casual modes use the first list, formal modes the second.
_TRANSITION_SWAPS: dict[str, tuple[list[str], list[str]]] = {
    "furthermore": (["On top of that,", "Plus,", "Also,", "What's more,"], ["Beyond this,", "Also,"]),
    "moreover": (["On top of that,", "Plus,", "What's more,"], ["Beyond this,", "Also,"]),
    "additionally": (["Also,", "Plus,", "On top of that,"], ["Also,", "Beyond this,"]),
    "in addition": (["Also,", "Plus,"], ["Also,", "Beyond this,"]),
    "however": (["That said,", "Still,", "But"], ["Even so,", "Yet"]),
    "nevertheless": (["Even so,", "Still,"], ["Even so,", "Still,"]),
    "nonetheless": (["Even so,", "Still,"], ["Even so,", "Still,"]),
    "consequently": (["So", "Because of that,"], ["As a result,", "For this reason,"]),
    "therefore": (["So", "Because of that,"], ["For this reason,", "As a result,"]),
    "thus": (["So"], ["As a result,"]),
    "similarly": (["In the same way,", "Likewise,"], ["Likewise,", "In the same way,"]),
}
_TRANSITION_SWAP_RE = re.compile(
    r"(^|[.!?][\"”’)\]]*\s+|\n\s*)(" + "|".join(k.replace(" ", r"\s") for k in _TRANSITION_SWAPS) + r"),\s+(\S)",
    re.IGNORECASE)
_THIS_RE = re.compile(
    r"([^.!?\n]{10,}?)\.\s+(?:This|That)\s+(shows|means|suggests|indicates|highlights|demonstrates|reflects|"
    r"explains|helps|allows|makes|leads|creates|is|was)\b")
_SUMMARY_START = re.compile(r"^(?:" + "|".join(o.replace(" ", r"\s") for o in _OPENERS) + r"),", re.IGNORECASE)


def _swap_transitions(text: str, src: str, casual: bool, rng: random.Random) -> tuple[str, int]:
    """Replace stiff sentence-opening connectors, never with the same one twice in a part."""
    used: set[str] = set()
    count = 0

    def sub(m: re.Match) -> str:
        nonlocal count
        key = re.sub(r"\s+", " ", m.group(2).lower())
        if key in src or rng.random() < 0.3:  # the author's own words, or leave some as they are
            return m.group(0)
        options = [o for o in _TRANSITION_SWAPS[key][0 if casual else 1] if o not in used]
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
    """"X. This shows Y." -> "X, which shows Y." when X is short enough to carry a clause."""
    count = 0

    def sub(m: re.Match) -> str:
        nonlocal count
        if word_count(m.group(1)) > 22 or m.group(1).rstrip().endswith((",", ";", ":")):
            return m.group(0)
        count += 1
        return m.group(1) + ", which " + m.group(2)

    return _THIS_RE.sub(sub, text, count=1), count  # once per part, or it becomes its own tic


def _drop_added_summary(text: str, source: str) -> tuple[str, int]:
    """Drop a closing "Overall, ..." sentence the model added (the source has no such sentence)."""
    out_sents, src_sents = split_sentences(text), split_sentences(source)
    if len(out_sents) <= len(src_sents) or len(out_sents) < 3 or not out_sents:
        return text, 0
    last = out_sents[-1]
    if not _SUMMARY_START.match(last) or any(_SUMMARY_START.match(s) for s in src_sents):
        return text, 0
    i = text.rfind(last)
    return text[:i].rstrip() + text[i + len(last):], 1


# Elliptical phrasing: drop words the reader fills in ("If it is possible" -> "If possible").
_ELLIPSES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(if|when|where|unless|whenever) it is (possible|necessary|needed|required|appropriate|available)\b",
                re.IGNORECASE), r"\1 \2"),
    (re.compile(r"\b(as) (?:it is|it was|was|is) (shown|mentioned|noted|described|discussed|expected)\b",
                re.IGNORECASE), r"\1 \2"),
    (re.compile(r"\b(when|if) (?:it is|they are) (compared|combined|used|applied) (with|to)\b", re.IGNORECASE),
     r"\1 \2 \3"),
    (re.compile(r"\bif you are able to\b", re.IGNORECASE), "if you can"),
    # reduced relative clause: "the method that was used" -> "the method used"
    (re.compile(r"(?<=[a-z]) that (?:is|are|was|were) ((?:[a-z]+ed|built|made|done|given|known|seen|shown|taken|written))\b"),
     r" \1"),
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
    return text[:m.start()] + f"{m.group(1)} ({m.group(2)} {m.group(3)}) " + text[m.end():], 1


def _standalone_takeaway(text: str, source: str, rng: random.Random) -> tuple[str, int]:
    """Move a short closing sentence of a long paragraph onto its own line (once per part)."""
    sep = "\n\n" if "\n\n" in source or "\n" not in source else "\n"
    paragraphs = text.split("\n\n") if sep == "\n\n" else text.split("\n")
    for i, para in enumerate(paragraphs):
        sents = split_sentences(para)
        if len(sents) >= 4 and 3 <= word_count(sents[-1]) <= 14 and rng.random() < 0.5:
            cut = para.rfind(sents[-1])
            if cut > 0:
                paragraphs[i] = para[:cut].rstrip() + sep + para[cut:]
                return sep.join(paragraphs), 1
    return text, 0


def longest_sentence(raw: str, min_words: int) -> tuple[int, int] | None:
    """Span of the longest sentence with at least ``min_words`` words."""
    spans = [s for s in sentence_spans(raw) if word_count(raw[s[0]:s[1]]) >= min_words]
    return max(spans, key=lambda s: word_count(raw[s[0]:s[1]])) if spans else None


def repeated_opener(raw: str) -> tuple[int, int] | None:
    """The second of two consecutive sentences that start with the same word, if any."""
    spans = sentence_spans(raw)
    firsts = [(WORD_RE.findall(raw[a:b]) or [""])[0].lower() for a, b in spans]
    for i in range(1, len(spans)):
        if firsts[i] and firsts[i] == firsts[i - 1] and word_count(raw[spans[i][0]:spans[i][1]]) >= 5:
            return spans[i]
    return None


def restructure(text: str, source: str, mode: str, rng: random.Random) -> tuple[str, int]:
    """Meaning-preserving edits against the structures detectors flag. Returns (text, edits)."""
    edits = 0
    src = source.lower()
    casual = mode in CASUAL_MODES

    def opener(m: re.Match) -> str:
        nonlocal edits
        if m.group(2).lower() in src:
            return m.group(0)  # the author wrote it
        edits += 1
        return m.group(1) + _cap(m.group(3))

    text, n = _drop_added_summary(text, source)
    edits += n
    text = _OPENER_RE.sub(opener, text)

    if "—" not in source:
        # Em dashes are a well-known AI tell (the logit bias misses ones merged into other tokens).
        # Casual modes may keep one per part; used that sparingly, it reads human.
        kept = 0 if casual and rng.random() < 0.5 else 1

        def dash(m: re.Match) -> str:
            nonlocal kept, edits
            if kept == 0:
                kept = 1
                return "—"
            edits += 1
            return ", "

        text = _EM_DASH_RE.sub(dash, text)

    if "not only" not in src:
        text, n = _NOT_ONLY_RE.subn(r"\1 and", text)
        edits += n

    text, n = _swap_transitions(text, src, casual, rng)
    edits += n
    text, n = _merge_this_openers(text)
    edits += n
    text, n = _ellipsis(text, src)
    edits += n
    if casual:
        text, n = _parenthetical(text, rng)
        edits += n
    if mode == "creative":
        text, n = _standalone_takeaway(text, source, rng)
        edits += n

    if mode in ("fluent", "creative") or (casual and _HAS_CONTRACTION.search(source)):
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
            new = _split_long(s, casual, rng)
            if new and s in text:
                text = text.replace(s, new, 1)
                edits += 1
                budget -= 1
    return text, edits


# ---------------------------------------------------------------- style samples


def style_sample(mode: str) -> str:
    """Human writing to imitate: <mode>.txt or all.txt from the style folders, trimmed to fit the prompt."""
    for folder in style_dirs():
        for name in (f"{mode}.txt", "all.txt"):
            path = Path(folder) / name
            try:
                text = path.read_text(encoding="utf-8").strip()
            except OSError:
                continue
            if not text:
                continue
            if len(text) > STYLE_SAMPLE_CHARS:
                cut = text[:STYLE_SAMPLE_CHARS]
                end = max(cut.rfind("\n\n"), cut.rfind(". "))
                text = cut[: end + 1] if end > STYLE_SAMPLE_CHARS // 2 else cut
            return text.strip()
    return ""


def custom_avoid_words() -> dict[str, float]:
    """Extra words to discourage, one per line in avoid.txt in a style folder ("word" or "word -20")."""
    words: dict[str, float] = {}
    for folder in style_dirs():
        try:
            lines = (Path(folder) / "avoid.txt").read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            parts = line.split("#")[0].split()
            if not parts:
                continue
            try:
                value = float(parts[1]) if len(parts) > 1 else -6.0
            except ValueError:
                value = -6.0
            words.setdefault(parts[0].lower(), max(-100.0, min(0.0, value)))
    return words


# ---------------------------------------------------------------- preference data for fine-tuning

_log_lock = threading.Lock()


def record_preference(system: str, user: str, chosen: str, rejected: str, scores: dict) -> None:
    """Append a (prompt, chosen, rejected) pair to $MERO_COLLECT_PREFS (JSON lines) for DPO training."""
    path = os.environ.get("MERO_COLLECT_PREFS")
    if not path or chosen.strip() == rejected.strip():
        return
    row = {"system": system, "prompt": user, "chosen": chosen.strip(), "rejected": rejected.strip(), "scores": scores}
    try:
        with _log_lock, open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        pass  # collecting data must never break paraphrasing
