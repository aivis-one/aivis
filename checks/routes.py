"""The router table is well formed: every route named, every name unique.

WHY THIS EXISTS. A duplicate route name does not throw. Vue Router keeps the
last registration and every `router.push({ name })` for the shadowed one goes
somewhere else -- a dead link that resolves, which is worse than a broken one.

WHAT IS EASY TO GET WRONG AND IS THEREFORE DONE PROPERLY HERE. A route table is
a TREE: parents hold `children`, and a child's `path` is relative to its
parent's. Reading it with a flat regex -- nearest enclosing brace, first
`name:` inside -- attributes a CHILD's name to its PARENT and produces a table
with more records than routes and phantom duplicates. This walks the braces and
only reads keys at each object's OWN depth.

It also asserts the one deliberate exception: there is exactly ONE `name:` in
the file that is not a route record -- a `next({ name: ... })` inside a
navigation guard. If that count ever changes, either a route was added without
a name or a second guard started redirecting by name, and both are worth seeing.
"""
from __future__ import annotations

import os
import re

LINE_COMMENT = re.compile(r"(?<![:/])//[^\n]*")
BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
STRING = re.compile(r"'([^'\\]*(?:\\.[^'\\]*)*)'")

GUARD_NAME_CALLS = 1  # next({ name: 'login' }) inside /r/:code's guard


def _mask(text: str) -> str:
    def repl(m: re.Match) -> str:
        return "".join("\n" if ch == "\n" else " " for ch in m.group(0))
    return LINE_COMMENT.sub(repl, BLOCK_COMMENT.sub(repl, text))


def _objects(src: str, start: int, end: int):
    depth, i, obj_start = 0, start, None
    while i < end:
        c = src[i]
        if c == "{":
            if depth == 0:
                obj_start = i
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                yield obj_start, i
        i += 1


def _own_key(src: str, start: int, end: int, key: str):
    """Value of `key: '...'` at this object's OWN depth, never a child's."""
    depth, i = 0, start
    pattern = re.compile(r"%s\s*:\s*" % re.escape(key))
    while i <= end:
        c = src[i]
        if c in "{[":
            depth += 1
        elif c in "}]":
            depth -= 1
        elif depth == 1 and (i == 0 or src[i - 1] in "{, \n\t"):
            m = pattern.match(src, i)
            if m:
                s = STRING.match(src, m.end())
                return s.group(1) if s else None
        i += 1
    return None


def _children(src: str, start: int, end: int):
    m = re.search(r"children\s*:\s*\[", src[start:end])
    if not m:
        return None
    open_at = start + m.end() - 1
    depth, i = 0, open_at
    while i <= end:
        if src[i] == "[":
            depth += 1
        elif src[i] == "]":
            depth -= 1
            if depth == 0:
                return open_at + 1, i
        i += 1
    return None


def _join(parent: str, child: str) -> str:
    if child.startswith("/"):
        return child
    if not child:
        return parent or "/"
    return (parent.rstrip("/") + "/" + child) if parent else "/" + child


def _walk(src, start, end, parent, out):
    for obj_start, obj_end in _objects(src, start, end):
        path = _own_key(src, obj_start, obj_end, "path")
        if path is None:
            continue
        full = _join(parent, path)
        name = _own_key(src, obj_start, obj_end, "name")
        if name:
            out.append({"path": full, "name": name,
                        "line": src.count("\n", 0, obj_start) + 1})
        kids = _children(src, obj_start, obj_end)
        if kids:
            _walk(src, kids[0], kids[1], full, out)


def table(root: str) -> tuple[list[dict], int]:
    path = os.path.join(root, "frontend", "src", "router", "index.ts")
    src = _mask(open(path, encoding="utf-8").read())
    m = re.search(r"routes\s*:\s*\[|const\s+routes[^=]*=\s*\[", src)
    if not m:
        raise ValueError("cannot find the routes array in router/index.ts")
    open_at = src.index("[", m.start())
    depth, i = 0, open_at
    while i < len(src):
        if src[i] == "[":
            depth += 1
        elif src[i] == "]":
            depth -= 1
            if depth == 0:
                break
        i += 1
    out: list[dict] = []
    _walk(src, open_at + 1, i, "", out)
    tokens = len(re.findall(r"(?:^|[{,\s])name\s*:\s*'", src))
    return out, tokens


def run(root: str) -> tuple[bool, list[str]]:
    records, tokens = table(root)
    names = [r["name"] for r in records]
    duplicates = sorted({n for n in names if names.count(n) > 1})
    concrete = [r for r in records if ":" not in r["path"] and "*" not in r["path"]]

    lines = [
        "named routes: %d, distinct names: %d" % (len(records), len(set(names))),
        "directly loadable without an id: %d | parameterised: %d"
        % (len(concrete), len(records) - len(concrete)),
        "`name:` occurrences in the file: %d = %d route records + %d guard call(s)"
        % (tokens, len(records), tokens - len(records)),
    ]
    ok = True
    if duplicates:
        lines.append("DUPLICATE ROUTE NAME(S): %s" % duplicates)
        ok = False
    if tokens - len(records) != GUARD_NAME_CALLS:
        lines.append("EXPECTED exactly %d `name:` outside the route table, found %d -- either a "
                     "route lost its name or a new guard redirects by name"
                     % (GUARD_NAME_CALLS, tokens - len(records)))
        ok = False
    return ok, lines


def selftest(root: str) -> list[str]:
    out = []
    records, tokens = table(root)
    assert records, "the route table came back empty"
    names = [r["name"] for r in records]
    assert len(names) == len(set(names)), "the real table already has a duplicate name"
    out.append("  the real table parses: %d routes, %d distinct names" % (len(records), len(set(names))))

    # a synthetic nested table where a flat reader would report a duplicate
    sample = """
    const routes = [
      { path: '/a', name: 'a', children: [ { path: 'x', name: 'ax' } ] },
      { path: '/b', name: 'b', children: [ { path: 'x', name: 'bx' } ] },
    ]
    """
    src = _mask(sample)
    open_at = src.index("[")
    depth, i = 0, open_at
    while i < len(src):
        if src[i] == "[":
            depth += 1
        elif src[i] == "]":
            depth -= 1
            if depth == 0:
                break
        i += 1
    got: list[dict] = []
    _walk(src, open_at + 1, i, "", got)
    paths = sorted(r["path"] for r in got)
    assert paths == ["/a", "/a/x", "/b", "/b/x"], "nested paths mis-joined: %r" % paths
    names = sorted(r["name"] for r in got)
    assert names == ["a", "ax", "b", "bx"], "nested names mis-attributed: %r" % names
    out.append("  nested children are joined onto their parent and keep their own names")
    return out
