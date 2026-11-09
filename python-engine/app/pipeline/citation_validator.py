"""Layer 7: citation validation - citations, quotations and references.

Per part (before restoring tokens): every [[n]] token comes back exactly once,
and the model didn't invent new citations. On the final text: every protected
citation, quotation and link is present verbatim, and the reference list is
unchanged.
"""

from __future__ import annotations

from collections import Counter

from ..schemas.paraphrase import ProcessedInput
from ..utils.text_utils import PLACEHOLDER_RE
from .input_processor import CITATION_RE


def check_tokens(source: str, output: str) -> tuple[list[str], bool]:
    """Returns (issues, critical). Critical issues mean the part can't be used as is."""
    want = Counter(PLACEHOLDER_RE.findall(source))
    got = Counter(PLACEHOLDER_RE.findall(output))
    issues: list[str] = []
    missing = sorted(set(want) - set(got), key=int)
    extra = sorted(set(got) - set(want), key=int)
    doubled = sorted((t for t in want if got[t] > want[t]), key=int)
    if missing:
        issues.append(f"Dropped {len(missing)} citation or quotation marker(s): " + ", ".join(f"[[{t}]]" for t in missing) + ".")
    if extra or doubled:
        issues.append("Repeated or unknown citation markers.")
    invented = CITATION_RE.findall(PLACEHOLDER_RE.sub(" ", output))
    if invented:
        issues.append(f"Added a citation that isn't in the original: {invented[0]}.")
    return issues, bool(issues)


class CitationValidator:
    def validate(self, processed: ProcessedInput, final_text: str) -> dict:
        body = final_text[: len(final_text) - len(processed.references)] if processed.references else final_text
        missing = [p for p in processed.protected if p.text not in body]
        references_ok = not processed.references or final_text.endswith(processed.references)
        return {
            "citations": processed.count("citation"),
            "quotes": processed.count("quote"),
            "links": processed.count("url") + processed.count("doi") + processed.count("email"),
            "references": bool(processed.references),
            "references_ok": references_ok,
            "missing": [p.text for p in missing],
            "ok": not missing and references_ok,
        }
