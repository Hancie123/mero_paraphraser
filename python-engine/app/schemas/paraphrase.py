"""Data passed between the API and the eight pipeline layers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from ..core.config import MAX_CHARS, MODES
from ..core.preferences import MAX_ITEMS, MAX_LEN, NONE, Preferences


class ParaphraseError(ValueError):
    """Invalid input or a failure the user should see (bad mode, text too long...)."""


@dataclass
class ParaphraseRequest:
    text: str
    mode: str = "humanize"
    strength: int = 50
    seed: int | None = None
    prefs: Preferences = NONE
    # How much Layer 4b restructures sentences (0-100), separate from ``strength`` (word changes).
    restructure: int = 50

    @classmethod
    def from_dict(cls, d: dict) -> ParaphraseRequest:
        text = d.get("text", "")
        if not isinstance(text, str):
            raise ParaphraseError("text must be a string")
        if len(text) > MAX_CHARS:
            raise ParaphraseError(f"text is too long ({len(text):,} characters, max {MAX_CHARS:,})")
        mode = d.get("mode", "humanize")
        if mode not in MODES:
            raise ParaphraseError(f"unknown mode {mode!r}; choose one of {', '.join(MODES)}")
        try:
            strength = max(0, min(100, int(d.get("strength", 50))))
        except (TypeError, ValueError):
            raise ParaphraseError("strength must be a number from 0 to 100") from None
        try:  # older clients send only "strength"; it then sets both
            restructure = max(0, min(100, int(d.get("restructure", strength))))
        except (TypeError, ValueError):
            raise ParaphraseError("restructure must be a number from 0 to 100") from None
        seed = d.get("seed")
        return cls(text, mode, strength, None if seed is None else int(seed), _preferences(d), restructure)


def _strings(value: object, what: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ParaphraseError(f"{what} must be a list of strings")
    if len(value) > MAX_ITEMS:
        raise ParaphraseError(f"at most {MAX_ITEMS} {what}")
    for v in value:
        if len(v) > MAX_LEN:
            raise ParaphraseError(f"{what} must be at most {MAX_LEN} characters each")
    return value


def _preferences(d: dict) -> Preferences:
    """``locked_terms`` and ``banned``: lists of strings; ``preferred``: {word: replacement}."""
    preferred = d.get("preferred") or {}
    if not isinstance(preferred, dict):
        raise ParaphraseError("preferred must be an object of word -> replacement")
    words = _strings(list(preferred), "preferred words")
    repls = _strings(list(preferred.values()), "preferred replacements")
    return Preferences.build(
        _strings(d.get("locked_terms"), "locked terms"),
        dict(zip(words, repls)),
        _strings(d.get("banned"), "banned words"),
    )


@dataclass
class Protected:
    """A span kept out of the rewrite (Layer 1) and checked afterwards (Layer 7)."""

    index: int
    kind: str  # citation | quote | url | email | doi | code | math | codeblock | data | heading | locked
    text: str
    lang: str = ""  # codeblock language
    label: str = ""  # heading / locked section name
    replacement: str | None = None  # codeblock with reworded comments (code verified unchanged)

    @property
    def token(self) -> str:
        return f"[[{self.index}]]"

    @property
    def output(self) -> str:
        return self.text if self.replacement is None else self.replacement


@dataclass
class ProcessedInput:
    """Layer 1 output."""

    original: str
    body: str  # cleaned text without the reference list
    references: str  # reference list (with its heading), kept verbatim
    masked: str  # body with protected spans replaced by [[n]] tokens
    protected: list[Protected]
    paragraphs: int
    sentences: int
    words: int
    invisible: int = 0  # invisible / look-alike characters removed by clean()
    sections: list[tuple[str, bool]] = field(default_factory=list)  # (heading, locked)

    def count(self, kind: str) -> int:
        return sum(1 for p in self.protected if p.kind == kind)


@dataclass
class Context:
    """Layer 2 output."""

    register: str  # academic | professional | general
    names: list[str]  # proper nouns and acronyms that must not change
    terms: list[str]  # repeated key terms to keep consistent
    relationships: list[str]  # logical relations between ideas (contrast, cause...)


@dataclass
class Facts:
    """Layer 3 output: what a correct paraphrase must keep."""

    numbers: list[str] = field(default_factory=list)
    names: list[str] = field(default_factory=list)
    negations: int = 0
    hedges: int = 0
    claims: int = 0  # sentences that state something


@dataclass
class ChunkResult:
    """One part of the text as it moves through layers 4 to 7."""

    index: int
    source: str  # masked source text of this part
    output: str = ""  # masked rewritten text
    rewrite: bool = True  # False for blank separators
    attempts: int = 0
    fixes: int = 0  # Layer 5 corrections
    phrases: int = 0  # Layer 5 stock-phrase replacements
    dashes: int = 0  # Layer 5 em dashes replaced
    issues: list[str] = field(default_factory=list)
    critical: bool = False
    kept_original: bool = False
    restored_sentences: int = 0  # sentences put back because the rewrite lost a number, negation or hedge
    # human-like output (humanizer.py)
    drafts: int = 0  # drafts written per attempt
    human_score: float | None = None  # higher reads more human
    restructured: int = 0  # Layer 5 edits against AI-typical structure
    reshaped: int = 0  # Layer 4b sentence transformations (sentence_rewriter.py)
    patterns: list[str] = field(default_factory=list)  # AI-typical structures still present


@dataclass
class LayerReport:
    id: str
    name: str
    status: str  # ok | warning
    detail: str

    def to_dict(self) -> dict:
        return asdict(self)
