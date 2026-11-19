"""Engine settings: limits and modes."""

from __future__ import annotations

VERSION = "0.1.0"

MAX_CHARS = 20_000
CHUNK_CHARS = 1_500  # the rewriting layer works a few paragraphs at a time
MAX_ATTEMPTS = 2  # a part that fails validation is rewritten once more

MODES = {"humanize": "Humanize"}  # mode id -> label
LENGTH = (0.55, 1.7)  # allowed output/input word ratio per part

# Words that make text read as AI-written. tools/build_lexicon.py never offers
# them as synonyms. Multi-word phrases are handled by Layer 5 (language_refiner).
AVOID_WORDS: frozenset[str] = frozenset(
    {
        "delve",
        "delves",
        "delved",
        "delving",
        "tapestry",
        "testament",
        "multifaceted",
        "realm",
        "seamless",
        "seamlessly",
        "embark",
        "showcasing",
        "underscore",
        "underscores",
        "pivotal",
        "intricate",
        "moreover",
        "furthermore",
        "additionally",
        "notably",
        "crucial",
        "leverage",
        "foster",
        "robust",
        "heightened",
        "meticulous",
        "meticulously",
        "paramount",
        "commendable",
        "unwavering",
        "holistic",
        "synergy",
        "bustling",
        "vibrant",
        "nuanced",
        "utilize",
        "utilizes",
        "utilized",
        "facilitate",
        "facilitates",
        "endeavor",
        "endeavors",
        "myriad",
        "plethora",
        "invaluable",
        "noteworthy",
        "profound",
        "transformative",
        "elevate",
        "elevates",
        "dynamically",
        "landscape",
    }
)


def drafts_for(strength: int) -> int:
    """Drafts Layer 4 writes per part (different seeds); the most human-sounding one is kept."""
    return 2 if strength < 34 else 3
