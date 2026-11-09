"""Layer 8: final output - revised text, highlighted changes and explanations.

Diffs the final text against the original word by word so the UI can
highlight each change (with its kind and alternatives), and turns what every
layer found into a short report and plain-language explanations.
"""

from __future__ import annotations

import difflib

from ..core import lexicon as lx
from ..core.config import MODEL_NAME, MODES
from ..schemas.paraphrase import ChunkResult, Context, Facts, LayerReport, ProcessedInput
from ..utils.text_utils import (
    WORD_RE,
    avg_sentence_length,
    match_case,
    reading_ease,
    split_sentences,
    tokens,
    word_count,
)

LAYER_NAMES = [
    ("input", "Input processing"),
    ("context", "Context analysis"),
    ("semantic", "Semantic understanding"),
    ("rewrite", "AI rewriting"),
    ("refine", "Language refinement"),
    ("meaning", "Meaning validation"),
    ("citations", "Citation validation"),
    ("output", "Final output"),
]


def change_kind(text: str, original: str) -> str:
    if not original:
        return "Added"
    if text.lower() == original.lower():
        return "Capitalization"
    new_words, old_words = WORD_RE.findall(text), WORD_RE.findall(original)
    if len(new_words) == 1 and len(old_words) == 1 and text.lower() in (lx.suggestions_for(original.lower()) or []):
        return "Synonym"
    if len(new_words) < len(old_words):
        return "Shortened"
    if len(new_words) > len(old_words) + 1:
        return "Expanded"
    return "Reworded"


def alternatives(text: str, original: str) -> list[str]:
    alts: list[str] = []
    if WORD_RE.fullmatch(text):
        for alt in lx.suggestions_for(text.lower()) or []:
            alt = match_case(text, alt)
            if alt != text and alt not in alts:
                alts.append(alt)
    if original and original != text and original not in alts:
        alts.append(original)  # always offer "go back to the original"
    return alts[:8]


def diff_segments(source: str, output: str) -> tuple[list[dict], int, int]:
    """Returns (segments, number of changes, number of source words changed)."""
    a, b = tokens(source), tokens(output)
    sm = difflib.SequenceMatcher(None, [t.strip() for t in a], [t.strip() for t in b], autojunk=False)
    segments: list[dict] = []

    def plain(text: str) -> None:
        if not text:
            return
        if segments and "original" not in segments[-1]:
            segments[-1]["text"] += text
        else:
            segments.append({"text": text})

    changes = changed_words = 0
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            plain("".join(b[j1:j2]))
            continue
        orig = "".join(a[i1:i2])
        changed_words += len(WORD_RE.findall(orig))
        if op == "delete":
            continue
        new = "".join(b[j1:j2])
        core = new.rstrip()
        if not core:  # only whitespace changed
            plain(new)
            continue
        changes += 1
        orig_core = orig.strip()
        segments.append({
            "text": core,
            "original": orig_core,
            "kind": change_kind(core, orig_core),
            "alternatives": alternatives(core, orig_core),
        })
        plain(new[len(core):])
    return segments, changes, changed_words


def _n(n: int, word: str, plural: str | None = None) -> str:
    return f"{n} {word if n == 1 else plural or word + 's'}"


def _strength_label(strength: int) -> str:
    return "light" if strength < 34 else "moderate" if strength < 67 else "strong"


def _list(items: list[str], limit: int = 4) -> str:
    items = items[:limit]
    return ", ".join(items[:-1]) + (" and " if len(items) > 1 else "") + items[-1] if items else ""


class OutputFormatter:
    def format(
        self,
        processed: ProcessedInput,
        final_text: str,
        chunks: list[ChunkResult],
        context: Context,
        facts: Facts,
        meaning: dict,
        citations: dict,
        *,
        engine: str,
        mode: str,
        strength: int,
    ) -> dict:
        source = processed.original
        segments, changes, changed_words = diff_segments(source, final_text)
        words_in = word_count(source)
        words_out = word_count(final_text)
        fixes = sum(c.fixes for c in chunks)
        phrases = sum(c.phrases for c in chunks)
        rewritten = [c for c in chunks if c.rewrite]
        restructured = sum(c.restructured for c in rewritten)
        swaps = sum(c.swaps for c in rewritten)
        sentence_rewrites = sum(c.sentence_rewrites for c in rewritten)
        human_scores = [c.human_score for c in rewritten if c.human_score is not None and not c.kept_original]
        patterns = sorted({p for c in rewritten if not c.kept_original for p in c.patterns})
        drafts = max((c.drafts for c in rewritten), default=0)
        protected_parts = []
        if citations["citations"]:
            protected_parts.append(f"{citations['citations']} citation{'s' * (citations['citations'] != 1)}")
        if citations["quotes"]:
            protected_parts.append(f"{citations['quotes']} quotation{'s' * (citations['quotes'] != 1)}")
        if citations["links"]:
            protected_parts.append(f"{citations['links']} link{'s' * (citations['links'] != 1)}")

        # ---- per-layer report
        layers: list[LayerReport] = []

        def add(i: int, status: str, detail: str) -> None:
            layers.append(LayerReport(LAYER_NAMES[i][0], LAYER_NAMES[i][1], status, detail))

        detail = f"{_n(processed.paragraphs, 'paragraph')}, {_n(processed.sentences, 'sentence')}, {_n(processed.words, 'word')}"
        if protected_parts:
            detail += "; protected " + _list(protected_parts)
        if processed.references:
            detail += "; reference list set aside"
        add(0, "ok", detail + ".")

        detail = f"{context.register.capitalize()} writing"
        if context.terms:
            detail += "; key terms: " + _list(context.terms, 5)
        if context.relationships:
            detail += "; relationships: " + _list(context.relationships, 4)
        add(1, "ok", detail + ".")

        tracked = []
        if facts.numbers:
            tracked.append(f"{len(facts.numbers)} number{'s' * (len(facts.numbers) != 1)}")
        if facts.names:
            tracked.append(f"{len(facts.names)} name{'s' * (len(facts.names) != 1)} and terms")
        if facts.negations:
            tracked.append(f"{facts.negations} negation{'s' * (facts.negations != 1)}")
        if facts.hedges:
            tracked.append(f"{facts.hedges} hedge{'s' * (facts.hedges != 1)}")
        claims = _n(facts.claims, "claim")
        add(2, "ok", (f"{claims}; tracking " + _list(tracked, 4) if tracked else claims) + ".")

        engine_name = MODEL_NAME if engine == "ai" else "the rule-based engine"
        detail = (f"Rewrote {len(rewritten)} part{'s' * (len(rewritten) != 1)} with {engine_name} in "
                  f"{MODES[mode].label} mode ({_strength_label(strength)} changes)")
        if drafts > 1:
            detail += f"; kept the most human-sounding of {drafts} drafts per part"
        if sentence_rewrites:
            detail += f"; rewrote {_n(sentence_rewrites, 'predictable sentence')}"
        if swaps:
            detail += f"; varied {_n(swaps, 'predictable word')}"
        if meaning["retried"]:
            detail += f"; {meaning['retried']} rewritten again after validation"
        add(3, "ok", detail + ".")

        detail = (f"{fixes} spacing, punctuation or grammar fix{'es' * (fixes != 1)}" if fixes else "No corrections needed")
        if phrases:
            detail += f"; replaced {phrases} overused phrase{'s' * (phrases != 1)}"
        if restructured:
            detail += f"; {_n(restructured, 'structural edit')} for a more natural rhythm"
        add(4, "ok", detail + ".")

        if meaning["issues"]:
            add(5, "warning", f"{meaning['passed']} of {meaning['parts']} parts passed. " + " ".join(meaning["issues"][:3]))
        else:
            detail = "Facts, numbers, names, negations and hedging preserved"
            if meaning["average_score"] is not None:
                detail += f"; meaning score {meaning['average_score']}/5"
            add(5, "ok", detail + ".")

        if not citations["ok"]:
            add(6, "warning", "Some protected text changed: " + _list(citations["missing"], 3) + ".")
        elif protected_parts or citations["references"]:
            kept = _list(protected_parts + (["the reference list"] if citations["references"] else []))
            add(6, "ok", f"Kept {kept} exactly as written.")
        else:
            add(6, "ok", "No citations, quotations or references to check.")

        pct = min(100, round(100 * changed_words / words_in)) if words_in else 0
        add(7, "ok", f"{changes} change{'s' * (changes != 1)} highlighted; {pct}% of words changed.")

        # ---- explanations
        explain: list[str] = []
        final_body = final_text[: len(final_text) - len(processed.references)] if processed.references else final_text
        n_in, n_out = len(split_sentences(processed.body)), len(split_sentences(final_body))
        if changes:
            explain.append(f"Reworded {changes} passage{'s' * (changes != 1)}, changing {pct}% of the words.")
        if n_in and n_out and n_in != n_out:
            how = "split long sentences" if n_out > n_in else "combined related sentences"
            explain.append(f"Restructured the text from {n_in} to {n_out} sentences ({how}).")
        a, b = avg_sentence_length(processed.body), avg_sentence_length(final_body)
        if a and b and abs(a - b) >= 2:
            explain.append(f"Average sentence length went from {a:.0f} to {b:.0f} words.")
        ea, eb = reading_ease(processed.body), reading_ease(final_body)
        if ea is not None and eb is not None and abs(ea - eb) >= 5:
            explain.append("The text is now easier to read." if eb > ea else "The wording is now more formal and dense.")
        if mode == "shorten" and words_in:
            explain.append(f"Shortened from {words_in} to {words_out} words ({round(100 * (words_in - words_out) / words_in)}% shorter).")
        if facts.numbers or facts.names:
            explain.append("Kept every number, name and technical term from the original.")
        if protected_parts or citations["references"]:
            explain.append("Citations, quotations and references were left exactly as written.")
        if phrases:
            explain.append(f"Replaced {phrases} overused AI-style phrase{'s' * (phrases != 1)} with plainer wording.")
        if drafts > 1 or restructured or swaps:
            explain.append("Chose less predictable wording and a more varied sentence rhythm, so the text reads more like a person wrote it.")
        if patterns:
            explain.append("Still reads a little machine-like here: " + _list(patterns, 3) + ".")
        if meaning["kept_original"]:
            explain.append(f"{meaning['kept_original']} part{'s' * (meaning['kept_original'] != 1)} kept unchanged because the rewrite didn't pass validation.")

        return {
            "text": final_text,
            "segments": segments,
            "stats": {
                "words_in": words_in,
                "words_out": words_out,
                "changes": changes,
                "change_pct": pct,
            },
            "engine": engine,
            "report": {
                "layers": [l.to_dict() for l in layers],
                "explanations": explain,
                "warnings": meaning["issues"] + ([] if citations["ok"] else ["Some citations or quotations changed."]),
                "register": context.register,
                "humanness": {
                    "score": round(sum(human_scores) / len(human_scores), 2) if human_scores else None,
                    "drafts": drafts,
                    "sentence_rewrites": sentence_rewrites,
                    "word_swaps": swaps,
                    "structural_edits": restructured,
                    "patterns": patterns,
                },
            },
        }
