#!/usr/bin/env python3
"""landing-studio v10.0.0 -- scripts/provenance-check.py

Numeric provenance (spec section 3.2). `scripts/gate.py`'s Q-PROVENANCE
(BLOCKER, unconditional) delegates to this script over its CLI, exactly as
Q-I18N delegates to `i18n-check.py`. This file is the only implementation of
both passes; no doc and no other script restates any of it.

Two passes, BOTH must hold -- that is the point of the file:

  Source pass.  Every item of every `evidence`/`state` section has a non-empty
                `claims[n-1].date` that parses as ISO `YYYY-MM-DD`, a non-empty
                `.grade` in the controlled vocabulary, and a non-empty
                `{id}.item{n}.value` in every locale (using the same
                default-locale fallback the renderer's `t{}` lookup uses: this
                locale's value if non-empty, else the default locale's).

  Render pass.  In every rendered page, every `.ls-fact__value` whose text
                carries 2+ CONSECUTIVE DIGITS has a non-empty sibling
                `.ls-fact__meta` inside the same item block. This catches a
                template regression the source pass cannot see -- the same
                reason Q-RESPONSIVE inspects the artifact instead of trusting
                the source. A figure whose date and grade exist in site.json
                but never reach the page is an undated figure on the page.

Q-PROVENANCE only bites `evidence`/`state` sections, which no v9 project has,
so a project carrying neither type passes trivially -- that asymmetry with
Q-DECLARE is deliberate (spec 3.2 / 8.3).

  Figure list.  That scoping means a figure typed into a `features` body carries
                no duty at all, and an invented statistic passes every gate. The
                BLOCKER is NOT widened -- prices, durations and node counts are
                legitimately undated and blocking there would be noise nobody
                could satisfy -- so the exemption is made VISIBLE instead: the
                render pass lists every figure it finds outside a
                `.ls-fact__value`, with its section and the surrounding text, as
                NOTE lines that print on every run, and the count rides in the
                summary so it reaches the gate line. A silent exemption is what
                shipped "99.4% node coverage and zero known defects" green.

Hard rules carried from v9: every count is an OCCURRENCE count
(`len(re.findall(...))`), never a line count (findings C8/C9/T10); exit 0 =
pass, 1 = fail, 2 = usage/setup error.

Usage:
  python3 scripts/provenance-check.py --site site.json --content-dir content \\
      --dist dist [--json out.json]
"""
import argparse
import html as html_mod
import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Controlled vocabulary. SSOT: references/claims.md -- this is this script's
# single module-level copy of that file's `grade` row (spec section 10's
# fact-ownership rule: one constant per script, no second list).
# ---------------------------------------------------------------------------
GRADES = ("C1", "C2", "C3", "C4", "C5", "C6", "advisory", "owner-confirmed")

# The two section types that carry numbers with a provenance duty (spec 3.1).
PROVENANCE_TYPES = ("evidence", "state")

ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TWO_DIGITS_RE = re.compile(r"\d{2}")
SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1\s*>", re.IGNORECASE | re.DOTALL)
TAG_RE = re.compile(r"<[^>]*>")
WS_RE = re.compile(r"\s+")


def load_json(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def occurrences(rx, text):
    """Occurrence count, never a line count (findings C8/C9/T10)."""
    return len(rx.findall(text))


def to_text(fragment):
    s = SCRIPT_STYLE_RE.sub(" ", fragment)
    s = TAG_RE.sub(" ", s)
    return WS_RE.sub(" ", html_mod.unescape(s)).strip()


def is_iso_date(v):
    if not isinstance(v, str) or not ISO_DATE_RE.match(v):
        return False
    y, m, d = (int(x) for x in v.split("-"))
    if not (1 <= m <= 12 and 1 <= d <= 31):
        return False
    days = [31, 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28,
            31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    return d <= days[m - 1]


def non_empty(v):
    return isinstance(v, str) and v.strip() != ""


# ----------------------------------------------------------------- source pass

def source_pass(site, content_dir, fails, notes):
    default = site.get("default_locale")
    locales = site.get("locales", []) or []
    tables = {}
    for loc in locales:
        cf = content_dir / f"{loc}.json"
        if not cf.exists():
            fails.append(f"missing content file for locale '{loc}': {cf}")
            tables[loc] = {}
            continue
        try:
            tables[loc] = (load_json(cf).get("t", {}) or {})
        except (OSError, json.JSONDecodeError) as e:
            fails.append(f"cannot read/parse content file '{cf}': {e}")
            tables[loc] = {}
    base_t = tables.get(default, {})

    checked = 0
    for sec in site.get("sections", []):
        if sec.get("type") not in PROVENANCE_TYPES:
            continue
        sid = sec.get("id", "<no id>")
        items = int(sec.get("items", 0) or 0)
        claims = sec.get("claims", []) or []
        for n in range(1, items + 1):
            checked += 1
            cl = claims[n - 1] if n <= len(claims) and isinstance(claims[n - 1], dict) else None
            if cl is None:
                fails.append(f"section '{sid}' item {n}: no claims[{n - 1}] entry, so the figure "
                              f"carries neither a date nor a grade")
                continue
            date = cl.get("date")
            if not non_empty(date):
                fails.append(f"section '{sid}' item {n}: claims[{n - 1}].date is missing or empty")
            elif not is_iso_date(date):
                fails.append(f"section '{sid}' item {n}: claims[{n - 1}].date {date!r} is not an "
                              f"ISO YYYY-MM-DD date")
            grade = cl.get("grade")
            if not non_empty(grade):
                fails.append(f"section '{sid}' item {n}: claims[{n - 1}].grade is missing or empty")
            elif grade not in GRADES:
                fails.append(f"section '{sid}' item {n}: claims[{n - 1}].grade {grade!r} not in "
                              f"the controlled vocabulary {list(GRADES)}")
            key = f"{sid}.item{n}.value"
            for loc in locales:
                # Same two-step the renderer's t{} lookup uses: this locale's
                # value when non-empty, else the default locale's.
                v = tables.get(loc, {}).get(key)
                if not non_empty(v):
                    v = base_t.get(key)
                if not non_empty(v):
                    fails.append(f"locale '{loc}' has no non-empty '{key}' (and no default-locale "
                                  f"'{default}' fallback value either)")
    return checked


# ----------------------------------------------------------------- render pass

def div_spans(html_text):
    """[(start, end)] for every <div> element, resolved by depth-scanning
    nested <div>/</div> pairs rather than by a non-greedy regex (which stops at
    the first inner close)."""
    open_rx = re.compile(r"<div\b[^>]*>", re.IGNORECASE)
    close_rx = re.compile(r"</div\s*>", re.IGNORECASE)
    events = [(m.start(), m.end(), "open", m.group(0)) for m in open_rx.finditer(html_text)]
    events += [(m.start(), m.end(), "close", None) for m in close_rx.finditer(html_text)]
    events.sort(key=lambda e: (e[0], 0 if e[2] == "close" else 1))
    stack, spans = [], []
    for start, end, kind, txt in events:
        if kind == "open":
            if txt.rstrip().endswith("/>"):
                continue
            stack.append(start)
        else:
            if stack:
                spans.append((stack.pop(), end))
    return spans


def enclosing_block(html_text, pos, spans):
    """The smallest <div> span containing `pos` -- the item block whose
    children are the value's siblings."""
    best = None
    for start, end in spans:
        if start <= pos < end:
            if best is None or (end - start) < (best[1] - best[0]):
                best = (start, end)
    return best


VALUE_EL_RE = re.compile(
    r'<(?P<tag>[a-zA-Z][a-zA-Z0-9]*)\b[^>]*class\s*=\s*"[^"]*\bls-fact__value\b[^"]*"[^>]*>'
    r'(?P<body>.*?)</(?P=tag)\s*>', re.IGNORECASE | re.DOTALL)
META_EL_RE = re.compile(
    r'<(?P<tag>[a-zA-Z][a-zA-Z0-9]*)\b[^>]*class\s*=\s*"[^"]*\bls-fact__meta\b[^"]*"[^>]*>'
    r'(?P<body>.*?)</(?P=tag)\s*>', re.IGNORECASE | re.DOTALL)


# ------------------------------------------------- F-5: the listed exemption
#
# Q-PROVENANCE's duty is scoped to `evidence`/`state` items, so a figure typed
# into a `features` body carries none: "99.4% node coverage and zero known
# defects" shipped undated, ungraded and contradicting the ledger 30 lines
# below, with every gate green. Widening the BLOCKER to every section is the
# wrong fix -- prices, durations, port numbers and node counts are legitimately
# undated, and a blocking check there would be noise nobody could satisfy.
#
# So the exemption is made VISIBLE instead of silent: the render pass reports
# EVERY figure it finds outside a `.ls-fact__value`, with its section and the
# surrounding text, as NOTE lines that print on every run -- and the count
# rides in the PASS summary, so it reaches the gate line too. An operator can
# read a list; nobody can read a silence.
#
# Scope, stated rather than assumed, because a boundary nobody prints is the
# same silence in a smaller box. The scan reads the WHOLE page's element text --
# every section, plus header, nav and footer, which render outside `<main>`.
# Excluded, and this is the entire exclusion list:
#   * `<script>`/`<style>` bodies -- not text the page asserts.
#   * `.ls-fact__value` -- its figures are gated by the two passes above.
#   * `.ls-fact__meta` -- that element IS the provenance line; reporting a date
#     and a grade as an undated figure would be a false report.
#   * attribute text -- swept for forbidden WORDINGS by claims-check.py, not
#     scanned for figures here, because `theme-color` hexes and image URLs are
#     digits with no reader and would bury the list this exists to be read.
FIGURE_TOKEN_RE = re.compile(r"\S*\d{2}\S*")
BODY_RE = re.compile(r"<body\b[^>]*>(?P<body>.*)</body\s*>", re.IGNORECASE | re.DOTALL)
# Named-group twin of SCRIPT_STYLE_RE, so a script/style BODY can be blanked
# while its tags stay in place. Blanking these first is load-bearing, not
# tidiness: the skill inlines its own CSS, that CSS contains the literal string
# "<main>" inside a comment, and a scan that reads raw HTML would take the
# stylesheet for the page's main content and report 289 CSS lengths as figures.
SCRIPT_STYLE_BODY_RE = re.compile(
    r"<(?P<tag>script|style)\b[^>]*>(?P<body>.*?)</(?P=tag)\s*>", re.IGNORECASE | re.DOTALL)
SECTION_OPEN_RE = re.compile(r"<section\b[^>]*>", re.IGNORECASE)
SECTION_CLOSE_RE = re.compile(r"</section\s*>", re.IGNORECASE)
SECTION_ID_RE = re.compile(r'\bid\s*=\s*"([^"]*)"', re.IGNORECASE)
CONTEXT_CHARS = 60


def blank_out(fragment, *element_res):
    """`fragment` with each matched element's BODY replaced by spaces of the
    same length -- offsets survive, so a later scan still reports positions
    that line up with the fragment it was given."""
    out = fragment
    for rx in element_res:
        for m in rx.finditer(out):
            start, end = m.span("body")
            out = out[:start] + (" " * (end - start)) + out[end:]
    return out


def section_regions(fragment):
    """[(section id or None, fragment)] for a page: one region per top-level
    <section>, plus the gaps between them (header, nav, footer, and anything
    between sections), so a figure is always reported with a place a reader can
    find."""
    events = [(m.start(), m.end(), "open", m.group(0)) for m in SECTION_OPEN_RE.finditer(fragment)]
    events += [(m.start(), m.end(), "close", None) for m in SECTION_CLOSE_RE.finditer(fragment)]
    events.sort(key=lambda e: (e[0], 0 if e[2] == "close" else 1))
    depth, spans, start, open_tag = 0, [], None, ""
    for s0, e0, kind, txt in events:
        if kind == "open":
            if depth == 0:
                start, open_tag = s0, txt
            depth += 1
        elif depth:
            depth -= 1
            if depth == 0 and start is not None:
                m = SECTION_ID_RE.search(open_tag)
                spans.append((start, e0, m.group(1) if m else None))
                start = None
    out, cursor = [], 0
    for s0, e0, ident in spans:
        if s0 > cursor:
            out.append((None, fragment[cursor:s0]))
        out.append((ident, fragment[s0:e0]))
        cursor = e0
    if cursor < len(fragment):
        out.append((None, fragment[cursor:]))
    return out


def unprovenanced_figures(page, notes):
    """Every figure on the page outside a `.ls-fact__value`, reported as a NOTE
    naming the section, the figure and the text around it. Returns the
    occurrence count -- an occurrence count, never a line count."""
    raw = blank_out(page.read_text(encoding="utf-8", errors="replace"), SCRIPT_STYLE_BODY_RE)
    m = BODY_RE.search(raw)
    whole = m.group("body") if m else raw
    body = blank_out(whole, VALUE_EL_RE, META_EL_RE)
    found = 0
    for ident, fragment in section_regions(body):
        text = to_text(fragment)
        for hit in FIGURE_TOKEN_RE.finditer(text):
            found += 1
            lo = max(0, hit.start() - CONTEXT_CHARS)
            hi = min(len(text), hit.end() + CONTEXT_CHARS)
            around = ("..." if lo > 0 else "") + text[lo:hi] + ("..." if hi < len(text) else "")
            where = f"section '{ident}'" if ident else "page chrome, outside any section"
            notes.append(f"NOTE: figure {hit.group(0)!r} in {where} of {page}, outside any "
                         f".ls-fact__value -- carries no date and no grade duty: \"{around}\"")
    return found


def render_pass(dist, fails, notes):
    if not dist.exists():
        fails.append(f"dist directory not found: {dist}")
        return 0, 0, 0
    pages = sorted(dist.rglob("*.html"))  # whole tree, never dist/*.html (D13)
    values_seen, numeric_seen, outside_seen = 0, 0, 0
    for page in pages:
        raw = page.read_text(encoding="utf-8", errors="replace")
        outside_seen += unprovenanced_figures(page, notes)
        spans = div_spans(raw)
        for m in VALUE_EL_RE.finditer(raw):
            values_seen += 1
            body = to_text(m.group("body"))
            if occurrences(TWO_DIGITS_RE, body) == 0:
                continue  # not a figure: no 2+ consecutive digits
            numeric_seen += 1
            block = enclosing_block(raw, m.start(), spans)
            if block is None:
                fails.append(f"{page}: .ls-fact__value {body!r} sits in no element block, so it "
                              f"has no sibling to carry .ls-fact__meta")
                continue
            fragment = raw[block[0]:block[1]]
            metas = [to_text(mm.group("body")) for mm in META_EL_RE.finditer(fragment)]
            metas = [x for x in metas if x]
            if not metas:
                fails.append(f"{page}: .ls-fact__value {body!r} carries 2+ consecutive digits but "
                              f"has no non-empty sibling .ls-fact__meta (date and grade never "
                              f"reached the page)")
    return len(pages), numeric_seen, outside_seen


def main(argv):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--site", required=True, type=Path)
    p.add_argument("--content-dir", required=True, type=Path)
    p.add_argument("--dist", required=True, type=Path)
    p.add_argument("--json", dest="json_out", type=Path, default=None)
    try:
        args = p.parse_args(argv[1:])
    except SystemExit as e:
        return e.code if e.code is not None else 2

    try:
        site = load_json(args.site)
    except (OSError, json.JSONDecodeError) as e:
        print(f"FAIL: cannot read/parse site file '{args.site}': {e}", file=sys.stderr)
        return 2
    if not isinstance(site, dict):
        print(f"FAIL: '{args.site}' does not contain a JSON object", file=sys.stderr)
        return 2

    fails, notes = [], []
    checked = source_pass(site, args.content_dir, fails, notes)
    pages, numeric, outside = render_pass(args.dist, fails, notes)

    print("=== provenance-check ===")
    # F-5: the NOTE list prints on EVERY run, pass or fail, and its header says
    # what the scan covered -- an exemption an operator can read instead of a
    # silence they cannot.
    print(f"NOTE: figure scan scope: the whole page's element text -- every section plus "
          f"header, nav and footer -- excluding script/style bodies, .ls-fact__value (gated "
          f"above), .ls-fact__meta (the provenance line itself) and attribute text (swept for "
          f"wordings by claims-check.py). {outside} figure(s) found outside .ls-fact__value "
          f"across {pages} page(s), each listed below, NONE carrying a date-and-grade duty.")
    for n in notes:
        print(n)
    summary = (f"source pass: {checked} evidence/state item(s); render pass: {numeric} numeric "
               f".ls-fact__value element(s) across {pages} page(s); {outside} figure(s) outside "
               f".ls-fact__value carry no provenance duty (listed as NOTE)")
    if fails:
        print(f"FAIL ({len(fails)}):")
        for f in fails:
            print(f"  - {f}")
    else:
        print(f"PASS: {summary}.")

    if args.json_out:
        report = {"result": "FAIL" if fails else "PASS", "summary": summary,
                  "items_checked": checked, "pages": pages, "numeric_values": numeric,
                  "figures_outside_fact_value": outside,
                  "fails": fails, "notes": notes}
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
