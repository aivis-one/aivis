"""Every response of the frontend's nginx carries the security headers.

WHY THIS EXISTS. nginx inherits `add_header` from the enclosing level into a
`location` ONLY if that location declares no `add_header` of its own. One
`add_header Cache-Control ...` in a location therefore drops every header
declared at `server` level, silently -- no warning, no error, and the page still
works. That is how frontend/nginx.conf served /assets/, /icons/, /manifest.json
and /health without X-Content-Type-Options, Content-Security-Policy and
Referrer-Policy until H22 (P-110), measured with curl against the config. The
file now keeps every `add_header` at `server` level and varies Cache-Control
through a `map`; this check holds it to that. Nothing else reads nginx.conf:
the backend tests run from an image built out of ./backend, where frontend/
does not exist.

WHAT IT ASSERTS -- rules, not the current text:
  1. there is a `server` block, and it declares X-Content-Type-Options,
     Content-Security-Policy and Referrer-Policy with a non-empty value and
     `always` (error pages carry them too);
  2. no block nested under `server` (a `location`, an `if`, ...) declares any
     `add_header`;
  3. Cache-Control is declared once at `server` level from a variable that a
     top-level `map` produces; that map's default is `no-cache` (a file whose
     name does not change with its content must be revalidated), and
     `immutable` appears only on entries keyed to /assets/, and on at least
     one of them (the hashed build output keeps its long cache).

WHAT IT DOES NOT CHECK, on purpose: the lifetimes of /icons/ or
/manifest.json and the content of the CSP. Those are data. The file names the
service worker build produces are not checked either -- they are not in the
repository -- which is why rule 3 is stated on the DEFAULT, not on a list.

STANDARD LIBRARY ONLY. The reader tokenises the nginx grammar it needs --
words, quoted strings, `#` comments, `{`, `}`, `;` -- and refuses a file it
cannot close (an unbalanced brace, a statement left open) instead of guessing.
"""
from __future__ import annotations

import os

CONFIG = os.path.join("frontend", "nginx.conf")

SECURITY_HEADERS = ("X-Content-Type-Options", "Content-Security-Policy", "Referrer-Policy")


class Block:
    def __init__(self, words: list[str], line: int) -> None:
        self.words = words
        self.line = line
        self.statements: list[tuple[list[str], int]] = []
        self.children: list[Block] = []


def tokenize(text: str) -> list[tuple[str, int, bool]]:
    """-> [(token, line, was_quoted)]. Quotes are removed, comments dropped."""
    out: list[tuple[str, int, bool]] = []
    i, line, n = 0, 1, len(text)
    while i < n:
        c = text[i]
        if c == "\n":
            line += 1
            i += 1
        elif c.isspace():
            i += 1
        elif c == "#":
            while i < n and text[i] != "\n":
                i += 1
        elif c in "{};":
            out.append((c, line, False))
            i += 1
        elif c in "\"'":
            quote, start_line, i = c, line, i + 1
            buf = []
            while i < n and text[i] != quote:
                if text[i] == "\\" and i + 1 < n:
                    i += 1
                if text[i] == "\n":
                    line += 1
                buf.append(text[i])
                i += 1
            if i >= n:
                raise ValueError("line %d: unterminated string" % start_line)
            out.append(("".join(buf), start_line, True))
            i += 1
        else:
            start = i
            while i < n and not text[i].isspace() and text[i] not in "{};\"'#":
                i += 1
            out.append((text[start:i], line, False))
    return out


def parse(text: str) -> Block:
    root = Block([], 0)
    stack = [root]
    words: list[str] = []
    first_line = 0
    for token, line, quoted in tokenize(text):
        if not quoted and token == ";":
            if not words:
                raise ValueError("line %d: empty statement" % line)
            stack[-1].statements.append((words, first_line))
            words = []
        elif not quoted and token == "{":
            block = Block(words, first_line or line)
            stack[-1].children.append(block)
            stack.append(block)
            words = []
        elif not quoted and token == "}":
            if words:
                raise ValueError("line %d: statement not closed by `;`" % line)
            if len(stack) == 1:
                raise ValueError("line %d: unbalanced `}`" % line)
            stack.pop()
        else:
            if not words:
                first_line = line
            words.append(token)
    if words:
        raise ValueError("end of file: statement not closed by `;`")
    if len(stack) != 1:
        raise ValueError("end of file: %d block(s) not closed" % (len(stack) - 1))
    return root


def _nested_add_headers(block: Block, path: str) -> list[str]:
    found = []
    for child in block.children:
        where = "%s > %s (line %d)" % (path, " ".join(child.words), child.line)
        found += [
            "%s: add_header %s" % (where, " ".join(words[1:2]))
            for words, _ in child.statements
            if words[0] == "add_header"
        ]
        found += _nested_add_headers(child, where)
    return found


def check(text: str) -> tuple[bool, list[str]]:
    try:
        root = parse(text)
    except ValueError as exc:
        return False, ["cannot read the config -- refusing to guess: %s" % exc]

    servers = [b for b in root.children if b.words[:1] == ["server"]]
    if len(servers) != 1:
        # The pair of "no location has an add_header": a server was read. An
        # empty file has no location with an add_header either.
        return False, ["expected exactly one `server` block, read %d" % len(servers)]
    server = servers[0]
    ok = True
    lines = [
        "server blocks read                 : 1 (line %d)" % server.line,
        "blocks nested under server         : %d" % _count_blocks(server),
    ]

    headers = {}
    for words, line in server.statements:
        if words[0] == "add_header":
            if len(words) < 3:
                ok = False
                lines.append("line %d: add_header without a value" % line)
                continue
            if words[1] in headers:
                ok = False
                lines.append("line %d: add_header %s declared twice" % (line, words[1]))
            headers[words[1]] = words[2:]

    for name in SECURITY_HEADERS:
        rest = headers.get(name)
        if rest is None:
            ok = False
            lines.append("server level does not declare %s" % name)
        elif not rest[0].strip():
            ok = False
            lines.append("%s is declared with an EMPTY value" % name)
        elif rest[1:] != ["always"]:
            ok = False
            lines.append("%s is declared without `always` (error pages lose it)" % name)
    if all(
        name in headers and headers[name][0].strip() and headers[name][1:] == ["always"]
        for name in SECURITY_HEADERS
    ):
        lines.append("server level declares the three security headers, non-empty, `always`")

    nested = _nested_add_headers(server, "server")
    if nested:
        ok = False
        lines.append("add_header inside a nested block -- it drops every server-level header there:")
        lines += ["  " + item for item in nested]
    else:
        lines.append("no nested block declares an add_header")

    cache = headers.get("Cache-Control")
    if cache is None or not cache[0].startswith("$"):
        ok = False
        lines.append("Cache-Control is not declared at server level from a map variable")
        return ok, lines
    variable = cache[0]
    maps = [b for b in root.children if b.words[:1] == ["map"] and b.words[2:3] == [variable]]
    if len(maps) != 1:
        ok = False
        lines.append("expected one top-level `map` producing %s, read %d" % (variable, len(maps)))
        return ok, lines
    entries = {}
    for words, line in maps[0].statements:
        if len(words) != 2:
            ok = False
            lines.append("line %d: map entry this check cannot read: %s" % (line, " ".join(words)))
            continue
        entries[words[0]] = words[1]
    default = entries.get("default")
    if default != "no-cache":
        ok = False
        lines.append("the Cache-Control map's default is %r, not 'no-cache'" % default)
    immutable = [key for key, value in entries.items() if "immutable" in value]
    stray = [key for key in immutable if not key.lstrip("~*").lstrip("^").startswith("/assets/")]
    if stray:
        ok = False
        lines.append("`immutable` on entries not keyed to /assets/: %s" % ", ".join(stray))
    if len(immutable) == len(stray):
        ok = False
        lines.append("no /assets/ entry is `immutable` -- the hashed build lost its long cache")
    if default == "no-cache" and not stray and immutable:
        lines.append(
            "Cache-Control from %s: default no-cache, immutable only on /assets/ (%d entries read)"
            % (variable, len(entries))
        )
    return ok, lines


def _count_blocks(block: Block) -> int:
    return sum(1 + _count_blocks(child) for child in block.children)


def run(root: str) -> tuple[bool, list[str]]:
    with open(os.path.join(root, CONFIG), encoding="utf-8") as handle:
        return check(handle.read())


def selftest(root: str) -> list[str]:
    out = []
    with open(os.path.join(root, CONFIG), encoding="utf-8") as handle:
        real = handle.read()

    def refused(text: str, what: str) -> None:
        ok, _ = check(text)
        assert not ok, what
        out.append("  refuses " + what)

    def plant(anchor: str, replacement: str) -> str:
        assert real.count(anchor) == 1, "the real config has no unique %r to plant on" % anchor
        return real.replace(anchor, replacement, 1)

    assets = "    location /assets/ {\n"
    csp = "    add_header Content-Security-Policy "
    referrer = '    add_header Referrer-Policy "strict-origin-when-cross-origin" always;\n'
    default = '    default             "no-cache";\n'
    root_location = "    location / {\n"

    assert check(real)[0], "a copy of the real config does not pass"
    out.append("  a copy of the real config passes")

    refused(
        plant(assets, assets + '        add_header Cache-Control "public, immutable";\n'),
        "an add_header put back into location /assets/ (the H22 defect)",
    )
    refused(
        plant(root_location, '    if ($uri = /x) {\n        add_header X-Probe "1";\n    }\n' + root_location),
        "an add_header inside a server-level `if`",
    )
    no_csp = "\n".join(l for l in real.split("\n") if not l.startswith(csp))
    assert no_csp != real, "the real config has no CSP line to remove"
    refused(no_csp, "a config that lost its Content-Security-Policy")
    refused(
        plant(referrer, '    add_header Referrer-Policy "" always;\n'),
        "a security header declared with an empty value (the pair)",
    )
    refused(
        plant(referrer, '    add_header Referrer-Policy "strict-origin-when-cross-origin";\n'),
        "a security header without `always`",
    )
    refused(plant(default, '    default             "public, max-age=600";\n'),
            "a cache map whose default is not no-cache")
    refused(plant(default, default + '    ~^/fonts/           "public, immutable";\n'),
            "`immutable` on an entry outside /assets/")
    refused("", "an empty config -- no server, nothing checked (the pair)")
    refused(real + "\nserver {\n", "a config it cannot close")

    ok, _ = run(root)
    assert ok, "the real tree does not pass its own nginx headers check"
    out.append("  the real tree passes")
    return out
