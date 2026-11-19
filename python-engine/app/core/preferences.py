"""The user's word preferences: locked terms, preferred synonyms and banned synonyms.

* Locked terms ("Mero Paraphraser", "p-value") are masked in Layer 1 like a
  citation, so no layer can change them. Matching ignores case.
* A preferred synonym ("utilize" -> "use") is what the rule engine swaps that
  word or phrase for, whenever it swaps it. It overrides the built-in groups,
  and words outside them become swappable too. Only the exact form matches.
* A banned word is never put into the text: not by a swap, not by Layer 5, and
  not as an editor suggestion.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

MAX_ITEMS = 500  # per list; checked by ParaphraseRequest.from_dict
MAX_LEN = 100


@dataclass(frozen=True)
class Preferences:
    locked: tuple[str, ...] = ()
    preferred: dict[str, str] = field(default_factory=dict)  # lowercase word or phrase -> replacement
    banned: frozenset[str] = frozenset()  # lowercase words

    @classmethod
    def build(cls, locked: list[str], preferred: dict[str, str], banned: list[str]) -> Preferences:
        """From already validated strings: normalises spacing and case, drops blanks."""

        def norm(t: str) -> str:
            return " ".join(t.split())

        terms = {norm(t).lower(): norm(t) for t in locked if norm(t)}
        prefs = {norm(w).lower(): norm(r) for w, r in preferred.items() if norm(w) and norm(r)}
        prefs = {w: r for w, r in prefs.items() if w != r.lower()}
        bans = frozenset(norm(b).lower() for b in banned if norm(b))
        # Longest first, so "Mero Paraphraser" wins over "Mero".
        return cls(tuple(sorted(terms.values(), key=len, reverse=True)), prefs, bans)

    def __bool__(self) -> bool:
        return bool(self.locked or self.preferred or self.banned)

    def allows(self, candidate: str) -> bool:
        """False if ``candidate`` is a banned word or phrase, or contains a banned word."""
        if not self.banned:
            return True
        low = candidate.lower()
        return low not in self.banned and not any(w in self.banned for w in re.findall(r"[\w'’-]+", low))

    def locked_re(self) -> re.Pattern | None:
        """One pattern matching any locked term as a whole word, ignoring case."""
        if not self.locked:
            return None
        alts = "|".join(re.escape(t).replace(r"\ ", r"\s+") for t in self.locked)
        return re.compile(rf"(?<![\w-])(?:{alts})(?![\w-])", re.IGNORECASE)


NONE = Preferences()
