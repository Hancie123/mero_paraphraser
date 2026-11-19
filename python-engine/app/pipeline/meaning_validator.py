"""Layer 6: meaning validation - factual consistency.

Checks each part's rewrite against what Layer 3 extracted: numbers, names,
negations, hedges and length must stay consistent. A part that fails is
rewritten once more.
"""

from __future__ import annotations

import re

from ..core.config import LENGTH
from ..schemas.paraphrase import ChunkResult, Facts
from ..utils.text_utils import word_count
from .semantic_analyzer import HEDGE_RE, NEGATION_RE, NUMBER_WORDS, numbers_in


def check_facts(source: str, output: str, facts: Facts) -> list[str]:
    issues: list[str] = []
    out_numbers = set(numbers_in(output))
    out_lower = output.lower()
    words_as_numbers = {NUMBER_WORDS[w] for w in re.findall(r"[a-z]+", out_lower) if w in NUMBER_WORDS}
    missing = [n for n in facts.numbers if n not in out_numbers and n not in words_as_numbers]
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
            "issues": [f"Part {c.index}: {i}" for c in parts for i in c.issues],
        }
