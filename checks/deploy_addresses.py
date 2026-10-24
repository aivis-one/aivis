"""No deployment address in the product's code (H35 P-127).

WHY THIS EXISTS. The product must install on any server with one command.
Until H35 it stood up only on aivis.one: the API address was a fallback in the
frontend's API client and a value in frontend/.env.production, the CSP in
frontend/nginx.conf named api. and files., the registration page linked the
privacy policy by its full address, and the installer carried the domains as
constants. On another domain the cabinet was a white page of CSP errors. Now
every address of a server comes from the two answers the installer asks for
and travels from there (scripts/install_aivis.sh, "Deployment Addresses");
this check keeps a literal from coming back.

WHAT IT REFUSES, in the product's code (ROOTS, minus EXCLUDED):
  - `aivis.one` in lowercase, anywhere: a host name, a comment naming the
    production address, test data;
  - the domain in ANY case where it can only be an address: after `//`, after
    `@`, or after a label and a dot (`API.AIVIS.ONE`);
  - the bot's handle (`aivisonebot`), a t.me/ or telegram.me/ link to a named
    bot, and the address of the production box.
The brand in capitals -- `AIVIS.ONE` in file headers, the API title, the TOTP
issuer, letter subjects -- is a name, not an address, and passes by the rule
itself rather than by a list.

WHAT IT DOES NOT CATCH, and cannot: a deployment address of ANOTHER domain
written into the code. The check knows the one domain this product was tied
to; it is a guard against that tie coming back, not a proof that no address
of any kind is hard-coded.

TESTS ARE SCANNED like everything else. Where an address is just data, tests
use the reserved domains (RFC 2606: example.com, example.org), so no test
needs an exception here.

THE BUILT OUTPUT, `--built PATH [--expect ORIGIN ...]` (CI, after building
with example.com origins): a built bundle and a rendered nginx.conf are
scanned for the address forms only -- the bare lowercase rule does not apply,
because the brand's accessible name (`aria-label`) is inside the bundle as a
string and minified code has no lines to except. legal/ is skipped there for
the same reason as in the source (EXCLUDED). Every `--expect` origin must be
found at least once: an empty or wrongly built tree must not pass for having
nothing in it.

STANDARD LIBRARY ONLY, like every check here.
"""
from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile

# The product's code: what the installer deploys and what builds it. Each
# root must exist and yield at least one scanned file -- a renamed directory
# must make this check fail, not pass vacuously.
ROOTS = (
    "backend",
    "frontend",
    "scripts",
    "comms-profile",
    "docker-compose.yml",
    ".github",
)

# Directories that are not source: dependencies, build output, caches. Never
# tracked; skipped wherever they appear so that a local run after `npm ci`
# and `npm run build` scans what CI scans.
SKIP_DIRS = {"node_modules", "dist", ".vite", "__pycache__", ".pytest_cache",
             ".mypy_cache", ".ruff_cache", ".venv", "venv"}

# Not product code, each for a stated reason (H35 handover, section 4). The
# reason is printed with every run so the list cannot become a hiding place.
EXCLUDED = (
    ("frontend/public/legal/", "legal texts of AIVIS.ONE LLC: the operator's "
     "contact e-mail and the domain in them are text of the document, changed "
     "by the lawyer, not configuration"),
    ("*.md", "documents, not code"),
)

# Exact strings allowed in exactly these files: the brand's accessible name.
# Masked before the scan, so ANY other literal in the same file is still
# caught; an entry whose string is no longer in its file fails the check (a
# stale exception is a hole nobody remembers opening).
BRAND_NAMES = (
    ("frontend/src/components/ui/AivisLogo.vue", 'aria-label="aivis.one"',
     "the logo's accessible name is the brand, read aloud"),
    ("frontend/public/aivis-wordmark.svg", 'aria-label="aivis.one"',
     "the wordmark's accessible name is the brand, read aloud"),
)

# The address forms. Applied to source and to built output.
ADDRESS_RULES = (
    ("address", re.compile(r"(?://|@|[A-Za-z0-9-]\.)aivis\.one(?![A-Za-z0-9-])", re.I)),
    ("bot handle", re.compile(r"aivisonebot", re.I)),
    ("bot link", re.compile(r"(?<![A-Za-z0-9-])(?:t|telegram)\.me/[A-Za-z0-9_]", re.I)),
    ("box address", re.compile(r"(?<![0-9.])38\.180\.96\.106(?![0-9])")),
)
# Source only: the domain in lowercase anywhere.
SOURCE_RULES = (("domain", re.compile(r"aivis\.one(?![A-Za-z0-9-])")),) + ADDRESS_RULES

# Never text: skipped by extension, and anything with a NUL byte besides.
BINARY_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".woff", ".woff2",
              ".ttf", ".otf", ".eot", ".pdf", ".zip", ".gz", ".tar", ".pyc",
              ".mp4", ".webm", ".mp3"}


def _rel(root: str, path: str) -> str:
    return os.path.relpath(path, root).replace(os.sep, "/")


def _excluded(rel: str) -> bool:
    for pattern, _reason in EXCLUDED:
        if pattern.startswith("*."):
            if rel.endswith(pattern[1:]):
                return True
        elif rel.startswith(pattern):
            return True
    return False


def _read_text(path: str) -> str | None:
    if os.path.splitext(path)[1].lower() in BINARY_EXT:
        return None
    with open(path, "rb") as handle:
        data = handle.read()
    if b"\0" in data:
        return None
    return data.decode("utf-8", errors="replace")


def _walk(base: str):
    if os.path.isfile(base):
        yield base
        return
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            yield os.path.join(dirpath, name)


def _findings(rel: str, text: str, rules) -> list[str]:
    """One finding per occurrence: the first rule (in order) that matches a
    span reports it, so `https://aivis.one` is one finding, not two."""
    out = []
    for number, line in enumerate(text.split("\n"), 1):
        taken: list[tuple[int, int]] = []
        for label, rule in rules:
            for match in rule.finditer(line):
                start, end = match.span()
                if any(start < e and s < end for s, e in taken):
                    continue
                taken.append((start, end))
                out.append("%s:%d: %s %r" % (rel, number, label, match.group(0)))
    return out


def scan_source(root: str) -> tuple[bool, list[str]]:
    """The product's code under `root` (a checkout)."""
    lines: list[str] = []
    bad: list[str] = []
    brand: dict[str, list[str]] = {}
    for path, allowed, _reason in BRAND_NAMES:
        brand.setdefault(path, []).append(allowed)
    seen_brand: set[str] = set()

    for top in ROOTS:
        base = os.path.join(root, top)
        if not os.path.exists(base):
            bad.append("%s: missing -- a root of the product's code is gone; "
                       "update ROOTS rather than scan nothing" % top)
            continue
        scanned = 0
        for path in _walk(base):
            rel = _rel(root, path)
            if _excluded(rel):
                continue
            text = _read_text(path)
            if text is None:
                continue
            scanned += 1
            for allowed in brand.get(rel, []):
                if allowed in text:
                    seen_brand.add(rel)
                    text = text.replace(allowed, " " * len(allowed))
            bad.extend(_findings(rel, text, SOURCE_RULES))
        if scanned == 0:
            bad.append("%s: no file scanned -- an empty root proves nothing" % top)
        lines.append("%s: %d files scanned" % (top, scanned))

    for path, allowed, _reason in BRAND_NAMES:
        if path not in seen_brand:
            bad.append("%s: the allowed %r is not there -- a stale exception; "
                       "remove it from BRAND_NAMES" % (path, allowed))

    for pattern, reason in EXCLUDED:
        lines.append("not scanned: %s -- %s" % (pattern, reason))
    for path, allowed, reason in BRAND_NAMES:
        lines.append("allowed: %s in %s -- %s" % (allowed, path, reason))
    if bad:
        return False, bad + lines
    lines.append("no deployment address in the product's code")
    return True, lines


def scan_built(path: str, expect: list[str]) -> tuple[bool, list[str]]:
    """A built tree (dist/) or a single rendered file (nginx default.conf)."""
    bad: list[str] = []
    found = {origin: 0 for origin in expect}
    scanned = 0
    base = path if os.path.isdir(path) else os.path.dirname(path) or "."
    if not os.path.exists(path):
        return False, ["%s: does not exist" % path]
    for file in _walk(path):
        rel = _rel(base, file)
        if rel.startswith("legal/"):
            continue
        text = _read_text(file)
        if text is None:
            continue
        scanned += 1
        bad.extend(_findings(rel, text, ADDRESS_RULES))
        for origin in expect:
            found[origin] += text.count(origin)
    if scanned == 0:
        bad.append("%s: no file scanned -- an empty build proves nothing" % path)
    for origin, count in found.items():
        if count == 0:
            bad.append("%s: the expected origin %s is not in it -- not built "
                       "with the addresses it was given" % (path, origin))
    lines = ["%s: %d files scanned (legal/ skipped)" % (path, scanned)]
    lines += ["  %s: %d occurrence(s)" % (o, c) for o, c in found.items()]
    if bad:
        return False, bad + lines
    lines.append("no deployment address in %s" % path)
    return True, lines


def run(root: str) -> tuple[bool, list[str]]:
    return scan_source(root)


# ---------------------------------------------------------------------------
# selftest
# ---------------------------------------------------------------------------

def _write(base: str, rel: str, text: str) -> None:
    path = os.path.join(base, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def _clean_tree(root: str, tmp: str) -> None:
    """A minimal tree with every root and the two real brand files."""
    _write(tmp, "backend/app/x.py", "# AIVIS.ONE Backend -- header\nTITLE = 'AIVIS.ONE API'\n")
    _write(tmp, "frontend/src/a.ts", "export const A = 1\n")
    _write(tmp, "scripts/x.sh", "#!/bin/bash\n# AIVIS.ONE -- header\nAPI_DOMAIN=\"api.${D}\"\n")
    _write(tmp, "comms-profile/types.yaml", "types: {}\n")
    _write(tmp, "docker-compose.yml", "services: {}\n")
    _write(tmp, ".github/workflows/ci.yml", "name: CI\n")
    for path, _allowed, _reason in BRAND_NAMES:
        dst = os.path.join(tmp, path)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(os.path.join(root, path), dst)


def selftest(root: str) -> list[str]:
    out: list[str] = []

    def case(plant, expect_ok: bool, what: str, must_report: int = 0) -> None:
        tmp = tempfile.mkdtemp(prefix="deploy-addresses-", dir=os.path.dirname(os.path.abspath(__file__)))
        try:
            _clean_tree(root, tmp)
            plant(tmp)
            ok, lines = scan_source(tmp)
        finally:
            shutil.rmtree(tmp)
        assert ok == expect_ok, "%s: expected %s, got %s\n%s" % (
            what, "pass" if expect_ok else "refusal", "pass" if ok else "refusal",
            "\n".join(lines))
        if must_report:
            hits = [l for l in lines if ": domain " in l or ": address " in l]
            assert len(hits) >= must_report, "%s: %d reported, %d expected" % (
                what, len(hits), must_report)
        out.append("  %s %s" % ("passes" if expect_ok else "refuses", what))

    def put(rel: str, text: str):
        return lambda tmp: _write(tmp, rel, text)

    case(lambda tmp: None, True, "a clean tree (brand headers, the real brand files)")
    case(put("frontend/src/api/client.ts", "const B = 'https://api.aivis.one'\n"),
         False, "the API fallback put back into src/ (the H35 defect)")
    case(put("frontend/src/a.ts", "// talks to aivis.one\n"),
         False, "the domain named in a comment in src/")
    case(put("frontend/src/a.ts", "const A = 'https://API.AIVIS.ONE'\n"),
         False, "the address in capitals")
    case(put("frontend/src/a.ts", "const A = 'x@aivis.one'\n"),
         False, "an e-mail address on the domain")
    case(put("frontend/src/a.ts", "a = 'https://aivis.one'\nb = 'https://files.aivis.one'\n"),
         False, "two literals in one file, both reported (repeat)", must_report=2)
    case(put("frontend/.env.production", "VITE_TELEGRAM_BOT_URL=https://t.me/aivisonebot\n"),
         False, "a bot link and handle in an env file")
    case(put("scripts/x.sh", "BOX=38.180.96.106\n"), False, "the production box's address")
    case(put("backend/tests/test_x.py", "URL = 'https://files.aivis.one'\n"),
         False, "the domain as test data (tests use example.com)")
    case(put("frontend/public/legal/en/terms.html", "<p>hello@aivis.one, aivis.one</p>\n"),
         True, "the domain in a legal text (excluded: frontend/public/legal/)")
    case(put("frontend/README.md", "Served at https://aivis.one/app/\n"),
         True, "the domain in a document (excluded: *.md)")
    case(put("landing/site/index.html", "<a href='https://aivis.one/'>\n"),
         True, "the domain in landing/ (not a root)")
    case(put("frontend/src/a.ts", "// AIVIS.ONE Frontend -- header\nconst T = 'AIVIS.ONE'\n"),
         True, "the brand in capitals")

    logo = BRAND_NAMES[0][0]

    def extra_in_logo(tmp: str) -> None:
        with open(os.path.join(tmp, logo), "a", encoding="utf-8") as handle:
            handle.write("\n<!-- https://aivis.one -->\n")
    case(extra_in_logo, False, "another literal in a file with an allowed brand name")

    def stale(tmp: str) -> None:
        path = os.path.join(tmp, logo)
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text.replace(BRAND_NAMES[0][1], 'aria-label="logo"'))
    case(stale, False, "an allowed brand name no longer in its file (stale exception)")
    case(lambda tmp: shutil.rmtree(os.path.join(tmp, "comms-profile")),
         False, "a missing root")

    def empty_root(tmp: str) -> None:
        shutil.rmtree(os.path.join(tmp, "comms-profile"))
        os.makedirs(os.path.join(tmp, "comms-profile"))
    case(empty_root, False, "an empty root (the pair: scanned and non-empty)")

    # --built
    def built(files: dict[str, str], expect: list[str], expect_ok: bool, what: str) -> None:
        tmp = tempfile.mkdtemp(prefix="deploy-addresses-built-", dir=os.path.dirname(os.path.abspath(__file__)))
        try:
            for rel, text in files.items():
                _write(tmp, rel, text)
            ok, lines = scan_built(tmp, expect)
        finally:
            shutil.rmtree(tmp)
        assert ok == expect_ok, "%s\n%s" % (what, "\n".join(lines))
        out.append("  --built %s %s" % ("passes" if expect_ok else "refuses", what))

    api = "https://api.example.com"
    bundle_ok = 'fetch("https://api.example.com/x");{"aria-label":"aivis.one"}'
    built({"assets/i.js": bundle_ok, "legal/en/t.html": "hello@aivis.one"}, [api], True,
          "a bundle on example.com with the brand name and legal texts")
    built({"assets/i.js": bundle_ok + 'u="https://api.aivis.one"'}, [api], False,
          "a bundle carrying the production API")
    built({"assets/i.js": 'fetch("https://api.other.org/x")'}, [api], False,
          "a bundle without the expected origin (the pair)")
    built({}, [api], False, "an empty build")

    ok, lines = run(root)
    assert ok, "the real tree does not pass:\n" + "\n".join(lines)
    out.append("  the real tree passes")
    return out


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for line in selftest(root):
            print(line)
        print("SELFTEST OK")
        return 0
    if argv[:1] == ["--built"] and len(argv) >= 2:
        path, rest, expect = argv[1], argv[2:], []
        while rest:
            if rest[0] != "--expect" or len(rest) < 2:
                print("usage: deploy_addresses.py --built PATH [--expect ORIGIN ...]")
                return 2
            expect.append(rest[1])
            rest = rest[2:]
        ok, lines = scan_built(path, expect)
    elif not argv:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ok, lines = run(root)
    else:
        print("usage: deploy_addresses.py [--selftest | --built PATH [--expect ORIGIN ...]]")
        return 2
    for line in lines:
        print(line)
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
