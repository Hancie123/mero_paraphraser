"""Tests for the human-like output helpers."""

import random
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import lexicon as lx  # noqa: E402
from app.pipeline.humanizer import ai_patterns, burstiness, human_score, restructure  # noqa: E402


def rng():
    return random.Random(0)


class PatternTests(unittest.TestCase):
    def test_detects_ai_structures(self):
        text = ("It not only saves time but also money. Furthermore, it is cheap. Furthermore, it is fast. "
                "Overall, it works.")
        found = ai_patterns(text)
        for name in ("not only... but also", "summary opener", "repeated sentence openers"):
            self.assertIn(name, found)

    def test_plain_list_of_two_is_not_a_triplet(self):
        self.assertNotIn("lists of three", ai_patterns("It raises problems, like privacy risks and bias."))

    def test_burstiness(self):
        self.assertLess(burstiness("One two three four. Five six seven eight. Nine ten eleven twelve."), 0.1)
        self.assertGreater(burstiness("Short. This one is a good deal longer than the first one was."), 0.5)


class RestructureTests(unittest.TestCase):
    def test_drops_summary_opener_and_not_only(self):
        out, n = restructure("It not only cuts costs but also saves time. Overall, it works.", "x", rng())
        self.assertEqual(out, "It cuts costs and saves time. It works.")
        self.assertEqual(n, 2)

    def test_keeps_what_the_author_wrote(self):
        text = "Overall, it works. It not only cuts costs but also saves time."
        self.assertEqual(restructure(text, text, rng())[0], text)

    def test_drops_added_summary_sentence(self):
        out, _ = restructure("It rains. Roads flood. People stay home. In summary, storms disrupt life.",
                             "It rains. Roads flood. People stay home.", rng())
        self.assertEqual(out, "It rains. Roads flood. People stay home.")

    def test_contractions(self):
        outs = {restructure("We do not know yet.", "x", random.Random(s))[0] for s in range(10)}
        self.assertIn("We don't know yet.", outs)

    def test_em_dashes_removed(self):
        from app.pipeline.language_refiner import LanguageRefiner
        out = LanguageRefiner().refine("It failed—badly. Then—later—it worked.", "It failed—badly.", 1).text
        self.assertEqual(out, "It failed, badly. Then, later, it worked.")

    def test_transition_swap_keeps_meaning_and_names(self):
        outs = {restructure("However, Smith left.", "x", random.Random(s))[0] for s in range(20)}
        self.assertTrue(outs <= {"However, Smith left.", "That said, Smith left.", "Still, Smith left.", "But Smith left."})
        self.assertGreater(len(outs), 1)

    def test_this_opener_merged(self):
        out, _ = restructure("Sleep was tracked. This shows a clear effect.", "x", rng())
        self.assertEqual(out, "Sleep was tracked, which shows a clear effect.")

    def test_ellipsis(self):
        out, _ = restructure("If it is possible, test the method that was used.", "x", rng())
        self.assertEqual(out, "If possible, test the method used.")

    def test_splits_long_sentence_when_lengths_are_even(self):
        long = ("Companies are investing in new digital tools for their staff, and they are training managers "
                "to lead distributed teams with care.")
        text = f"{long} {long} {long}"
        out, n = restructure(text, "x", rng())
        self.assertGreaterEqual(n, 1)
        self.assertRegex(out, r"staff\. (?:And t|T)hey(?: are|'re) training")


class ScoringTests(unittest.TestCase):
    def test_varied_text_without_patterns_scores_higher(self):
        even = "The cat sat on the mat. The dog sat on the rug. The cow sat on the hay."
        varied = "The cat sat on the mat. Nearby, a dog was asleep on the rug by the door. Quiet."
        self.assertGreater(human_score(varied).total, human_score(even).total)


class LexiconTests(unittest.TestCase):
    def test_generated_synonyms_stay_out_of_rule_engine(self):
        self.assertIsNone(lx.synonyms_for("thorough"))  # the rule engine keeps to hand-written groups
        self.assertEqual(lx.suggestions_for("thorough"), ["exhaustive"])
        self.assertFalse(set(lx.EXTRA_SYNONYMS) & set(lx.SYNONYMS))  # hand-written groups win
        self.assertTrue(all(pos in (lx.A, lx.R) for pos, _ in lx.EXTRA_SYNONYMS.values()))

    def test_missing_generated_file_is_fine(self):
        self.assertEqual(lx._load_extra(Path(tempfile.gettempdir()) / "no-such-synonyms.json"), {})


if __name__ == "__main__":
    unittest.main()
