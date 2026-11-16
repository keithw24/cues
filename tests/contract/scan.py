"""Static extraction of the database calls made by the Python and TypeScript code.

Pure text scanning (no imports of app code), so a call the contract tests cannot read is a
test failure, not a silent gap.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE_DIRS = ("web/lib", "web/app", "web/components", "agent", "vision", "shared")
SKIP_PARTS = {"tests", "node_modules", "__pycache__", ".next", "fixtures"}
STRING = re.compile(r"""(?P<q>["'])(?P<s>[^"'\n]*)(?P=q)""")


def source_files() -> list[Path]:
    found: list[Path] = []
    for directory in SOURCE_DIRS:
        for path in (ROOT / directory).rglob("*"):
            if path.suffix not in {".py", ".ts", ".tsx"} or SKIP_PARTS & set(path.parts):
                continue
            if path.name.startswith("test_") or ".test." in path.name:
                continue
            found.append(path)
    return sorted(found)


def balanced(text: str, open_index: int) -> str:
    """The text inside the parentheses that open at text[open_index] (ignores strings)."""
    depth, quote, i = 0, None, open_index
    while i < len(text):
        c = text[i]
        if quote:
            if c == "\\":
                i += 1
            elif c == quote:
                quote = None
        elif c in "\"'`":
            quote = c
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return text[open_index + 1 : i]
        i += 1
    raise ValueError("unbalanced parentheses")


@dataclass(frozen=True)
class TableUse:
    file: str
    line: int
    table: str
    columns: frozenset[str]


@dataclass(frozen=True)
class RpcUse:
    file: str
    line: int
    functions: frozenset[str]
    keys: frozenset[str]


_TABLE = re.compile(r"\b(?:from|table)\(\s*[\"'](\w+)[\"']\s*\)")
_FILTER = re.compile(r"\.(?:eq|neq|is_|is|in_|in|gte|lte|gt|lt|order)\(\s*[\"'](\w+)[\"']")
_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")


def table_uses() -> list[TableUse]:
    uses: list[TableUse] = []
    for path in source_files():
        text = path.read_text()
        matches = list(_TABLE.finditer(text))
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            chain = text[match.end() : min(end, match.end() + 1500)]
            columns: set[str] = set()
            select = re.search(r"\.select\(", chain)
            if select:
                inner = balanced(chain, select.end() - 1)
                for literal in STRING.finditer(inner):
                    for part in literal.group("s").split(","):
                        part = part.strip()
                        if _IDENT.match(part):
                            columns.add(part)
            columns.update(_FILTER.findall(chain))
            if columns:
                line = text.count("\n", 0, match.start()) + 1
                uses.append(
                    TableUse(str(path.relative_to(ROOT)), line, match.group(1), frozenset(columns))
                )
    return uses


def _argument_keys(call: str, functions: set[str]) -> set[str]:
    """Argument names in an rpc call's object literal.

    Keys of the argument object itself count, and so does any `p_` key in a conditional spread
    (`...(cond ? {} : { p_x })`); keys of nested value objects (like a JSON payload) do not.
    """
    keys: set[str] = set()
    depth, i = 0, 0
    while i < len(call):
        c = call[i]
        if c in "{[":
            depth += 1
        elif c in "}]":
            depth -= 1
        else:
            m = re.match(r"[\"']?\b([a-z_][a-z0-9_]*)\b[\"']?\s*:", call[i:])
            at_word_start = i == 0 or not (call[i - 1].isalnum() or call[i - 1] == "_")
            if m and at_word_start and m.group(1) not in functions:
                if depth == 1 or m.group(1).startswith("p_"):
                    keys.add(m.group(1))
                i += m.end() - 1
        i += 1
    return keys


def rpc_uses(known_functions: set[str]) -> list[RpcUse]:
    uses: list[RpcUse] = []
    for path in source_files():
        text = path.read_text()
        for match in re.finditer(r"\.rpc\(", text):
            inner = balanced(text, match.end() - 1)
            functions = {
                m.group("s") for m in STRING.finditer(inner) if m.group("s") in known_functions
            }
            keys = _argument_keys(inner, functions)
            # TypeScript shorthand properties, e.g. `{ review_id: id, action }`.
            keys.update(re.findall(r"[{,]\s*(action)\s*[,}]", inner))
            line = text.count("\n", 0, match.start()) + 1
            uses.append(
                RpcUse(str(path.relative_to(ROOT)), line, frozenset(functions), frozenset(keys))
            )
    return uses
