"""Layer 1: input processing - text cleaning, paragraph splitting and citation extraction.

Section-aware: code blocks, tables, display math, headings and locked
sections (Declarations, Funding, Data availability...) are found first by
sections.py and kept out of the rewrite as whole blocks. Invisible characters
are purged by utils/invisible.py.

Citations, direct quotations, links, inline code and math are replaced by ``[[n]]`` tokens
before rewriting so the rewrite can't alter them; Layer 7 checks they all come
back exactly once. A trailing reference list is split off and kept verbatim.
"""

from __future__ import annotations

import re
import unicodedata

from ..schemas.paraphrase import ProcessedInput, Protected
from ..utils.document_utils import count_paragraphs, split_references
from ..utils.invisible import purge
from ..utils.text_utils import PLACEHOLDER_RE, split_sentences, word_count
from .sections import Layout, analyze

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
    # inline math: $x^2$ and \(a+b\), but not "$5 and $10"
    ("math", r"\$(?=[^\s$\d])[^$\n]{1,200}(?<=\S)\$(?!\d)|\\\([^\n]{1,200}?\\\)"),
    ("quote", r"“[^”\n]{1,600}”|\"[^\"\n]{1,600}\""),
    # (Smith, 2020), (Smith & Lee, 2019; Wang et al., 2021, p. 4), (see WHO, 2020)
    ("citation", r"\((?=[^()\n]*" + _YEAR + r")(?=[^()\n]*[A-Z])[^()\n]{2,250}\)"),
    # Smith (2020), Smith et al. (2020, p. 12), Smith and Lee (2019)
    (
        "citation",
        _NAME
        + r"(?:\s+(?:et\s+al\.|(?:and|&)\s+"
        + _NAME
        + r"))?\s+\("
        + _YEAR
        + r"(?:,\s*pp?\.\s*\d+(?:\s*[-–]\s*\d+)?)?\)",
    ),
    # [1], [2, 5], [3-7]
    ("citation", r"\[\d+(?:\s*[-–,]\s*\d+)*\]"),
]
PROTECT_RE = re.compile("|".join(f"(?P<p{i}>{pat})" for i, (_, pat) in enumerate(PATTERNS)))
KINDS = [kind for kind, _ in PATTERNS]
CITATION_RE = re.compile("|".join(f"(?:{pat})" for kind, pat in PATTERNS if kind == "citation"))


def clean_count(text: str) -> tuple[str, int]:
    """Normalise line endings and invisible characters without changing the wording.

    Returns the text and how many invisible or look-alike characters were removed
    (see utils/invisible.py for what is kept: Devanagari joiners, emoji sequences...).
    """
    text, removed = purge(unicodedata.normalize("NFC", text))
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)  # trailing spaces
    return re.sub(r"\n{3,}", "\n\n", text), removed


def clean(text: str) -> str:
    return clean_count(text)[0]


def _protect_inline(text: str, protected: list[Protected]) -> str:
    def sub(m: re.Match) -> str:
        kind = KINDS[int(m.lastgroup[1:])]
        p = Protected(len(protected) + 1, kind, m.group())
        protected.append(p)
        return p.token

    return PROTECT_RE.sub(sub, text)  # one pass, so our tokens are never re-matched


def protect(text: str, layout: Layout | None = None) -> tuple[str, list[Protected]]:
    """Replace protected spans with [[n]] tokens.

    Whole blocks first (code, tables, math, headings, locked sections; see sections.py),
    then inline spans (citations, quotations, links, inline code, math) in the prose between them.
    """
    layout = analyze(text) if layout is None else layout
    protected: list[Protected] = []
    out: list[str] = []
    pos = 0
    for b in layout.blocks:
        out.append(_protect_inline(text[pos : b.start], protected))
        p = Protected(len(protected) + 1, b.kind, text[b.start : b.end], b.lang, b.label)
        protected.append(p)
        out.append(p.token)
        pos = b.end
    out.append(_protect_inline(text[pos:], protected))
    return "".join(out), protected


def restore(masked: str, protected: list[Protected]) -> str:
    by_index = {p.index: p.output for p in protected}
    return PLACEHOLDER_RE.sub(lambda m: by_index.get(int(m.group(1)), m.group()), masked)


class InputProcessor:
    def process(self, text: str) -> ProcessedInput:
        cleaned, invisible = clean_count(text)
        body, references = split_references(cleaned)
        layout = analyze(body)
        masked, protected = protect(body, layout)
        return ProcessedInput(
            original=text,
            body=body,
            references=references,
            masked=masked,
            protected=protected,
            paragraphs=count_paragraphs(body),
            sentences=len(split_sentences(body)),
            words=word_count(body),
            invisible=invisible,
            sections=layout.sections,
        )
