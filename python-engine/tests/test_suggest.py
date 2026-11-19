import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.paraphrase import handle  # noqa: E402
from app.core.thesaurus import is_risky, senses_for  # noqa: E402
from app.schemas.paraphrase import ParaphraseError  # noqa: E402


def words(word, context=""):
    return [w for s in senses_for(word, context) for w in s.words]


class ThesaurusTests(unittest.TestCase):
    def test_curated_group_first(self):
        senses = senses_for("problems", "We found many problems.")
        self.assertEqual(senses[0].pos, "")  # the reviewed lexicon group
        self.assertIn("issues", senses[0].words)

    def test_keeps_the_word_form(self):
        self.assertIn("examined", words("analysed", "They analysed the data."))
        senses = senses_for("showing", "It is showing signs.")
        self.assertEqual(senses[0].pos, "verb")  # "is showing": verb senses first, the noun ("a showing") after
        verbs = [w for s in senses if s.pos == "verb" for w in s.words]
        self.assertTrue(verbs and all(w.split()[0].endswith("ing") for w in verbs), verbs)

    def test_matches_case(self):
        self.assertTrue(all(w[0].isupper() for w in words("Bright")))

    def test_context_orders_senses(self):
        self.assertEqual(senses_for("show", "We watched a show.")[0].pos, "noun")
        self.assertEqual(senses_for("show", "The results show a trend.")[0].pos, "verb")

    def test_glosses(self):
        self.assertTrue(all(s.gloss for s in senses_for("bright")))

    def test_function_words_and_numbers(self):
        self.assertEqual(senses_for("the"), [])
        self.assertEqual(senses_for("2021"), [])

    def test_risky_words_flagged(self):
        self.assertTrue(is_risky("suggest"))
        self.assertTrue(is_risky("shows"))
        self.assertFalse(is_risky("bright"))


class CommandTests(unittest.TestCase):
    def test_suggest(self):
        r = handle({"cmd": "suggest", "word": "suggest", "context": "The data suggest a link."})
        self.assertTrue(r["senses"])
        self.assertTrue(r["note"])  # reporting verb: warn
        r = handle({"cmd": "suggest", "word": "bright", "context": ""})
        self.assertEqual(r["note"], "")

    def test_suggest_rejects_bad_input(self):
        with self.assertRaises(ParaphraseError):
            handle({"cmd": "suggest", "word": "x" * 100})

    def test_rephrase(self):
        text = "The team made a decision to stop the trial because costs rose."
        r = handle({"cmd": "rephrase", "text": text, "strength": 50, "restructure": 30, "seed": 1})
        alts = r["alternatives"]
        self.assertTrue(1 <= len(alts) <= 3)
        self.assertEqual(len({a.lower() for a in alts}), len(alts))
        self.assertNotIn(text, alts)
        for a in alts:
            self.assertNotIn("not", a.split())  # no negation sneaks in

    def test_rephrase_keeps_numbers(self):
        r = handle({"cmd": "rephrase", "text": "Sales rose by 12% in 2021 because demand was high.", "seed": 4})
        for a in r["alternatives"]:
            self.assertIn("12%", a)
            self.assertIn("2021", a)

    def test_rephrase_limits(self):
        with self.assertRaises(ParaphraseError):
            handle({"cmd": "rephrase", "text": ""})
        with self.assertRaises(ParaphraseError):
            handle({"cmd": "rephrase", "text": "word " * 600})


if __name__ == "__main__":
    unittest.main()
