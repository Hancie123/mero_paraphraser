"""Layer 3: semantic understanding - extract key information and factual claims to preserve.

Produces the facts each part of the text must keep: numbers, names, negations
(which flip meaning) and hedges (which set how strong a claim is). Layer 6
checks the rewrite against them.
"""

from __future__ import annotations

import re

from ..schemas.paraphrase import Context, Facts, ProcessedInput
from ..utils.text_utils import split_sentences

NUMBER_RE = re.compile(r"(?<![\w\[])[-+]?\d+(?:[.,]\d+)*%?(?![\w\]])")
NEGATION_RE = re.compile(
    r"\b(?:not|no|never|none|nor|neither|nobody|nothing|nowhere|without|cannot|lack(?:s|ed|ing)?|fail(?:s|ed)? to|"
    # negative words that carry the same meaning ("will not affect" -> "is unlikely to affect")
    r"unlikely|unable|hardly|barely|scarcely|rarely|seldom|absent|free of)\b|n['’]t\b",
    re.IGNORECASE,
)
HEDGE_RE = re.compile(
    r"\b(?:may|might|could|possibly|perhaps|probably|likely|unlikely|potentially|suggests?|suggested|"
    r"appears?|appeared|seems?|seemed|tends? to|approximately|roughly|arguably|somewhat|partly|partially)\b",
    re.IGNORECASE,
)
NUMBER_WORDS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7",
    "eight": "8", "nine": "9", "ten": "10", "eleven": "11", "twelve": "12", "twenty": "20", "hundred": "100",
    "half": "50%", "percent": "%",
}


def normalize_number(n: str) -> str:
    n = n.lstrip("+")
    return n.replace(",", "") if re.fullmatch(r"-?\d{1,3}(?:,\d{3})+(?:\.\d+)?%?", n) else n


def numbers_in(text: str) -> list[str]:
    return [normalize_number(m) for m in NUMBER_RE.findall(text)]


def facts_for(text: str, context: Context) -> Facts:
    """Facts in one (masked) part of the text."""
    return Facts(
        numbers=list(dict.fromkeys(numbers_in(text))),
        names=[n for n in context.names if n in text],
        negations=len(NEGATION_RE.findall(text)),
        hedges=len(HEDGE_RE.findall(text)),
        claims=len(split_sentences(text)),
    )


class SemanticAnalyzer:
    def analyze(self, processed: ProcessedInput, context: Context) -> Facts:
        return facts_for(processed.masked, context)
