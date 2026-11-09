"""Tests for the eight pipeline layers that don't need the AI model."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.paraphrase import handle  # noqa: E402
from app.pipeline.citation_validator import check_tokens  # noqa: E402
from app.pipeline.context_analyzer import ContextAnalyzer  # noqa: E402
from app.pipeline.input_processor import InputProcessor, restore  # noqa: E402
from app.pipeline.language_refiner import LanguageRefiner  # noqa: E402
from app.pipeline.meaning_validator import check_facts, parse_judgement  # noqa: E402
from app.pipeline.output_formatter import diff_segments  # noqa: E402
from app.pipeline.semantic_analyzer import facts_for  # noqa: E402
from app.schemas.paraphrase import ParaphraseError  # noqa: E402
from app.utils.document_utils import chunk_text, split_references  # noqa: E402
from app.utils.text_utils import split_sentences  # noqa: E402

ACADEMIC = (
    "Research by Twenge (2019) suggests that teens who spend more than 5 hours a day online may feel lonely. "
    "However, other studies did not find a clear link (Orben & Przybylski, 2019; Lee et al., 2021, p. 4). "
    'As one author wrote, "screen time is not a single thing" [3]. See https://example.org/study.\n\n'
    "References\nTwenge, J. (2019). iGen. Atria Books."
)


class Layer1InputTests(unittest.TestCase):
    def test_protects_citations_quotes_links_and_references(self):
        p = InputProcessor().process(ACADEMIC)
        kinds = [x.kind for x in p.protected]
        self.assertEqual(kinds.count("citation"), 3)
        self.assertEqual(kinds.count("quote"), 1)
        self.assertEqual(kinds.count("url"), 1)
        self.assertTrue(p.references.strip().startswith("References"))
        self.assertNotIn("Twenge (2019)", p.masked)
        self.assertNotIn("References", p.masked)
        self.assertEqual(restore(p.masked, p.protected) + p.references, ACADEMIC)

    def test_literal_tokens_in_user_text_survive(self):
        p = InputProcessor().process("Use [[1]] as a marker (Smith, 2020).")
        self.assertEqual(restore(p.masked, p.protected), "Use [[1]] as a marker (Smith, 2020).")

    def test_cleaning_keeps_wording(self):
        p = InputProcessor().process("Hello​ world.\r\nNext line.   \n")
        self.assertEqual(p.body, "Hello world.\nNext line.\n")

    def test_no_reference_split_without_heading(self):
        self.assertEqual(split_references("Just text."), ("Just text.", ""))


class Layer2And3AnalysisTests(unittest.TestCase):
    def test_academic_register_numbers_negations_hedges(self):
        p = InputProcessor().process(ACADEMIC)
        c = ContextAnalyzer().analyze(p)
        self.assertEqual(c.register, "academic")
        self.assertIn("contrast", c.relationships)
        f = facts_for(p.masked, c)
        self.assertIn("5", f.numbers)
        self.assertGreaterEqual(f.negations, 1)
        self.assertGreaterEqual(f.hedges, 2)

    def test_general_register(self):
        c = ContextAnalyzer().analyze(InputProcessor().process("I went to the shop and bought some bread."))
        self.assertEqual(c.register, "general")

    def test_sentence_split_ignores_abbreviations(self):
        self.assertEqual(len(split_sentences("Smith et al. found it. See e.g. the data. Done.")), 3)


class Layer5RefineTests(unittest.TestCase):
    def test_fixes_spacing_articles_doubles_and_stock_phrases(self):
        r = LanguageRefiner().refine("It is important to note that the the plan works . a apple, e.g. this.", "The plan works.")
        self.assertEqual(r.text, "The plan works. An apple, e.g. this.")
        self.assertEqual(r.phrases, 1)
        self.assertGreaterEqual(r.fixes, 3)

    def test_leaves_author_phrases(self):
        r = LanguageRefiner().refine("We delve into it.", "We delve into it.")
        self.assertEqual(r.text, "We delve into it.")


class Layer6And7ValidationTests(unittest.TestCase):
    def setUp(self):
        p = InputProcessor().process("Sales did not grow in 2023; they may fall by 5% at Acme Corp.")
        self.context = ContextAnalyzer().analyze(p)
        self.src = p.masked
        self.facts = facts_for(p.masked, self.context)

    def test_good_rewrite_passes(self):
        out = "Sales did not rise in 2023, and they may drop by 5% at Acme Corp."
        self.assertEqual(check_facts(self.src, out, self.facts, "standard"), [])

    def test_detects_lost_number_negation_hedge_and_name(self):
        issues = " ".join(check_facts(self.src, "Sales grew in 2022 and they will fall at Acme.", self.facts, "standard"))
        self.assertIn("Numbers", issues)
        self.assertIn("negation", issues)
        self.assertIn("Hedging", issues)
        self.assertIn("Names", issues)

    def test_token_checks(self):
        self.assertEqual(check_tokens("A [[1]] b [[2]].", "B [[2]] a [[1]]."), ([], False))
        issues, critical = check_tokens("A [[1]] b [[2]].", "A b [[2]] (Smith, 2020).")
        self.assertTrue(critical)
        self.assertEqual(len(issues), 2)  # dropped [[1]] and invented a citation

    def test_parse_judgement(self):
        self.assertEqual(parse_judgement('{"added": [], "missing": [], "changed": [], "score": 5}'), (5, ""))
        score, issue = parse_judgement('{"added": ["a new claim"], "missing": [], "changed": [], "score": 5}')
        self.assertEqual(score, 3)  # listed problems outweigh the score
        self.assertIn("a new claim", issue)
        self.assertEqual(parse_judgement("Score: 2")[0], 2)


class Layer8OutputTests(unittest.TestCase):
    def test_segments_rebuild_output_with_kinds(self):
        segs, changes, _ = diff_segments("The big dog ran home, and it was happy.", "The large dog ran home, and it felt happy.")
        self.assertEqual("".join(s["text"] for s in segs), "The large dog ran home, and it felt happy.")
        changed = [s for s in segs if "original" in s]
        self.assertEqual([(s["original"], s["text"], s["kind"]) for s in changed],
                         [("big", "large", "Synonym"), ("was", "felt", "Reworded")])
        self.assertIn("big", changed[0]["alternatives"])
        self.assertEqual(changes, 2)


class ChunkTests(unittest.TestCase):
    def test_roundtrip_and_long_paragraphs(self):
        text = "Intro.\n\n" + "This is one sentence that repeats. " * 100 + "\n\n\nOutro.  "
        chunks = chunk_text(text, 300)
        self.assertEqual("".join(p for p, _ in chunks), text)
        self.assertTrue(all(len(p) <= 500 for p, rw in chunks if rw))


class PipelineTests(unittest.TestCase):
    """The whole pipeline with the rule-based engine (engine "basic")."""

    def test_end_to_end_report(self):
        r = handle({"cmd": "paraphrase", "text": ACADEMIC, "mode": "academic", "strength": 60, "seed": 2})
        self.assertEqual(r["engine"], "basic")
        self.assertEqual("".join(s["text"] for s in r["segments"]), r["text"])
        for kept in ("Twenge (2019)", "(Orben & Przybylski, 2019; Lee et al., 2021, p. 4)",
                     '"screen time is not a single thing"', "[3]", "https://example.org/study",
                     "References\nTwenge, J. (2019). iGen. Atria Books."):
            self.assertIn(kept, r["text"])
        layers = r["report"]["layers"]
        self.assertEqual([l["id"] for l in layers],
                         ["input", "context", "semantic", "rewrite", "refine", "meaning", "citations", "output"])
        self.assertEqual(layers[6]["status"], "ok")

    def test_old_formal_mode_still_works(self):
        r = handle({"cmd": "paraphrase", "text": "I don't know.", "mode": "formal", "seed": 1})
        self.assertEqual(r["text"], "I do not know.")

    def test_invalid_requests(self):
        for bad in ({"mode": "bogus"}, {"engine": "gpt"}, {"strength": "x"}, {"text": "x" * 20_001}):
            with self.assertRaises(ParaphraseError):
                handle({"cmd": "paraphrase", "text": "hi", **bad})

    def test_empty_text(self):
        r = handle({"cmd": "paraphrase", "text": "", "seed": 1})
        self.assertEqual(r["text"], "")


if __name__ == "__main__":
    unittest.main()
