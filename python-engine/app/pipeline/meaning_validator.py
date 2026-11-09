"""Layer 6: meaning validation - semantic similarity and factual consistency.

Two checks per part:
1. Facts (always): numbers, names, negations, hedges and length stay consistent
   with what Layer 3 extracted.
2. Meaning (with the AI model): the model compares the rewrite with the original
   and scores it 1-5. It only runs when the fact checks pass, to save time.
A part that fails is rewritten once more with the problems as feedback.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from ..core.config import MODES
from ..core.model_manager import ModelManager
from ..schemas.paraphrase import ChunkResult, Facts, ParaphraseError
from ..utils.text_utils import word_count
from .rewriting_engine import prompt
from .semantic_analyzer import HEDGE_RE, NEGATION_RE, NUMBER_WORDS, numbers_in

PASS_SCORE = 3  # meaning scores at or below this trigger a retry


@dataclass
class Check:
    issues: list[str] = field(default_factory=list)
    score: int | None = None

    @property
    def ok(self) -> bool:
        return not self.issues


def check_facts(source: str, output: str, facts: Facts, mode: str) -> list[str]:
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
    lo, hi = MODES[mode].length
    if n_in >= 8 and not (lo <= n_out / max(1, n_in) <= hi):
        issues.append(f"The length changed too much ({n_in} to {n_out} words).")
    return issues


def parse_judgement(reply: str) -> tuple[int | None, str]:
    """Returns (score 1-5, short description of the problems)."""
    m = re.search(r"\{.*\}", reply, re.DOTALL)
    try:
        data = json.loads(m.group() if m else reply)
    except ValueError:
        m = re.search(r"\b([1-5])\b", reply)
        return (int(m.group(1)) if m else None), ""
    problems = []
    for key, label in (("added", "Added"), ("missing", "Left out"), ("changed", "Changed")):
        items = [str(i).strip() for i in data.get(key) or [] if str(i).strip()]
        if items:
            problems.append(f"{label}: {'; '.join(items[:2])}.")
    try:
        score = max(1, min(5, int(data.get("score"))))
    except (TypeError, ValueError):
        score = None
    # Listed problems outweigh a generous score.
    if problems and (score is None or score > PASS_SCORE):
        score = PASS_SCORE
    return score, " ".join(problems)


class MeaningValidator:
    def __init__(self, model_manager: ModelManager | None):
        self.models = model_manager  # None: fact checks only (rule-based engine)

    def check(self, chunk: ChunkResult, facts: Facts, mode: str) -> Check:
        result = Check(check_facts(chunk.source, chunk.output, facts, mode))
        if result.ok and self.models is not None and chunk.output.strip() != chunk.source.strip():
            result.score, issue = self.judge(chunk.source, chunk.output)
            if result.score is not None and result.score <= PASS_SCORE:
                result.issues.append(issue or "The meaning changed.")
        return result

    def judge(self, original: str, rewrite: str) -> tuple[int | None, str]:
        try:
            reply = self.models.complete(
                prompt("judge.txt"),
                f"ORIGINAL:\n{original.strip()}\n\nREWRITE:\n{rewrite.strip()}",
                temperature=0.0,
                max_tokens=200,
                seed=0,
                json_mode=True,
            )
        except ParaphraseError:
            return None, ""
        return parse_judgement(reply)

    @staticmethod
    def summary(chunks: list[ChunkResult]) -> dict:
        parts = [c for c in chunks if c.rewrite]
        scores = [c.meaning_score for c in parts if c.meaning_score is not None]
        return {
            "parts": len(parts),
            "passed": sum(1 for c in parts if not c.issues),
            "average_score": round(sum(scores) / len(scores), 1) if scores else None,
            "retried": sum(1 for c in parts if c.attempts > 1),
            "kept_original": sum(1 for c in parts if c.kept_original),
            "issues": [f"Part {c.index}: {i}" for c in parts for i in c.issues],
        }
