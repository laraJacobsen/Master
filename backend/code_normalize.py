"""
Normalised code, for telling a real change from a resubmission of the same code.

Two submissions are the same if their normal forms are equal:
  - Python: the AST (ast.dump without line/column positions), so comments, blank
    lines, spacing, parentheses that don't change parsing and quote style don't
    matter. Code that doesn't parse (a syntax error is a real, gradeable attempt)
    falls back to its token stream without comments.
  - C, C++, Java: the token stream without comments and whitespace. String and
    character literals stay whole, so editing the text a program prints is a change.

Renaming a variable IS a change: a rename can change behaviour (a test imports a
function by name; a C macro), so a renamed submission is never served a stored
result. Multi-file submissions (test-graded tasks) are normalised file by file.

similarity() is for the optional looser threshold (hint_policy.duplicate_similarity
below 1): difflib's ratio over the two submissions' source tokens (comments and
whitespace dropped). Not over the AST dump: its boilerplate (ctx=Load(), keywords=[])
makes unrelated programs score around 0.7.
"""

import ast
import difflib
import io
import re
import tokenize

# C-family tokens: comments first (dropped), then literals (kept whole), then the rest.
_C_TOKEN = re.compile(
    r"""
    (?P<comment>//[^\n]*|/\*.*?\*/)
    |(?P<string>"(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*')
    |(?P<word>[A-Za-z_]\w*|\d[\w.]*)
    |(?P<space>\s+)
    |(?P<other>.)
    """,
    re.VERBOSE | re.DOTALL,
)


def _python_tokens(code: str) -> list[str]:
    """Python's tokens without comments and non-logical newlines. Indentation stays
    (INDENT/DEDENT), since in Python it's meaning, not layout."""
    out = []
    end = (1, 0)  # where the last token yielded ended (line, column)
    try:
        for tok in tokenize.generate_tokens(io.StringIO(code).readline):
            end = tok.end
            if tok.type in (tokenize.COMMENT, tokenize.NL, tokenize.ENCODING, tokenize.ENDMARKER):
                continue
            if tok.type == tokenize.INDENT:
                out.append("<INDENT>")
            elif tok.type == tokenize.DEDENT:
                out.append("<DEDENT>")
            elif tok.type == tokenize.NEWLINE:
                out.append("<NL>")
            else:
                out.append(tok.string)
    except (tokenize.TokenError, IndentationError, SyntaxError):
        # The tokens up to the problem (an unclosed bracket or string at the end) were
        # already yielded; whatever comes after the last one is kept as plain words.
        lines = code.split("\n")
        rest = "\n".join([lines[end[0] - 1][end[1]:]] + lines[end[0]:]) if end[0] <= len(lines) else ""
        out.extend(rest.split())
    return out


def _c_tokens(code: str) -> list[str]:
    return [m.group() for m in _C_TOKEN.finditer(code) if m.lastgroup not in ("comment", "space")]


def normalize(code: str, language: str) -> str:
    """One file's normal form."""
    code = (code or "").replace("\r\n", "\n")
    if language == "python":
        try:
            return "ast:" + ast.dump(ast.parse(code), include_attributes=False)
        except (SyntaxError, ValueError):
            return "tok:" + " ".join(_python_tokens(code))
    return "tok:" + " ".join(_c_tokens(code))


def normalize_submission(source_code: str, files: dict | None, language: str) -> str:
    """A whole submission's normal form: its files one by one (test-graded tasks,
    {path: text}), else its single source."""
    if files:
        return "\n".join(f"{path}\0{normalize(files[path], language)}" for path in sorted(files))
    return normalize(source_code, language)


def tokens(code: str, language: str) -> list[str]:
    """One file's source tokens without comments or layout."""
    code = (code or "").replace("\r\n", "\n")
    return _python_tokens(code) if language == "python" else _c_tokens(code)


def submission_tokens(source_code: str, files: dict | None, language: str) -> list[str]:
    if files:
        return [t for path in sorted(files) for t in [f"<FILE {path}>"] + tokens(files[path], language)]
    return tokens(source_code, language)


def similarity(a: list[str], b: list[str]) -> float:
    """0..1 between two token sequences (submission_tokens()): difflib's ratio."""
    if a == b:
        return 1.0
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()
