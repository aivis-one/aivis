"""The design system's files copied into frontend/ stay equal to their source.

WHY THIS EXISTS. The cabinet serves the design system from copies under
frontend/ (the build cannot read outside it). A copy that is edited, or that is
left behind when the system changes, is a second source of truth that nothing
notices. This check holds every copy byte-equal to its source, so a change to
the system is carried over in the same commit or the gate refuses.

WHAT IT ASSERTS:
  1. design-system/tokens/tokens.css, tokens-dark.css and
     components/components.css equal frontend/src/styles/ds/ of the same name;
  2. design-system/components/icons/icons.svg equals
     frontend/src/assets/icons/ds-icons.svg;
  3. every design-system/fonts/*.woff2 equals frontend/public/fonts/ of the
     same name, and no woff2 sits in frontend/public/fonts without a source;
  4. design-system/fonts/fonts.css equals frontend/src/styles/ds/fonts.css
     once its `url('./<file>')` is rewritten to `url('/fonts/<file>')`.

STANDARD LIBRARY ONLY.
"""
from __future__ import annotations

import glob
import os
import re
import shutil
import tempfile

SYSTEM = "design-system"
FONTS_SRC = os.path.join(SYSTEM, "fonts")
FONTS_DST = os.path.join("frontend", "public", "fonts")
FONTS_CSS_SRC = os.path.join(FONTS_SRC, "fonts.css")
FONTS_CSS_DST = os.path.join("frontend", "src", "styles", "ds", "fonts.css")

PAIRS = [
    (os.path.join(SYSTEM, "tokens", "tokens.css"),
     os.path.join("frontend", "src", "styles", "ds", "tokens.css")),
    (os.path.join(SYSTEM, "tokens", "tokens-dark.css"),
     os.path.join("frontend", "src", "styles", "ds", "tokens-dark.css")),
    (os.path.join(SYSTEM, "components", "components.css"),
     os.path.join("frontend", "src", "styles", "ds", "components.css")),
    (os.path.join(SYSTEM, "components", "icons", "icons.svg"),
     os.path.join("frontend", "src", "assets", "icons", "ds-icons.svg")),
]


def _read(root: str, path: str) -> bytes | None:
    try:
        with open(os.path.join(root, path), "rb") as handle:
            return handle.read()
    except OSError:
        return None


def _woff2(root: str, folder: str) -> list[str]:
    return sorted(os.path.basename(p) for p in glob.glob(os.path.join(root, folder, "*.woff2")))


def run(root: str) -> tuple[bool, list[str]]:
    ok = True
    lines: list[str] = []
    pairs = list(PAIRS)
    names = _woff2(root, FONTS_SRC)
    for name in names:
        pairs.append((os.path.join(FONTS_SRC, name), os.path.join(FONTS_DST, name)))
    for src, dst in pairs:
        a, b = _read(root, src), _read(root, dst)
        if a is None:
            ok = False
            lines.append("source missing: %s" % src)
        elif b is None:
            ok = False
            lines.append("copy missing: %s (source %s)" % (dst, src))
        elif a != b:
            ok = False
            lines.append("copy differs from its source: %s <> %s" % (dst, src))
    for name in sorted(set(_woff2(root, FONTS_DST)) - set(names)):
        ok = False
        lines.append("font copy with no source: %s" % os.path.join(FONTS_DST, name))
    lines.insert(0, "files compared byte for byte        : %d (%d fonts)" % (len(pairs), len(names)))

    css_src, css_dst = _read(root, FONTS_CSS_SRC), _read(root, FONTS_CSS_DST)
    if css_src is None or css_dst is None:
        ok = False
        lines.append("fonts.css or its copy is missing")
    else:
        rewritten = re.sub(rb"url\((['\"]?)\./([^'\")]+)\1\)", rb"url(\1/fonts/\2\1)", css_src)
        if rewritten == css_src:
            ok = False
            lines.append("fonts.css: no `./<file>` url to rewrite -- the check has nothing to compare")
        elif rewritten != css_dst:
            ok = False
            lines.append("fonts.css copy differs from its source after the url rewrite")
        else:
            lines.append("fonts.css equals its copy after `./<file>` -> `/fonts/<file>`")
    return ok, lines


def _flip(path: str) -> None:
    with open(path, "rb") as handle:
        data = bytearray(handle.read())
    data[len(data) // 2] ^= 1
    with open(path, "wb") as handle:
        handle.write(bytes(data))


def selftest(root: str) -> list[str]:
    out: list[str] = []
    ok, _ = run(root)
    assert ok, "the real tree does not pass its own ds copies check"
    out.append("  the real tree passes")

    # The fixture lives inside checks/ and is removed in `finally`; the system
    # temp folder is not used.
    base = tempfile.mkdtemp(prefix="ds-copies-", dir=os.path.dirname(os.path.abspath(__file__)))
    try:
        files = [p for pair in PAIRS for p in pair] + [FONTS_CSS_SRC, FONTS_CSS_DST]
        for name in _woff2(root, FONTS_SRC):
            files += [os.path.join(FONTS_SRC, name), os.path.join(FONTS_DST, name)]
        for path in files:
            dst = os.path.join(base, path)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(os.path.join(root, path), dst)
        clean, _ = run(base)
        assert clean, "the untouched fixture already fails"
        out.append("  an untouched copy passes")

        font = _woff2(root, FONTS_DST)[0]
        for what, path in (
            ("a one-byte change in the tokens copy", PAIRS[0][1]),
            ("a one-byte change in the icons copy", PAIRS[3][1]),
            ("a one-byte change in a font copy", os.path.join(FONTS_DST, font)),
            ("a one-byte change in the fonts.css copy", FONTS_CSS_DST),
        ):
            target = os.path.join(base, path)
            with open(target, "rb") as handle:
                before = handle.read()
            _flip(target)
            with open(target, "rb") as handle:
                assert handle.read() != before, "the plant did not change the file"
            bad, _ = run(base)
            assert not bad, "the check accepted " + what
            out.append("  refuses " + what)
            with open(target, "wb") as handle:
                handle.write(before)
            again, _ = run(base)
            assert again, "the restored fixture fails"

        os.remove(os.path.join(base, FONTS_DST, font))
        bad, _ = run(base)
        assert not bad, "the check accepted a missing font copy"
        out.append("  refuses a missing font copy")
    finally:
        shutil.rmtree(base, ignore_errors=True)
    return out
