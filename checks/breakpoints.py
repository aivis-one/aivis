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

BOTH DIRECTIONS, and the second was missing until 2026-08-25. Asserting that
every width IN USE is declared says nothing about a token that is declared and
used by NOTHING. `--bp-tier-lg` sat in that state while the only rule keyed to
its value lived in CSideNav as a bare literal -- a tier that existed only in the
stylesheet's own opinion of itself, which is the same drift the first direction
exists to prevent, pointing the other way. A token counts as USED if its VALUE
appears in a width query, or its NAME appears in a `var()` or in a script that
reads it off the computed style. Comments are masked everywhere, so a breakpoint
merely DISCUSSED in prose is not mistaken for one in service.

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
# A REFERENCE, not a declaration: var(--bp-x) or getPropertyValue('--bp-x').
# The name is matched GREEDILY and the declaration is excluded by looking at what
# FOLLOWS it, not by a lookahead inside the name. A lookahead there backtracks:
# `--bp-([\w-]+)\s*(?!\s*:)` matches "tier-l" on the line that declares
# --bp-tier-lg, because dropping the final "g" makes the lookahead succeed. That
# both invents a token nobody wrote and would let a token whose name is a prefix
# of another count as used. Measured on `--bp-tier-lg: 1472px;` before the fix:
# ['tier-l'] where the answer is [].
NAME_USE = re.compile(r"--bp-([\w-]+)")
DECLARATION_TAIL = re.compile(r"\s*:")
SCRIPT_LINE_COMMENT = re.compile(r"(?<![:/])//[^\n]*")
SCRIPT_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)


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


def referenced_names(root: str) -> set[str]:
    """`--bp-*` names reached by NAME rather than by value: a var() on a painting
    surface, or a script reading the token off the computed style. Comments are
    masked first -- a token named in prose is discussed, not used, and counting
    prose would make this half of the check unable to fail."""
    src = os.path.join(root, "frontend", "src")
    names: set[str] = set()
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [d for d in dirnames if d != "node_modules"]
        for name in sorted(filenames):
            if not name.endswith((".vue", ".css", ".ts", ".js")):
                continue
            path = os.path.join(dirpath, name)
            text = open(path, encoding="utf-8").read()
            if name.endswith(".css"):
                body = mask_comments(text)
            elif name.endswith(".vue"):
                # the <style> region is CSS; the rest is script/template, and a
                # .vue file is three languages -- one masker over the whole SFC
                # lets a /* inside a // comment swallow the template.
                body = mask_comments(style_css(path, text)) + "\n" + _mask_script(text)
            else:
                body = _mask_script(text)
            for m in NAME_USE.finditer(body):
                if DECLARATION_TAIL.match(body, m.end()):
                    continue          # this is the declaration itself
                names.add("--bp-" + m.group(1))
    return names


def _mask_script(text: str) -> str:
    """Blank // and /* */ comments, preserving length and newlines."""
    return SCRIPT_LINE_COMMENT.sub(
        lambda m: "".join("\n" if c == "\n" else " " for c in m.group(0)),
        SCRIPT_BLOCK_COMMENT.sub(
            lambda m: "".join("\n" if c == "\n" else " " for c in m.group(0)), text))


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
    referenced = referenced_names(root)
    live = {px for _f, _l, _k, px in sites}
    unused = sorted((px, declared[px]) for px in declared
                    if px not in live and declared[px] not in referenced)
    ok = True
    if undeclared:
        lines.append("UNDECLARED VALUES IN USE  : %s" % undeclared)
        for f, l, k, px in sorted(sites):
            if px in undeclared:
                lines.append("    %s:%d  (%s-width: %dpx)" % (f, l, k, px))
        ok = False
    else:
        lines.append("UNDECLARED VALUES IN USE  : none")
    if unused:
        lines.append("DECLARED BUT USED BY NOTHING : %s"
                     % ", ".join("%s (%dpx)" % (name, px) for px, name in unused))
        lines.append("    a tier nothing keys off is a tier that exists only in this "
                     "stylesheet's opinion of itself -- use it or delete it")
        ok = False
    else:
        lines.append("DECLARED BUT UNUSED       : none")
    return ok, lines


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

    # THE OTHER DIRECTION, added 2026-08-25. Three plants in a throwaway copy of
    # frontend/src, the way the other checks do it. Each asserts THE TEXT CHANGED
    # before it asserts any outcome.
    import shutil
    import tempfile

    base = tempfile.mkdtemp()
    try:
        shutil.copytree(os.path.join(root, "frontend", "src"),
                        os.path.join(base, "frontend", "src"))
        clean, _ = run(base)
        assert clean, "the untouched copy already fails"
        variables = os.path.join(base, "frontend", "src", "styles", "variables.css")
        original = open(variables, encoding="utf-8", newline="").read()
        anchor = "  --bp-tier-md: "
        assert anchor in original, "selftest anchor missing in variables.css"
        orphan = "  --bp-zz-orphan: 777px;\n"
        nl = "\r\n" if "\r\n" in original else "\n"

        def write_vars(text):
            with open(variables, "w", encoding="utf-8", newline="") as fh:
                fh.write(text)

        # 1 -- declared, used by nothing
        planted = original.replace(anchor, orphan.replace("\n", nl) + anchor, 1)
        assert planted != original, "the orphan-token plant changed nothing"
        write_vars(planted)
        broke, reported = run(base)
        assert not broke and any("USED BY NOTHING" in ln for ln in reported), \
            "a declared-and-unused breakpoint was not caught: %r" % reported
        assert any("--bp-zz-orphan" in ln for ln in reported), "the wrong token was named"
        out.append("  caught: a breakpoint declared and used by nothing")

        # 2 -- the same token named ONLY in a comment. Prose is not use, and if
        #      the masker stopped working this half of the check could never fail.
        probe = os.path.join(base, "frontend", "src", "styles", "zz_probe.css")
        open(probe, "w", encoding="utf-8").write("/* about --bp-zz-orphan */\n.zz { color: red }\n")
        broke, reported = run(base)
        assert not broke and any("--bp-zz-orphan" in ln for ln in reported), \
            "a token mentioned only in a comment was counted as USED -- the masker is off"
        out.append("  caught: still caught when the token is named only in a comment")

        # 3 -- SURVIVAL: a script that actually reads the token off the computed
        #      style. This must NOT fire, or the check punishes a legitimate use.
        os.remove(probe)
        reader = os.path.join(base, "frontend", "src", "zz_reader.ts")
        open(reader, "w", encoding="utf-8").write(
            "export const bp = getComputedStyle(document.documentElement)\n"
            "  .getPropertyValue('--bp-zz-orphan')\n")
        survived, reported = run(base)
        assert survived, \
            "a token read by a script was reported unused: %r" % reported
        out.append("  survives: a breakpoint reached by NAME from a script")

        os.remove(reader)
        write_vars(original)
        restored, _ = run(base)
        assert restored, "the plants left the copy broken"
    finally:
        shutil.rmtree(base, ignore_errors=True)

    return out
