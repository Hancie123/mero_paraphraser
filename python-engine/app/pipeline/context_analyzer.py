"""Layer 2: context analysis - meaning, arguments, terminology and relationships.

Rule-based on purpose: every extra model call costs seconds on a CPU, and these
signals are reliable to detect from the text itself.
"""

from __future__ import annotations

import re
from collections import Counter

from ..schemas.paraphrase import Context, ProcessedInput
from ..utils.text_utils import STOPWORDS, avg_sentence_length, split_sentences

_ACRONYM = re.compile(r"\b[A-Z][A-Z0-9&]*(?:-[A-Z0-9]+)*[A-Z0-9]s?\b")
_CAP_RUN = re.compile(r"\b[A-Z][a-z][\w'’-]*(?:\s+(?:of|the|and|for|de|van|von|la)?\s*[A-Z][a-z][\w'’-]*)*")
_LEAD_WORDS = {"The", "A", "An", "This", "That", "These", "Those", "In", "On", "At", "For", "However", "But",
               "And", "It", "We", "They", "He", "She", "I", "If", "When", "While", "As", "Our", "Their", "My",
               "Its", "Many", "Some", "Most", "All", "Each", "Every", "There", "Here", "Although", "Because"}

RELATIONSHIPS = {
    "contrast": r"\b(?:however|but|although|though|whereas|yet|nevertheless|nonetheless|despite|in contrast|on the other hand|while)\b",
    "cause and effect": r"\b(?:because|since|therefore|thus|consequently|as a result|hence|due to|leads? to|led to|so that|results? in)\b",
    "condition": r"\b(?:if|unless|provided that|as long as|only when)\b",
    "addition": r"\b(?:moreover|furthermore|in addition|additionally|also)\b",
    "comparison": r"\b(?:similarly|likewise|compared (?:to|with)|than)\b",
    "example": r"\b(?:for example|for instance|such as|e\.g\.)\b",
    "sequence": r"\b(?:first(?:ly)?|second(?:ly)?|then|finally|subsequently|afterwards)\b",
}
_ACADEMIC = re.compile(
    r"\b(?:study|studies|research|researchers|findings|analysis|analy[sz]ed|evidence|hypothes[ie]s|data|"
    r"participants|results|theory|theoretical|framework|methodology|literature|significant(?:ly)?|"
    r"empirical|et al|suggests?|indicates?|demonstrates?|examined?|investigat\w+)\b",
    re.IGNORECASE,
)
_PROFESSIONAL = re.compile(
    r"\b(?:client|customer|stakeholders?|team|meeting|project|deadline|quarter|revenue|budget|policy|"
    r"please|regards|proposal|report|management|strategy)\b",
    re.IGNORECASE,
)


def proper_names(text: str) -> list[str]:
    """Acronyms and capitalised names that appear mid-sentence (so they aren't just sentence starts)."""
    names: list[str] = []
    for sentence in split_sentences(text):
        for m in _CAP_RUN.finditer(sentence):
            run = m.group()
            first = m.start() == len(sentence) - len(sentence.lstrip("\"“‘([")) or m.start() == 0
            parts = run.split()
            if first:
                if parts[0] in _LEAD_WORDS:
                    parts = parts[1:]
                if len(parts) < 2:
                    continue  # a single capitalised word at sentence start is usually not a name
            name = " ".join(parts).strip()
            if name and name not in _LEAD_WORDS:
                names.append(name)
    names += _ACRONYM.findall(text)
    seen: dict[str, None] = {}
    for n in names:
        if len(n) > 1 and n != "I":
            seen.setdefault(n, None)
    return list(seen)


def key_terms(text: str, names: list[str], limit: int = 8) -> list[str]:
    """Repeated content words and two-word phrases: the vocabulary the text is about."""
    lowered = text.lower()
    tokens = re.findall(r"[a-z][a-z'-]{3,}", lowered)
    name_words = {w.lower() for n in names for w in n.split()}
    content = [t for t in tokens if t not in STOPWORDS and t not in name_words]
    bigrams = Counter(
        f"{a} {b}" for a, b in zip(content, content[1:]) if f"{a} {b}" in lowered
    )
    terms = [b for b, n in bigrams.most_common() if n >= 2][:limit]
    singles = Counter(t for t in content if len(t) >= 6)
    for w, n in singles.most_common():
        if n >= 3 and not any(w in t for t in terms):
            terms.append(w)
    return terms[:limit]


class ContextAnalyzer:
    def analyze(self, processed: ProcessedInput) -> Context:
        text = processed.body
        names = proper_names(processed.masked)
        relationships = [name for name, pat in RELATIONSHIPS.items() if re.search(pat, text, re.IGNORECASE)]

        academic = len(_ACADEMIC.findall(text)) + 3 * processed.count("citation")
        professional = len(_PROFESSIONAL.findall(text))
        long_sentences = avg_sentence_length(text) >= 18
        if processed.count("citation") or (academic >= 3 and long_sentences) or academic >= 5:
            register = "academic"
        elif professional >= 2:
            register = "professional"
        else:
            register = "general"

        return Context(register, names, key_terms(processed.masked, names), relationships)
