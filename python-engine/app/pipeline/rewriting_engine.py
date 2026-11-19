"""Layer 4: rewriting engine - rewrite each part so it reads naturally.

Rewrites one part at a time with the rule-based engine (app/core/rule_engine.py).
``drafts`` writes several versions with different seeds so the orchestrator can
keep the one that reads most human (see humanizer.py).
"""

from __future__ import annotations

from ..core import rule_engine
from ..core.preferences import NONE, Preferences


class RewritingEngine:
    def drafts(
        self, text: str, strength: int, seed: int | None, retry: bool = False, n: int = 1, prefs: Preferences = NONE
    ) -> list[str]:
        """``n`` different rewrites of ``text``. A retry shifts the seeds so it gets new wording."""
        return [self.draft(text, strength, s, prefs) for s in self.seeds(seed, retry, n)]

    @staticmethod
    def seeds(seed: int | None, retry: bool = False, n: int = 1) -> list[int | None]:
        """One seed per draft; 101 is an arbitrary stride that keeps drafts apart."""
        bump = 1 if retry else 0
        return [None if seed is None else seed + k * 101 + bump for k in range(n)]

    def draft(self, text: str, strength: int, seed: int | None, prefs: Preferences = NONE) -> str:
        return rule_engine.paraphrase(text, strength, seed, prefs)["text"]
