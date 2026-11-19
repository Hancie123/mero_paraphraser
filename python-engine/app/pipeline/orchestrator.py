"""Runs the eight layers in order.

    1 Input processing        clean, split off references, protect citations/quotes/links
    2 Context analysis        register, names, key terms, logical relationships
    3 Semantic understanding  numbers, names, negations, hedges to preserve
    4 Rewriting               rewrite each part with the rule-based engine (Humanize)
    4b Sentence rewriting     move clauses, active/passive, "make a decision" -> "decide"...
    5 Language refinement     grammar, spacing, articles, stock phrases
    6 Meaning validation      numbers, names, negations, hedges and length still match
    7 Citation validation     every protected span back exactly once; no invented citations
    8 Final output            highlighted changes, per-layer report, explanations

Layers 4-7 run per part so a part that fails validation can be rewritten
again with new wording; if it still fails on citations it is kept unchanged.

Layer 4 writes several drafts per part. Each goes through Layer 5 and the
checks, then the drafts are ranked by problems found and by how human they
read (humanizer.human_score), and the best one is kept.

``strength`` sets how many words Layer 4 changes; ``restructure`` sets how many
sentences Layer 4b reshapes (sentence_rewriter.py).
"""

from __future__ import annotations

import os
import random
import sys
import time
from dataclasses import dataclass

from ..core.config import MAX_ATTEMPTS, drafts_for
from ..core.preferences import Preferences
from ..schemas.paraphrase import ChunkResult, ParaphraseRequest
from ..utils.document_utils import chunk_text
from .citation_validator import CitationValidator, check_tokens
from .code_guard import rewrite_block
from .context_analyzer import ContextAnalyzer
from .humanizer import HumanScore, human_score
from .input_processor import InputProcessor, restore
from .language_refiner import LanguageRefiner
from .meaning_validator import MeaningValidator, check_facts, meaning_lost, restore_sentences
from .output_formatter import OutputFormatter
from .rewriting_engine import RewritingEngine
from .semantic_analyzer import SemanticAnalyzer, facts_for
from .sentence_rewriter import reshape

# Each text part and code block gets its own seed, derived from the request seed, so
# parts don't all pick the same wording while one seed still reproduces the whole
# result. The strides are arbitrary; changing them changes the output for a given seed.
PART_SEED_STRIDE = 7
CODE_BLOCK_SEED_STRIDE = 31


def _derive_seed(seed: int | None, index: int, stride: int) -> int | None:
    return None if seed is None else seed + index * stride


_PROFILE = bool(os.environ.get("MERO_PROFILE"))  # per-part timing on stderr


@dataclass
class _Trial:
    result: ChunkResult
    score: HumanScore

    @property
    def rank(self) -> tuple:
        """Smaller is better: fewer critical problems, fewer issues, more human."""
        r = self.result
        return (int(r.critical), len(r.issues), -self.score.total)


class ParaphrasePipeline:
    def __init__(self):
        self.input_processor = InputProcessor()
        self.context_analyzer = ContextAnalyzer()
        self.semantic_analyzer = SemanticAnalyzer()
        self.rewriting_engine = RewritingEngine()
        self.language_refiner = LanguageRefiner()
        self.meaning_validator = MeaningValidator()
        self.citation_validator = CitationValidator()
        self.output_formatter = OutputFormatter()

    def process(self, request: ParaphraseRequest) -> dict:
        mode, strength, seed, prefs = request.mode, request.strength, request.seed, request.prefs
        restructure = request.restructure

        # Layer 1
        processed = self.input_processor.process(request.text, prefs)
        # Layer 2
        context = self.context_analyzer.analyze(processed)
        # Layer 3
        facts = self.semantic_analyzer.analyze(processed, context)

        # Layers 4-7, part by part
        chunks: list[ChunkResult] = []
        for i, (piece, rewrite) in enumerate(chunk_text(processed.masked)):
            chunk = ChunkResult(
                index=sum(1 for c in chunks if c.rewrite) + 1, source=piece, output=piece, rewrite=rewrite
            )
            if rewrite:
                started = time.perf_counter()
                self._rewrite_part(
                    chunk, strength, context, _derive_seed(seed, i, PART_SEED_STRIDE), prefs, restructure=restructure
                )
                if _PROFILE:
                    print(
                        f"[mero] part {chunk.index}: {len(piece)} chars, {chunk.attempts} attempt(s), "
                        f"{time.perf_counter() - started:.1f}s",
                        file=sys.stderr,
                        flush=True,
                    )
            chunks.append(chunk)

        # Code blocks: reword comments only; code_guard verifies the code is byte-identical.
        code = {"blocks": 0, "comments": 0, "rewritten": 0, "untouched": 0}
        for p in processed.protected:
            if p.kind != "codeblock":
                continue
            code["blocks"] += 1
            res = rewrite_block(p.text, p.lang, strength, _derive_seed(seed, p.index, CODE_BLOCK_SEED_STRIDE), prefs)
            code["comments"] += res.comments
            code["rewritten"] += res.rewritten
            if res.lang is None:
                code["untouched"] += 1
            if res.text != p.text:
                p.replacement = res.text

        final = restore("".join(c.output for c in chunks), processed.protected) + processed.references
        meaning = self.meaning_validator.summary(chunks)
        # Layer 7 (whole text)
        citations = self.citation_validator.validate(processed, final)
        # Layer 8
        return self.output_formatter.format(
            processed,
            final,
            chunks,
            context,
            facts,
            meaning,
            citations,
            mode=mode,
            strength=strength,
            restructure=restructure,
            code=code,
            prefs=prefs,
        )

    def _rewrite_part(
        self, chunk: ChunkResult, strength: int, context, seed: int | None, prefs: Preferences, *, restructure: int = 0
    ) -> None:
        facts = facts_for(chunk.source, context)
        n = drafts_for(strength)
        best: _Trial | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            attempt_seed = None if seed is None else seed + attempt - 1
            # Layer 4: several drafts
            drafts = self.rewriting_engine.drafts(chunk.source, strength, attempt_seed, attempt > 1, n, prefs)
            # Layers 5-7 per draft, then keep the best. Ties go to the later attempt.
            for k, raw in enumerate(drafts):
                # Layer 4b: reshape some sentences. Each draft gets its own seed so drafts differ.
                rng = random.Random(None if attempt_seed is None else attempt_seed * 1009 + k)
                shaped = reshape(raw, restructure, rng, context.names, prefs.locked)
                trial = self._trial(
                    chunk, shaped.text, facts, context.register == "academic", attempt, attempt_seed, prefs
                )
                trial.result.reshaped = shaped.count
                if best is None or trial.rank <= best.rank:
                    best = trial
            if not best.result.issues:
                break

        winner = best.result
        chunk.output, chunk.fixes, chunk.phrases = winner.output, winner.fixes, winner.phrases
        chunk.dashes = winner.dashes
        chunk.issues, chunk.critical = winner.issues, winner.critical
        chunk.drafts, chunk.human_score, chunk.patterns = n, winner.human_score, winner.patterns
        chunk.restructured = winner.restructured
        chunk.reshaped = winner.reshaped
        chunk.attempts = attempt
        if not winner.critical:
            # A lost number, negation or hedge changes the meaning: those sentences keep their original.
            repaired = restore_sentences(chunk.source, chunk.output)
            if repaired and repaired[1]:
                chunk.output, chunk.restored_sentences = repaired
                token_issues, critical = check_tokens(chunk.source, chunk.output)
                chunk.critical = critical
                chunk.issues = token_issues if critical else check_facts(chunk.source, chunk.output, facts)
            elif repaired is None and meaning_lost(chunk.source, chunk.output):
                chunk.critical = True  # sentences don't line up, so keep the whole part
        if chunk.critical:  # citations or meaning couldn't be preserved: never ship a broken part
            chunk.output, chunk.kept_original, chunk.fixes, chunk.phrases = chunk.source, True, 0, 0
            chunk.dashes = 0
            chunk.restructured = 0
            chunk.reshaped = 0
            chunk.restored_sentences = 0

    def _trial(
        self, chunk: ChunkResult, raw: str, facts, academic: bool, attempt: int, seed: int | None, prefs: Preferences
    ) -> _Trial:
        """Layer 5, then the Layer 7 token check and the Layer 6 fact checks."""
        refined = self.language_refiner.refine(raw, chunk.source, seed, humanize=True, academic=academic, prefs=prefs)
        result = ChunkResult(chunk.index, chunk.source, refined.text, True, attempt, refined.fixes, refined.phrases)
        result.restructured = refined.restructured
        result.dashes = refined.dashes
        token_issues, critical = check_tokens(chunk.source, result.output)
        result.issues = token_issues if critical else check_facts(chunk.source, result.output, facts)
        result.critical = critical
        score = human_score(result.output)
        result.human_score, result.patterns = score.total, score.patterns
        return _Trial(result, score)
