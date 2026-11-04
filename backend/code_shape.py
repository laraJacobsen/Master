"""
"Same code, different names" -- the lecturer dashboard's grouping key for showing
student code (an issue's "View code"): two submissions that differ only in what the
student called their own variables, functions and parameters, in comments, in
whitespace, or in '...' vs "..." quoting, get the same shape key, so they're shown
once with each naming as a switchable variant instead of as N near-identical blocks.

Deliberately NOT aggregation._canonicalize(): that renames every identifier,
builtins and methods included, which is fine for its job (TF-IDF similarity
clustering) but wrong for "these are identical": print(max(nums)) and
print(min(nums)) canonicalize to the same text there, so the min-bug student would
be shown as having the correct code. Here only names the student *binds* (assignment
and loop targets, def/class names, parameters, `as` aliases) are renamed; max, min,
.split, print and every other name they didn't create stay as written.

Python only. Anything else -- other languages, or Python that doesn't parse (a
syntax error) -- gets no shape, and the dashboard falls back to exact-text grouping.
"""

import ast
import io
import keyword
import re
import tokenize


def _bound_names(tree: ast.AST) -> set:
    """Every name the program itself binds."""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            names.add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.alias) and node.asname:
            names.add(node.asname)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
    return names


# An identifier not preceded by a word character or "." -- so the "f" in a
# {avg:.1f} format spec and the "split" in {s.split()} don't count.
_IDENT = re.compile(r"(?<![\w.])[A-Za-z_]\w*")


def _fstring_names(token: str) -> list:
    """(offset, name) of every identifier inside an f-string token's {...}
    fields. Before Python 3.12, tokenize returns a whole f-string as one STRING
    token, so f"{avg:.1f}" vs f"{mean:.1f}" would otherwise never group."""
    found = []
    i = 0
    while i < len(token):
        if token.startswith("{{", i) or token.startswith("}}", i):
            i += 2
        elif token[i] == "{":
            depth, j = 1, i + 1
            while j < len(token) and depth:
                depth += {"{": 1, "}": -1}.get(token[j], 0)
                j += 1
            for m in _IDENT.finditer(token, i + 1, j - 1):
                if not keyword.iskeyword(m.group()):
                    found.append((m.start(), m.group()))
            i = j
        else:
            i += 1
    return found


def _string_key(token: str) -> str:
    # Plain literals compare by value (quote style doesn't matter); f-strings and
    # anything else literal_eval can't read compare as written.
    try:
        return repr(ast.literal_eval(token))
    except (ValueError, SyntaxError):
        return token


def code_shape(source_code: str, language: str) -> dict:
    """{"shape_key": str | None, "shape_names": [...], "shape_spans": [[slot, start, end], ...]}

    shape_names[i] is what this submission called its i-th own name (in order of
    first appearance); shape_spans are every occurrence of those names as character
    offsets into source_code, so the dashboard can mark the names that differ
    between two submissions with the same shape_key.
    """
    empty = {"shape_key": None, "shape_names": [], "shape_spans": []}
    if language != "python":
        return empty
    try:
        bound = _bound_names(ast.parse(source_code))
        tokens = list(tokenize.generate_tokens(io.StringIO(source_code).readline))
    except (SyntaxError, ValueError, tokenize.TokenError, IndentationError):
        return empty

    # tokenize positions are (line, column) -- turned into offsets for the spans.
    line_starts = [0]
    for line in source_code.splitlines(keepends=True):
        line_starts.append(line_starts[-1] + len(line))

    slots = {}
    names = []
    spans = []
    out = []

    def slot_of(name: str, start: int) -> int:
        if name not in slots:
            slots[name] = len(names)
            names.append(name)
        spans.append([slots[name], start, start + len(name)])
        return slots[name]

    prev = None
    for tok in tokens:
        if tok.type in (tokenize.COMMENT, tokenize.NL, tokenize.ENCODING, tokenize.ENDMARKER):
            continue
        tok_start = line_starts[tok.start[0] - 1] + tok.start[1]
        if tok.type == tokenize.NAME and not keyword.iskeyword(tok.string):
            # After a ".", it's an attribute (obj.best), not the student's variable.
            if tok.string in bound and not (prev and prev.string == "."):
                out.append(f"NAME{slot_of(tok.string, tok_start)}")
            else:
                out.append(tok.string)
        elif tok.type == tokenize.STRING and re.match(r"[rRbB]?[fF]", tok.string):
            text, at = [], 0
            for offset, name in _fstring_names(tok.string):
                if name in bound:
                    text.append(tok.string[at:offset])
                    text.append(f"NAME{slot_of(name, tok_start + offset)}")
                    at = offset + len(name)
            text.append(tok.string[at:])
            out.append("".join(text))
        elif tok.type == tokenize.STRING:
            out.append(_string_key(tok.string))
        elif tok.type == tokenize.NEWLINE:
            out.append("<NEWLINE>")
        elif tok.type == tokenize.INDENT:
            out.append("<INDENT>")
        elif tok.type == tokenize.DEDENT:
            out.append("<DEDENT>")
        else:
            out.append(tok.string)
        prev = tok
    return {"shape_key": " ".join(out), "shape_names": names, "shape_spans": spans}


def with_shape(row: dict) -> dict:
    """A submission row plus its code_shape() fields."""
    return {**row, **code_shape(row.get("source_code") or "", row.get("language") or "")}
