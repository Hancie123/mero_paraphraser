"""Layer 1 helper: find the parts of a document that must not be reworded as prose.

Block kinds:
    codeblock  fenced (```lang) or unfenced code. Only its comments may be
               reworded, by code_guard.py, which checks the code itself is unchanged.
    math       display math ($$...$$, \\[...\\], LaTeX equation environments)
    data       tables (Markdown pipes, tab-separated or numeric rows) and LaTeX tables
    heading    section headings ("Abstract", "2.1 Methods", "## Results")
    locked     whole sections kept verbatim: Declarations, Funding, Conflicts of
               interest, Data availability, Author contributions, Keywords...

Prose sections (Abstract, Introduction, Discussion, Conclusion...) are rewritten as usual.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Block:
    start: int
    end: int
    kind: str
    lang: str = ""
    label: str = ""


@dataclass
class Layout:
    blocks: list[Block] = field(default_factory=list)
    sections: list[tuple[str, bool]] = field(default_factory=list)  # (heading, locked)


_PROSE_SECTIONS = (
    r"abstract|summary|executive summary|overview|introduction|background|literature review|related work|"
    r"theoretical framework|methods?|methodology|materials and methods|research design|approach|"
    r"results?|findings|analysis|discussion|results and discussion|implications|limitations|"
    r"future (?:work|research)|recommendations|conclusions?|concluding remarks|case study"
)
_LOCKED_SECTIONS = (
    r"declarations?|declaration of (?:competing )?interests?|competing interests?|conflicts? of interests?|"
    r"disclosures?|funding(?: information| statement| sources)?|financial support|acknowledge?ments?|"
    r"author(?:s'?|'s)? contributions?|credit authorship contribution statement|author information|"
    r"data(?: availability)?(?: statement)?|availability of data(?: and materials)?|data and code availability|"
    r"code availability|ethics(?: approval| statement| declarations?)?(?: and consent to participate)?|"
    r"ethical (?:approval|considerations|statement)|(?:informed )?consent(?: to participate| for publication)?|"
    r"institutional review board statement|keywords|key words|abbreviations|nomenclature|glossary|"
    r"supplementary (?:materials?|information|data)|supporting information|appendix(?: [A-Z0-9]+)?|appendices|"
    r"orcid|trial registration"
)
_NUMBERING = r"(?:(?:\d+(?:\.\d+)*|[IVXLC]+|[A-Z])[.)]?\s+)?"
_HEADING_RE = re.compile(
    r"^[ \t]*(?:#{1,6}[ \t]*)?(?:\*\*)?"
    + _NUMBERING
    + r"(?P<name>"
    + _PROSE_SECTIONS
    + "|"
    + _LOCKED_SECTIONS
    + r")(?:\*\*)?[ \t]*:?[ \t]*$",
    re.IGNORECASE,
)
_LOCKED_RE = re.compile(r"^(?:" + _LOCKED_SECTIONS + r")$", re.IGNORECASE)
_MD_HEADING_RE = re.compile(r"^[ \t]*#{1,6}[ \t]+\S.*$")
_NUMBERED_HEADING_RE = re.compile(r"^[ \t]*\d+(?:\.\d+)*\.?[ \t]+[A-Z][^.!?]{0,80}$")
# "Keywords: a; b; c" on one line
_KEYWORD_LINE_RE = re.compile(
    r"^[ \t]*(?:keywords|key words|index terms|jel(?: classification)?(?: codes)?|msc(?: \d+)?)[ \t]*[:—–-].*$",
    re.IGNORECASE,
)

_FENCE_RE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})[ \t]*([\w+#.-]*)")
_LATEX_ENV_RE = re.compile(
    r"\\begin\{(equation|align|gather|multline|eqnarray|displaymath|math|array|"
    r"[pbvBV]?matrix|cases|split|table|tabular|tabularx|longtable|figure|algorithm|"
    r"algorithmic|verbatim|lstlisting|minted|code)(\*?)\}"
)
_LISTING_LANG_RE = re.compile(r"language\s*=\s*([\w+#]+)|\\begin\{minted\}(?:\[[^\]]*\])?\{([\w+#]+)\}")


def heading_name(line: str) -> str | None:
    """The section name if ``line`` is a section heading, else None."""
    m = _HEADING_RE.match(line)
    if m:
        return re.sub(r"\s+", " ", m.group("name")).strip()
    if _MD_HEADING_RE.match(line):
        return line.strip().lstrip("#").strip()
    if _NUMBERED_HEADING_RE.match(line) and len(line.split()) <= 10:
        return line.strip()
    return None


# ---------------------------------------------------------------- code detection

_CODE_LINE = [
    # (pattern, language vote or "", strong)
    (r"^\s*(?:async\s+)?def\s+\w+\s*\(.*\)\s*(?:->.*)?:\s*(?:#.*)?$", "python", True),
    (r"^\s*class\s+\w+(?:\(.*\))?\s*:\s*$", "python", True),
    (r"^\s*(?:import\s+[\w.]+(?:\s+as\s+\w+)?(?:\s*,\s*[\w.]+)*|from\s+[\w.]+\s+import\s+.+)\s*$", "python", True),
    (r"^\s*(?:if|elif|for|while|with|except)\b[^.;{}]*:\s*(?:#.*)?$", "python", True),
    (r"^\s*(?:else|try|finally)\s*:\s*$", "python", True),
    (r"^\s*print\(.*\)\s*$", "python", True),
    (r"^\s*#include\s*[<\"]", "c", True),
    (r"^\s*(?:public|private|protected)\s+(?:static\s+)?[\w<>\[\], ]+\s+\w+\s*\(.*\)\s*\{?\s*$", "java", True),
    (
        r"^\s*(?:function\s+\w*\s*\(|(?:const|let|var)\s+[\w{}\[\], ]+\s*=|export\s+(?:default\s+)?(?:function|const|class|interface|type)\b|"
        r"console\.log\(|import\s+.*\s+from\s+['\"])",
        "js",
        True,
    ),
    (r"^\s*(?:fn\s+\w+|let\s+mut\s|use\s+[\w:]+(?:::\{.*\})?;|impl\b|pub\s+(?:fn|struct|enum)\b)", "rust", True),
    (r"^\s*(?:package\s+\w+\s*$|func\s+(?:\(.*\)\s*)?\w+\s*\()", "go", True),
    (
        r"^\s*(?:SELECT|INSERT\s+INTO|UPDATE|DELETE\s+FROM|CREATE\s+(?:TABLE|INDEX|VIEW)|ALTER\s+TABLE|DROP\s+TABLE)\b",
        "sql",
        True,
    ),
    (
        r"^\s*(?:#!/|sudo\s|apt(?:-get)?\s|pip\s+install|npm\s+(?:install|run)|cd\s+\S+$|echo\s|export\s+\w+=)",
        "shell",
        True,
    ),
    (r".*[;{]\s*(?://.*)?$|^\s*[})\]]+[;,)]*\s*$", "", True),
    (r"^\s*[\w.\[\]'\"]+\s*(?:[-+*/%]?=)(?!=)\s*\S", "", False),
    (r"^\s*(?:#|//|/\*|\*|\*/|--)", "", False),
    (r"^\s*return\b.*$", "", False),
]
_CODE_LINE = [(re.compile(p), lang, strong) for p, lang, strong in _CODE_LINE]


def _guess_code(lines: list[str]) -> str | None:
    """Returns a language ('' if unknown) when the paragraph is code, else None."""
    content = [l for l in lines if l.strip()]
    if not content:
        return None
    votes: dict[str, int] = {}
    code_like = strong = 0
    for line in content:
        for pat, lang, is_strong in _CODE_LINE:
            if pat.match(line):
                code_like += 1
                strong += is_strong
                if lang:
                    votes[lang] = votes.get(lang, 0) + 1
                break
    if not strong or code_like < max(1, 0.6 * len(content)):
        return None
    if not votes and len(content) == 1:  # one line ending in ";" is more likely prose
        return None
    if not votes:
        braces = sum(l.count("{") + l.count(";") for l in content)
        return "c" if braces else ""
    return max(votes, key=votes.get)


# ---------------------------------------------------------------- data detection

_NUM_TOKEN = re.compile(r"^[-+±(]?[$€£]?\d[\d,.]*%?\)?$|^[-–—]$|^n/?a$", re.IGNORECASE)


def _is_data(lines: list[str]) -> bool:
    content = [l for l in lines if l.strip()]
    if not content:
        return False
    rows = 0
    for line in content:
        s = line.strip()
        if s.count("|") >= 2 or re.fullmatch(r"[-+:| =]{3,}", s) or line.count("\t") >= 1:
            rows += 1
            continue
        cells = re.split(r"\s{2,}|,\s*", s)
        toks = s.split()
        if len(cells) >= 3 and sum(bool(_NUM_TOKEN.match(t)) for t in toks) >= 0.5 * len(toks):
            rows += 1
    if len(content) == 1:
        return content[0].count("|") >= 3
    return rows >= max(2, 0.7 * len(content))


# ---------------------------------------------------------------- scanning


def _lines(text: str) -> list[tuple[int, int, str]]:
    """(start, end-without-newline, line) for every line."""
    out, pos = [], 0
    for line in text.split("\n"):
        out.append((pos, pos + len(line), line))
        pos += len(line) + 1
    return out


def analyze(text: str) -> Layout:
    layout = Layout()
    lines = _lines(text)
    blocks: list[Block] = []
    i, n = 0, len(lines)
    para: list[int] = []  # indexes of the current paragraph's lines

    def flush_para() -> None:
        if not para:
            return
        body = [lines[k][2] for k in para]
        first = 0
        # heading line(s) at the top of the paragraph
        while first < len(body) and heading_name(body[first]) is not None and len(body[first].split()) <= 12:
            s, e, line = lines[para[first]]
            blocks.append(Block(s, e, "heading", label=heading_name(line) or ""))
            first += 1
        rest = [para[k] for k in range(first, len(para))]
        if rest:
            rbody = [lines[k][2] for k in rest]
            rs, re_ = lines[rest[0]][0], lines[rest[-1]][1]
            if len(rbody) == 1 and _KEYWORD_LINE_RE.match(rbody[0]):
                blocks.append(Block(rs, re_, "locked", label=rbody[0].split(":")[0].strip()))
            elif _is_data(rbody):
                blocks.append(Block(rs, re_, "data"))
            else:
                lang = _guess_code(rbody)
                if lang is not None:
                    blocks.append(Block(rs, re_, "codeblock", lang=lang))
        para.clear()

    while i < n:
        s, e, line = lines[i]
        fence = _FENCE_RE.match(line)
        if fence:
            flush_para()
            mark, lang = fence.group(1), fence.group(2).lower()
            j = i + 1
            while j < n and not lines[j][2].strip().startswith(mark[0] * len(mark)):
                j += 1
            end = lines[min(j, n - 1)][1]
            blocks.append(Block(s, end, "codeblock", lang=lang))
            i = j + 1
            continue
        env = _LATEX_ENV_RE.search(line)
        if env or line.strip().startswith(("$$", "\\[")):
            flush_para()
            if env:
                closer = "\\end{" + env.group(1) + env.group(2) + "}"
                name = env.group(1)
                kind = (
                    "data"
                    if name in ("table", "tabular", "tabularx", "longtable", "figure")
                    else "codeblock"
                    if name in ("verbatim", "lstlisting", "minted", "code", "algorithm", "algorithmic")
                    else "math"
                )
            else:
                closer = "$$" if line.strip().startswith("$$") else "\\]"
                kind, name = "math", ""
            j = i
            after_open = line[line.find(closer[:2]) + 2 :] if not env else line[env.end() :]
            if closer not in after_open:
                j = i + 1
                while j < n and closer not in lines[j][2]:
                    j += 1
            end = lines[min(j, n - 1)][1]
            lang = ""
            if kind == "codeblock":
                lm = _LISTING_LANG_RE.search(text[s:end])
                lang = (lm.group(1) or lm.group(2)).lower() if lm else ""
            blocks.append(Block(s, end, kind, lang=lang))
            i = j + 1
            continue
        if line.strip():
            para.append(i)
        else:
            flush_para()
        i += 1
    flush_para()
    blocks.sort(key=lambda b: b.start)

    # Locked sections: from a locked heading to the next heading of any kind.
    headings = [b for b in blocks if b.kind == "heading"]
    locked: list[Block] = []
    for k, h in enumerate(headings):
        is_locked = bool(_LOCKED_RE.match(h.label))
        layout.sections.append((h.label, is_locked))
        if not is_locked:
            continue
        stop = headings[k + 1].start if k + 1 < len(headings) else len(text)
        end = len(text[:stop].rstrip())
        if end > h.start:
            locked.append(Block(h.start, end, "locked", label=h.label))
    if locked:
        merged: list[Block] = []
        for b in locked:
            if merged and b.start <= merged[-1].end + 2:  # adjacent locked sections become one
                merged[-1].end = max(merged[-1].end, b.end)
            else:
                merged.append(b)
        blocks = [b for b in blocks if not any(m.start <= b.start < m.end for m in merged)] + merged
        blocks.sort(key=lambda b: b.start)
    layout.blocks = blocks
    return layout
