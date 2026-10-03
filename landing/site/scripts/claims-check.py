#!/usr/bin/env python3
"""landing-studio v10.0.0 -- scripts/claims-check.py

The claims layer's only implementation (spec sections 2.1/2.2/2.4). Three modes:

  --mode declare      every item of every claim-bearing section carries a
                      structural declaration in site.json `claims[]`, using the
                      controlled vocabularies below.
  --mode sweep        the rendered pages are swept against the project's
                      red-line register, `redlines.json` -- element text AND
                      attribute text (`<meta>` content, alt, title,
                      aria-label), because a sweep blind to attributes exempts
                      the highest-reach text on the page by construction.
  --mode record-read  write ONE reading record for ONE locale and ONE row
                      that nothing machine-checks -- a `manual-read`
                      prohibition, or an obligation no gate covers -- into
                      `claims-read.json`, stamping the rendered page's sha256
                      into it.

The writer lives in this file because the reader does: spec 2.1 says the hash
is stored "on write", and a hash rule with two owners is a hash rule that
drifts. There is deliberately no bulk "certify everything" mode -- the record
is a claim that one named reader read one text, so it is written one row, one
locale, one invocation at a time. The record names its reader and hashes the
text; it does not establish that the reader is a person -- `--reader` takes
whatever string it is given, and the printed NOTE says so rather than asserting
humanity the flag cannot check.

`scripts/gate.py` calls this script over its CLI (Q-DECLARE, Q-CLAIMS) exactly
as it calls `i18n-check.py` and `contrast-check.py`. Nothing imports anything
from this module; `gate.py` reaches it over the CLI, not by import.

One carrier per fact (spec section 10):
  - the forbidden wordings, their status, their match mode and the per-locale
    retraction lexicon live in `redlines.json`. This script is that file's ONLY
    reader and hardcodes no pattern and no lexicon term -- including no Russian
    one; the register is data, the script is a reader.
  - the controlled vocabularies are held once, as the module-level constants
    below, whose SSOT is `references/claims.md`. No second list anywhere.
  - locale resolution uses `locale_path` imported from `render-page.py` (the
    v9 SSOT mechanism build-site.py already uses -- finding D3's class); it is
    never re-implemented here.

Hard rules carried from v9:
  - every count is an OCCURRENCE count (`len(re.findall(...))`), never a line
    count (findings C8/C9/T10).
  - exit 0 = pass, 1 = fail, 2 = usage/setup error.

Two region kinds are NEVER exempt, for the same reason: page chrome and
attribute text belong to no `data-ls-item`, so there is no item for a
retraction declaration to scope an exemption to. An attribute hit names which
attribute of which element carried it, plus the attribute's own text.

Obligation rows: `check: "disclosure-present"` is the ONE obligation a gate
really checks, and prints as delegated to `Q-DISCLOSE`. EVERY OTHER obligation
row is treated exactly like a `manual-read` prohibition -- a reading record per
locale, or the sweep fails -- because nothing else in the tool reads it. An
obligation nobody checks is worse than no obligation: the register makes it
look covered.

The use/mention rule runs in BOTH directions (spec 2.4 sweep items 4 and 5):
  1. a red-lined wording inside the one item that declares `retraction_of` for
     that row AND carries a DECLARED withdrawal of it -- an element with class
     `ls-retraction` and `data-ls-retracts="<row>"`, with non-empty visible
     text -- is exempt. The lexicon decides nothing here; it only supplies the
     hint printed when a withdrawal is written but never declared. The
     exemption is scoped to that single `<div class="ls-item"
     data-ls-item="{sec}.{n}">...</div>` block -- never to the page. A hit in
     page chrome, in a heading, or in an item declared for a DIFFERENT row is
     never exempt.
  2. an item that declares `retraction_of` and carries the wording but NO
     retraction term FAILS, and the failure names the MISSING RETRACTION
     LANGUAGE rather than the forbidden wording -- the wording is legitimate
     there; the missing retraction is the defect.

Manual rows (`match: "manual-read"`) are never reported as passing. They print
`READ-REQUIRED <row> <rule>` unless `claims-read.json` carries a record for
that row and locale whose stored page sha256 equals the sha256 of the page
being certified; a mismatched or absent hash prints `STALE-READ`. The
mechanism proves a named reader was recorded against THIS text, never that the
reader is a person nor that the look was sincere (`references/claims.md` says so
out loud).

Verdict vocabulary: `clear` (nothing to say), `deviation-accepted` (a real
departure from the row's rule was found and is accepted -- certifies the page,
requires `--note` describing it, and prints as `READ-OK-DEVIATION` so it never
reads as a plain pass), `breach` (the page must not do this). Before v10 there
were two verdicts, and an accepted deviation had nowhere to land: it was routed
to a `not-applicable` row and printed as CARRIED, i.e. as though nobody had
looked.

Usage:
  python3 scripts/claims-check.py --mode {declare|sweep} --site site.json --dist dist \\
      [--redlines redlines.json] [--reads claims-read.json] [--json out.json]

  python3 scripts/claims-check.py --mode record-read --site site.json --dist dist \\
      --row RL-4b --locale en --reader artem --verdict clear [--note "..."] \\
      (or --verdict deviation-accepted --note "what was accepted, and by whom")
      [--redlines redlines.json] [--reads claims-read.json] [--json out.json]

  --redlines defaults to `redlines.json` next to --site, --reads to
  `claims-read.json` next to --site (the standard project layout).

`--mode record-read` REFUSES (exit 1, loudly) to write a record for a row id
the register does not carry, for a row that is neither `manual-read` nor an
obligation nothing machine-checks, or for a locale with no rendered page: a record that certifies nothing is worse
than no record, because it reads as certification. Every other record in
`claims-read.json` is preserved; a record for the same row AND locale is
replaced, since a re-read supersedes the read before it.
"""
import argparse
import datetime
import hashlib
import html as html_mod
import importlib.util
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent

# ---------------------------------------------------------------------------
# Controlled vocabularies. SSOT: references/claims.md -- these constants are
# the single machine-readable copy of that file's tables (spec section 2.2 and
# the fact-ownership table in section 10). Do not restate them in another
# script: gate.py reaches this file over its CLI, never by import.
# ---------------------------------------------------------------------------
KINDS = (
    "customer-testimonial", "operator-observation", "dogfood-note",
    "build-metric", "partner-relationship", "prospective-lead",
    "not-a-customer", "owner-entity", "deployment-site", "integration",
    "stack-component", "retraction", "undeclared",
)
SPEAKER_ROLES = (
    "paying-customer", "owner-operator", "internal-team", "named-partner",
    "anonymous", "undeclared",
)
DEPLOYMENT_STATES = ("planned", "in-progress", "complete")
GRADES = ("C1", "C2", "C3", "C4", "C5", "C6", "advisory", "owner-confirmed")

# The claim-bearing section types -- the set --mode declare walks. A future
# type joins the set by being listed in references/claims.md AND here; this is
# the one list (spec section 2.2).
CLAIM_BEARING = ("logos", "testimonials", "evidence", "state")

# `"undeclared"` always fails declare: it is the placeholder migrate-claims.py
# writes to make a gap visible, never a value an ingest may choose.
UNDECLARED = "undeclared"

# Reading-record verdicts. SSOT: references/claims.md.
#
# Three verdicts, because two were not enough. `clear` is a reading that found
# nothing to say; `breach` is a reading that found something the page must not
# do. Between them sat the case this vocabulary could not express: a reading
# that found a REAL deviation and accepted it -- a deliberate, owned departure
# from the row's rule. With no verdict for it, such a reading was routed to a
# `not-applicable` row, which the sweep then printed as CARRIED: exactly as
# though nobody had looked. `deviation-accepted` gives it a name, certifies the
# page like `clear`, and stays visibly different in every line that prints it.
#
# The certifying SET (not a single verdict) is the load-bearing change: a
# reading may certify while recording that something is off, which is what an
# owned deviation is.
READ_VERDICTS = ("clear", "deviation-accepted", "breach")
CERTIFYING_VERDICTS = ("clear", "deviation-accepted")
DEVIATION_VERDICT = "deviation-accepted"
# `--note` is mandatory for DEVIATION_VERDICT: a deviation that is accepted
# without being described is indistinguishable from `clear`, and a second way
# to say `clear` would be a wish, not a mechanism. Enforced in mode_record_read.
CERTIFYING_VERDICT = "clear"  # retained: the verdict a plain clean read writes

# The obligation `check` values this tool really machine-checks, each mapped to
# the gate id that does the checking. SSOT: references/claims.md. An obligation
# row whose `check` is not a key here is machine-checked by NOTHING, so it is
# read exactly like a `manual-read` prohibition: a reading record per locale, or
# the sweep fails. Printing the id of a gate that does not read the row is how
# an obligation nobody checks comes to look covered.
DELEGATED_OBLIGATION_CHECKS = {"disclosure-present": "Q-DISCLOSE"}

# redlines.json vocabulary (spec section 2.1).
ROW_TYPES = ("obligation", "prohibition", "implicature")
MATCH_MODES = ("literal", "regex", "manual-read", "not-applicable")
ACTIVE_STATUSES = ("not_released", "permanently_narrowed", "in_force")
SWEPT_TYPES = ("prohibition", "implicature")


def _load_locale_path(here):
    """Import locale_path from render-page.py -- the SSOT for the locale/path
    rule (finding D3). This is the ONLY thing taken from that module, by the
    same mechanism build-site.py uses; render-page.py is owned by another
    wave, so nothing else about its internals is assumed here."""
    render_page_path = here / "render-page.py"
    # Do not leave a __pycache__ behind inside the skill tree: a gate run must
    # not add files to the tree it is checking.
    saved, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    spec = importlib.util.spec_from_file_location("renderpage_for_claimscheck", render_page_path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.dont_write_bytecode = saved
    return mod.locale_path


def load_locale_path_or_report():
    """(locale_path, error) -- the import is attempted in exactly one place so
    the sweep and the record writer fail the same way when render-page.py
    cannot be read."""
    try:
        return _load_locale_path(HERE), None
    except Exception as e:  # noqa: BLE001 -- report, never re-implement
        return None, (f"cannot import locale_path from render-page.py ({type(e).__name__}: {e}); "
                      f"locale resolution has exactly one carrier and this script does not "
                      f"re-implement it")


def load_json(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def occurrences(rx, text):
    """Occurrence count, never a line count (findings C8/C9/T10)."""
    return len(rx.findall(text))


# ------------------------------------------------------------- text handling

SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1\s*>", re.IGNORECASE | re.DOTALL)
TAG_RE = re.compile(r"<[^>]*>")
WS_RE = re.compile(r"\s+")


def to_text(html_fragment):
    """Visible text of an HTML fragment: script/style bodies dropped, tags
    replaced by a space, entities unescaped, whitespace collapsed. Collapsing
    means a wording split across a line break or an inline tag is still one
    occurrence -- the register describes wordings, not source formatting."""
    s = SCRIPT_STYLE_RE.sub(" ", html_fragment)
    s = TAG_RE.sub(" ", s)
    s = html_mod.unescape(s)
    return WS_RE.sub(" ", s).strip()


def element_spans(html_text, tag, want_re):
    """[(start, end, ident)] for every <tag ...> element whose OPEN TAG matches
    `want_re` (group 1 = ident), with the end resolved by depth-scanning nested
    <tag>/</tag> pairs rather than by a non-greedy regex (which would stop at
    the first inner close). Nested matches are dropped: only the outermost
    match survives, so a region decomposition never double-counts."""
    open_rx = re.compile(r"<%s\b[^>]*>" % tag, re.IGNORECASE)
    close_rx = re.compile(r"</%s\s*>" % tag, re.IGNORECASE)
    events = [(m.start(), m.end(), "open", m.group(0)) for m in open_rx.finditer(html_text)]
    events += [(m.start(), m.end(), "close", m.group(0)) for m in close_rx.finditer(html_text)]
    events.sort(key=lambda e: (e[0], 0 if e[2] == "close" else 1))
    stack, spans = [], []
    for start, end, kind, txt in events:
        if kind == "open":
            if txt.rstrip().endswith("/>"):
                continue
            stack.append((start, txt))
        else:
            if not stack:
                continue
            s, open_txt = stack.pop()
            m = want_re.search(open_txt)
            if m:
                spans.append((s, end, m.group(1)))
    spans.sort()
    out = []
    for span in spans:
        if out and span[0] < out[-1][1]:
            continue  # nested inside an already-recorded span
        out.append(span)
    return out


def regions(html_text, spans):
    """Decompose a page into non-overlapping regions:
    ('item'|'section', ident, text) for each span, and (None, None, text) for
    every gap between them (page chrome: header, nav, headings, footer).
    Chrome pieces stay separate so a wording can never be matched across the
    hole left by a removed item."""
    out, cursor = [], 0
    for start, end, ident in spans:
        if start > cursor:
            out.append((None, None, to_text(html_text[cursor:start])))
        out.append(("span", ident, to_text(html_text[start:end])))
        cursor = end
    if cursor < len(html_text):
        out.append((None, None, to_text(html_text[cursor:])))
    return [r for r in out if r[2]]


# --------------------------------------------------- attribute text (F-12)
#
# to_text() replaces whole tags with a space, so every attribute value on the
# page is invisible to a sweep that reads element text only: <meta
# name="description">, every og:/twitter: card value, every alt and every
# aria-label was exempt BY CONSTRUCTION. The <meta> description is what a
# search result, a Slack unfurl and a Twitter card render, and an aria-label is
# what a screen-reader user hears -- the highest-reach text on the page was the
# one surface nothing read.
#
# Two rules hold for these regions, and they are the whole reason they are a
# region kind of their own:
#   1. attribute text belongs to NO `data-ls-item`, so exactly like page chrome
#      it is NEVER exempt from a retraction declaration -- there is no item to
#      scope an exemption to.
#   2. a hit must name WHERE it was: which attribute of which element, plus the
#      attribute's own text, so the fix is obvious from the report line.
# A wording present once in the body and once in a <meta> tag is reported
# twice, once per location, and never summed: attribute values are not part of
# to_text()'s output, so the two scans cannot double-count one occurrence.
SWEPT_ATTRS = ("alt", "title", "aria-label")
META_ONLY_ATTRS = ("content",)
TAG_OPEN_SCAN_RE = re.compile(r"<([a-zA-Z][a-zA-Z0-9]*)\b([^>]*)>")
LABEL_ATTRS = ("name", "property", "http-equiv", "id", "class", "rel")
SNIPPET_MAX = 90


def attr_value(open_tag_body, name):
    """One attribute's raw value from an open tag's attribute source, double- or
    single-quoted. An unquoted value is not read: the renderer always quotes,
    and guessing where an unquoted value ends is how a scanner invents text."""
    for quote in ('"', "'"):
        m = re.search(r"\b%s\s*=\s*%s([^%s]*)%s"
                      % (re.escape(name), quote, quote, quote),
                      open_tag_body, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def element_label(tag, open_tag_body):
    """`meta[name="description"]`, `img[id="hero"]`, `a[class="ls-cta"]` -- the
    element named the way an operator can find it in the source. The first
    identifying attribute present wins; a tag with none is named by its tag."""
    for key in LABEL_ATTRS:
        v = attr_value(open_tag_body, key)
        if v and v.strip():
            v = WS_RE.sub(" ", v).strip()
            if key == "class":
                v = v.split(" ")[0]
            return '%s[%s="%s"]' % (tag, key, v[:40])
    return tag


def snippet(text):
    """The surrounding text, bounded. ASCII-safe: three dots, never an
    ellipsis character (the source is ASCII-only by contract)."""
    return text if len(text) <= SNIPPET_MAX else text[:SNIPPET_MAX] + "..."


def attribute_regions(html_text):
    """[(location, text)] for every swept attribute value on the page:
    `content` on every <meta>, plus alt/title/aria-label on any element.

    `<script>`/`<style>` BODIES are dropped first, exactly as to_text() drops
    them: the skill inlines its own JS and CSS, and a string literal inside
    them is not text the page asserts (the same reason to_text()'s stripping is
    load-bearing rather than incidental)."""
    body = SCRIPT_STYLE_RE.sub(" ", html_text)
    out = []
    for m in TAG_OPEN_SCAN_RE.finditer(body):
        tag = m.group(1).lower()
        attrs = m.group(2)
        wanted = (META_ONLY_ATTRS + SWEPT_ATTRS) if tag == "meta" else SWEPT_ATTRS
        for attr in wanted:
            raw = attr_value(attrs, attr)
            if raw is None:
                continue
            text = WS_RE.sub(" ", html_mod.unescape(raw)).strip()
            if not text:
                continue
            out.append(("%s@%s" % (element_label(tag, attrs), attr), text))
    return out


ITEM_OPEN_RE = re.compile(r'data-ls-item\s*=\s*"([^"]+)"')
SECTION_OPEN_RE = re.compile(r'id\s*=\s*"([^"]+)"')


def item_spans(html_text):
    """Every `<div class="ls-item" data-ls-item="{sec}.{n}">...</div>` block.
    The class is required as well as the attribute: the anchor is the item
    wrapper's contract (spec 2.3), not a stray attribute."""
    want = re.compile(r'class\s*=\s*"[^"]*\bls-item\b[^"]*"[^>]*data-ls-item\s*=\s*"([^"]+)"'
                      r'|data-ls-item\s*=\s*"([^"]+)"[^>]*class\s*=\s*"[^"]*\bls-item\b[^"]*"')

    class _G:
        """Adapter so element_spans' group(1) contract holds for either
        attribute order in the open tag."""
        def __init__(self, rx):
            self.rx = rx

        def search(self, s):
            m = self.rx.search(s)
            if not m:
                return None
            value = m.group(1) if m.group(1) is not None else m.group(2)

            class _M:
                def group(self, _i):
                    return value
            return _M()

    return element_spans(html_text, "div", _G(want))


def section_spans(html_text):
    return element_spans(html_text, "section", SECTION_OPEN_RE)


def pattern_regex(row, pattern):
    """A `literal` pattern is escaped, with every run of whitespace allowed to
    match any whitespace run; a `regex` pattern is used as written. Both are
    case-insensitive: a breach in different case is still a breach."""
    if row.get("match") == "regex":
        return re.compile(pattern, re.IGNORECASE)
    parts = [re.escape(p) for p in WS_RE.split(pattern.strip()) if p]
    return re.compile(r"\s+".join(parts), re.IGNORECASE)


# ----------------------------------------------------------------- registers

def row_is_active(row):
    return row.get("type") in SWEPT_TYPES and row.get("status") in ACTIVE_STATUSES


def obligation_is_live(row):
    """An obligation row still carrying its duty. `released` obligations print
    CARRIED and are inert, like every other released row."""
    return row.get("type") == "obligation" and row.get("status") in ACTIVE_STATUSES


def obligation_delegate(row):
    """The gate id that really checks this obligation, or None -- and None is
    the answer for every obligation except the disclosure duty (F-10). A row
    whose `check` names something this tool does not implement gets None too:
    an unimplemented check is not a check, and the row falls back to the
    reading record rather than to the name of a gate that never reads it."""
    return DELEGATED_OBLIGATION_CHECKS.get(row.get("check"))


def load_register(path, fails):
    """Read redlines.json and validate its own shape. A malformed register is
    a FAIL, never a silently empty sweep -- an unreadable register certifying a
    page clean is the failure mode this layer exists to prevent."""
    reg = load_json(path)
    rows = reg.get("rows", [])
    if not isinstance(rows, list):
        fails.append(f"REGISTER {path}: 'rows' is not a list")
        return reg, []
    for row in rows:
        rid = row.get("id", "<no id>")
        if row.get("type") not in ROW_TYPES:
            fails.append(f"REGISTER {rid}: type {row.get('type')!r} not in {list(ROW_TYPES)}")
        if row.get("type") in SWEPT_TYPES and row.get("match") not in MATCH_MODES:
            fails.append(f"REGISTER {rid}: match {row.get('match')!r} not in {list(MATCH_MODES)}")
        if row.get("match") in ("manual-read", "not-applicable") and not row.get("rule"):
            fails.append(f"REGISTER {rid}: match={row.get('match')} requires a 'rule' "
                          f"(printed verbatim by the gate)")
        if obligation_is_live(row) and not obligation_delegate(row) and not row.get("rule"):
            # An obligation row validates with no `match` and no `rule`, so an
            # empty one used to print as covered. Nothing machine-checks this
            # row, so its `rule` is the only thing a human can read it against
            # -- without one the row asserts a duty nobody can even state.
            named = (f"check={row.get('check')!r}, which no gate implements,"
                     if row.get("check") else "no 'check',")
            fails.append(f"REGISTER {rid}: obligation row has {named} and no 'rule'; nothing "
                          f"machine-checks it, so the constraint has to be written out for a "
                          f"human to read against the page")
        if row.get("type") == "implicature" and not row.get("requires_kind"):
            fails.append(f"REGISTER {rid}: implicature row has no 'requires_kind'")
    return reg, rows


# --------------------------------------------------------------- mode declare

def mode_declare(args, site, register_rows, fails, notes):
    row_ids = {r.get("id") for r in register_rows} if register_rows is not None else None
    checked = 0
    for sec in site.get("sections", []):
        stype = sec.get("type")
        if stype not in CLAIM_BEARING:
            continue
        sid = sec.get("id", "<no id>")
        items = int(sec.get("items", 0) or 0)
        claims = sec.get("claims", []) or []
        if not isinstance(claims, list):
            fails.append(f"section '{sid}': claims is not a list")
            continue
        if len(claims) > items:
            # A silently ignored declaration is a declaration nobody checked.
            fails.append(f"section '{sid}': claims[] has {len(claims)} entr(ies) but items={items}; "
                          f"surplus declaration(s) at index {list(range(items + 1, len(claims) + 1))} "
                          f"would never be rendered or checked")
        for n in range(1, items + 1):
            checked += 1
            if n > len(claims):
                fails.append(f"section '{sid}' item {n}: no claims[{n - 1}] entry "
                              f"(every item of a {stype} section declares what it asserts)")
                continue
            cl = claims[n - 1]
            if not isinstance(cl, dict):
                fails.append(f"section '{sid}' item {n}: claims[{n - 1}] is not an object")
                continue
            kind = cl.get("kind")
            if not kind:
                fails.append(f"section '{sid}' item {n}: no 'kind'")
            elif kind not in KINDS:
                fails.append(f"section '{sid}' item {n}: kind {kind!r} not in the controlled "
                              f"vocabulary {list(KINDS)}")
            elif kind == UNDECLARED:
                fails.append(f"section '{sid}' item {n}: kind is \"undeclared\" -- the migration "
                              f"placeholder, never an answer; the owner replaces it by hand")
            if stype == "testimonials":
                role = cl.get("speaker_role")
                if not role:
                    fails.append(f"section '{sid}' item {n}: testimonials item has no 'speaker_role'")
                elif role not in SPEAKER_ROLES:
                    fails.append(f"section '{sid}' item {n}: speaker_role {role!r} not in "
                                  f"{list(SPEAKER_ROLES)}")
                elif role == UNDECLARED:
                    fails.append(f"section '{sid}' item {n}: speaker_role is \"undeclared\"")
            if kind == "deployment-site":
                st = cl.get("state")
                if not st:
                    fails.append(f"section '{sid}' item {n}: kind=deployment-site requires 'state'")
                elif st not in DEPLOYMENT_STATES:
                    fails.append(f"section '{sid}' item {n}: state {st!r} not in "
                                  f"{list(DEPLOYMENT_STATES)}")
            for ref_field in ("red_line", "retraction_of"):
                ref = cl.get(ref_field)
                if ref is None:
                    continue
                if row_ids is None:
                    continue
                if ref not in row_ids:
                    fails.append(f"section '{sid}' item {n}: {ref_field}={ref!r} names no row in "
                                  f"the register")
    if row_ids is None:
        notes.append("NOTE: no redlines.json in the project; red_line / retraction_of references "
                     "were not resolved (nothing to resolve them against).")
    return checked


# ----------------------------------------------------------------- mode sweep

def expected_pages(site, dist, locale_path):
    """{locale: page path} by the locale_path rule imported from
    render-page.py -- never a second implementation of it. One helper, so the
    sweep and the record writer can never disagree about which file a locale's
    certification is about."""
    default = site.get("default_locale")
    out = {}
    for loc in site.get("locales", []) or []:
        rel = locale_path(loc, default).strip("/")
        out[loc] = (dist / rel / "index.html") if rel else (dist / "index.html")
    return out


def page_map(site, dist, locale_path, fails):
    """[(page, locale)] for every rendered locale page, and a FAIL for every
    locale whose page is missing."""
    expected = {v.resolve(): k for k, v in expected_pages(site, dist, locale_path).items()}
    pages = []
    for page in sorted(dist.rglob("*.html")):
        loc = expected.get(page.resolve())
        if loc is None:
            continue  # not a locale index page; Q-ORPHAN owns stray pages
        pages.append((page, loc))
    seen = {loc for _, loc in pages}
    for loc, path in expected_pages(site, dist, locale_path).items():
        if loc not in seen:
            fails.append(f"rendered page missing for locale '{loc}': {path}")
    return pages


def claims_for(site):
    """{section id: (type, [claim, ...])} from site.json."""
    out = {}
    for sec in site.get("sections", []):
        out[sec.get("id")] = (sec.get("type"), sec.get("claims", []) or [])
    return out


def item_claim(by_section, ident):
    """The claims[] entry an item anchor points at, or None."""
    if "." not in (ident or ""):
        return None
    sid, num = ident.rsplit(".", 1)
    try:
        n = int(num)
    except ValueError:
        return None
    entry = by_section.get(sid)
    if not entry:
        return None
    claims = entry[1]
    if n < 1 or n > len(claims):
        return None
    cl = claims[n - 1]
    return cl if isinstance(cl, dict) else None


def require_reading_record(row, kind_phrase, locale, page, page_sha, reads, fails, notes):
    """The reading-record check, shared by `manual-read` prohibition rows and by
    every obligation row nothing machine-checks (F-10). One record per row AND
    per locale, hash-bound to the page it certifies; a row checked here is never
    reported as passing without one. `kind_phrase` names WHY the read was
    demanded, so the report says which row type is asking."""
    rid = row.get("id", "<no id>")
    rec = None
    for r in reads.get("records", []) or []:
        if r.get("row") == rid and r.get("locale") == locale:
            rec = r
            break
    if rec is None:
        fails.append(f"READ-REQUIRED {rid} {locale}: {row.get('rule', '')} "
                      f"-- no record in claims-read.json; {kind_phrase} is never "
                      f"reported as passing")
        return
    stored = rec.get("page_sha256") or rec.get("sha256")
    if not stored:
        fails.append(f"STALE-READ {rid} {locale}: the record carries no page sha256, so it "
                      f"certifies no particular text (page is {page_sha[:16]}...)")
        return
    if stored != page_sha:
        fails.append(f"STALE-READ {rid} {locale}: record certifies page sha256 "
                      f"{str(stored)[:16]}... but {page} is {page_sha[:16]}...; the page "
                      f"changed since it was read")
        return
    verdict = rec.get("verdict")
    if verdict not in READ_VERDICTS:
        fails.append(f"READ-REQUIRED {rid} {locale}: record verdict {verdict!r} is not in "
                      f"the vocabulary {list(READ_VERDICTS)}")
        return
    if verdict not in CERTIFYING_VERDICTS:
        fails.append(f"READ-REQUIRED {rid} {locale}: record verdict is {verdict!r}; only "
                      f"{list(CERTIFYING_VERDICTS)} certify a page")
        return
    if verdict == DEVIATION_VERDICT:
        # Certifying, and never quietly: the accepted deviation is printed with
        # its description, so a reader of the report sees what was accepted
        # rather than a green line.
        notes.append(f"READ-OK-DEVIATION {rid} {locale}: read by {rec.get('reader')!r} on "
                      f"{rec.get('read_at')}, page sha256 matches; an accepted deviation is "
                      f"on record: {rec.get('note') or '(no description)'}")
        return
    notes.append(f"READ-OK {rid} {locale}: read by {rec.get('reader')!r} on "
                  f"{rec.get('read_at')}, page sha256 matches.")


def sweep_page(args, site, rows, reg, reads, page, locale, fails, notes):
    raw = page.read_text(encoding="utf-8", errors="replace")
    page_sha = hashlib.sha256(page.read_bytes()).hexdigest()
    by_section = claims_for(site)
    lexicon = (reg.get("retraction_lexicon", {}) or {}).get(locale, []) or []

    reported_missing = set()  # (row id, item anchor) -- report a missing
    # retraction once per item, whether it was found by a wording hit or by
    # the declared-retraction sweep below.
    item_spans_raw = item_spans(raw)
    item_regions = regions(raw, item_spans_raw)
    # The RAW html per item, kept beside the visible-text regions: a declared
    # retraction is an ATTRIBUTE (`data-ls-retracts`), and to_text() strips
    # tags, so the structural fact is invisible in the text regions by
    # construction.
    raw_item = {ident: raw[start:end] for start, end, ident in item_spans_raw}

    # Fourth state of the use/mention rule: the page carries a declared
    # retraction of a row the item's own claims[] entry does not name. The
    # markup asserts a withdrawal the structure does not back -- the same
    # defect class as an undeclared claim, and invisible to the per-row loop
    # below when the row has no wording hit on the page.
    for ident, item_html in sorted(raw_item.items()):
        cl = item_claim(by_section, ident) or {}
        for claimed in sorted(declared_retractions(item_html)):
            if cl.get("retraction_of") == claimed:
                continue
            declared = cl.get("retraction_of")
            why = (f"its claims[] entry declares retraction_of={declared!r}"
                   if declared else "its claims[] entry declares no retraction_of")
            fails.append(f"BREACH {claimed} {page} item {ident}: the page carries a declared "
                          f"retraction of {claimed} but {why}; markup cannot assert a withdrawal "
                          f"the declaration does not back")

    section_regions = regions(raw, section_spans(raw))
    attr_regions = attribute_regions(raw)
    declared_items = [(ident, text) for kind, ident, text in item_regions if kind == "span"]

    for row in rows:
        rid = row.get("id", "<no id>")
        if obligation_is_live(row):
            # F-10. The disclosure duty is the one obligation a gate really
            # checks; every other obligation row is machine-checked by NOTHING,
            # so it is treated exactly like a manual-read prohibition -- a
            # reading record per locale, or this sweep fails. An obligation
            # nobody checks is worse than no obligation, because the register
            # makes it look covered.
            if not obligation_delegate(row):
                require_reading_record(row, "an obligation nothing machine-checks",
                                       locale, page, page_sha, reads, fails, notes)
            continue
        if not row_is_active(row):
            continue
        match = row.get("match")

        if match == "not-applicable":
            continue  # printed once, before the per-page loop

        if match == "manual-read":
            require_reading_record(row, "a manual-read row", locale, page, page_sha,
                                   reads, fails, notes)
            continue

        # literal / regex rows -------------------------------------------------
        patterns = row.get("patterns", {}) or {}
        plist = patterns.get(locale)
        if plist is None:
            plist = patterns.get("*")
        if not plist:
            # M-2b: a register written in English cannot certify a Russian
            # page. Reporting that locale clean is the exact failure mode this
            # layer exists to prevent.
            fails.append(f"NO-PATTERNS {rid} {locale}: active {row.get('type')} row has no pattern "
                          f"list for locale '{locale}' and no \"*\" list; {page} cannot be certified")
            continue

        for pattern in plist:
            rx = pattern_regex(row, pattern)
            if row.get("type") == "implicature":
                required = row.get("requires_kind", []) or []
                for kind, ident, text in section_regions:
                    hits = occurrences(rx, text)
                    if not hits:
                        continue
                    if kind == "span":
                        stype, claims = by_section.get(ident, (None, []))
                        kinds = [c.get("kind") for c in claims if isinstance(c, dict)]
                        if any(k in required for k in kinds):
                            continue
                        fails.append(f"IMPLICATURE {rid} {page} section '{ident}': {hits} "
                                      f"occurrence(s) of {pattern!r}, but the section declares "
                                      f"{kinds or 'no claims'}; one of {required} would make the "
                                      f"wording legal")
                    else:
                        fails.append(f"IMPLICATURE {rid} {page} <page chrome>: {hits} occurrence(s) "
                                      f"of {pattern!r} outside any declaring section; one of "
                                      f"{required} in a section would make the wording legal")
                # F-12: attribute text. It belongs to no section and no item, so
                # no declaration anywhere can legalise it -- the wording itself
                # has to change.
                for location, text in attr_regions:
                    hits = occurrences(rx, text)
                    if not hits:
                        continue
                    fails.append(f"IMPLICATURE {rid} {page} <attribute {location}>: {hits} "
                                  f"occurrence(s) of {pattern!r} in \"{snippet(text)}\"; "
                                  f"attribute text sits in no declaring section, so no "
                                  f"{required} declaration reaches it")
                continue

            # prohibition rows: the use/mention rule, scoped to ONE item.
            for kind, ident, text in item_regions:
                hits = occurrences(rx, text)
                if not hits:
                    continue
                if kind != "span":
                    fails.append(f"BREACH {rid} {page} <page chrome>: {hits} occurrence(s) of "
                                  f"{pattern!r} outside any declared item; page chrome is never "
                                  f"exempt")
                    continue
                cl = item_claim(by_section, ident) or {}
                if cl.get("retraction_of") != rid:
                    declared = cl.get("retraction_of")
                    why = (f"item declares retraction_of={declared!r}, not {rid!r}"
                           if declared else "item declares no retraction_of")
                    fails.append(f"BREACH {rid} {page} item {ident}: {hits} occurrence(s) of "
                                  f"{pattern!r}; {why}")
                    continue
                declared = declared_retractions(raw_item.get(ident, ""))
                if rid in declared:
                    notes.append(f"EXEMPT-DECLARED {rid} {page} item {ident}: {hits} "
                                  f"occurrence(s); the item carries a declared retraction of "
                                  f"{rid} (ls-retraction / data-ls-retracts)")
                    continue
                # Migration path: the declaration exists in site.json but the
                # page carries no retraction element, which is every v9/v10
                # project. Nothing breaks -- it routes to a named reader rather
                # than being exempted on prose or failed outright.
                present = [term for term in lexicon
                           if occurrences(pattern_regex({"match": "literal"}, term), text)]
                hint = (f"; retraction language is present ({present[0]!r}) but not declared -- "
                        f"fill {ident.split('.')[0]}.item{ident.split('.')[-1]}.retraction_text"
                        if present else "")
                fails.append(f"READ-REQUIRED {rid} {page} item {ident}: {hits} occurrence(s) of "
                              f"{pattern!r}; the item declares retraction_of={rid} but the page "
                              f"carries no declared retraction of it{hint}")
                continue

            # F-12: attribute text, swept as its own region set. It belongs to
            # no `data-ls-item`, so -- exactly like page chrome -- it can never
            # be exempt: there is no item for a retraction declaration to scope
            # an exemption to. The report names which attribute of which element
            # carried the hit, and the attribute's own text, so the fix is
            # obvious without reading the rendered page.
            for location, text in attr_regions:
                hits = occurrences(rx, text)
                if not hits:
                    continue
                fails.append(f"BREACH {rid} {page} <attribute {location}>: {hits} "
                              f"occurrence(s) of {pattern!r} in \"{snippet(text)}\"; attribute "
                              f"text belongs to no data-ls-item, so like page chrome it is "
                              f"never exempt")

    # An item declaring retraction_of for an active row must carry retraction
    # language even if the sweep found no wording occurrence in it -- a
    # declared retraction that says nothing retracts nothing.
    for ident, text in declared_items:
        cl = item_claim(by_section, ident) or {}
        target = cl.get("retraction_of")
        if not target:
            continue
        row = next((r for r in rows if r.get("id") == target), None)
        if row is None or not row_is_active(row):
            continue
        if (target, ident) in reported_missing:
            continue
        if not lexicon:
            reported_missing.add((target, ident))
            fails.append(f"MISSING-RETRACTION {target} {page} item {ident}: the item declares "
                          f"retraction_of={target} but redlines.json has no "
                          f"retraction_lexicon['{locale}']")
            continue
        present = [term for term in lexicon
                   if occurrences(pattern_regex({"match": "literal"}, term), text)]
        if not present:
            reported_missing.add((target, ident))
            fails.append(f"MISSING-RETRACTION {target} {page} item {ident}: the item declares "
                          f"retraction_of={target} but carries no term from "
                          f"retraction_lexicon['{locale}'] = {list(lexicon)}")


# The exemption reads the SLOT, not a loose attribute. Both orders of the two
# attributes are accepted; the element must carry the ls-retraction class, and
# (below) non-empty visible text. An adversarial pass shipped a red-lined claim
# past the previous version with `<span data-ls-retracts="RL-1"
# style="display:none"></span>` plus an unrelated "correction:" sentence: the
# attribute alone was the whole test, while claims.md called the class
# load-bearing. The class was asserted in three comments and enforced nowhere.
RETRACTION_SLOT_RE = re.compile(
    r'<(?P<tag>[a-z]+)\b(?=[^>]*class\s*=\s*"[^"]*\bls-retraction\b[^"]*")'
    r'(?=[^>]*data-ls-retracts\s*=\s*"(?P<row>[^"]+)")[^>]*>(?P<body>.*?)</\1\s*>',
    re.IGNORECASE | re.DOTALL)


def declared_retractions(item_html):
    """Register rows this item DECLARES it withdraws, read from the markup.

    The v10 completion pass tried twice to detect a retraction in prose: first
    a lexicon term anywhere in the item, then one in the same sentence as the
    withdrawn wording. Both are co-occurrence, and an adversarial pass walked a
    fabricated claim through the second with ordinary compound copy ("used by
    NASA, and by the way here is our support-hours correction: ..."). A third
    narrowing would be the same error a third time.

    So the question stops being semantic. A withdrawal is a declared structural
    fact -- `<p class="ls-retraction" data-ls-retracts="RL-1">` -- exactly like
    every other assertion this layer checks: `kind` in `claims[]`, `date` and
    `grade` in site.json, none of them sniffed out of the copy. What remains
    fakeable is a `retraction_text` that withdraws nothing, and that is a false
    declaration, covered by the layer's disclosed limit: coherence is checked,
    truth is not. It now takes a deliberate lie in a dedicated field instead of
    an accident in ordinary prose."""
    found = set()
    for m in RETRACTION_SLOT_RE.finditer(item_html or ""):
        # An empty or invisible slot withdraws nothing a reader can see. The
        # text is what a person reads; the attribute is what the check reads.
        # Requiring both is the difference between a declaration and a token.
        if to_text(m.group("body")).strip():
            found.add(m.group("row"))
    return found


def coverage(rows):
    """How the register's rows were actually checked, counted by mechanism. The
    PASS line used to say "N active row(s)" and nothing else, which read as
    "N rows checked" while most of them were carried, delegated or resting on a
    reading record -- the sweep overstating its own reach is the same defect
    class as an unchecked obligation printing a gate id (F-10)."""
    swept = sum(1 for r in rows if row_is_active(r) and r.get("match") in ("literal", "regex"))
    read = sum(1 for r in rows if row_is_active(r) and r.get("match") == "manual-read")
    read += sum(1 for r in rows if obligation_is_live(r) and not obligation_delegate(r))
    carried = sum(1 for r in rows if r.get("match") == "not-applicable")
    delegated = sum(1 for r in rows if obligation_is_live(r) and obligation_delegate(r))
    inert = sum(1 for r in rows if r.get("status") == "released")
    parts = [f"{swept} machine-swept", f"{read} certified by a reading record",
             f"{carried} carried not-applicable", f"{delegated} delegated to another gate",
             f"{inert} released and inert"]
    return "checked as: " + ", ".join(parts)


def mode_sweep(args, site, reg, rows, fails, notes):
    if args.dist is None:
        print("FAIL: --mode sweep needs --dist", file=sys.stderr)
        return 2
    if not args.dist.exists():
        fails.append(f"dist directory not found: {args.dist}")
        return 1
    locale_path, err = load_locale_path_or_report()
    if err:
        print(f"FAIL: {err}", file=sys.stderr)
        return 2

    reads = {}
    if args.reads and args.reads.exists():
        try:
            reads = load_json(args.reads)
        except (OSError, json.JSONDecodeError) as e:
            fails.append(f"cannot read/parse reads file '{args.reads}': {e}")

    # Printed once, never swept (spec 2.4 item 8 / G10): nothing is dropped.
    for row in rows:
        if row.get("match") == "not-applicable":
            print(f"CARRIED {row.get('id')} {row.get('reason', row.get('rule', ''))}")
        elif row.get("status") == "released":
            print(f"CARRIED {row.get('id')} status=released "
                  f"(kept inert; the history is the point)")
        elif row.get("type") == "obligation":
            # Its own token, not CARRIED: an obligation is live, it is simply
            # not swept for wording (spec 2.1). WHICH token depends on whether
            # anything actually checks it (F-10) -- printing one gate's id for
            # every obligation row is what made unchecked duties look covered.
            gate = obligation_delegate(row)
            if gate:
                print(f"OBLIGATION {row.get('id')} check={row.get('check')!r} delegated to "
                      f"{gate}, never swept for wording")
            elif not obligation_is_live(row):
                print(f"CARRIED {row.get('id')} obligation status={row.get('status')!r} "
                      f"(kept inert)")
            else:
                unknown = (f" (check={row.get('check')!r} names no check this tool implements)"
                           if row.get("check") else "")
                print(f"UNCHECKED-BY-MACHINE {row.get('id')} obligation{unknown}: read like a "
                      f"manual-read row, one record per locale -- {row.get('rule', '')}")

    pages = page_map(site, args.dist, locale_path, fails)
    for page, locale in pages:
        sweep_page(args, site, rows, reg, reads, page, locale, fails, notes)
    return None if not fails else 1


# ----------------------------------------------------------- mode record-read

def mode_record_read(args, site, rows):
    """Write ONE reading record for ONE manual-read row and ONE locale, with
    the rendered page's sha256 stamped in (spec 2.1). Returns (exit code,
    report). One row, one locale, one invocation: the record is a claim that a
    human read one text, and a bulk "certify everything" switch would make it a
    claim that nobody read anything.

    It refuses, with a nonzero exit, to write a record that certifies nothing:
    an unknown row id, a row that is not `manual-read` (those rows are swept,
    and a reading cannot stand in for a sweep), or a locale with no rendered
    page. Every other record in claims-read.json survives untouched; a record
    for the same row AND locale is replaced, because a re-read supersedes the
    read before it."""
    required = [flag for flag, value in (("--row", args.row), ("--locale", args.locale),
                                         ("--reader", args.reader), ("--verdict", args.verdict))
                if not value]
    if required:
        print(f"FAIL: --mode record-read needs {', '.join(required)}", file=sys.stderr)
        return 2, None
    if args.verdict == DEVIATION_VERDICT and not (args.note or "").strip():
        print(f"FAIL: verdict {DEVIATION_VERDICT!r} needs --note describing the deviation that "
              f"was accepted. Without it this verdict is a second spelling of "
              f"{CERTIFYING_VERDICT!r} and certifies a page while saying nothing.",
              file=sys.stderr)
        return 2, None
    if args.dist is None:
        print("FAIL: --mode record-read needs --dist; the record certifies one rendered page",
              file=sys.stderr)
        return 2, None

    row = next((r for r in rows if r.get("id") == args.row), None)
    if row is None:
        print(f"REFUSED {args.row} {args.locale}: no row with that id in {args.redlines}; a record "
              f"naming a row the register does not carry certifies nothing")
        return 1, None
    # An obligation nothing machine-checks is read exactly like a manual-read
    # row (F-10), so it is the second row type a reading record may certify.
    if not (row.get("match") == "manual-read"
            or (obligation_is_live(row) and not obligation_delegate(row))):
        gate = obligation_delegate(row)
        why = (f"that obligation's check={row.get('check')!r} is delegated to {gate}, which is "
               f"what checks it" if gate else
               f"row match is {row.get('match')!r}, not 'manual-read'; that row is swept by "
               f"--mode sweep, and a reading record can never stand in for a sweep")
        print(f"REFUSED {args.row} {args.locale}: {why}")
        return 1, None

    locale_path, err = load_locale_path_or_report()
    if err:
        print(f"FAIL: {err}", file=sys.stderr)
        return 2, None
    pages = expected_pages(site, args.dist, locale_path)
    if args.locale not in pages:
        print(f"REFUSED {args.row} {args.locale}: locale '{args.locale}' is not in site.json "
              f"locales {list(pages)}")
        return 1, None
    page = pages[args.locale]
    if not page.exists():
        print(f"REFUSED {args.row} {args.locale}: no rendered page at {page}; there is no text for "
              f"any reader to have read")
        return 1, None

    sha = hashlib.sha256(page.read_bytes()).hexdigest()
    reads = {"records": []}
    if args.reads.exists():
        try:
            reads = load_json(args.reads)
        except (OSError, json.JSONDecodeError) as e:
            print(f"FAIL: cannot read/parse reads file '{args.reads}': {e}", file=sys.stderr)
            return 2, None
        if not isinstance(reads, dict) or not isinstance(reads.get("records", []), list):
            print(f"FAIL: '{args.reads}' is not a {{\"records\": [...]}} object", file=sys.stderr)
            return 2, None
    records = list(reads.get("records", []) or [])

    record = {"row": args.row, "locale": args.locale, "reader": args.reader,
              "read_at": datetime.date.today().isoformat(), "verdict": args.verdict,
              "page_sha256": sha, "page": page.name}
    if args.note:
        record["note"] = args.note

    replaced = None
    for i, existing in enumerate(records):
        if isinstance(existing, dict) and existing.get("row") == args.row \
                and existing.get("locale") == args.locale:
            replaced = existing
            records[i] = record
            break
    else:
        records.append(record)
    reads["records"] = records
    args.reads.parent.mkdir(parents=True, exist_ok=True)
    args.reads.write_text(json.dumps(reads, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    verb = "REPLACED" if replaced else "RECORDED"
    print(f"{verb} {args.row} {args.locale}: reader={args.reader!r} verdict={args.verdict!r} "
          f"page={page} sha256={sha}")
    if replaced:
        print(f"NOTE: the previous record (read_at={replaced.get('read_at')}, "
              f"sha256={str(replaced.get('page_sha256'))[:16]}...) was superseded, not merged.")
    print(f"NOTE: {len(records)} record(s) now in {args.reads}; every other record was left "
          f"untouched.")
    if not (row_is_active(row) or obligation_is_live(row)):
        print(f"NOTE: row {args.row} has status {row.get('status')!r} and is not active, so the "
              f"sweep will not consult this record.")
    # trial finding B3: this compared against the retained SINGULAR
    # CERTIFYING_VERDICT while the sweep consults the plural set, so recording
    # a real accepted deviation printed "does not certify ... will still report
    # READ-REQUIRED" and the very next sweep printed READ-OK-DEVIATION. A tool
    # telling its operator the opposite of what its own next command will do is
    # the same defect class this file exists to prevent on a page.
    if args.verdict not in CERTIFYING_VERDICTS:
        print(f"NOTE: verdict {args.verdict!r} does not certify the page; --mode sweep will still "
              f"report {args.row} as READ-REQUIRED.")
    elif args.verdict == DEVIATION_VERDICT:
        print(f"NOTE: verdict {args.verdict!r} certifies the page; --mode sweep will report "
              f"{args.row} as READ-OK-DEVIATION, carrying the note above, never as a plain pass.")
    print(f"NOTE: this record attests that the named reader ({args.reader!r}) was recorded "
          f"against THIS text, identified by its sha256. It does not establish that the reader "
          f"is a person, nor that the reading was careful -- --reader takes whatever string it "
          f"is given (references/claims.md says so out loud).")
    return 0, {"mode": "record-read", "result": "PASS", "record": record,
               "replaced": replaced, "reads": str(args.reads)}


def main(argv):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--mode", required=True, choices=("declare", "sweep", "record-read"))
    p.add_argument("--site", required=True, type=Path)
    p.add_argument("--dist", type=Path, default=None,
                   help="Rendered tree. Required by --mode sweep; accepted and unused by "
                        "--mode declare, which is a source-only check.")
    p.add_argument("--redlines", type=Path, default=None,
                   help="Red-line register. Defaults to 'redlines.json' next to --site.")
    p.add_argument("--reads", type=Path, default=None,
                   help="Human reading records. Defaults to 'claims-read.json' next to --site.")
    p.add_argument("--json", dest="json_out", type=Path, default=None)
    # --mode record-read only. One row, one locale, one invocation: there is
    # deliberately no bulk switch, because the record is a claim that a human
    # read one text.
    p.add_argument("--row", default=None,
                   help="record-read: the row id this reading certifies -- a manual-read "
                        "prohibition, or an obligation no gate machine-checks.")
    p.add_argument("--locale", default=None,
                   help="record-read: the locale whose rendered page was read.")
    p.add_argument("--reader", default=None,
                   help="record-read: who read it -- a person, named.")
    p.add_argument("--verdict", default=None, choices=READ_VERDICTS,
                   help="record-read: the reading's verdict. Only 'clear' certifies a page.")
    p.add_argument("--note", default=None,
                   help="record-read: optional free text -- what the reader saw.")
    try:
        args = p.parse_args(argv[1:])
    except SystemExit as e:
        return e.code if e.code is not None else 2

    if args.redlines is None:
        args.redlines = args.site.parent / "redlines.json"
    if args.reads is None:
        args.reads = args.site.parent / "claims-read.json"

    try:
        site = load_json(args.site)
    except (OSError, json.JSONDecodeError) as e:
        print(f"FAIL: cannot read/parse site file '{args.site}': {e}", file=sys.stderr)
        return 2
    if not isinstance(site, dict):
        print(f"FAIL: '{args.site}' does not contain a JSON object", file=sys.stderr)
        return 2

    fails, notes = [], []
    reg, rows = {}, None
    if args.redlines.exists():
        try:
            reg, rows = load_register(args.redlines, fails)
        except (OSError, json.JSONDecodeError) as e:
            print(f"FAIL: cannot read/parse register '{args.redlines}': {e}", file=sys.stderr)
            return 2

    print(f"=== claims-check ({args.mode}) ===")
    rc = None
    if args.mode == "record-read":
        if rows is None:
            print(f"FAIL: --mode record-read needs a register; none at '{args.redlines}'",
                  file=sys.stderr)
            return 2
        if fails:  # a malformed register is never a base for a certification
            print(f"FAIL ({len(fails)}):")
            for f in fails:
                print(f"  - {f}")
            return 1
        code, report = mode_record_read(args, site, rows)
        if args.json_out and report is not None:
            args.json_out.parent.mkdir(parents=True, exist_ok=True)
            args.json_out.write_text(json.dumps(report, indent=2, ensure_ascii=False),
                                     encoding="utf-8")
        return code

    if args.mode == "declare":
        checked = mode_declare(args, site, rows, fails, notes)
        summary = (f"{checked} item(s) across {len([s for s in site.get('sections', []) if s.get('type') in CLAIM_BEARING])} "
                   f"claim-bearing section(s)")
    else:
        if rows is None:
            print(f"FAIL: --mode sweep needs a register; none at '{args.redlines}'", file=sys.stderr)
            return 2
        rc = mode_sweep(args, site, reg, rows, fails, notes)
        if rc == 2:
            return 2
        active = [r for r in rows if row_is_active(r)]
        summary = f"{len(active)} active row(s) of {len(rows)} in {args.redlines}; {coverage(rows)}"

    for n in notes:
        print(n)
    if fails:
        print(f"FAIL ({len(fails)}):")
        for f in fails:
            print(f"  - {f}")
    else:
        print(f"PASS: {summary}.")

    if args.json_out:
        report = {"mode": args.mode, "result": "FAIL" if fails else "PASS",
                  "summary": summary, "fails": fails, "notes": notes}
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
