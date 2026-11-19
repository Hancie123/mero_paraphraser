"""Frozen words, opposites and the user's word preferences (locked, preferred, banned)."""

import random
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.paraphrase import handle  # noqa: E402
from app.core import lexicon as lx  # noqa: E402
from app.core.preferences import NONE, Preferences  # noqa: E402
from app.core.rule_engine import Paraphraser  # noqa: E402
from app.pipeline.input_processor import protect  # noqa: E402
from app.pipeline.output_formatter import alternatives  # noqa: E402
from app.schemas.paraphrase import ParaphraseError, ParaphraseRequest  # noqa: E402


def changes(text, prefs=NONE, seeds=200):
    """Every (original, replacement) the rule engine makes over many seeds at full strength."""
    seen = set()
    for seed in range(seeds):
        for seg in Paraphraser(text, 100, random.Random(seed), prefs).run():
            if seg.changed:
                seen.add((seg.original.lower(), seg.text.lower()))
    return seen


class FrozenTests(unittest.TestCase):
    def test_hedges_and_reporting_verbs_never_swapped(self):
        text = "The results suggest that the method may not work, and the authors recommend a larger trial."
        changed = {orig for orig, _ in changes(text)}
        self.assertFalse(changed & {"suggest", "may", "not", "recommend"})

    def test_frozen_words_never_suggested(self):
        self.assertIsNone(lx.suggestions_for("suggest"))
        self.assertNotIn("propose", lx.suggestions_for("advise") or [])


class OppositeTests(unittest.TestCase):
    def test_opposed(self):
        self.assertTrue(lx.opposed("strong", "weak"))
        self.assertTrue(lx.opposed("increases", "decrease"))
        self.assertFalse(lx.opposed("strong", "powerful"))

    def test_contrast_pair_kept(self):
        changed = {orig for orig, _ in changes("A strong team and a weak team met.")}
        self.assertFalse(changed & {"strong", "weak"})

    def test_opposite_never_suggested(self):
        for word in lx.SYNONYMS:
            for alt in lx.suggestions_for(word) or []:
                self.assertFalse(lx.opposed(word, alt), (word, alt))


class PreferenceTests(unittest.TestCase):
    prefs = Preferences.build(["Mero Paraphraser"], {"utilize": "employ", "in order to": "to"}, ["use"])

    def test_request_validation(self):
        req = ParaphraseRequest.from_dict({"text": "x", "locked_terms": [" Foo  Bar "], "banned": ["Use"]})
        self.assertEqual(req.prefs.locked, ("Foo Bar",))
        self.assertEqual(req.prefs.banned, frozenset({"use"}))
        for bad in ({"locked_terms": "Foo"}, {"banned": [1]}, {"preferred": ["a"]}, {"locked_terms": ["x" * 101]}):
            with self.assertRaises(ParaphraseError):
                ParaphraseRequest.from_dict({"text": "x", **bad})

    def test_locked_terms_masked_ignoring_case(self):
        masked, protected = protect("We ship mero paraphraser and (Smith, 2020).", prefs=self.prefs)
        self.assertEqual(masked, "We ship [[1]] and [[2]].")
        self.assertEqual([p.kind for p in protected], ["term", "citation"])

    def test_locked_terms_case_does_not_leak_into_citations(self):
        # Only the terms ignore case: a lowercase "smith (2020)" is still not a citation.
        _, protected = protect("as smith (2020) said", prefs=self.prefs)
        self.assertEqual(protected, [])

    def test_locked_words_never_change_in_rule_engine(self):
        prefs = Preferences.build(["important"], {}, [])
        self.assertTrue(any(o == "important" for o, _ in changes("This is an important step.")))
        self.assertFalse(any(o == "important" for o, _ in changes("This is an important step.", prefs)))

    def test_preferred_word_and_phrase(self):
        got = changes("We utilize it in order to win the game.", self.prefs, 50)
        self.assertIn(("utilize", "employ"), got)
        self.assertIn(("in order to", "to"), got)
        self.assertFalse({new for orig, new in got if orig == "utilize"} - {"employ"})

    def test_pipeline_keeps_locked_and_avoids_banned(self):
        text = (
            "We need to utilize the Mero Paraphraser engine to get a significant improvement. "
            "The team will attempt to leverage the important figures in order to find the main result."
        )
        req = {
            "cmd": "paraphrase", "text": text, "mode": "humanize", "strength": 100,
            "locked_terms": ["Mero Paraphraser"], "preferred": {"utilize": "employ"}, "banned": ["use"],
        }  # fmt: skip
        for seed in range(20):
            out = handle({**req, "seed": seed})
            self.assertIn("Mero Paraphraser", out["text"])
            self.assertNotIn("use", re.findall(r"[a-z]+", out["text"].lower()))
            for seg in out["segments"]:
                self.assertNotIn("use", [a.lower() for a in seg.get("alternatives", [])])

    def test_alternatives_put_preferred_first_and_skip_banned(self):
        prefs = Preferences.build([], {"big": "huge"}, ["sizable"])
        alts = alternatives("large", "big", prefs)
        self.assertEqual(alts[0], "huge")
        self.assertNotIn("sizable", alts)
        self.assertEqual(alts[-1], "big")


if __name__ == "__main__":
    unittest.main()
