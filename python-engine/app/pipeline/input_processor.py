"""Layer 1: input processing - text cleaning, paragraph splitting and citation extraction.

Citations, direct quotations, links and code are replaced by ``[[n]]`` tokens
before rewriting so the model can't alter them; Layer 7 checks they all come
back exactly once. A trailing reference list is split off and kept verbatim.
"""

from __future__ import annotations

import re
import unicodedata

from ..schemas.paraphrase import ProcessedInput, Protected
from ..utils.document_utils import count_paragraphs, split_references
from ..utils.text_utils import PLACEHOLDER_RE, split_sentences, word_count

_YEAR = r"\b(?:1[5-9]\d\d|20\d\d)[a-z]?\b"
_NAME = r"[A-Z][\w'’-]+"

# Order matters: at the same position the earlier pattern wins.
PATTERNS: list[tuple[str, str]] = [
    # A literal "[[n]]" in the user's text would be mistaken for one of our tokens.
    ("code", r"\[\[\s*\d+\s*\]\]"),
    ("url", r"https?://[^\s<>\"]+[^\s<>\".,;:!?)\]]|www\.[^\s<>\"]+[^\s<>\".,;:!?)\]]"),
    ("email", r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"),
    ("doi", r"\b(?:doi:\s*)?10\.\d{4,9}/[^\s\"<>]+[^\s\"<>.,;:!?)\]]"),
    ("code", r"`[^`\n]+`"),
    ("quote", r"“[^”\n]{1,600}”|\"[^\"\n]{1,600}\""),
    # (Smith, 2020), (Smith & Lee, 2019; Wang et al., 2021, p. 4), (see WHO, 2020)
    ("citation", r"\((?=[^()\n]*" + _YEAR + r")(?=[^()\n]*[A-Z])[^()\n]{2,250}\)"),
    # Smith (2020), Smith et al. (2020, p. 12), Smith and Lee (2019)
    ("citation", _NAME + r"(?:\s+(?:et\s+al\.|(?:and|&)\s+" + _NAME + r"))?\s+\(" + _YEAR
     + r"(?:,\s*pp?\.\s*\d+(?:\s*[-–]\s*\d+)?)?\)"),
    # [1], [2, 5], [3-7]
    ("citation", r"\[\d+(?:\s*[-–,]\s*\d+)*\]"),
]
PROTECT_RE = re.compile("|".join(f"(?P<p{i}>{pat})" for i, (_, pat) in enumerate(PATTERNS)))
KINDS = [kind for kind, _ in PATTERNS]
CITATION_RE = re.compile("|".join(f"(?:{pat})" for kind, pat in PATTERNS if kind == "citation"))

_INVISIBLE = dict.fromkeys(map(ord, "​‌‍⁠﻿­"), None)


def clean(text: str) -> str:
    """Normalise line endings and invisible characters without changing the wording."""
    text = unicodedata.normalize("NFC", text).translate(_INVISIBLE)
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace(" ", " ")
    text = re.sub(r"[ \t]+\n", "\n", text)  # trailing spaces
    return re.sub(r"\n{3,}", "\n\n", text)


def protect(text: str) -> tuple[str, list[Protected]]:
    protected: list[Protected] = []

    def sub(m: re.Match) -> str:
        kind = KINDS[int(m.lastgroup[1:])]
        p = Protected(len(protected) + 1, kind, m.group())
        protected.append(p)
        return p.token

    return PROTECT_RE.sub(sub, text), protected  # one pass, so our tokens are never re-matched


def restore(masked: str, protected: list[Protected]) -> str:
    by_index = {p.index: p.text for p in protected}
    return PLACEHOLDER_RE.sub(lambda m: by_index.get(int(m.group(1)), m.group()), masked)


class InputProcessor:
    def process(self, text: str) -> ProcessedInput:
        cleaned = clean(text)
        body, references = split_references(cleaned)
        masked, protected = protect(body)
        return ProcessedInput(
            original=text,
            body=body,
            references=references,
            masked=masked,
            protected=protected,
            paragraphs=count_paragraphs(body),
            sentences=len(split_sentences(body)),
            words=word_count(body),
        )
