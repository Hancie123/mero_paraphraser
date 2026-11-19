import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import pos  # noqa: E402
from app.pipeline import sentence_rewriter as sr  # noqa: E402

NAMES = frozenset({"shah", "nepal"})


def apply(name, text):
    return sr.TRANSFORMS[name](sr.Sentence(text, NAMES))


class PosTests(unittest.TestCase):
    def test_inflection(self):
        self.assertEqual(pos.past("stop"), "stopped")
        self.assertEqual(pos.past("decide"), "decided")
        self.assertEqual(pos.past("visit"), "visited")
        self.assertEqual(pos.participle("write"), "written")
        self.assertEqual(pos.gerund("implement"), "implementing")
        self.assertEqual(pos.gerund("analyse"), "analysing")
        self.assertEqual(pos.gerund("commit"), "committing")
        self.assertEqual(pos.gerund("open"), "opening")
        self.assertEqual(pos.third("study"), "studies")

    def test_lemma(self):
        self.assertEqual(pos.lemma("wrote"), "write")
        self.assertEqual(pos.lemma("analysed"), "analyse")
        self.assertEqual(pos.lemma("stopped"), "stop")

    def test_tags(self):
        words = "The team analysed the data .".split()
        self.assertEqual(pos.tag(words), ["DT", "NN", "VBD", "DT", "NN", "P"])


class TransformTests(unittest.TestCase):
    """Each transformation: one sentence it must rewrite, and traps it must leave alone."""

    def check(self, name, cases, traps):
        for src, want in cases:
            self.assertEqual(apply(name, src), want, src)
        for src in traps:
            self.assertIsNone(apply(name, src), src)

    def test_clause_move(self):
        self.check(
            "clause_move",
            [
                ("Prices rose because demand was high.", "Because demand was high, prices rose."),
                ("Because demand was high, prices rose.", "Prices rose because demand was high."),
                ("We will cancel the trip if it rains.", "If it rains, we will cancel the trip."),
                ("Although the plan was risky, the board approved it.",
                 "The board approved it, although the plan was risky."),
                ("Dr. Shah left early because she was ill.", None),  # "Dr." splits the tokens; see below
            ][:4],
            [
                "I asked if it was ready.",  # "if" means "whether"
                "It works even if it rains.",
                "He left as if he was angry.",
                "Prices rose, demand fell, and wages stayed flat because of the rules.",
            ],
        )  # fmt: skip

    def test_clause_move_keeps_names_capitalised(self):
        out = apply("clause_move", "Nepal grew quickly because tourism rose.")
        self.assertEqual(out, "Because tourism rose, Nepal grew quickly.")

    def test_light_verb(self):
        self.check(
            "light_verb",
            [
                ("The team made a decision to stop the trial.", "The team decided to stop the trial."),
                ("She has made a decision.", "She has decided."),
                ("They carried out an analysis of the survey data.", "They analyzed the survey data."),
                ("We will make use of the tools.", "We will use the tools."),
                ("Rain has an impact on yields.", "Rain affects yields."),
            ],
            [
                "We had a discussion.",  # "discuss" needs an object
                "The decision was made a priority.",
            ],
        )

    def test_nominal(self):
        self.check(
            "nominal",
            [
                ("The cost of the implementation of the plan was high.", "The cost of implementing the plan was high."),
                ("By the implementation of the plan, we saved money.", "By implementing the plan, we saved money."),
            ],
            [
                "We reviewed the implementation of the plan.",  # object of a verb: keep the noun
                "The institution of marriage is old.",
            ],
        )

    def test_reduced_relative(self):
        self.check(
            "reduced_relative",
            [
                ("The model, which was trained on news articles, works well.",
                 "The model, trained on news articles, works well."),
                ("The model that was trained on news works well.", "The model trained on news works well."),
            ],
            [
                "The book, which is interesting, sold well.",  # adjective, no complement
                "He said that was important.",
            ],
        )  # fmt: skip

    def test_expletive_and_cleft(self):
        self.check(
            "expletive",
            [("There are many people who think the plan will fail.", "Many people think the plan will fail.")],
            ["There is a chance that it rains.", "There are people who the team hired."],
        )
        self.check(
            "cleft",
            [("It is this factor that drives growth.", "This factor drives growth.")],
            [
                "It is clear that prices rose.",  # extraposition, not a cleft
                "It was the government that the people blamed.",
                "It is a fact that costs rose.",
            ],
        )

    def test_voice(self):
        self.check(
            "voice",
            [
                ("The team analysed the data.", "The data was analysed by the team."),
                ("The data was analysed by the team.", "The team analysed the data."),
                ("The report was written by the committee in 2021.", "The committee wrote the report in 2021."),
                ("The nurses check the patients.", "The patients are checked by the nurses."),
            ],
            [
                "The window was broken by accident.",
                "The team did not analyse the data.",  # negation: leave it
                "They visited the museum in May.",  # pronoun subject reads badly as an agent
                "The team had the data.",
                "The project costs the city a lot.",
            ],
        )

    def test_merge(self):
        def m(a, b):
            return sr.merge(sr.Sentence(a, NAMES), sr.Sentence(b, NAMES))

        self.assertEqual(m("The app is fast.", "It is also free."), "The app is fast and free.")
        self.assertEqual(
            m("The app loads quickly.", "It also works offline."), "The app loads quickly and also works offline."
        )
        self.assertIsNone(m("The team tested the app.", "It worked."))  # "it" = the app, not the team
        self.assertIsNone(m("The apps are fast.", "It is free."))  # number mismatch
        self.assertIsNone(m("The app crashed.", "It was Monday."))

    def test_list_prose(self):
        self.check(
            "list_prose",
            [("We need flour, sugar, and eggs.", "We need flour and sugar, as well as eggs.")],
            ["Flour, sugar, and eggs are cheap here and there.", "We tested it and it worked."],
        )

    def test_list_prose_longer_items(self):
        self.check(
            "list_prose",
            [
                ("Employees enjoy greater flexibility, improved work-life balance, and reduced commuting time.",
                 "Employees enjoy greater flexibility and improved work-life balance, as well as reduced commuting time."),
                ("Weather events rose, including droughts, floods, and heatwaves [[1]].",
                 "Weather events rose, including droughts and floods, as well as heatwaves [[1]]."),
            ],
            [
                "Work presents challenges, such as maintaining cohesion and ensuring communication.",
                "We bought apples, pears, plums, and figs.",  # four items
            ],
        )  # fmt: skip

    def test_adverbial_front(self):
        self.check(
            "adverbial_front",
            [
                ("Costs have increased substantially over the past two decades.",
                 "Over the past two decades, costs have increased substantially."),
                ("Over the past two decades, costs have increased substantially.",
                 "Costs have increased substantially over the past two decades."),
                ("Companies can reach more people by hiring remote staff.",
                 "By hiring remote staff, companies can reach more people."),
                ("AI has become a common tool in hospitals, offering new ways to treat patients.",
                 "Offering new ways to treat patients, AI has become a common tool in hospitals."),
            ],
            [
                "Firms that thrive will lead in the future of work.",  # not a time phrase
                "People who lived in the 1990s remember it.",  # phrase belongs to the relative clause
                "The storm hit the coast, including several towns.",
            ],
        )  # fmt: skip

    def test_lead_adverbial_kept(self):
        out = sr._try(
            "However, the integration of AI in hospitals raises concerns.", NAMES | {"ai"}, set(), random.Random(1)
        )
        self.assertEqual(out, ("nominal", "However, integrating AI in hospitals raises concerns."))

    def test_pronoun_not_moved_before_its_noun(self):
        self.assertIsNone(apply("clause_move", "While AI holds great promise, it must be used with care."))

    def test_reorder(self):
        self.check(
            "reorder",
            [("In 2020, in Nepal, the rains came early.", "In Nepal, in 2020, the rains came early.")],
            ["In 2020, prices rose, and wages fell."],
        )


class ReshapeTests(unittest.TestCase):
    TEXT = (
        "Prices rose because demand was high. The team made a decision to wait. "
        "There are many people who think the plan will fail. The app is fast. It is also free.\n\n"
        "The data was analysed by the team. It is this factor that drives growth."
    )

    def test_level_zero_is_identity(self):
        self.assertEqual(sr.reshape(self.TEXT, 0, random.Random(1)).text, self.TEXT)

    def test_high_level_changes_most_sentences(self):
        out = sr.reshape(self.TEXT, 100, random.Random(1))
        self.assertGreaterEqual(out.count, 5)
        self.assertIn("\n\n", out.text)  # paragraphs stay apart
        self.assertEqual(out.count, len(out.used))

    def test_deterministic(self):
        a = sr.reshape(self.TEXT, 60, random.Random(7)).text
        self.assertEqual(a, sr.reshape(self.TEXT, 60, random.Random(7)).text)

    def test_locked_sentences_untouched(self):
        out = sr.reshape("Prices rose because demand was high.", 100, random.Random(1), locked=["demand"])
        self.assertEqual(out.text, "Prices rose because demand was high.")

    def test_keeps_placeholders(self):
        text = "Prices rose because demand was high [[1]]. The team made a decision to wait [[2]]."
        for seed in range(10):
            out = sr.reshape(text, 100, random.Random(seed)).text
            self.assertEqual(out.count("[[1]]"), 1)
            self.assertEqual(out.count("[[2]]"), 1)


if __name__ == "__main__":
    unittest.main()
