"""Every `var(--x)` the frontend paints with must resolve to a declared token.

WHY THIS EXISTS. An undeclared custom property does not error and does not
warn: the declaration is simply dropped and the element keeps whatever it would
have had. So `background: var(--surfase)` looks fine in review, passes the type
check, builds clean, and quietly paints nothing.

The usual token audit asks "does every DECLARED token resolve". This asks the
other direction -- "does every USED token exist" -- which is the direction that
catches a typo.

SCOPE. This is a check on what PAINTS, so it reads `<style>` blocks, `.css`
files AND inline `style=` attributes in templates: an inline style is CSS that
paints, whatever file type it lives in. `var()` inside `<script>` is reported
separately, because a hex or a token name there may be data rather than paint.

A `var(--x, fallback)` with a fallback is NOT a failure -- it degrades on
purpose -- but it is counted and shown, because a long list of fallbacks is
usually a sign that something was renamed and not finished.
"""
from __future__ import annotations

import os
import re
from collections import defaultdict

from lib.css import mask_comments

LINE_COMMENT = re.compile(r"(?<![:/])//[^\n]*")
STYLE = re.compile(r"<style\b[^>]*>(.*?)</style>", re.S | re.I)
SCRIPT = re.compile(r"<script\b[^>]*>(.*?)</script>", re.S | re.I)
INLINE = re.compile(r"""\bstyle=(["'])(.*?)\1""", re.S)

DECL = re.compile(r"(?:^|[;{\s])(--[\w-]+)\s*:")
USE = re.compile(r"var\(\s*(--[\w-]+)\s*(,)?")


def _surfaces(path: str, text: str) -> list[tuple[str, int, str]]:
    """-> [(kind, offset_in_file, css_text)] for everything that paints."""
    out = []
    if path.endswith(".css"):
        out.append(("css", 0, mask_comments(text)))
    elif path.endswith(".vue"):
        for m in STYLE.finditer(text):
            out.append(("style", m.start(1), mask_comments(m.group(1))))
        template = text
        for m in SCRIPT.finditer(text):
            template = template[:m.start(1)] + " " * (m.end(1) - m.start(1)) + template[m.end(1):]
        for m in INLINE.finditer(template):
            out.append(("inline-style", m.start(2), m.group(2)))
        for m in SCRIPT.finditer(text):
            out.append(("script", m.start(1),
                        LINE_COMMENT.sub(" ", mask_comments(m.group(1)))))
    return out


def scan(paths):
    declared: set[str] = set()
    uses: list[tuple[str, int, str, bool, str]] = []
    for path in paths:
        text = open(path, encoding="utf-8").read()
        for kind, offset, css in _surfaces(path, text):
            for m in DECL.finditer(css):
                declared.add(m.group(1))
            for m in USE.finditer(css):
                uses.append((path, text.count("\n", 0, offset + m.start()) + 1,
                             m.group(1), bool(m.group(2)), kind))
    return declared, uses


def _files(root: str) -> list[str]:
    src = os.path.join(root, "frontend", "src")
    out = []
    for dirpath, dirnames, names in os.walk(src):
        dirnames[:] = [d for d in dirnames if d != "node_modules"]
        for name in sorted(names):
            if name.endswith((".vue", ".css")):
                out.append(os.path.join(dirpath, name))
    return sorted(out)


def run(root: str) -> tuple[bool, list[str]]:
    src = os.path.join(root, "frontend", "src")
    declared, uses = scan(_files(root))
    painting = [u for u in uses if u[4] != "script"]

    missing = defaultdict(list)
    fallback = defaultdict(list)
    for path, line, token, has_fallback, _kind in painting:
        if token in declared:
            continue
        (fallback if has_fallback else missing)[token].append(
            (os.path.relpath(path, src).replace("\\", "/"), line))

    lines = [
        "declared tokens: %d | var() uses on painting surfaces: %d" % (len(declared), len(painting)),
        "undeclared WITHOUT a fallback (silently dropped): %d token(s), %d site(s)"
        % (len(missing), sum(len(v) for v in missing.values())),
    ]
    for token in sorted(missing):
        lines.append("  %s" % token)
        for rel, line in sorted(missing[token]):
            lines.append("     %s:%d" % (rel, line))
    lines.append("undeclared WITH a fallback (degrades on purpose): %d token(s)" % len(fallback))
    for token in sorted(fallback):
        lines.append("  %-28s %d site(s)" % (token, len(fallback[token])))
    return (not missing), lines


def selftest(root: str) -> list[str]:
    import tempfile

    out = []
    d = tempfile.mkdtemp()
    probe = os.path.join(d, "Probe.vue")
    open(probe, "w", encoding="utf-8").write(
        "<script setup lang=\"ts\">const x = 1</script>\n"
        "<template><div style=\"color: var(--inline-missing)\">hi</div></template>\n"
        "<style scoped>\n"
        ".a { --local: 4px; padding: var(--local); }\n"
        ".b { color: var(--not-declared-anywhere); }\n"
        ".c { gap: var(--also-missing, 8px); }\n"
        "</style>\n")
    declared, uses = scan([probe])
    assert "--local" in declared, "a locally declared token was not collected"
    painting = [u for u in uses if u[4] != "script"]
    bad = {u[2] for u in painting if u[2] not in declared and not u[3]}
    assert bad == {"--not-declared-anywhere", "--inline-missing"}, \
        "wrong undeclared set: %r" % bad
    out.append("  detects an undeclared token in <style> and in an inline style=")
    withfb = {u[2] for u in painting if u[3]}
    assert withfb == {"--also-missing"}, "fallback not classified separately: %r" % withfb
    out.append("  classifies a var() with a fallback separately")

    ok, _ = run(root)
    assert ok, "the real tree does not pass its own token check"
    out.append("  the real tree passes")
    return out
