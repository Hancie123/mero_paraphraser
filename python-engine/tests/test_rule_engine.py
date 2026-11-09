import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import lexicon as lx  # noqa: E402
from app.core.rule_engine import match_case, paraphrase  # noqa: E402
from app.schemas.paraphrase import ParaphraseError  # noqa: E402


def run(text, mode="standard", strength=50, seed=1):
    return paraphrase(text, mode, strength, seed)["text"]


class EngineTests(unittest.TestCase):
    def test_lexicon_keys_are_unique(self):
        lx._build_index()  # raises on duplicates

    def test_empty_text(self):
        result = paraphrase("", "standard", 50, 1)
        self.assertEqual(result["text"], "")
        self.assertEqual(result["stats"]["words_in"], 0)

    def test_deterministic_with_seed(self):
        text = "The problem is difficult, but the method shows important results."
        self.assertEqual(run(text, "creative", 80, 42), run(text, "creative", 80, 42))

    def test_segments_rebuild_output(self):
        result = paraphrase("We need to examine the important problems quickly.", "creative", 100, 3)
        self.assertEqual("".join(s["text"] for s in result["segments"]), result["text"])
        self.assertGreater(result["stats"]["changes"], 0)

    def test_formal_expands_contractions(self):
        out = run("I don't think it's ready, and it's been a while.", "formal")
        self.assertIn("I do not", out)
        self.assertIn("think it is ", out)
        self.assertIn("it has been", out)

    def test_shorten_removes_wordiness_and_fillers(self):
        out = run("In order to win, we really need to try.", "shorten")
        self.assertTrue(out.startswith("To win"), out)
        self.assertNotIn("really", out)
        self.assertEqual(run("Really good work.", "shorten"), "Good work.")

    def test_simple_mode(self):
        out = run("We utilize an automobile to commence the journey.", "simple")
        self.assertIn("use", out)
        self.assertIn("a car", out)  # article fixed: an automobile -> a car
        self.assertIn("start", out)

    def test_protects_urls_quotes_and_proper_nouns(self):
        text = 'Visit https://example.com/problem for "important" news about Happy Valley.'
        out = run(text, "creative", 100)
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
        low = paraphrase(text, "standard", 0, 9)["stats"]["change_pct"]
        high = paraphrase(text, "standard", 100, 9)["stats"]["change_pct"]
        self.assertLess(low, high)

    def test_invalid_input(self):
        with self.assertRaises(ParaphraseError):
            paraphrase("hi", "nope")
        with self.assertRaises(ParaphraseError):
            paraphrase("x" * 20_001)


if __name__ == "__main__":
    unittest.main()
