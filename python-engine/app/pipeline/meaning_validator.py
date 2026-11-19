"""Layer 6: meaning validation - factual consistency.

Checks each part's rewrite against what Layer 3 extracted: numbers, names,
negations, hedges and length must stay consistent. A part that fails is
rewritten once more.

A dropped number, negation or hedge changes what the text claims, so the
winning draft is then repaired sentence by sentence (``restore_sentences``):
each sentence that lost one gets its original wording back. If the sentences
no longer line up, the whole part keeps its original text.
"""

from __future__ import annotations

import re

from ..core.config import LENGTH
from ..schemas.paraphrase import ChunkResult, Facts
from ..utils.text_utils import sentence_spans, word_count
from .semantic_analyzer import HEDGE_RE, NEGATION_RE, NUMBER_WORDS, numbers_in


def _missing_numbers(numbers: list[str], output: str) -> list[str]:
    out_numbers = set(numbers_in(output))
    words_as_numbers = {NUMBER_WORDS[w] for w in re.findall(r"[a-z]+", output.lower()) if w in NUMBER_WORDS}
    return [n for n in numbers if n not in out_numbers and n not in words_as_numbers]


def meaning_lost(source: str, output: str) -> bool:
    """True if ``output`` lost a number, a negation or a hedge that ``source`` has."""
    return bool(
        _missing_numbers(list(dict.fromkeys(numbers_in(source))), output)
        or len(NEGATION_RE.findall(output)) < len(NEGATION_RE.findall(source))
        or len(HEDGE_RE.findall(output)) < len(HEDGE_RE.findall(source))
    )


def restore_sentences(source: str, output: str) -> tuple[str, int] | None:
    """Put back the original of each sentence whose rewrite lost meaning.

    Returns the repaired text and how many sentences were restored, or None
    when source and output have different sentence counts (can't pair them).
    """
    src, out = sentence_spans(source), sentence_spans(output)
    if len(src) != len(out):
        return None
    text, restored = output, 0
    for (sa, sb), (oa, ob) in reversed(list(zip(src, out))):
        if meaning_lost(source[sa:sb], output[oa:ob]):
            text = text[:oa] + source[sa:sb] + text[ob:]
            restored += 1
    return text, restored


def check_facts(source: str, output: str, facts: Facts) -> list[str]:
    issues: list[str] = []
    missing = _missing_numbers(facts.numbers, output)
    if missing:
        issues.append(f"Numbers changed or missing: {', '.join(missing[:5])}.")

    lost = [n for n in facts.names if n not in output]
    if lost:
        issues.append(f"Names or terms changed: {', '.join(lost[:5])}.")

    if facts.negations and not NEGATION_RE.search(output):
        issues.append("A negation was dropped, which can reverse the meaning.")
    elif facts.negations >= 2 and len(NEGATION_RE.findall(output)) < facts.negations / 2:
        issues.append("Some negations were dropped.")

    if facts.hedges and not HEDGE_RE.search(output):
        issues.append("Hedging words were removed, so a claim now sounds more certain than in the original.")

    n_in, n_out = word_count(source), word_count(output)
    lo, hi = LENGTH
    if n_in >= 8 and not (lo <= n_out / max(1, n_in) <= hi):
        issues.append(f"The length changed too much ({n_in} to {n_out} words).")
    return issues


class MeaningValidator:
    @staticmethod
    def summary(chunks: list[ChunkResult]) -> dict:
        parts = [c for c in chunks if c.rewrite]
        return {
            "parts": len(parts),
            "passed": sum(1 for c in parts if not c.issues),
            "retried": sum(1 for c in parts if c.attempts > 1),
            "kept_original": sum(1 for c in parts if c.kept_original),
            "restored_sentences": sum(c.restored_sentences for c in parts if not c.kept_original),
            "issues": [f"Part {c.index}: {i}" for c in parts for i in c.issues],
        }
