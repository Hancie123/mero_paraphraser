"""Code blocks: reword natural-language comments, never the code.

A code block is split into tokens of four kinds: ``code`` (everything that
runs, including string literals), ``line`` comments (# // --), ``block``
comments (/* */ <!-- --> {- -}) and Python ``doc`` strings. Only comment and
docstring text that reads like prose is reworded; the rest is copied as is.

The result is then checked: the block is lexed again and every code token
must be byte-for-byte identical, with the same number and kinds of comments.
For Python, the parsed syntax tree (docstrings aside) must also be the same.
If any check fails, or the lexer isn't sure (unterminated string, unknown
language), the block is returned unchanged.

Python uses the standard ``tokenize`` module. Other languages use a small
lexer that knows each family's strings and comments and leans towards
treating anything ambiguous as code.
"""

from __future__ import annotations

import ast
import io
import re
import tokenize
from dataclasses import dataclass, field

Token = tuple[str, str]  # (kind, text)


# ---------------------------------------------------------------- language specs

@dataclass(frozen=True)
class Spec:
    line: tuple[str, ...] = ()
    block: tuple[tuple[str, str], ...] = ()
    quotes: str = ""
    triple: bool = False  # """...""" strings
    multiline_quotes: str = ""  # quote characters whose strings may span lines
    char_strict: bool = False  # ' starts a char literal only if it closes right away ('a', '\n')
    nested: bool = False  # nested block comments (Rust, Swift, Kotlin, Haskell...)
    hash_ws: bool = False  # # starts a comment only at line start or after whitespace (shell, YAML)
    heredoc: bool = False
    regex: bool = False  # JavaScript regex literals
    raw_pairs: tuple[tuple[str, str], ...] = ()  # strings without escapes, e.g. Lua [[...]], C++ R"(...)"
    no_escape_prev: str = ""  # a comment marker preceded by this char is not a comment (LaTeX \%)


_C = Spec(line=("//",), block=(("/*", "*/"),), quotes="\"'", char_strict=True)
SPECS: dict[str, Spec] = {
    "python": Spec(line=("#",), quotes="'\"", triple=True),
    "shell": Spec(line=("#",), quotes="'\"", multiline_quotes="'\"", hash_ws=True, heredoc=True),
    "yaml": Spec(line=("#",), quotes="'\"", hash_ws=True),
    "toml": Spec(line=("#",), quotes="'\"", triple=True, hash_ws=True),
    "ruby": Spec(line=("#",), quotes="'\"`", multiline_quotes="'\"", hash_ws=True),
    "r": Spec(line=("#",), quotes="'\"`", multiline_quotes="'\""),
    "c": _C,
    "cpp": Spec(line=("//",), block=(("/*", "*/"),), quotes="\"'", char_strict=True, raw_pairs=(('R"(', ')"'),)),
    "go": Spec(line=("//",), block=(("/*", "*/"),), quotes="\"'`", multiline_quotes="`", char_strict=True),
    "rust": Spec(line=("//",), block=(("/*", "*/"),), quotes="\"'", multiline_quotes="\"", char_strict=True, nested=True),
    "swift": Spec(line=("//",), block=(("/*", "*/"),), quotes="\"", triple=True, nested=True),
    "kotlin": Spec(line=("//",), block=(("/*", "*/"),), quotes="\"'", triple=True, char_strict=True, nested=True),
    "js": Spec(line=("//",), block=(("/*", "*/"),), quotes="'\"`", multiline_quotes="`", regex=True),
    "php": Spec(line=("//", "#"), block=(("/*", "*/"),), quotes="'\"", multiline_quotes="'\""),
    "css": Spec(block=(("/*", "*/"),), quotes="'\""),
    "scss": Spec(line=("//",), block=(("/*", "*/"),), quotes="'\""),
    "sql": Spec(line=("--",), block=(("/*", "*/"),), quotes="'\"", multiline_quotes="'"),
    "lua": Spec(line=("--",), block=(("--[[", "]]"),), quotes="'\"", raw_pairs=(("[[", "]]"),)),
    "haskell": Spec(line=("--",), block=(("{-", "-}"),), quotes="\"", char_strict=True, nested=True),
    "html": Spec(block=(("<!--", "-->"),)),
    "latex": Spec(line=("%",), no_escape_prev="\\"),
}
ALIASES = {
    "py": "python", "python3": "python", "py3": "python", "ipython": "python", "pycon": None,
    "sh": "shell", "bash": "shell", "zsh": "shell", "console": None, "shell-session": None, "dockerfile": "shell",
    "docker": "shell", "makefile": "shell", "make": "shell", "powershell": "shell", "ps1": "shell", "ps": "shell",
    "yml": "yaml", "rb": "ruby", "c": "c", "h": "c", "objc": "c", "objective-c": "c",
    "c++": "cpp", "cc": "cpp", "cxx": "cpp", "hpp": "cpp", "java": "c", "cs": "c", "csharp": "c", "c#": "c",
    "scala": "kotlin", "kt": "kotlin", "kts": "kotlin", "dart": "kotlin", "golang": "go", "rs": "rust",
    "javascript": "js", "jsx": "js", "ts": "js", "typescript": "js", "tsx": "js", "mjs": "js", "cjs": "js",
    "json5": "js", "jsonc": "js", "less": "scss", "sass": "scss", "psql": "sql", "mysql": "sql",
    "plsql": "sql", "postgresql": "sql", "tsql": "sql", "hs": "haskell", "xml": "html", "svg": "html",
    "vue": "html", "xhtml": "html", "tex": "latex", "r": "r",
}


def resolve(lang: str) -> str | None:
    lang = (lang or "").lower().strip()
    if lang in SPECS:
        return lang
    return ALIASES.get(lang)


# ---------------------------------------------------------------- generic lexer

_CHAR_LIT = re.compile(r"'(?:\\(?:u\{[0-9a-fA-F]{1,6}\}|x[0-9a-fA-F]{2}|u[0-9a-fA-F]{4}|[0-7]{1,3}|.)|[^'\\\n])'")
_REGEX_BEFORE = set("(,=:[!&|?{};+-*%~^<>") | {""}
_HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_]\w*)\1")


class _Unsure(Exception):
    pass


def _scan_string(src: str, i: int, q: str, multiline: bool, escapes: bool = True) -> int:
    """End index (exclusive) of the string starting at src[i] == q."""
    j, n = i + 1, len(src)
    while j < n:
        c = src[j]
        if c == "\\" and escapes:
            j += 2
            continue
        if c == q:
            return j + 1
        if c == "\n" and not multiline:
            raise _Unsure
        j += 1
    raise _Unsure


def lex(src: str, spec: Spec) -> list[Token]:
    """Split ``src`` into code and comment tokens. Raises _Unsure when it can't be certain."""
    out: list[Token] = []
    i, n, code_start = 0, len(src), 0
    prev_sig = ""  # last non-space code character (for regex literals)
    prev_word = ""

    def emit(kind: str, start: int, end: int) -> None:
        nonlocal code_start
        if code_start < start:
            out.append(("code", src[code_start:start]))
        out.append((kind, src[start:end]))
        code_start = end

    while i < n:
        c = src[i]
        # heredoc: everything up to the terminator line is code
        if spec.heredoc and c == "<" and src.startswith("<<", i):
            m = _HEREDOC.match(src, i)
            if m:
                term = re.compile(r"^[ \t]*" + re.escape(m.group(2)) + r"[ \t]*$", re.MULTILINE)
                t = term.search(src, src.find("\n", m.end()) + 1 if "\n" in src[m.end():] else n)
                if not t:
                    raise _Unsure
                i = t.end()
                continue
        # block comments (checked before line comments: Lua "--[[")
        matched = False
        for opener, closer in spec.block:
            if src.startswith(opener, i):
                j, depth = i + len(opener), 1
                while j < n and depth:
                    if spec.nested and src.startswith(opener, j):
                        depth += 1
                        j += len(opener)
                    elif src.startswith(closer, j):
                        depth -= 1
                        j += len(closer)
                    else:
                        j += 1
                if depth:
                    raise _Unsure
                emit("block", i, j)
                i, matched = j, True
                break
        if matched:
            continue
        for marker in spec.line:
            if src.startswith(marker, i):
                if spec.hash_ws and i > 0 and src[i - 1] not in " \t\n;|&(":
                    continue
                if spec.no_escape_prev and i > 0 and src[i - 1] == spec.no_escape_prev:
                    continue
                j = src.find("\n", i)
                j = n if j < 0 else j
                if src[i:j].rstrip().endswith("\\") and marker == "//":
                    raise _Unsure  # C line splice: the next line is part of the comment
                emit("line", i, j)
                i, matched = j, True
                break
        if matched:
            continue
        for opener, closer in spec.raw_pairs:
            if src.startswith(opener, i):
                j = src.find(closer, i + len(opener))
                if j < 0:
                    raise _Unsure
                i, matched = j + len(closer), True
                break
        if matched:
            prev_sig = '"'
            continue
        if c in spec.quotes:
            if c == "'" and spec.char_strict:
                m = _CHAR_LIT.match(src, i)
                if not m:  # a Rust lifetime or similar: plain code
                    i += 1
                    prev_sig = c
                    continue
                i = m.end()
            elif spec.triple and src.startswith(c * 3, i):
                j = i + 3
                while j < n and not src.startswith(c * 3, j):
                    j += 2 if src[j] == "\\" else 1
                if j >= n:
                    raise _Unsure
                i = j + 3
            else:
                i = _scan_string(src, i, c, c in spec.multiline_quotes, escapes=not (spec.heredoc and c == "'"))
            prev_sig = c
            continue
        if spec.regex and c == "/" and (prev_sig in _REGEX_BEFORE or prev_word in ("return", "typeof", "case", "in", "of")):
            j, in_class = i + 1, False
            while j < n:
                d = src[j]
                if d == "\\":
                    j += 2
                    continue
                if d == "\n":
                    raise _Unsure
                if d == "[":
                    in_class = True
                elif d == "]":
                    in_class = False
                elif d == "/" and not in_class:
                    break
                j += 1
            if j >= n:
                raise _Unsure
            i = j + 1
            prev_sig = "/"
            continue
        if not c.isspace():
            prev_sig = c
            if c.isalnum() or c == "_":
                m = re.match(r"\w+", src[i:])
                prev_word = m.group()
                prev_sig = "a"
                i += len(prev_word)
                continue
            prev_word = ""
        i += 1
    if code_start < n:
        out.append(("code", src[code_start:]))
    return out


# ---------------------------------------------------------------- Python

def _py_lex(src: str) -> list[Token]:
    """Exact tokens from the ``tokenize`` module; docstrings are module/def/class first strings."""
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError) as exc:
        raise _Unsure from exc
    starts = [0]
    for line in src.splitlines(keepends=True):
        starts.append(starts[-1] + len(line))

    def off(pos: tuple[int, int]) -> int:
        return starts[pos[0] - 1] + pos[1]

    spans: list[tuple[int, int, str]] = []
    skip = {tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT, tokenize.COMMENT, tokenize.ENCODING}
    sig = [t for t in toks if t.type not in skip]
    sig_index = {id(t): k for k, t in enumerate(sig)}
    for k, t in enumerate(toks):
        if t.type == tokenize.COMMENT:
            spans.append((off(t.start), off(t.end), "line"))
        elif t.type == tokenize.STRING:
            si = sig_index[id(t)]
            before = sig[si - 1] if si else None
            after = toks[k + 1] if k + 1 < len(toks) else None
            first_stmt = before is None or (before.type == tokenize.OP and before.string == ":")
            alone = after is not None and after.type in (tokenize.NEWLINE, tokenize.ENDMARKER)
            prefix = re.match(r"[A-Za-z]*", t.string).group().lower()
            if first_stmt and alone and prefix in ("", "r", "u") and t.string[len(prefix):][:3] in ('"""', "'''"):
                spans.append((off(t.start), off(t.end), "doc"))
    out: list[Token] = []
    pos = 0
    for s, e, kind in spans:
        if pos < s:
            out.append(("code", src[pos:s]))
        out.append((kind, src[s:e]))
        pos = e
    if pos < len(src):
        out.append(("code", src[pos:]))
    return out


def _strip_docstrings(tree: ast.AST) -> str:
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                first.value.value = ""
    return ast.dump(tree)


def _tokens(src: str, lang: str) -> list[Token]:
    if lang == "python":
        try:
            return _py_lex(src)
        except _Unsure:
            pass  # a fragment that doesn't tokenize: comments only, via the generic lexer
    return lex(src, SPECS[lang])


# ---------------------------------------------------------------- prose rewriting

# Never reworded: tool directives, licences, commented-out code, tags.
_DIRECTIVE = re.compile(
    r"^\s*(?:!|-\*-|type:|noqa|pragma|pylint|pyright|mypy|isort|fmt:|nosec|coding[:=]|vim?:|eslint|jshint|jslint|"
    r"global\s|exported\s|prettier|istanbul|c8\s|@ts-|ts-|tslint|biome-|NOLINT|clang-|region\b|endregion\b|#?region\b|"
    r"SPDX|copyright|\(c\)|©|licen[cs]e|webpack|swiftlint|rubocop|frozen_string_literal|shellcheck|cython|"
    r"language=|eslint-)", re.IGNORECASE)
_CODE_START = re.compile(
    r"^\s*(?:def|class|import|from|return|if|elif|else|for|while|try|except|print|const|let|var|function|"
    r"public|private|static|void|int|float|double|char|struct|fn|func|SELECT|INSERT|UPDATE|DELETE|echo|sudo|cd)\b")
_CODEY = re.compile(
    r"`[^`]+`|\[\[\s*\d+\s*\]\]|https?://\S+|www\.\S+|"
    r"\S*\w[./\\:]\w\S*|"  # paths, dotted names, module.attr, a::b
    r"\b\w+\([^()\s]*\)|"  # calls: foo(), len(x)
    r"\b\w*_\w*\b|\b[a-z]+[A-Z]\w*\b|\b[A-Z][a-z]+[A-Z]\w*\b|"  # snake_case, camelCase, PascalCase
    r"\b\w*\d\w*\b|\b[A-Z]{2,}s?\b|"  # numbers, ACRONYMS
    r"\b(?:TODO|FIXME|XXX|HACK|NOTE|BUG|OPTIMIZE|WARNING|SAFETY)\b:?")
_FORBIDDEN = re.compile(r"[{}<>=$\\|;@]")


@dataclass
class _Context:
    strength: int
    seed: int | None
    rewritten: int = 0
    counter: int = 0


def _rewrite_prose(text: str, ctx: _Context) -> str:
    """Reword one line of comment prose, keeping identifiers and code-like words exactly."""
    from ..core import rule_engine
    from .citation_validator import check_tokens
    from .language_refiner import LanguageRefiner

    lead = text[: len(text) - len(text.lstrip())]
    trail = text[len(text.rstrip()):]
    core = text.strip()
    if not core or _DIRECTIVE.match(core) or _CODE_START.match(core) or core.endswith((":", "{", "(", ",")):
        return text
    kept: list[str] = []

    def mask(m: re.Match) -> str:
        kept.append(m.group())
        return f"[[{len(kept)}]]"

    masked = _CODEY.sub(mask, core)
    words = re.findall(r"[A-Za-z]{2,}", re.sub(r"\[\[\d+\]\]", " ", masked))
    if len(words) < 4 or _FORBIDDEN.search(masked):
        return text
    ctx.counter += 1
    seed = None if ctx.seed is None else ctx.seed + ctx.counter * 13
    out = rule_engine.paraphrase(masked, ctx.strength, seed)["text"]
    out = LanguageRefiner().refine(out, masked, seed).text
    _, critical = check_tokens(masked, out)
    if critical or "\n" in out or not out.strip():
        return text
    out = re.sub(r"\[\[\s*(\d+)\s*\]\]", lambda m: kept[int(m.group(1)) - 1], out)
    if out != core:
        ctx.rewritten += 1
    return lead + out + trail


_FIELD = re.compile(r"^(\s*(?::[^:\n]+:|[\w*]+(?:\s*\([^)\n]*\))?\s*:)\s+)(.+)$")  # ":param x: ..." / "x (int): ..."
_SKIP_LINE = re.compile(r"^\s*(?:[-=~^*#]{3,}|\w+(?: \w+)?:|>>>|\.\.\.|\.\. |[-*+]\s+\w+\s*:)\s*$")


def _rewrite_line(line: str, ctx: _Context) -> str:
    if _SKIP_LINE.match(line):
        return line
    m = _FIELD.match(line)
    if m:
        return m.group(1) + _rewrite_prose(m.group(2), ctx)
    return _rewrite_prose(line, ctx)


_LINE_MARK = re.compile(r"^(#+!?|//+!?|--|%+)(.*)$", re.DOTALL)


def _rewrite_comment(kind: str, text: str, ctx: _Context) -> str:
    if kind == "line":
        m = _LINE_MARK.match(text)
        if not m or text.startswith("#!"):  # shebang
            return text
        return m.group(1) + _rewrite_line(m.group(2), ctx)
    if kind == "block":
        if text.startswith(("/*!", "/**@")) or "@" in text:  # preserved licence comments, JSDoc tags
            return text
        opener = re.match(r"^(/\*+|<!--|\{-|--\[\[)", text).group()
        closer = re.search(r"(\*+/|-->|-\}|\]\])$", text).group()
        inner = text[len(opener): len(text) - len(closer)]
        lines = inner.split("\n")
        new = []
        for line in lines:
            m = re.match(r"^(\s*\*(?!/)\s?)(.*)$", line)
            new.append(m.group(1) + _rewrite_line(m.group(2), ctx) if m else _rewrite_line(line, ctx))
        body = "\n".join(new)
        bad = ("*/", "/*") if opener.startswith("/*") else ("--",) if opener == "<!--" else ("-}", "{-") if opener == "{-" else ("]]",)
        if any(b in body for b in bad):
            return text
        return opener + body + closer
    if kind == "doc":
        prefix = re.match(r"[A-Za-z]*", text).group()
        quote = text[len(prefix): len(prefix) + 3]
        inner = text[len(prefix) + 3: -3]
        if ">>>" in inner or "\\" in inner:  # doctests run; escapes change meaning
            return text
        body = "\n".join(_rewrite_line(line, ctx) for line in inner.split("\n"))
        if quote in body or "\\" in body or body.endswith(quote[0]):
            return text
        return text[: len(prefix) + 3] + body + quote
    return text


# ---------------------------------------------------------------- public API

@dataclass
class CodeResult:
    text: str
    lang: str | None
    comments: int = 0  # comments and docstrings found
    rewritten: int = 0  # comment lines reworded
    verified: bool = True  # the code itself is unchanged (always true for what is returned)
    notes: list[str] = field(default_factory=list)


def _same_code(a: list[Token], b: list[Token]) -> bool:
    if len(a) != len(b):
        return False
    return all(ka == kb and (ka != "code" or ta == tb) for (ka, ta), (kb, tb) in zip(a, b))


def verify(original: str, rewritten: str, lang: str) -> bool:
    """True when ``rewritten`` has exactly the same code as ``original`` (comments aside)."""
    try:
        a, b = _tokens(original, lang), _tokens(rewritten, lang)
    except _Unsure:
        return False
    if not _same_code(a, b):
        return False
    if lang == "python":
        try:
            ta = ast.parse(original)
        except SyntaxError:
            return True  # a fragment: the token check above is the guarantee
        try:
            return _strip_docstrings(ta) == _strip_docstrings(ast.parse(rewritten))
        except SyntaxError:
            return False
    return True


def split_fence(block: str) -> tuple[str, str, str]:
    """(opening fence line, body, closing fence line) for a fenced block; plain code has empty fences."""
    m = re.match(r"^([ \t]{0,3}(?:`{3,}|~{3,})[^\n]*\n)", block)
    if not m:
        return "", block, ""
    rest = block[m.end():]
    c = re.search(r"(\n?[ \t]*(?:`{3,}|~{3,})[ \t]*)$", rest)
    if not c:
        return m.group(1), rest, ""
    return m.group(1), rest[: c.start()], rest[c.start():]


def rewrite_block(block: str, lang: str, strength: int, seed: int | None = None) -> CodeResult:
    """Reword the comments in a code block. The code itself is guaranteed unchanged."""
    name = resolve(lang)
    if name is None and not lang:
        return CodeResult(block, None, notes=["unknown language: left unchanged"])
    if name is None:
        return CodeResult(block, None, notes=[f"{lang}: left unchanged"])
    head, body, tail = split_fence(block)
    try:
        toks = _tokens(body, name)
    except _Unsure:
        return CodeResult(block, name, notes=["couldn't be read with certainty: left unchanged"])
    ctx = _Context(strength, seed)
    comments = sum(1 for k, _ in toks if k != "code")
    new_body = "".join(t if k == "code" else _rewrite_comment(k, t, ctx) for k, t in toks)
    if new_body == body:
        return CodeResult(block, name, comments, 0)
    if not verify(body, new_body, name):
        return CodeResult(block, name, comments, 0, notes=["comment rewrite failed the code check: left unchanged"])
    return CodeResult(head + new_body + tail, name, comments, ctx.rewritten)
