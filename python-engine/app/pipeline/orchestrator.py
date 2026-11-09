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
"""

from __future__ import annotations

from ..core.config import MAX_ATTEMPTS
from ..core.model_manager import ModelManager
from ..schemas.paraphrase import ChunkResult, ParaphraseRequest
from ..utils.document_utils import chunk_text
from .citation_validator import CitationValidator, check_tokens
from .context_analyzer import ContextAnalyzer
from .input_processor import InputProcessor, restore
from .language_refiner import LanguageRefiner
from .meaning_validator import MeaningValidator
from .output_formatter import OutputFormatter
from .rewriting_engine import RewritingEngine
from .semantic_analyzer import SemanticAnalyzer, facts_for


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
        best: tuple[tuple[int, int, int], ChunkResult] | None = None
        feedback: list[str] | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            # Layer 4
            attempt_seed = None if seed is None else seed + attempt - 1
            raw = self.rewriting_engine.rewrite(chunk.source, mode, strength, context, facts, attempt_seed, feedback)
            # Layer 5
            refined = self.language_refiner.refine(raw, chunk.source)
            trial = ChunkResult(chunk.index, chunk.source, refined.text, True, attempt, refined.fixes, refined.phrases)
            # Layer 7 (tokens) then Layer 6
            token_issues, critical = check_tokens(chunk.source, trial.output)
            check = self.meaning_validator.check(trial, facts, mode) if not critical else None
            trial.issues = token_issues + (check.issues if check else [])
            trial.critical = critical
            trial.meaning_score = check.score if check else None

            # Fewer critical problems, then fewer issues, then a better meaning score.
            # Ties go to the later attempt, which had the feedback.
            rank = (int(critical), len(trial.issues), -(trial.meaning_score or 0))
            if best is None or rank <= best[0]:
                best = (rank, trial)
            if not trial.issues:
                break
            feedback = trial.issues

        _, winner = best
        chunk.output, chunk.fixes, chunk.phrases = winner.output, winner.fixes, winner.phrases
        chunk.issues, chunk.critical, chunk.meaning_score = winner.issues, winner.critical, winner.meaning_score
        chunk.attempts = attempt
        if winner.critical:  # citations couldn't be preserved: never ship a broken part
            chunk.output, chunk.kept_original, chunk.fixes, chunk.phrases = chunk.source, True, 0, 0
