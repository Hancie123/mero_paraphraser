"""Data passed between the API and the eight pipeline layers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from ..core.config import MAX_CHARS, MODE_ALIASES, MODES

ENGINES = ("auto", "ai", "basic")


class ParaphraseError(ValueError):
    """Invalid input or a failure the user should see (bad mode, text too long, model error...)."""


@dataclass
class ParaphraseRequest:
    text: str
    mode: str = "standard"
    strength: int = 50
    seed: int | None = None
    engine: str = "basic"  # "auto" | "ai" | "basic"

    @classmethod
    def from_dict(cls, d: dict) -> "ParaphraseRequest":
        text = d.get("text", "")
        if not isinstance(text, str):
            raise ParaphraseError("text must be a string")
        if len(text) > MAX_CHARS:
            raise ParaphraseError(f"text is too long ({len(text):,} characters, max {MAX_CHARS:,})")
        mode = MODE_ALIASES.get(d.get("mode", "standard"), d.get("mode", "standard"))
        if mode not in MODES:
            raise ParaphraseError(f"unknown mode {mode!r}; choose one of {', '.join(MODES)}")
        engine = d.get("engine", "basic")
        if engine not in ENGINES:
            raise ParaphraseError(f"unknown engine {engine!r}; choose one of {', '.join(ENGINES)}")
        try:
            strength = max(0, min(100, int(d.get("strength", 50))))
        except (TypeError, ValueError):
            raise ParaphraseError("strength must be a number from 0 to 100") from None
        seed = d.get("seed")
        return cls(text, mode, strength, None if seed is None else int(seed), engine)


@dataclass
class Protected:
    """A span kept out of the rewrite (Layer 1) and checked afterwards (Layer 7)."""

    index: int
    kind: str  # citation | quote | url | email | doi | code
    text: str

    @property
    def token(self) -> str:
        return f"[[{self.index}]]"


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
    issues: list[str] = field(default_factory=list)
    critical: bool = False
    meaning_score: int | None = None  # 1-5 from the model's meaning check
    kept_original: bool = False
    # human-like output (humanizer.py)
    drafts: int = 0  # drafts written per attempt
    human_score: float | None = None  # higher reads more human
    restructured: int = 0  # Layer 5 edits against AI-typical structure
    swaps: int = 0  # predictable words swapped for synonyms
    sentence_rewrites: int = 0  # flat sentences rewritten
    patterns: list[str] = field(default_factory=list)  # AI-typical structures still present


@dataclass
class LayerReport:
    id: str
    name: str
    status: str  # ok | warning
    detail: str

    def to_dict(self) -> dict:
        return asdict(self)
