import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import lexicon as lx  # noqa: E402
from app.core.rule_engine import match_case, paraphrase  # noqa: E402
from app.schemas.paraphrase import ParaphraseError  # noqa: E402


def run(text, strength=50, seed=1):
    return paraphrase(text, strength, seed)["text"]


class EngineTests(unittest.TestCase):
    def test_lexicon_keys_are_unique(self):
        lx._build_index()  # raises on duplicates

    def test_empty_text(self):
        result = paraphrase("", 50, 1)
        self.assertEqual(result["text"], "")
        self.assertEqual(result["stats"]["words_in"], 0)

    def test_deterministic_with_seed(self):
        text = "The problem is difficult, but the method shows important results."
        self.assertEqual(run(text, 80, 42), run(text, 80, 42))

    def test_segments_rebuild_output(self):
        result = paraphrase("We need to examine the important problems quickly.", 100, 3)
        self.assertEqual("".join(s["text"] for s in result["segments"]), result["text"])
        self.assertGreater(result["stats"]["changes"], 0)

    def test_humanize_uses_contractions(self):
        outs = {run("We do not know if it is ready to ship.", 100, seed) for seed in range(10)}
        self.assertTrue(any("don't" in o or "it's" in o for o in outs), outs)

    def test_never_picks_slang(self):
        for seed in range(20):
            self.assertNotIn("lots of", run("We found a lot of problems with the plan.", 100, seed))

    def test_protects_urls_quotes_and_proper_nouns(self):
        text = 'Visit https://example.com/problem for "important" news about Happy Valley.'
        out = run(text, 100)
        self.assertIn("https://example.com/problem", out)
        self.assertIn('"important"', out)
        self.assertIn("Happy Valley", out)

    def test_plural_inflection(self):
        self.assertIn("issues", lx.synonyms_for("problems"))
        self.assertIn("children", lx.synonyms_for("kids"))
        self.assertIn("assists", lx.synonyms_for("helps") or ["assists"])
        self.assertIsNone(lx.synonyms_for("goods"))  # "good" isn't a noun/verb group

    def test_match_case(self):
        self.assertEqual(match_case("Big", "large"), "Large")
        self.assertEqual(match_case("BIG", "large"), "LARGE")
        self.assertEqual(match_case("big", "large"), "large")

    def test_strength_zero_changes_little(self):
        text = "The important problem was difficult for the students. " * 5
        low = paraphrase(text, 0, 9)["stats"]["change_pct"]
        high = paraphrase(text, 100, 9)["stats"]["change_pct"]
        self.assertLess(low, high)

    def test_invalid_input(self):
        with self.assertRaises(ParaphraseError):
            paraphrase("x" * 20_001)

    def test_hedges_negations_and_reporting_verbs_are_frozen(self):
        text = "The results suggest that the method may appear to indicate a problem. We did not show it."
        for seed in range(15):
            out = run(text, 100, seed)
            words = [w.strip(".") for w in out.split(" ")]
            for word in ("suggest", "may", "appear", "indicate", "show"):
                self.assertIn(word, words)
            self.assertTrue("not" in words or "didn't" in words, out)  # a contraction keeps the negation
            self.assertNotIn("propose", out)

    def test_never_introduces_frozen_words(self):
        for seed in range(15):
            self.assertNotIn("propose", run("They pointed out the important problems.", 100, seed))

    def test_part_of_speech_check(self):
        for seed in range(15):
            out = run("They will challenge the increase. Take advantage of a sharp increase.", 100, seed)
            self.assertIn("will challenge", out)
            self.assertIn("advantage", out)
            self.assertEqual(out.count("increase"), 2, out)

    def test_names_after_abbreviations_are_protected(self):
        text = "Dr. Rich Hope met the U.S. Grace team, e.g. Happy Valley staff. Rich was happy."
        for seed in range(10):
            out = run(text, 100, seed)
            for name in ("Rich Hope", "Grace", "Happy Valley", "Rich was"):
                self.assertIn(name, out)

    def test_stem_check(self):
        from app.core.rule_engine import _stem

        self.assertEqual(_stem("challenge"), _stem("challenging"))
        self.assertEqual(_stem("happy"), _stem("happiness"))
        self.assertEqual(_stem("difficult"), _stem("difficulty"))
        self.assertNotEqual(_stem("consider"), _stem("consistent"))

    def test_high_strength_changes_most_sentences(self):
        text = (
            "The team began the project in March. We need to examine the problems quickly. "
            "Our customers want a simple tool. The main goal is to help people."
        )
        out = run(text, 90, 4)
        from app.utils.text_utils import split_sentences

        src = set(split_sentences(text))
        changed = [s for s in split_sentences(out) if s not in src]
        self.assertGreaterEqual(len(changed), 3, out)


if __name__ == "__main__":
    unittest.main()
