"""Runs the eight layers in order.

    1 Input processing        clean, split off references, protect citations/quotes/links
    2 Context analysis        register, names, key terms, logical relationships
    3 Semantic understanding  numbers, names, negations, hedges to preserve
    4 AI rewriting            rewrite each part with the local model (or rule-based fallback)
    5 Language refinement     grammar, spacing, articles, stock phrases
    6 Meaning validation      fact checks + the model's meaning score
    7 Citation validation     every protected span back exactly once; no invented citations
    8 Final output            highlighted changes, per-layer report, explanations

Layers 4-7 run per part so a part that fails validation can be rewritten
again with feedback; if it still fails on citations it is kept unchanged.

To read as human-written, Layer 4 writes several drafts at once. Each goes
through Layer 5 and the cheap checks (tokens, facts), then the drafts are
ranked by how human they score (humanizer.human_score). The best one gets its
flattest sentence rewritten and a few predictable words swapped, and only then
faces the model's meaning check, which is the slow part.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from ..core.config import MAX_ATTEMPTS, drafts_for
from ..core.model_manager import ModelManager
from ..schemas.paraphrase import ChunkResult, ParaphraseRequest
from ..utils.document_utils import chunk_text
from .citation_validator import CitationValidator, check_tokens
from .context_analyzer import ContextAnalyzer
from .humanizer import (
    HumanScore, Tokens, flattest_sentence, human_score, longest_sentence, record_preference, repeated_opener,
    sentence_spans, splice_tokens, swap_predictable,
)
from .input_processor import InputProcessor, restore
from .language_refiner import LanguageRefiner
from .meaning_validator import MeaningValidator, check_facts
from .output_formatter import OutputFormatter
from .rewriting_engine import RewritingEngine, prompt
from .semantic_analyzer import SemanticAnalyzer, facts_for

MAX_JUDGED = 2  # drafts the model's meaning check may look at per attempt


@dataclass
class _Trial:
    result: ChunkResult
    raw: str  # the draft before Layer 5
    tokens: Tokens  # its token probabilities (empty with the rule-based engine)
    score: HumanScore
    prompt: str = ""
    judged: bool = False

    @property
    def rank(self) -> tuple:
        """Smaller is better: fewer critical problems, fewer issues, a better meaning score, more human."""
        r = self.result
        return (int(r.critical), len(r.issues), -(r.meaning_score or 0), -self.score.total)


class ParaphrasePipeline:
    def __init__(self, model_manager: ModelManager, use_ai: bool = True):
        self.input_processor = InputProcessor()
        self.context_analyzer = ContextAnalyzer()
        self.semantic_analyzer = SemanticAnalyzer()
        self.rewriting_engine = RewritingEngine(model_manager, use_ai)
        self.language_refiner = LanguageRefiner()
        self.meaning_validator = MeaningValidator(model_manager if self.rewriting_engine.use_ai else None)
        self.citation_validator = CitationValidator()
        self.output_formatter = OutputFormatter()

    def process(self, request: ParaphraseRequest) -> dict:
        mode, strength, seed = request.mode, request.strength, request.seed

        # Layer 1
        processed = self.input_processor.process(request.text)
        # Layer 2
        context = self.context_analyzer.analyze(processed)
        # Layer 3
        facts = self.semantic_analyzer.analyze(processed, context)

        # Layers 4-7, part by part
        chunks: list[ChunkResult] = []
        for i, (piece, rewrite) in enumerate(chunk_text(processed.masked)):
            chunk = ChunkResult(index=sum(1 for c in chunks if c.rewrite) + 1, source=piece, output=piece, rewrite=rewrite)
            if rewrite:
                self._rewrite_part(chunk, mode, strength, context, None if seed is None else seed + i * 7)
            chunks.append(chunk)

        final = restore("".join(c.output for c in chunks), processed.protected) + processed.references
        meaning = self.meaning_validator.summary(chunks)
        # Layer 7 (whole text)
        citations = self.citation_validator.validate(processed, final)
        # Layer 8
        return self.output_formatter.format(
            processed, final, chunks, context, facts, meaning, citations,
            engine=self.rewriting_engine.name, mode=mode, strength=strength,
        )

    def _rewrite_part(self, chunk: ChunkResult, mode: str, strength: int, context, seed: int | None) -> None:
        facts = facts_for(chunk.source, context)
        keep = {w.lower() for item in [*facts.names, *context.terms] for w in item.split()}
        n = drafts_for(strength)
        best: _Trial | None = None
        feedback: list[str] | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            attempt_seed = None if seed is None else seed + attempt - 1
            # Layer 4: several drafts at once
            drafts = self.rewriting_engine.drafts(chunk.source, mode, strength, context, facts, attempt_seed, feedback, n)
            # Layer 5 + cheap Layer 7/6 checks, then rank by how human each one reads
            trials = [self._trial(chunk, d.text, d.tokens, facts, mode, attempt, attempt_seed, d.prompt) for d in drafts]
            trials.sort(key=lambda t: t.rank)
            if not trials[0].result.issues:
                trials[0] = self._polish(trials[0], chunk, facts, keep, mode, strength, attempt, attempt_seed)

            # Layer 6 meaning check, best draft first
            winner = None
            judged = 0
            for t in trials:
                if t.result.issues:
                    continue
                if judged == MAX_JUDGED:
                    break
                self._judge(t, facts, mode)
                judged += 1
                if not t.result.issues:
                    winner = t
                    break

            # Only fully checked drafts can be shipped. Ties go to the later attempt, which had the feedback.
            for t in trials:
                if (t.judged or t.result.issues) and (best is None or t.rank <= best.rank):
                    best = t
            if winner is not None:
                if len(trials) > 1:
                    worst = min((t for t in trials if t is not winner), key=lambda t: t.score.total)
                    record_preference(prompt("system.txt"), winner.prompt, winner.result.output, worst.raw,
                                      {"chosen": winner.score.total, "rejected": worst.score.total, "mode": mode})
                break
            feedback = trials[0].result.issues

        winner = best.result
        chunk.output, chunk.fixes, chunk.phrases = winner.output, winner.fixes, winner.phrases
        chunk.issues, chunk.critical, chunk.meaning_score = winner.issues, winner.critical, winner.meaning_score
        chunk.drafts, chunk.human_score, chunk.patterns = n, winner.human_score, winner.patterns
        chunk.restructured, chunk.swaps, chunk.sentence_rewrites = winner.restructured, winner.swaps, winner.sentence_rewrites
        chunk.attempts = attempt
        if winner.critical:  # citations couldn't be preserved: never ship a broken part
            chunk.output, chunk.kept_original, chunk.fixes, chunk.phrases = chunk.source, True, 0, 0
            chunk.restructured = chunk.swaps = chunk.sentence_rewrites = 0

    def _trial(self, chunk: ChunkResult, raw: str, tokens: Tokens, facts, mode: str, attempt: int,
               seed: int | None, user_prompt: str = "") -> _Trial:
        """Layer 5, then the checks that need no model call (Layer 7 tokens, Layer 6 facts)."""
        refined = self.language_refiner.refine(raw, chunk.source, mode, seed)
        result = ChunkResult(chunk.index, chunk.source, refined.text, True, attempt, refined.fixes, refined.phrases)
        result.restructured = refined.restructured
        token_issues, critical = check_tokens(chunk.source, result.output)
        result.issues = token_issues if critical else check_facts(chunk.source, result.output, facts, mode)
        result.critical = critical
        score = human_score(result.output, raw, tokens)
        result.human_score, result.patterns = score.total, score.patterns
        return _Trial(result, raw, tokens, score, user_prompt)

    def _judge(self, trial: _Trial, facts, mode: str) -> None:
        check = self.meaning_validator.check(trial.result, facts, mode)
        trial.result.issues, trial.result.meaning_score = check.issues, check.score
        trial.judged = True

    def _polish(self, trial: _Trial, chunk: ChunkResult, facts, keep: set[str], mode: str, strength: int,
                attempt: int, seed: int | None) -> _Trial:
        """Rewrite one sentence (a repeated opener or the flattest) and swap a few predictable words; keep the draft if that breaks a check."""
        raw, tokens = trial.raw, trial.tokens
        if not tokens:
            return trial
        rewrites, skip = 0, None
        # A sentence that opens like the one before it comes first, then the most predictable one.
        # When every sentence is about as long as the next, the target is split into a short and a long one.
        even = trial.score.burstiness < 0.3 and len(sentence_spans(raw)) >= 3
        flat = repeated_opener(raw) or (flattest_sentence(raw, tokens) if strength >= 34 else None)
        if even and not flat:
            flat = longest_sentence(raw, 14)
        if flat:
            new = self.rewriting_engine.rewrite_sentence(raw, flat[0], flat[1], mode, strength, seed,
                                                         vary_length=even)
            if new:
                raw = raw[:flat[0]] + new + raw[flat[1]:]
                tokens = splice_tokens(tokens, flat[0], flat[1], len(new))
                rewrites, skip = 1, (flat[0], flat[0] + len(new))
        formal = mode in ("academic", "professional")
        raw, tokens, swaps = swap_predictable(raw, tokens, keep, strength, formal, random.Random(seed), skip)
        if not (rewrites or swaps):
            return trial
        polished = self._trial(chunk, raw, tokens, facts, mode, attempt, seed, trial.prompt)
        if polished.result.issues:
            return trial
        polished.result.swaps, polished.result.sentence_rewrites = swaps, rewrites
        return polished
