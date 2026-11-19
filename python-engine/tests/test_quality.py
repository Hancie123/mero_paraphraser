"""Guards output quality: fails when a change makes the sample passages read less human.

Runs tools/eval_humanness.py's local metrics (offline, seeded, so deterministic) over
tools/samples/*.txt and compares them with tests/data/humanness_baseline.json.

A change that improves the numbers passes; refresh the baseline so the gain is locked in:

    UPDATE_BASELINE=1 python -m unittest python-engine/tests/test_quality.py      (bash)
    $env:UPDATE_BASELINE=1; python -m unittest python-engine/tests/test_quality.py (PowerShell)

and commit the updated JSON with the change, so the diff shows what moved.
"""

import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from eval_humanness import measure  # noqa: E402

from app.core.config import MODES  # noqa: E402

SAMPLES = ROOT / "tools" / "samples"
BASELINE = Path(__file__).with_name("data") / "humanness_baseline.json"
STRENGTH, SEED = 60, 7
# Slack for small, harmless shifts; anything bigger is a real regression.
SCORE_TOLERANCE = 0.05
BURSTINESS_TOLERANCE = 0.05
KEYS = ("burstiness_out", "patterns_out", "human_score", "meaning_ok")


def current() -> dict[str, dict]:
    out = {}
    for mode in MODES:
        for f in sorted(SAMPLES.glob("*.txt")):
            row = measure(f.read_text(encoding="utf-8").strip(), mode, STRENGTH, SEED)
            out[f"{mode}/{f.name}"] = {k: row[k] for k in KEYS}
    return out


class QualityRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = current()
        if os.environ.get("UPDATE_BASELINE"):
            BASELINE.parent.mkdir(exist_ok=True)
            BASELINE.write_text(json.dumps(cls.results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        cls.baseline = json.loads(BASELINE.read_text(encoding="utf-8"))

    def test_every_sample_has_a_baseline(self):
        self.assertEqual(sorted(self.results), sorted(self.baseline), "samples changed: refresh the baseline")

    def test_no_sample_got_worse(self):
        for key, base in self.baseline.items():
            now = self.results.get(key)
            if now is None:
                continue
            with self.subTest(sample=key):
                if base["meaning_ok"]:
                    self.assertTrue(now["meaning_ok"], "fact check now fails")
                self.assertLessEqual(
                    len(now["patterns_out"]),
                    len(base["patterns_out"]),
                    f"more AI-typical patterns: {now['patterns_out']} (was {base['patterns_out']})",
                )
                self.assertGreaterEqual(now["burstiness_out"], base["burstiness_out"] - BURSTINESS_TOLERANCE)
                if base["human_score"] is not None:
                    self.assertIsNotNone(now["human_score"])
                    self.assertGreaterEqual(now["human_score"], base["human_score"] - SCORE_TOLERANCE)


if __name__ == "__main__":
    unittest.main()
