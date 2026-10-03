#!/usr/bin/env python3
"""landing-studio v10.0.0 -- scripts/gate.py

The single carrier of every gate command (spec section 1). In v8 the gate
commands lived twice -- as inline greps inside protocols/deliver.md, and as
a second, drifted copy of prose in references/quality.md. That double
carriage produced findings D1, D2, D7, D13, and let C8/C9/T10 ship (grep -c
LINE counts instead of occurrence counts let a page carrying a live
`<script>alert(1)</script>` pass the integrity gate). v9 replaces both
carriers with this one script; `protocols/deliver.md` invokes it and
contains no grep strings, and `references/quality.md` documents ids/
severities/symptoms only, pointing here as the SSOT.

Carrier notes (avoiding a second implementation of anything already owned
elsewhere -- "pick one and state which" per section 4.12/1):
  - Q-INTEGRITY CALLS `scripts/integrity-check.sh` (does not reimplement it).
    That script is already the one occurrence-count-based implementation of
    the tail/cdn-cgi/__cf_email__/script-balance/html-body-balance/
    placeholder-residue checks; gate.py just runs it against every *.html
    page found by walking `dist/` and reports its result.
  - Q-I18N delegates to `scripts/i18n-check.py` over its CLI.
  - Q-CONTRAST delegates to `scripts/contrast-check.py` over its CLI.
  - Q-DECLARE and Q-CLAIMS delegate to `scripts/claims-check.py` over its CLI
    (--mode declare / --mode sweep), by the same mechanism -- no gate here
    hardcodes a red-line pattern, a retraction term or a vocabulary; the
    register is `redlines.json` and its only reader is that script.
  - Q-PROVENANCE delegates to `scripts/provenance-check.py` over its CLI.
  - Q-DS-ABSENCE delegates to `scripts/ds-verify-absence.py` over its CLI,
    re-deriving the design system's declared absence from the DS recorded in
    `deviations.json` -- nothing about that verification is stored.
  - Q-VOICE-INDEP and Q-VOICE-SCAN are implemented directly here (the voice
    skill owns the rule lists; the records are this file's to read). Both
    resolve a locale's page through `locale_path` IMPORTED from
    render-page.py -- the one carrier of the locale/path rule -- and never
    re-derive it.
  - Q-REVIEW, Q-RESPONSIVE, Q-CF-READY, Q-WCAG, Q-ORPHAN are implemented
    directly in this file (there is no other existing carrier for them).
    Q-ORPHAN's dist-walk overlaps deliberately with the orphan scan
    `i18n-check.py` also runs when given `--dist` (spec section 3 item 11) --
    the catalog lists Q-ORPHAN as its own MAJOR-severity gate distinct from
    Q-I18N's BLOCKER, so both run; this is intentional redundancy, not an
    accidental duplicate carrier.

Hard rules (do not regress these -- this is the whole point of the file):
  - every count is an OCCURRENCE count (`len(re.findall(...))`), never a line
    count -- this is finding C8/C9/T10.
  - every truncated list SAYS HOW MANY IT DROPPED (`joined()`, finding F-8).
    A detail line showing 5 of 10 failures with no marker is the display-side
    version of the same defect: an operator fixes the five names, re-runs, and
    is surprised by five more.
  - a gate that reads a RECORD binds that record to the artifact it judges.
    Q-VOICE-SCAN recomputes `text_sha256` from the rendered page's visible
    text, the way claims-check.py's reading record already re-hashes the page
    (F-6); a PASS text never asserts what the gate can only attest (F-1).
  - Q-WCAG checks each control SEPARATELY; a single generic `aria-label`
    count is forbidden (finding D2) -- a page can lose the language switch's
    aria-label while an unrelated aria-label (e.g. the menu toggle's)
    survives, and a generic count would still read "aria-label count >= 1"
    and falsely pass.
  - Q-CF-READY walks the WHOLE `dist/` tree (`dist.rglob(...)`), never globs
    `dist/*.html` (finding D13 -- that glob never matches `dist/{lang}/
    index.html`), requires a per-locale sitemap for every locale in
    site.json, and requires every `<loc>` and the robots `Sitemap:` line to
    be an absolute http(s) URL.

CLI:
  python3 scripts/gate.py --site site.json --content-dir content --dist dist \\
      [--tokens tokens.tokens.json] [--json report.json] [--allow-major]

  --tokens defaults to `tokens.tokens.json` sitting next to --site, falling
  back to the parent directory for a packaged child skill (the
  standard project layout); pass it explicitly if the tokens file lives
  elsewhere. This is an additive optional flag -- the literal command in
  spec section 1 works unchanged.

Conditional severity (spec 1.1 / OD-3): a GATES row is
`(id, severity_spec, fn)` where `severity_spec` is either a literal severity
string or a callable `(args, site) -> "BLOCKER"|"MAJOR"|"MINOR"`. Two gates
use a callable, `sev_claims`: the claims layer bites as a BLOCKER when the
project carries a red-line register and is a MAJOR debt when it does not.

Gate status has THREE values: PASS, FAIL and N/A. `N/A` means the check could
not run because the feature it checks is absent from this project -- it counts
toward no severity bucket and never changes the exit code, and it always
prints its REASON. An absent feature and a passing check are different states;
collapsing them is how v8 shipped green.

Output: one line per gate --
  GATE  <id>  <BLOCKER|MAJOR|MINOR>  <PASS|FAIL|N/A>  <detail>
then a summary line --
  RESULT: <PASS|FAIL> blocker=<n> major=<n> minor=<n>
(<n> = number of FAILING gates at that severity, in THIS catalog; there are
currently no MINOR-severity gates, so minor=0 always.)

Exit codes:
  0 -- zero BLOCKER failures, and (zero MAJOR failures OR --allow-major set).
  1 -- any BLOCKER failure (regardless of flags), or a MAJOR failure without
       --allow-major.
  2 -- usage/setup error (bad CLI args, or site.json unreadable).

--allow-major downgrades MAJOR failures to a printed warning and allows
exit 0 -- an explicit user override, per quality.md's severity semantics.
It never downgrades a BLOCKER.

--json writes a machine report (consumed by protocols/package.md's GATE-IN)
containing the same result, per-gate rows, and a `result_line` field holding
the exact printed RESULT line so a raw text search for `RESULT: PASS` and
`blocker=0` inside the JSON file succeeds too.
"""
import argparse
import hashlib
import html
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent

SEVERITIES = ("BLOCKER", "MAJOR", "MINOR")


def load_json(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


TRUNCATE_AT = 5


def joined(items, hint=None, limit=TRUNCATE_AT):
    """Join a gate's findings for one detail line and, when the list was cut,
    SAY HOW MANY WERE DROPPED (F-8). An operator who fixes the five names in a
    truncated line and re-runs must not be surprised by five more: a list that
    hides its own length is a display count pretending to be a total, which is
    the display-side version of the line-count-versus-occurrence-count rule this
    whole file exists to hold. `hint` names where the full list lives."""
    shown = "; ".join(str(i) for i in items[:limit])
    dropped = len(items) - limit
    if dropped <= 0:
        return shown
    tail = f"... and {dropped} more"
    if hint:
        tail += f" (run {hint} directly for the full list)"
    return f"{shown}; {tail}" if shown else tail


def find_html_pages(dist):
    """Walk the WHOLE dist/ tree, never glob dist/*.html (finding D13)."""
    if not dist.exists():
        return []
    return sorted(dist.rglob("*.html"))


def occurrences(pattern, text, flags=0):
    """Occurrence count, never a line count (finding C8/C9/T10)."""
    return len(re.findall(pattern, text, flags))


# ---------------------------------------------------------------- Q-INTEGRITY

def gate_integrity(args, site):
    pages = find_html_pages(args.dist)
    if not pages:
        return "FAIL", f"no *.html page found under {args.dist} (walked whole tree)"
    script = HERE / "integrity-check.sh"
    if not script.exists():
        return "FAIL", f"carrier script missing: {script}"
    cmd = ["bash", str(script)] + [str(p) for p in pages]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode == 0:
        return "PASS", f"{len(pages)} page(s) OK via integrity-check.sh"
    fail_lines = [l for l in proc.stdout.splitlines() if l.startswith("FAIL")]
    detail = joined(fail_lines, "integrity-check.sh") if fail_lines \
        else (proc.stdout.strip() or proc.stderr.strip())
    return "FAIL", f"integrity-check.sh: {len(fail_lines)} failing check(s) across {len(pages)} page(s): {detail}"


# -------------------------------------------------------------------- Q-I18N

def gate_i18n(args, site):
    script = HERE / "i18n-check.py"
    cmd = [sys.executable, str(script), "--site", str(args.site),
           "--content-dir", str(args.content_dir), "--dist", str(args.dist)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    out_lines = [l for l in proc.stdout.splitlines() if l.strip()]
    if proc.returncode == 0:
        tail = out_lines[-1] if out_lines else "PASS"
        return "PASS", f"i18n-check.py: {tail}"
    issue_lines = [l.strip() for l in out_lines if l.strip().startswith("-")]
    detail = joined(issue_lines, "i18n-check.py") if issue_lines \
        else (out_lines[-1] if out_lines else proc.stderr.strip())
    return "FAIL", f"i18n-check.py exit {proc.returncode}: {detail}"


# ------------------------------------------------------------------ Q-REVIEW

REVIEW_MARKER_RE = re.compile(r"\[review:")


def gate_review(args, site):
    total = 0
    sources = []
    for page in find_html_pages(args.dist):
        text = page.read_text(encoding="utf-8", errors="replace")
        n = occurrences(r"\[review:", text)
        if n:
            total += n
            sources.append(f"{page}={n}")
    for cf in sorted(args.content_dir.glob("*.json")):
        text = cf.read_text(encoding="utf-8", errors="replace")
        n = occurrences(r"\[review:", text)
        if n:
            total += n
            sources.append(f"{cf}={n}")
    if total:
        return "FAIL", f"{total} occurrence(s) of '[review:' found: {', '.join(sources[:6])}"
    return "PASS", "zero [review:] occurrences in rendered pages or content values"


# -------------------------------------------------------------- Q-RESPONSIVE

FIXED_WIDTH_RE = re.compile(r"(?<![a-zA-Z-])width\s*:\s*(\d+(?:\.\d+)?)px")
MIN_HEIGHT_44_RE = re.compile(r"min-height\s*:\s*44px")
MIN_WIDTH_MEDIA_RE = re.compile(r"@media[^{]*\bmin-width\s*:")
STYLE_BLOCK_RE = re.compile(r"<style[^>]*>(.*?)</style>", re.DOTALL)


def strip_media_blocks(css_text):
    """Remove the body of every @media {...} block (one level of nested
    braces, as CSS media queries have) so a width declared INSIDE a
    breakpoint is not mistaken for an unconditional fixed width."""
    out = []
    i, n = 0, len(css_text)
    while i < n:
        idx = css_text.find("@media", i)
        if idx == -1:
            out.append(css_text[i:])
            break
        out.append(css_text[i:idx])
        brace_start = css_text.find("{", idx)
        if brace_start == -1:
            out.append(css_text[idx:])
            break
        depth = 1
        j = brace_start + 1
        while j < n and depth > 0:
            if css_text[j] == "{":
                depth += 1
            elif css_text[j] == "}":
                depth -= 1
            j += 1
        i = j
    return "".join(out)


def check_responsive_page(html_text):
    style_m = STYLE_BLOCK_RE.search(html_text)
    css = style_m.group(1) if style_m else ""
    outside_media = strip_media_blocks(css)
    bad_widths = sorted({m.group(0).strip() for m in FIXED_WIDTH_RE.finditer(outside_media)
                          if float(m.group(1)) >= 300})
    reasons = []
    if bad_widths:
        reasons.append(f"fixed width>=300px outside any breakpoint: "
                       f"{joined(bad_widths, limit=3)}")
    if not MIN_HEIGHT_44_RE.search(css):
        reasons.append("no 'min-height: 44px' declaration found")
    if not MIN_WIDTH_MEDIA_RE.search(css):
        reasons.append("no 'min-width:' media query found")
    return reasons


def gate_responsive(args, site):
    pages = find_html_pages(args.dist)
    if not pages:
        return "FAIL", f"no *.html page found under {args.dist}"
    bad = []
    for page in pages:
        reasons = check_responsive_page(page.read_text(encoding="utf-8"))
        if reasons:
            bad.append(f"{page}: {'; '.join(reasons)}")
    if bad:
        return "FAIL", joined(bad)
    return "PASS", f"{len(pages)} page(s): no unconditional fixed width>=300px, min-height:44px present, min-width: breakpoint present"


# --------------------------------------------------------------- Q-CF-READY

CDN_HOSTS_RE = re.compile(r"cdnjs|googleapis|unpkg|jsdelivr|fonts\.gstatic", re.IGNORECASE)
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
LOC_RE = re.compile(r"<loc>([^<]*)</loc>")
ABS_HTTP_RE = re.compile(r"^https?://", re.IGNORECASE)


def gate_cf_ready(args, site):
    dist = args.dist
    if not dist.exists():
        return "FAIL", f"dist directory not found: {dist}"
    reasons = []

    # PRE-LAUNCH (trial finding A1): with no base_url the build deliberately
    # omits every artifact that would have to state an origin -- the sitemaps
    # and robots.txt among them. Demanding them here made a pre-launch project
    # build successfully and then fail its own BLOCKER gate, which is worse
    # than refusing to build: the refusal at least named the cause. The
    # origin-free half of the package is still required, and the omission is
    # REPORTED, never silently tolerated -- an unchecked URL layer reported as
    # unchecked, never as correct. SSOT for the mode: build_head_urls() in
    # render-page.py, references/quality.md for this gate's catalog row.
    pre_launch = not str(site.get("base_url") or "").strip()

    required = ["_redirects", "_headers"] if pre_launch else \
               ["_redirects", "_headers", "robots.txt", "sitemap.xml"]
    for name in required:
        if not (dist / name).exists():
            reasons.append(f"missing {name}")

    locales = site.get("locales", [])
    if pre_launch:
        stray = [f.name for f in sorted(dist.glob("sitemap*.xml"))] + \
                (["robots.txt"] if (dist / "robots.txt").exists() else [])
        if stray:
            reasons.append(f"pre-launch build carries origin-dependent file(s) with no base_url "
                           f"to build them from: {', '.join(stray)}")
    else:
        for loc in locales:
            if not (dist / f"sitemap-{loc}.xml").exists():
                reasons.append(f"missing sitemap-{loc}.xml (locale '{loc}' in site.json)")

    for sm in sorted(dist.glob("sitemap*.xml")):
        text = sm.read_text(encoding="utf-8", errors="replace")
        for loc_url in LOC_RE.findall(text):
            if not ABS_HTTP_RE.match(loc_url):
                reasons.append(f"{sm}: <loc>{loc_url}</loc> is not an absolute http(s) URL")

    robots = dist / "robots.txt"
    if robots.exists():
        text = robots.read_text(encoding="utf-8", errors="replace")
        sm_lines = [l for l in text.splitlines() if l.strip().lower().startswith("sitemap:")]
        if not sm_lines:
            reasons.append("robots.txt has no 'Sitemap:' line")
        for l in sm_lines:
            url = l.split(":", 1)[1].strip()
            if not ABS_HTTP_RE.match(url):
                reasons.append(f"robots.txt 'Sitemap:' line is not absolute http(s): '{url}'")

    # Walk the WHOLE dist/ tree, never dist/*.html (finding D13).
    all_pages = find_html_pages(dist)
    for page in all_pages:
        text = page.read_text(encoding="utf-8", errors="replace")
        if EMAIL_RE.search(text):
            reasons.append(f"{page}: email-shaped string found")
        cdn_hits = sorted(set(m.group(0).lower() for m in CDN_HOSTS_RE.finditer(text)))
        if cdn_hits:
            reasons.append(f"{page}: CDN host reference(s) found: {cdn_hits}")

    if reasons:
        return "FAIL", "; ".join(reasons[:8])
    return "PASS", (f"package files + {len(locales)} per-locale sitemap(s) present; "
                     f"all <loc>/Sitemap: absolute http(s); zero CDN/email across "
                     f"{len(all_pages)} page(s) (whole dist/ tree walked)")


# ------------------------------------------------------------------- Q-WCAG

LANG_ATTR_RE = re.compile(r'<html\b[^>]*\blang="[^"]+"', re.IGNORECASE)
LANG_SWITCH_ARIA_RE = re.compile(r"data-ls-lang-switch[^>]*aria-label")
MENU_ARIA_LABEL_RE = re.compile(r"data-ls-menu-open[^>]*aria-label")
MENU_ARIA_EXPANDED_RE = re.compile(r"data-ls-menu-open[^>]*aria-expanded")
DRAWER_ROLE_RE = re.compile(r'data-ls-drawer[^>]*role="dialog"')
DRAWER_MODAL_RE = re.compile(r"data-ls-drawer[^>]*aria-modal")
FOCUS_VISIBLE_RE = re.compile(r":focus-visible")
SKIP_LINK_RE = re.compile(r'class="ls-skip"')
MAIN_ID_RE = re.compile(r'<main\b[^>]*id="ls-main"')

# Each control is its OWN regex, checked independently -- a single generic
# aria-label count is forbidden (finding D2): a page can lose the language
# switch's aria-label while the menu toggle's aria-label (unrelated) survives,
# and a combined/aggregate count would still read ">=1" and falsely pass.
WCAG_CHECKS = [
    ("<html lang=...>", LANG_ATTR_RE),
    ("language-switch aria-label (data-ls-lang-switch)", LANG_SWITCH_ARIA_RE),
    ("menu-toggle aria-label (data-ls-menu-open)", MENU_ARIA_LABEL_RE),
    ("menu-toggle aria-expanded (data-ls-menu-open)", MENU_ARIA_EXPANDED_RE),
    ('drawer role="dialog" (data-ls-drawer)', DRAWER_ROLE_RE),
    ("drawer aria-modal (data-ls-drawer)", DRAWER_MODAL_RE),
    (":focus-visible rule", FOCUS_VISIBLE_RE),
    ('skip link (class="ls-skip")', SKIP_LINK_RE),
    ('<main id="ls-main">', MAIN_ID_RE),
]


def check_wcag_page(html_text):
    return [label for label, rx in WCAG_CHECKS if not rx.search(html_text)]


def gate_wcag(args, site):
    pages = find_html_pages(args.dist)
    if not pages:
        return "FAIL", f"no *.html page found under {args.dist}"
    bad = []
    for page in pages:
        missing = check_wcag_page(page.read_text(encoding="utf-8"))
        if missing:
            bad.append(f"{page}: missing {missing}")
    if bad:
        return "FAIL", joined(bad)
    return "PASS", f"{len(pages)} page(s) pass all {len(WCAG_CHECKS)} independent WCAG checks"


# --------------------------------------------------------------- Q-CONTRAST

def gate_contrast(args, site):
    tokens_path = args.tokens
    if not tokens_path.exists():
        return "FAIL", f"tokens file not found: {tokens_path}"
    script = HERE / "contrast-check.py"
    cmd = [sys.executable, str(script), str(tokens_path)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    out_lines = [l for l in proc.stdout.splitlines() if l.strip()]
    tail = out_lines[-1] if out_lines else ""
    if proc.returncode == 0:
        return "PASS", f"contrast-check.py: {tail}"
    fail_lines = [l for l in out_lines if l.startswith("FAIL")]
    detail = joined(fail_lines, "contrast-check.py") if fail_lines else tail
    return "FAIL", f"contrast-check.py: {detail}"


# ----------------------------------------------------------------- Q-ORPHAN

def gate_orphan(args, site):
    dist = args.dist
    if not dist.exists():
        return "FAIL", f"dist directory not found: {dist}"
    locales = site.get("locales", [])
    orphans = []
    for child in sorted(dist.iterdir()):
        if child.is_dir() and (child / "index.html").exists():
            loc = child.name
            if loc not in locales and loc not in {x["slug"].split("/")[0] for x in site.get("pages", [])}:
                orphans.append(f"{child}/index.html (locale '{loc}' not in site.json)")
    for sm in sorted(dist.glob("sitemap-*.xml")):
        loc = sm.stem[len("sitemap-"):]
        if loc not in locales:
            orphans.append(f"{sm} (locale '{loc}' not in site.json)")
    if orphans:
        return "FAIL", f"{len(orphans)} orphan page/sitemap under dist/: {joined(orphans)}"
    return "PASS", f"no orphan locale page/sitemap under dist/ ({len(locales)} locale(s) expected)"


# ------------------------------------------------- delegation helper (new v10)

def run_script(name, script_args, issue_prefixes=("-",)):
    """Delegate to a sibling script over its CLI -- never by import -- and turn
    its output into (status, detail) exactly the way gate_i18n already does.
    This is the one place the new delegating gates share, so a change to the
    convention cannot drift between them."""
    script = HERE / name
    if not script.exists():
        return "FAIL", f"carrier script missing: {script}"
    proc = subprocess.run([sys.executable, str(script)] + list(script_args),
                          capture_output=True, text=True)
    out_lines = [l for l in proc.stdout.splitlines() if l.strip()]
    if proc.returncode == 0:
        tail = out_lines[-1] if out_lines else "PASS"
        return "PASS", f"{name}: {tail}"
    issues = [l.strip() for l in out_lines
              if any(l.strip().startswith(pfx) for pfx in issue_prefixes)]
    detail = joined(issues, name) if issues else (out_lines[-1] if out_lines else proc.stderr.strip())
    return "FAIL", f"{name} exit {proc.returncode}: {detail}"


# ------------------------------------------- conditional severity (spec 1.1)

def sev_claims(args, site):
    """OD-3: a register in the project means someone has claim constraints to
    check against, and the gate bites. No register means nothing to check
    against, so an undeclared item is a MAJOR debt, not a refusal to ship."""
    return "BLOCKER" if (args.site.parent / "redlines.json").exists() else "MAJOR"


def resolve_severity(spec, args, site):
    """A GATES row's severity is a literal string OR a callable
    (args, site) -> severity (spec 1.1). Anything else is a wiring bug and is
    reported as one rather than silently defaulting."""
    sev = spec(args, site) if callable(spec) else spec
    if sev not in SEVERITIES:
        raise ValueError(f"severity {sev!r} is not one of {list(SEVERITIES)}")
    return sev


# ----------------------------------------------------------------- Q-DECLARE

def gate_declare(args, site):
    """Every item of every claim-bearing section declares what it asserts.
    Delegates to claims-check.py --mode declare; the vocabularies live there
    (SSOT references/claims.md), never here."""
    cmd = ["--mode", "declare", "--site", str(args.site), "--dist", str(args.dist)]
    redlines = args.site.parent / "redlines.json"
    if redlines.exists():
        cmd += ["--redlines", str(redlines)]
    return run_script("claims-check.py", cmd)


# ------------------------------------------------------------------ Q-CLAIMS

def gate_claims(args, site):
    """Sweep the rendered pages against the project's red-line register.
    N/A -- never PASS -- when the project carries no register: there is
    nothing to sweep against, and a check that cannot run has not passed."""
    redlines = args.site.parent / "redlines.json"
    if not redlines.exists():
        return "N/A", (f"REASON: no register at {redlines}; there is no red-line wording to sweep "
                       f"against (absent feature, not a passing check)")
    cmd = ["--mode", "sweep", "--site", str(args.site), "--dist", str(args.dist),
           "--redlines", str(redlines)]
    reads = args.site.parent / "claims-read.json"
    if reads.exists():
        cmd += ["--reads", str(reads)]
    return run_script("claims-check.py", cmd)


# -------------------------------------------------------------- Q-PROVENANCE

def gate_provenance(args, site):
    """BLOCKER unconditionally: it only bites evidence/state sections, which no
    v9 project has, so it cannot turn an existing green project red (spec 3.2).
    Both passes -- source and render -- live in provenance-check.py."""
    return run_script("provenance-check.py",
                      ["--site", str(args.site), "--content-dir", str(args.content_dir),
                       "--dist", str(args.dist)])


# ---------------------------------------------------------------- Q-DISCLOSE

DISCLOSURE_CLASS_RE = re.compile(r'class="[^"]*\bls-disclosure\b[^"]*"')
DISCLOSURE_EL_RE = re.compile(
    r'<(?P<tag>[a-zA-Z][a-zA-Z0-9]*)\b[^>]*class="[^"]*\bls-disclosure\b[^"]*"[^>]*>'
    r'(?P<body>.*?)</(?P=tag)\s*>', re.DOTALL)
STRIP_TAGS_RE = re.compile(r"<[^>]*>")


def disclosure_active(site):
    """Spec 4.1: active when agent_authored is true AND eu_residency is not
    excluded/confirmed_non_eu -- UNKNOWN carries the duty, mirroring RL-1's own
    rule. An absent authorship block leaves the obligation inactive, so no v9
    project turns red; the REASON is always printed."""
    auth = site.get("authorship")
    if not isinstance(auth, dict):
        return False, "authorship absent"
    if not auth.get("agent_authored"):
        return False, "agent_authored=false"
    residency = auth.get("eu_residency", "unknown")
    if residency in ("excluded", "confirmed_non_eu"):
        return False, f"eu_residency={residency}"
    return True, ""


def gate_disclose(args, site):
    active, reason = disclosure_active(site)
    if not active:
        return "N/A", (f"REASON: {reason}; the agent-authorship disclosure obligation is not "
                       f"active for this project")
    pages = find_html_pages(args.dist)
    if not pages:
        return "FAIL", f"no *.html page found under {args.dist} (walked whole tree)"
    bad = []
    for page in pages:
        text = page.read_text(encoding="utf-8", errors="replace")
        # OCCURRENCE count of the class attribute (finding C8/C9/T10), so two
        # disclosures on one page are caught as loudly as none.
        n = occurrences(DISCLOSURE_CLASS_RE.pattern, text)
        if n != 1:
            bad.append(f"{page}: {n} .ls-disclosure element(s), expected exactly 1")
            continue
        m = DISCLOSURE_EL_RE.search(text)
        body = STRIP_TAGS_RE.sub("", m.group("body")).strip() if m else ""
        if not body:
            bad.append(f"{page}: .ls-disclosure element is empty")
    if bad:
        return "FAIL", joined(bad)
    return "PASS", (f"{len(pages)} page(s) carry exactly one non-empty .ls-disclosure "
                    f"(obligation active: agent_authored, eu_residency="
                    f"{site.get('authorship', {}).get('eu_residency', 'unknown')})")


# ------------------------------------------------- Q-VOICE-INDEP / Q-VOICE-SCAN

# --------------------------------------------------------- voice text binding
#
# F-6. Before this, `Q-VOICE-SCAN` read a number the operator typed and never
# compared it to any text: an edit made after the scan shipped a stale
# attestation with no warning, and a visible "world-class, enterprise-grade
# comprehensive solution" passed on hand-typed zeros. The record now carries
# `text_sha256`, the sha256 of the text that was scanned, and this gate
# RECOMPUTES it from the rendered page's VISIBLE TEXT.
#
# Why the rendered page and not `voice/copy-{locale}.txt`: that file is a second
# artifact the same operator hand-maintains, and the acceptance run's own
# demonstration was the copy file going stale while the page moved on -- hashing
# it would bind the record to the very thing that drifted and certify nothing.
# The rendered page is what ships and what a reader gets, and binding to it
# reuses the ONE staleness rule the tool already has (`claims-read.json`'s page
# hash) instead of inventing a second one. The consequence, stated so nobody
# reads it as an accident: the text to scan IS the page's visible text, which
# also settles the disagreement between the two tools about what "the page" is.
#
# What this proves and what it does not: the hash binds the attestation to one
# exact text, so a copy edit after the scan fails loudly and a partial
# extraction cannot certify the whole. It cannot prove the scanner was re-run
# over that text -- like the two session ids and like a reading record, the
# counts are ATTESTED. A false attestation is a discoverable artifact, not an
# impossibility.
PAGE_SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1\s*>",
                                  re.IGNORECASE | re.DOTALL)
PAGE_TAG_RE = re.compile(r"<[^>]*>")
PAGE_WS_RE = re.compile(r"\s+")

# The pre-flight line's declared slots. SSOT for what a pre-flight line carries:
# references/claims.md. `echo "x" > voice/pre-flight-en.txt` satisfied a
# non-empty check, so the voice skill's own rule -- "a line with a blank slot is
# not a pre-flight line" -- went unenforced (F-6). Each name is matched with
# either a space or an underscore, since both spellings appear in the wild.
PREFLIGHT_FIELDS = ("audience", "channel", "state", "lang", "spec block")


def page_visible_text(page):
    """The rendered page's visible text: script/style bodies dropped, tags
    replaced by a space, entities unescaped, whitespace collapsed. Deliberately
    the same normalisation `claims-check.py`'s `to_text()` uses -- one definition
    of "the visible text of a page", so the voice binding and the red-line sweep
    can never disagree about what the reader sees."""
    raw = page.read_text(encoding="utf-8", errors="replace")
    out = PAGE_SCRIPT_STYLE_RE.sub(" ", raw)
    out = PAGE_TAG_RE.sub(" ", out)
    return PAGE_WS_RE.sub(" ", html.unescape(out)).strip()


def page_text_sha256(page):
    return hashlib.sha256(page_visible_text(page).encode("utf-8")).hexdigest()


def preflight_gaps(text):
    """The declared slots a pre-flight line leaves blank. A slot's value runs to
    the next `|` or newline, which is the shape the voice skill's own pre-flight
    line uses."""
    gaps = []
    for field in PREFLIGHT_FIELDS:
        pattern = r"\b%s\s*=\s*([^|\n]*)" % field.replace(" ", r"[ _]")
        m = re.search(pattern, text, re.IGNORECASE)
        if m is None:
            gaps.append(f"{field} (no '{field}=' slot at all)")
        elif not m.group(1).strip():
            gaps.append(f"{field} (slot present, value blank)")
    return gaps


def locale_page(args, site, locale):
    """The rendered page for one locale, resolved by `locale_path` imported from
    render-page.py -- the ONE carrier of the locale/path rule (finding D3's
    class), the same mechanism claims-check.py and build-site.py use. This gate
    does not re-implement that rule: two carriers for "where does locale X's
    page live" is how a gate ends up checking a file nobody ships. Returns
    (path, error); the error is reported, never worked around."""
    render_page = HERE / "render-page.py"
    saved, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec = importlib.util.spec_from_file_location("renderpage_for_gate", render_page)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        rel = mod.locale_path(locale, site.get("default_locale")).strip("/")
    except Exception as e:  # noqa: BLE001 -- report, never re-implement
        return None, (f"cannot import locale_path from render-page.py "
                      f"({type(e).__name__}: {e}); locale resolution has exactly one carrier "
                      f"and this gate does not re-implement it")
    finally:
        sys.dont_write_bytecode = saved
    return ((args.dist / rel / "index.html") if rel else (args.dist / "index.html")), None


def voice_records(args, site):
    """(reason, [(locale, path, record_or_None, error_or_None)]). `reason` is
    non-empty when the voice channel is not wired for this project, which is an
    N/A -- never a PASS (spec 6.1)."""
    skill = site.get("voice_skill")
    if not skill:
        return "no 'voice_skill' in site.json; the voice channel is not wired for this project", []
    out = []
    for loc in site.get("locales", []) or []:
        path = args.site.parent / "voice" / f"scan-{loc}.json"
        if not path.exists():
            out.append((loc, path, None, "file missing"))
            continue
        try:
            out.append((loc, path, load_json(path), None))
        except (OSError, json.JSONDecodeError) as e:
            out.append((loc, path, None, f"unreadable: {e}"))
    return "", out


def gate_voice_indep(args, site):
    """Fix path one: re-run the scan in a different session. The two session
    ids are attested UUIDs an agent stamps, not a cryptographic boundary -- a
    false attestation becomes a discoverable artifact, not an impossibility
    (spec 6.3, stated in references/claims.md too)."""
    reason, records = voice_records(args, site)
    if reason:
        return "N/A", f"REASON: {reason}"
    bad = []
    for loc, path, rec, err in records:
        if rec is None:
            bad.append(f"locale '{loc}': {path} {err}")
            continue
        written, scanned = rec.get("written_session"), rec.get("scanned_session")
        if not written:
            bad.append(f"locale '{loc}': no written_session")
        if not scanned:
            bad.append(f"locale '{loc}': no scanned_session")
        if written and scanned and written == scanned:
            bad.append(f"locale '{loc}': written_session == scanned_session ({written}); the "
                       f"judgement was produced in the writing session")
        if not rec.get("scanned_at"):
            bad.append(f"locale '{loc}': no scanned_at")
        # The pre-flight line is half of the artifact the independence rule
        # rests on: the scan record says WHO judged, the pre-flight says what
        # was being written and against which spec block. A project carrying a
        # perfect scan record and no pre-flight file would otherwise pass green,
        # which makes the pre-flight step a wish instead of a lever.
        pre = args.site.parent / "voice" / f"pre-flight-{loc}.txt"
        if not pre.exists():
            bad.append(f"locale '{loc}': no voice/pre-flight-{loc}.txt")
        else:
            text = pre.read_text(encoding="utf-8", errors="replace")
            if not text.strip():
                bad.append(f"locale '{loc}': voice/pre-flight-{loc}.txt is empty")
            else:
                # F-6. A non-empty file is not a pre-flight line: `echo "x" >
                # voice/pre-flight-en.txt` satisfied the old check. The line has
                # to CARRY its declared slots, which is the voice skill's own
                # rule ("a line with a blank slot is not a pre-flight line")
                # finally enforced instead of assumed.
                gaps = preflight_gaps(text)
                if gaps:
                    bad.append(f"locale '{loc}': voice/pre-flight-{loc}.txt names no value for "
                               f"{joined(gaps, limit=len(PREFLIGHT_FIELDS))}; a line with a blank "
                               f"slot is not a pre-flight line")
    if bad:
        return "FAIL", joined(bad)
    # F-1. The PASS detail states what it can attest, not what it cannot prove.
    # It used to read "distinct written/scanned sessions", asserting as fact the
    # one thing this gate cannot check -- while `record-read`'s own NOTE has
    # always said the honest version out loud. Two ids differing is a difference
    # between two strings an agent stamped, and nothing here establishes that two
    # sessions existed.
    return "PASS", (f"{len(records)} locale scan record(s) with a filled pre-flight line: two "
                    f"DISTINCT session ids are ATTESTED (ids an agent stamped, not a proven "
                    f"session boundary), scanned_at present")


def gate_voice_scan(args, site):
    """Fix path two: change the copy. voicecheck.py exits 0 for `ran`, 2 for an
    input error and 3 for LIST CONTRACT VIOLATED -- so exit_code 0 asserts only
    that the scan executed (M-3). The hit counts are what this gate reads -- and
    `text_sha256` is what ties those counts to a text, recomputed here from the
    rendered page's visible text (F-6). Without it the counts were numbers in a
    file: a page reading "world-class, enterprise-grade comprehensive solution"
    passed on hand-typed zeros."""
    reason, records = voice_records(args, site)
    if reason:
        return "N/A", f"REASON: {reason}"
    bad = []
    for loc, path, rec, err in records:
        if rec is None:
            bad.append(f"locale '{loc}': {path} {err}")
            continue
        code = rec.get("exit_code")
        if code == 2:
            bad.append(f"locale '{loc}': voicecheck.py exit 2 (input error) -- the scan did not run")
        elif code == 3:
            bad.append(f"locale '{loc}': voicecheck.py exit 3 -- LIST CONTRACT VIOLATED")
        elif code != 0:
            bad.append(f"locale '{loc}': exit_code {code!r} is not 0/2/3")
        counts = rec.get("counts", {}) or {}
        hits = counts.get("never_use_hits")
        if hits is None:
            bad.append(f"locale '{loc}': counts.never_use_hits absent")
        elif hits != 0:
            bad.append(f"locale '{loc}': counts.never_use_hits={hits} (exit_code 0 only means the "
                       f"scan ran)")
        size = counts.get("never_use_list_size")
        if not isinstance(size, int) or size <= 0:
            bad.append(f"locale '{loc}': counts.never_use_list_size={size!r}; a clean report from "
                       f"an empty rule set is the failure the scan exists to prevent")
        items = counts.get("semantic_bans_items", 0) or 0
        reads = rec.get("semantic_bans_read", []) or []
        good_reads = [r for r in reads if isinstance(r, dict) and r.get("item") and r.get("reader")
                      and r.get("read_at") and r.get("verdict")]
        if len(good_reads) < items:
            bad.append(f"locale '{loc}': {items} semantic ban item(s) counted but only "
                       f"{len(good_reads)} complete semantic_bans_read record(s)")
        # F-6: bind the record to the text it judged. Everything above is a
        # number the operator typed; without this the counts belong to no text
        # at all.
        page, err = locale_page(args, site, loc)
        if err:
            bad.append(f"locale '{loc}': {err}")
            continue
        if not page.exists():
            bad.append(f"locale '{loc}': no rendered page at {page}, so the scan record's counts "
                       f"belong to no text this project ships")
            continue
        actual = page_text_sha256(page)
        stored = rec.get("text_sha256")
        # The expected hash is printed IN FULL, both times. A gate that names a
        # value the operator cannot reproduce is a wish: the whole point of this
        # check is that the text to scan is the page's visible text, and this is
        # where the run says which text that is.
        if not stored:
            bad.append(f"locale '{loc}': the record carries no text_sha256, so its counts certify "
                       f"no particular text; the visible text of {page} is sha256={actual}")
        elif stored != actual:
            bad.append(f"locale '{loc}': record scanned text sha256={str(stored)[:16]}... but the "
                       f"visible text of {page} is sha256={actual}; the copy changed after the "
                       f"scan, or a partial extraction was scanned")
    if bad:
        return "FAIL", joined(bad)
    return "PASS", (f"{len(records)} locale scan record(s): zero never-use hits against a "
                    f"non-empty list; semantic bans read; text_sha256 matches the rendered "
                    f"page's visible text (counts are ATTESTED against that text, not re-run "
                    f"here)")


# -------------------------------------------------------------- Q-DS-ABSENCE

def gate_ds_absence(args, site):
    """Re-derive the design system's declared absence at every run (spec 5.3):
    nothing about the verification is stored, so a DS that fixes its coverage
    table turns this gate green by itself and one that regresses turns it red
    again."""
    dev_path = args.site.parent / "deviations.json"
    if not dev_path.exists():
        return "N/A", (f"REASON: no {dev_path}; no design system has been ingested into this "
                       f"project, so it declares no absence to verify")
    try:
        dev = load_json(dev_path)
    except (OSError, json.JSONDecodeError) as e:
        return "FAIL", f"cannot read/parse {dev_path}: {e}"
    ds_path = (dev.get("ds") or {}).get("path")
    if not ds_path:
        return "FAIL", f"{dev_path} records no ds.path, so the design system cannot be re-verified"
    root = Path(ds_path)
    if not root.is_absolute():
        root = (args.site.parent / root)
    coverage = root / "references" / "coverage.md"
    payload = root / "assets" / "tokens-resolved.json"
    missing = [str(p) for p in (coverage, payload) if not p.exists()]
    if missing:
        return "FAIL", f"design system recorded at '{ds_path}' is not readable: missing {missing}"
    return run_script("ds-verify-absence.py", [str(coverage), str(payload)],
                      issue_prefixes=("-", "MISCLASSIFIED"))


# (id, severity_spec, fn) -- severity_spec is a literal severity string or a
# callable (args, site) -> severity (spec 1.1). Two rows use a callable.
GATES = [
    ("Q-INTEGRITY", "BLOCKER", gate_integrity),
    ("Q-I18N", "BLOCKER", gate_i18n),
    ("Q-REVIEW", "BLOCKER", gate_review),
    ("Q-RESPONSIVE", "MAJOR", gate_responsive),
    ("Q-CF-READY", "BLOCKER", gate_cf_ready),
    ("Q-WCAG", "BLOCKER", gate_wcag),
    ("Q-CONTRAST", "BLOCKER", gate_contrast),
    ("Q-ORPHAN", "MAJOR", gate_orphan),
    # v10. Q-DECLARE and Q-CLAIMS are two ids, not one: the fix for the first
    # is "fill in claims[]", the fix for the second is "change or retract a
    # wording" -- different owners, different drift-matrix rows.
    ("Q-DECLARE", sev_claims, gate_declare),
    ("Q-CLAIMS", sev_claims, gate_claims),
    ("Q-PROVENANCE", "BLOCKER", gate_provenance),
    ("Q-DISCLOSE", "BLOCKER", gate_disclose),
    ("Q-VOICE-INDEP", "BLOCKER", gate_voice_indep),
    ("Q-VOICE-SCAN", "BLOCKER", gate_voice_scan),
    ("Q-DS-ABSENCE", "MAJOR", gate_ds_absence),
]


def main(argv):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--site", required=True, type=Path)
    p.add_argument("--content-dir", required=True, type=Path)
    p.add_argument("--dist", required=True, type=Path)
    p.add_argument("--tokens", type=Path, default=None,
                    help="Tokens file for Q-CONTRAST. Defaults to 'tokens.tokens.json' next to --site.")
    p.add_argument("--json", dest="json_out", type=Path, default=None)
    p.add_argument("--allow-major", action="store_true",
                   help="Downgrade MAJOR failures to a printed warning and allow exit 0. "
                        "Never downgrades a BLOCKER.")
    try:
        args = p.parse_args(argv[1:])
    except SystemExit as e:
        return e.code if e.code is not None else 2

    if args.tokens is None:
        # Standard project layout: tokens beside site.json. A packaged child
        # skill puts site.json in content/ and tokens.tokens.json at the skill
        # root, so fall back one level up rather than reporting a missing
        # palette -- the file is there, the default was just looking one
        # directory too deep.
        args.tokens = args.site.parent / "tokens.tokens.json"
        if not args.tokens.exists():
            parent_layout = args.site.parent.parent / "tokens.tokens.json"
            if parent_layout.exists():
                args.tokens = parent_layout

    try:
        site = load_json(args.site)
    except (OSError, json.JSONDecodeError) as e:
        print(f"FAIL: cannot read/parse site file '{args.site}': {e}", file=sys.stderr)
        return 2
    if not isinstance(site, dict):
        print(f"FAIL: '{args.site}' does not contain a JSON object", file=sys.stderr)
        return 2

    rows = []
    for gate_id, sev_spec, fn in GATES:
        try:
            sev = resolve_severity(sev_spec, args, site)
        except Exception as e:  # a wiring bug is reported, never defaulted away
            sev, status, detail = "BLOCKER", "FAIL", f"severity spec raised {type(e).__name__}: {e}"
        else:
            try:
                status, detail = fn(args, site)
            except Exception as e:  # a gate must never crash the whole run
                status, detail = "FAIL", f"gate raised {type(e).__name__}: {e}"
        if status not in ("PASS", "FAIL", "N/A"):
            status, detail = "FAIL", f"gate returned unknown status {status!r}: {detail}"
        rows.append({"id": gate_id, "severity": sev, "status": status, "detail": detail})
        print(f"GATE  {gate_id}  {sev}  {status}  {detail}")

    blocker_fails = sum(1 for r in rows if r["severity"] == "BLOCKER" and r["status"] == "FAIL")
    major_fails = sum(1 for r in rows if r["severity"] == "MAJOR" and r["status"] == "FAIL")
    minor_fails = sum(1 for r in rows if r["severity"] == "MINOR" and r["status"] == "FAIL")
    # An N/A row counts toward no severity bucket: it is never "FAIL", so the
    # three sums above skip it by construction, and the exit code cannot move.
    na_rows = sum(1 for r in rows if r["status"] == "N/A")

    if args.allow_major and major_fails:
        print(f"NOTE: --allow-major set; {major_fails} MAJOR failure(s) downgraded to a "
              f"warning and will not block exit 0.")

    overall_pass = (blocker_fails == 0) and (major_fails == 0 or args.allow_major)
    result_line = (f"RESULT: {'PASS' if overall_pass else 'FAIL'} "
                   f"blocker={blocker_fails} major={major_fails} minor={minor_fails}")
    print(result_line)

    if args.json_out:
        report = {
            "result": "PASS" if overall_pass else "FAIL",
            "result_line": result_line,
            "blocker": blocker_fails,
            "major": major_fails,
            "minor": minor_fails,
            "na": na_rows,
            "allow_major": args.allow_major,
            "gates": rows,
        }
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    if blocker_fails > 0:
        return 1
    if major_fails > 0 and not args.allow_major:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
