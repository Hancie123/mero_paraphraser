"""Layer 8: final output - revised text, highlighted changes and explanations.

Diffs the final text against the original word by word so the UI can
highlight each change (with its kind and alternatives), and turns what every
layer found into a short report and plain-language explanations.
"""

from __future__ import annotations

import bisect
import difflib
import re
from dataclasses import dataclass

from ..core import lexicon as lx
from ..core.config import MODES
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
    ("rewrite", "Rewriting"),
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


_SENTENCE_MARKS = re.compile(r"[.!?;](?=\s|$)")


def change_level(text: str, original: str) -> str:
    """How big a change is, for colour-coded highlighting: word, phrase, sentence or added."""
    if not original:
        return "added"
    new_words, old_words = len(WORD_RE.findall(text)), len(WORD_RE.findall(original))
    # A sentence was split, joined or rebuilt: its end punctuation changed, or most of it was rewritten.
    if len(_SENTENCE_MARKS.findall(text)) != len(_SENTENCE_MARKS.findall(original)) or max(new_words, old_words) >= 8:
        return "sentence"
    if new_words <= 1 and old_words <= 1:
        return "word"
    return "phrase"


# Where a new sentence starts in the output: after end punctuation (and closing quotes) plus space, or a line break.
_SENTENCE_BREAK = re.compile(r"[.!?…][\"”’)\]]*\s+|\n+")


@dataclass
class _Piece:
    text: str  # output text
    orig: str  # the source text it replaces (equal to text when unchanged)
    changed: bool  # a visible change (deletions and whitespace-only edits are not)


def _pieces(source: str, output: str) -> tuple[list[_Piece], int]:
    """Token-level diff as pieces that join back to ``output`` (texts) and ``source`` (origs)."""
    a, b = tokens(source), tokens(output)
    sm = difflib.SequenceMatcher(None, [t.strip() for t in a], [t.strip() for t in b], autojunk=False)
    pieces: list[_Piece] = []
    changed_words = 0
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        new, orig = "".join(b[j1:j2]), "".join(a[i1:i2])
        if op == "equal":
            pieces.append(_Piece(new, orig, False))
            continue
        changed_words += len(WORD_RE.findall(orig))
        core = new.rstrip()
        if not core:  # a deletion, or only whitespace changed
            pieces.append(_Piece(new, orig, False))
            continue
        orig_core = orig.rstrip()
        pieces.append(_Piece(core, orig_core, True))
        if new[len(core) :] or orig[len(orig_core) :]:
            pieces.append(_Piece(new[len(core) :], orig[len(orig_core) :], False))
    return pieces, changed_words


def _sentence_spans(pieces: list[_Piece], output: str) -> list[tuple[int, int]]:
    """Output ranges of whole sentences that contain a sentence-level change."""
    bounds = sorted({0, len(output), *(m.end() for m in _SENTENCE_BREAK.finditer(output))})
    spans: list[list[int]] = []
    pos = 0
    for p in pieces:
        start, end = pos, pos + len(p.text)
        pos = end
        if p.changed and change_level(p.text, p.orig.strip()) == "sentence":
            s = bounds[bisect.bisect_right(bounds, start) - 1]
            e = bounds[bisect.bisect_left(bounds, end)]
            spans.append([s, e])
    # A piece that only partly overlaps a span (a change, or text whose source differs) joins it whole.
    changed = True
    while changed and spans:
        changed = False
        spans.sort()
        merged = [spans[0]]
        for s, e in spans[1:]:
            if s < merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], e)
            else:
                merged.append([s, e])
        spans = merged
        pos = 0
        for p in pieces:
            start, end = pos, pos + len(p.text)
            pos = end
            if not (p.changed or p.text != p.orig):
                continue
            for span in spans:
                if start < span[1] and end > span[0] and (start < span[0] or end > span[1]):
                    span[0], span[1] = min(span[0], start), max(span[1], end)
                    changed = True
    return [(s, e) for s, e in spans]


def diff_segments(source: str, output: str) -> tuple[list[dict], int, int]:
    """Returns (segments, number of changes, number of source words changed).

    Small changes are highlighted on their own. When a sentence was split, joined
    or largely rewritten, the whole new sentence is one highlighted segment whose
    ``original`` is the old sentence.
    """
    pieces, changed_words = _pieces(source, output)
    spans = _sentence_spans(pieces, output)
    segments: list[dict] = []

    def plain(text: str) -> None:
        if not text:
            return
        if segments and "original" not in segments[-1]:
            segments[-1]["text"] += text
        else:
            segments.append({"text": text})

    def change(text: str, orig: str, level: str | None = None, kind: str | None = None) -> None:
        core, orig_core = text.rstrip(), orig.strip()
        segments.append(
            {
                "text": core,
                "original": orig_core,
                "kind": kind or change_kind(core, orig_core),
                "level": level or change_level(core, orig_core),
                "alternatives": [orig_core] if level == "sentence" else alternatives(core, orig_core),
            }
        )
        plain(text[len(core) :])

    # Split unchanged pieces at span edges, so every piece is wholly inside or outside a span.
    edges = sorted({x for span in spans for x in span})
    placed: list[tuple[int, _Piece]] = []
    pos = 0
    for p in pieces:
        start = pos
        pos += len(p.text)
        if p.changed or p.text != p.orig:
            placed.append((start, p))
            continue
        prev = 0
        for cut in [x - start for x in edges if start < x < pos] + [len(p.text)]:
            placed.append((start + prev, _Piece(p.text[prev:cut], p.orig[prev:cut], False)))
            prev = cut

    current: int | None = None  # index of the span being collected
    span_text = span_orig = ""
    for start, p in placed:
        k = next((i for i, (s, e) in enumerate(spans) if s <= start < e), None)
        if k != current and current is not None:
            change(span_text, span_orig, "sentence", "Rewritten sentence")
            span_text = span_orig = ""
        current = k
        if k is not None:
            span_text += p.text
            span_orig += p.orig
        elif p.changed:
            change(p.text, p.orig)
        else:
            plain(p.text)
    if current is not None:
        change(span_text, span_orig, "sentence", "Rewritten sentence")
    changes = sum(1 for s in segments if "original" in s)
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
        mode: str,
        strength: int,
        code: dict | None = None,
    ) -> dict:
        code = code or {"blocks": 0, "comments": 0, "rewritten": 0, "untouched": 0}
        source = processed.original
        segments, changes, changed_words = diff_segments(source, final_text)
        words_in = word_count(source)
        words_out = word_count(final_text)
        fixes = sum(c.fixes for c in chunks)
        phrases = sum(c.phrases for c in chunks)
        dashes = sum(c.dashes for c in chunks)
        blocks = citations.get("blocks", {})
        locked_sections = [name for name, locked in processed.sections if locked]
        prose_sections = [name for name, locked in processed.sections if not locked]
        rewritten = [c for c in chunks if c.rewrite]
        restructured = sum(c.restructured for c in rewritten)
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
        if blocks.get("codeblock"):
            protected_parts.append(_n(blocks["codeblock"], "code block"))
        if blocks.get("data"):
            protected_parts.append(_n(blocks["data"], "table"))
        if processed.count("math"):
            protected_parts.append(_n(processed.count("math"), "equation"))
        if locked_sections or blocks.get("locked"):
            protected_parts.append(_n(max(len(locked_sections), blocks.get("locked", 0)), "locked section"))

        # ---- per-layer report
        layers: list[LayerReport] = []

        def add(i: int, status: str, detail: str) -> None:
            layers.append(LayerReport(LAYER_NAMES[i][0], LAYER_NAMES[i][1], status, detail))

        detail = f"{_n(processed.paragraphs, 'paragraph')}, {_n(processed.sentences, 'sentence')}, {_n(processed.words, 'word')}"
        if protected_parts:
            detail += "; protected " + _list(protected_parts)
        if processed.references:
            detail += "; reference list set aside"
        if processed.invisible:
            detail += f"; removed {_n(processed.invisible, 'invisible character')}"
        add(0, "ok", detail + ".")

        detail = f"{context.register.capitalize()} writing"
        if context.terms:
            detail += "; key terms: " + _list(context.terms, 5)
        if context.relationships:
            detail += "; relationships: " + _list(context.relationships, 4)
        if prose_sections:
            detail += "; sections rewritten: " + _list(prose_sections, 6)
        if locked_sections:
            detail += "; kept as written: " + _list(locked_sections, 6)
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

        detail = (
            f"Rewrote {len(rewritten)} part{'s' * (len(rewritten) != 1)} in "
            f"{MODES[mode]} mode ({_strength_label(strength)} changes)"
        )
        if drafts > 1:
            detail += f"; kept the most human-sounding of {drafts} drafts per part"
        if meaning["retried"]:
            detail += f"; {meaning['retried']} rewritten again after validation"
        add(3, "ok", detail + ".")

        detail = (
            f"{fixes} spacing, punctuation or grammar fix{'es' * (fixes != 1)}" if fixes else "No corrections needed"
        )
        if phrases:
            detail += f"; replaced {phrases} overused phrase{'s' * (phrases != 1)}"
        if dashes:
            detail += f"; replaced {_n(dashes, 'em dash', 'em dashes')}"
        if restructured:
            detail += f"; {_n(restructured, 'structural edit')} for a more natural rhythm"
        add(4, "ok", detail + ".")

        if meaning["issues"]:
            add(
                5,
                "warning",
                f"{meaning['passed']} of {meaning['parts']} parts passed. " + " ".join(meaning["issues"][:3]),
            )
        else:
            add(5, "ok", "Facts, numbers, names, negations and hedging preserved.")

        code_note = ""
        if code["blocks"]:
            code_note = (
                f" Code: {_n(code['rewritten'], 'comment line')} reworded in {_n(code['blocks'], 'block')}; "
                "the code itself was checked and is unchanged."
            )
            if code["untouched"]:
                code_note += f" {_n(code['untouched'], 'block')} in an unrecognised language left as is."
        if not citations["ok"]:
            add(6, "warning", "Some protected text changed: " + _list(citations["missing"], 3) + "." + code_note)
        elif protected_parts or citations["references"]:
            kept = _list(protected_parts + (["the reference list"] if citations["references"] else []), 8)
            add(6, "ok", f"Kept {kept} exactly as written." + code_note)
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
            explain.append(
                "The text is now easier to read." if eb > ea else "The wording is now more formal and dense."
            )
        if facts.numbers or facts.names:
            explain.append("Kept every number, name and technical term from the original.")
        if protected_parts or citations["references"]:
            explain.append("Citations, quotations and references were left exactly as written.")
        if code["rewritten"]:
            explain.append("Reworded comments in the code; variables, syntax and logic are byte-for-byte the same.")
        if locked_sections:
            explain.append("Left " + _list(locked_sections, 4) + " exactly as written.")
        if dashes:
            explain.append(f"Replaced {_n(dashes, 'em dash', 'em dashes')} with commas, colons or full stops.")
        if processed.invisible:
            explain.append(
                f"Removed {_n(processed.invisible, 'invisible character')} (zero-width spaces, soft hyphens and similar)."
            )
        if phrases:
            explain.append(f"Replaced {phrases} overused AI-style phrase{'s' * (phrases != 1)} with plainer wording.")
        if drafts > 1 or restructured:
            explain.append(
                "Chose more natural wording and a more varied sentence rhythm, so the text reads more like a person wrote it."
            )
        if patterns:
            explain.append("Still reads a little machine-like here: " + _list(patterns, 3) + ".")
        if meaning["kept_original"]:
            explain.append(
                f"{meaning['kept_original']} part{'s' * (meaning['kept_original'] != 1)} kept unchanged because the rewrite didn't pass validation."
            )

        return {
            "text": final_text,
            "segments": segments,
            "stats": {
                "words_in": words_in,
                "words_out": words_out,
                "changes": changes,
                "change_pct": pct,
                "levels": {
                    lvl: sum(1 for x in segments if x.get("level") == lvl)
                    for lvl in ("word", "phrase", "sentence", "added")
                },
            },
            "report": {
                "layers": [l.to_dict() for l in layers],
                "explanations": explain,
                "warnings": meaning["issues"] + ([] if citations["ok"] else ["Some citations or quotations changed."]),
                "register": context.register,
                "humanness": {
                    "score": round(sum(human_scores) / len(human_scores), 2) if human_scores else None,
                    "drafts": drafts,
                    "structural_edits": restructured,
                    "patterns": patterns,
                },
                "sections": [{"name": n, "locked": l} for n, l in processed.sections],
                "code": code,
                "invisible_removed": processed.invisible,
            },
        }
