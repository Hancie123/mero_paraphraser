"""Tests for the human-like output helpers (no AI model needed)."""

import os
import random
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.pipeline.humanizer import (  # noqa: E402
    ai_patterns,
    burstiness,
    custom_avoid_words,
    flattest_sentence,
    human_score,
    longest_sentence,
    repeated_opener,
    restructure,
    splice_tokens,
    style_sample,
    swap_predictable,
)
from app.pipeline.rewriting_engine import clean_draft  # noqa: E402


def fake_tokens(text: str, sure: set[str] = frozenset(), alts: dict[str, tuple] | None = None):
    """One token per word: logprob ~0 for words in ``sure``, -2 otherwise."""
    import re
    out = []
    for m in re.finditer(r"\S+", text):
        word = m.group().strip(".,").lower()
        lp = -0.01 if word in sure else -2.0
        out.append((m.start(), m.end(), lp, (alts or {}).get(word, ())))
    return out


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
        out, n = restructure("It not only cuts costs but also saves time. Overall, it works.", "x", "academic", rng())
        self.assertEqual(out, "It cuts costs and saves time. It works.")
        self.assertEqual(n, 2)

    def test_keeps_what_the_author_wrote(self):
        text = "Overall, it works. It not only cuts costs but also saves time."
        self.assertEqual(restructure(text, text, "standard", rng())[0], text)

    def test_drops_added_summary_sentence(self):
        out, _ = restructure("It rains. Roads flood. People stay home. In summary, storms disrupt life.",
                             "It rains. Roads flood. People stay home.", "standard", rng())
        self.assertEqual(out, "It rains. Roads flood. People stay home.")

    def test_contractions_only_in_casual_modes(self):
        text = "We do not know yet."
        self.assertEqual(restructure(text, "x", "academic", rng())[0], text)
        outs = {restructure(text, "x", "fluent", random.Random(s))[0] for s in range(10)}
        self.assertIn("We don't know yet.", outs)

    def test_em_dash_removed_in_formal_modes(self):
        self.assertEqual(restructure("It failed—badly.", "x", "academic", rng())[0], "It failed, badly.")

    def test_transition_swap_keeps_meaning_and_names(self):
        outs = {restructure("However, Smith left.", "x", "standard", random.Random(s))[0] for s in range(20)}
        self.assertTrue(outs <= {"However, Smith left.", "That said, Smith left.", "Still, Smith left.", "But Smith left."})
        self.assertGreater(len(outs), 1)

    def test_this_opener_merged(self):
        out, _ = restructure("Sleep was tracked. This shows a clear effect.", "x", "academic", rng())
        self.assertEqual(out, "Sleep was tracked, which shows a clear effect.")

    def test_ellipsis(self):
        out, _ = restructure("If it is possible, test the method that was used.", "x", "academic", rng())
        self.assertEqual(out, "If possible, test the method used.")

    def test_splits_long_sentence_when_lengths_are_even(self):
        long = ("Companies are investing in new digital tools for their staff, and they are training managers "
                "to lead distributed teams with care.")
        text = f"{long} {long} {long}"
        out, n = restructure(text, "x", "academic", rng())
        self.assertGreaterEqual(n, 1)
        self.assertIn("staff. They are training", out)


class ScoringTests(unittest.TestCase):
    def test_less_predictable_scores_higher(self):
        text = "The cat sat on the mat. It was warm there."
        flat = human_score(text, text, fake_tokens(text, sure={w.strip(".").lower() for w in text.split()}))
        lively = human_score(text, text, fake_tokens(text))
        self.assertGreater(lively.total, flat.total)

    def test_flattest_sentence(self):
        text = "Dogs bark loudly at night in the city. The results of the study are shown in the table below here."
        sure = {"the", "results", "of", "study", "are", "shown", "in", "table", "below", "here"}
        span = flattest_sentence(text, fake_tokens(text, sure))
        self.assertEqual(text[span[0]:span[1]], "The results of the study are shown in the table below here.")

    def test_repeated_opener(self):
        text = "This study tracks sleep. This study also tracks grades closely. Results vary."
        span = repeated_opener(text)
        self.assertEqual(text[span[0]:span[1]], "This study also tracks grades closely.")

    def test_longest_sentence(self):
        text = "Short one here. This sentence is clearly the longest of the three in the text. Tiny."
        span = longest_sentence(text, 5)
        self.assertEqual(text[span[0]:span[1]], "This sentence is clearly the longest of the three in the text.")
        self.assertIsNone(longest_sentence("Tiny. Small.", 5))

    def test_prompt_names_hedges_and_negations(self):
        from app.pipeline.rewriting_engine import build_user_prompt
        from app.schemas.paraphrase import Context, Facts
        p = build_user_prompt("Studies suggest it may not work.", "standard", 60, Context("general", [], [], []), Facts())
        self.assertIn("suggest, may.", p)
        self.assertIn("Keep every negation (not)", p)

    def test_splice_tokens(self):
        tokens = [(0, 3, -1, ()), (4, 8, -1, ()), (9, 12, -1, ())]
        self.assertEqual(splice_tokens(tokens, 4, 8, 6), [(0, 3, -1, ()), (11, 14, -1, ())])


class SwapTests(unittest.TestCase):
    def test_swaps_only_contextual_synonyms_of_adjectives(self):
        text = "They built a huge wall and helped people diagnose problems near the old river bank today."
        tokens = fake_tokens(text, sure={"huge", "helped"}, alts={"huge": (" enormous", " massive"), "helped": (" assisted",)})
        out, _, n = swap_predictable(text, tokens, set(), 100, False, rng())
        self.assertEqual(n, 1)
        self.assertIn("helped", out)  # verbs are never swapped
        self.assertTrue("enormous wall" in out or "massive wall" in out)

    def test_no_swap_without_model_support(self):
        text = "They built a huge wall and helped people diagnose problems near the old river bank today."
        out, _, n = swap_predictable(text, fake_tokens(text, sure={"huge"}), set(), 100, False, rng())
        self.assertEqual((out, n), (text, 0))

    def test_generated_synonyms_need_model_support(self):
        from app.core import lexicon as lx
        self.assertIn("thorough", lx.EXTRA_SYNONYMS)  # from app/data/synonyms_extra.json
        text = "The team ran a thorough review of every part of the old system before the launch."
        out, _, n = swap_predictable(text, fake_tokens(text, sure={"thorough"}, alts={"thorough": (" exhaustive",)}),
                                     set(), 100, False, rng())
        self.assertEqual(n, 1)
        self.assertIn("exhaustive review", out)
        out, _, n = swap_predictable(text, fake_tokens(text, sure={"thorough"}), set(), 100, False, rng())
        self.assertEqual((out, n), (text, 0))

    def test_generated_synonyms_stay_out_of_rule_engine(self):
        from app.core import lexicon as lx
        self.assertIsNone(lx.synonyms_for("thorough"))  # the offline engine has no context check
        self.assertEqual(lx.suggestions_for("thorough"), ["exhaustive"])
        self.assertFalse(set(lx.EXTRA_SYNONYMS) & set(lx.SYNONYMS))  # hand-written groups win
        self.assertTrue(all(pos in (lx.A, lx.R) for pos, _ in lx.EXTRA_SYNONYMS.values()))

    def test_missing_generated_file_is_fine(self):
        from app.core import lexicon as lx
        self.assertEqual(lx._load_extra(Path(tempfile.gettempdir()) / "no-such-synonyms.json"), {})

    def test_keep_words_are_not_swapped(self):
        text = "They built a huge wall and helped people diagnose problems near the old river bank today."
        tokens = fake_tokens(text, sure={"huge"}, alts={"huge": (" enormous",)})
        self.assertEqual(swap_predictable(text, tokens, {"huge"}, 100, False, rng())[2], 0)


class DraftAlignmentTests(unittest.TestCase):
    def test_tokens_follow_cleaning(self):
        reply = 'Here is the rewritten text: "Fast cars."'
        tokens = [(29, 33, -1.0, ()), (34, 39, -2.0, ())]  # "Fast", "cars."
        draft = clean_draft(reply, "  Quick cars.\n", tokens)
        self.assertEqual(draft.text, "  Fast cars.\n")
        self.assertEqual([draft.text[a:b] for a, b, _, _ in draft.tokens], ["Fast", "cars."])


class StyleFolderTests(unittest.TestCase):
    def test_style_sample_and_avoid_list(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "all.txt").write_text("I write short. Then I ramble on a bit.", encoding="utf-8")
            Path(d, "avoid.txt").write_text("synergize\nbeacon -20  # comment\n", encoding="utf-8")
            old = os.environ.get("MERO_STYLE_DIR")
            os.environ["MERO_STYLE_DIR"] = d
            try:
                self.assertEqual(style_sample("fluent"), "I write short. Then I ramble on a bit.")
                self.assertEqual(custom_avoid_words(), {"synergize": -6.0, "beacon": -20.0})
            finally:
                if old is None:
                    del os.environ["MERO_STYLE_DIR"]
                else:
                    os.environ["MERO_STYLE_DIR"] = old


if __name__ == "__main__":
    unittest.main()
