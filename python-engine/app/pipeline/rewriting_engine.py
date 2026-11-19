"""Layer 4: rewriting engine - rewrite each part in the right style.

Rewrites one part at a time with the rule-based engine (app/core/rule_engine.py).
``drafts`` writes several versions with different seeds so the orchestrator can
keep the one that reads most human (see humanizer.py).
"""

from __future__ import annotations

from ..core import rule_engine
from ..core.config import MODES


class RewritingEngine:
    name = "basic"

    def rewrite(self, text: str, mode: str, strength: int, seed: int | None, retry: bool = False) -> str:
        return self.drafts(text, mode, strength, seed, retry, 1)[0]

    def drafts(self, text: str, mode: str, strength: int, seed: int | None, retry: bool = False,
               n: int = 1) -> list[str]:
        """``n`` different rewrites of ``text``. A retry shifts the seeds so it gets new wording."""
        bump = 1 if retry else 0
        seeds = [None if seed is None else seed + k * 101 + bump for k in range(n)]
        return [rule_engine.paraphrase(text, MODES[mode].rule_mode, strength, s)["text"] for s in seeds]
