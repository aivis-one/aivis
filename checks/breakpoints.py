"""Every width breakpoint used in frontend/src must be a declared one.

WHY THIS EXISTS. The product had seven different width breakpoints spread over
31 media queries in 22 files, and only two of them were named anywhere. The
other five were one-off literals inside individual views, so nobody could tell
a deliberate breakpoint from a number somebody typed once.

The set is now declared in `frontend/src/styles/variables.css` as `--bp-*`
tokens. This check reads the declared set FROM THAT FILE -- it does not carry
its own copy -- and fails if any media query uses a width that is not in it.
Add a breakpoint to the stylesheet and this check starts accepting it; delete
one and it starts rejecting every query that used it. One source of truth.

WHY THE TOKENS CANNOT SIMPLY BE USED IN THE QUERIES: a CSS custom property is
not substituted inside a media condition. `@media (min-width: var(--bp-tier-md))`
is invalid and silently never matches -- no error, no warning. So every query
still writes its number literally, and this check is what keeps the numbers and
the declaration in step.
"""
from __future__ import annotations

import os
import re

from lib.css import mask_comments, media_blocks, style_css, style_langs

WIDTH = re.compile(r"\(\s*(min|max)-width\s*:\s*([0-9.]+)\s*(px|rem|em)\s*\)", re.I)
BP_TOKEN = re.compile(r"--bp-([\w-]+)\s*:\s*([0-9.]+)px\s*;")


def declared_set(root: str) -> dict[int, str]:
    """{pixels: token-name} read from variables.css, comments masked first so a
    breakpoint merely discussed in prose is not read as a declaration."""
    path = os.path.join(root, "frontend", "src", "styles", "variables.css")
    text = mask_comments(open(path, encoding="utf-8").read())
    return {int(float(m.group(2))): "--bp-" + m.group(1) for m in BP_TOKEN.finditer(text)}


def used(root: str, extra: tuple[str, str] | None = None) -> list[tuple[str, int, str, int]]:
    """-> [(relative_path, line, 'min'|'max', pixels)] for every width query."""
    src = os.path.join(root, "frontend", "src")
    out = []
    files = []
    for dirpath, dirnames, names in os.walk(src):
        dirnames[:] = [d for d in dirnames if d != "node_modules"]
        for name in sorted(names):
            if name.endswith((".vue", ".css")):
                files.append(os.path.join(dirpath, name))
    for path in sorted(files):
        text = open(path, encoding="utf-8").read()
        langs = [l for l in style_langs(text) if l.lower() != "css"]
        if langs:
            raise ValueError("%s uses <style lang=%r>; this check only reads plain CSS"
                             % (path, langs[0]))
        css = mask_comments(style_css(path, text))
        rel = os.path.relpath(path, src).replace("\\", "/")
        for condition, whole, _body in media_blocks(css):
            for kind, value, unit in WIDTH.findall(condition):
                px = int(float(value) * (16 if unit.lower() in ("rem", "em") else 1))
                line = css.count("\n", 0, css.find(whole)) + 1
                out.append((rel, line, kind.lower(), px))
    if extra:
        for kind, value, unit in WIDTH.findall(extra[1]):
            out.append((extra[0], 0, kind.lower(), int(float(value))))
    return out


def run(root: str) -> tuple[bool, list[str]]:
    declared = declared_set(root)
    sites = used(root)
    undeclared = sorted({px for _f, _l, _k, px in sites} - set(declared))
    lines = [
        "declared in variables.css : " + ", ".join(
            "%d (%s)" % (px, declared[px]) for px in sorted(declared)),
        "used in frontend/src      : %d width queries over %d files, values %s" % (
            len(sites), len({f for f, _l, _k, _p in sites}),
            sorted({px for _f, _l, _k, px in sites})),
    ]
    if undeclared:
        lines.append("UNDECLARED VALUES IN USE  : %s" % undeclared)
        for f, l, k, px in sorted(sites):
            if px in undeclared:
                lines.append("    %s:%d  (%s-width: %dpx)" % (f, l, k, px))
        return False, lines
    lines.append("UNDECLARED VALUES IN USE  : none")
    return True, lines


def selftest(root: str) -> list[str]:
    """A check that cannot fail is not a check. Plant an undeclared width in a
    synthetic file and prove the check rejects it, then prove the real tree
    still passes."""
    out = []
    declared = declared_set(root)
    assert declared, "no --bp-* tokens found -- the declared set cannot be empty"

    planted = used(root, extra=("<planted>", "@media (max-width: 777px) { .x { color: red } }"))
    bad = {px for _f, _l, _k, px in planted} - set(declared)
    assert bad == {777}, "planted 777px was not detected as undeclared (got %r)" % bad
    out.append("  planted an undeclared 777px width -> detected")

    ok, _ = run(root)
    assert ok, "the real tree does not pass its own breakpoint check"
    out.append("  the real tree passes")
    return out
