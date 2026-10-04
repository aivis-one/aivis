#!/usr/bin/env python3
"""landing-studio v10.0.0 -- scripts/render-page.py

Render ONE self-contained static landing page for a single locale.
Merges site structure (site.json) + locale text (content/{locale}.json) + DTCG tokens,
inlines all CSS/JS from assets/ (no framework, no CDN -- Invariant 1), and emits one HTML
file with correct <html lang dir>, canonical, symmetric hreflang, and x-default.

URL scheme (Invariant 3 / Q10): default locale at root '/', others at '/{lang}/';
the default locale is whatever site.json 'default_locale' names -- English is a
convention, not a rule (Q3); x-default points to root.

v9 changes (see spec/SPEC-v9.md):
  - single-pass {{PLACEHOLDER}} substitution via re.sub (finding C1)
  - every interpolation site is escaped at the point of use, including the
    CANON locale (finding C10)
  - safe_href() scheme allow-list for every user-sourced href (finding C11)
  - Content.meta_get() gives meta.title/meta.description the same default-locale
    fallback as t{} keys (finding C16); c.meta is never read raw
  - the hardcoded "pricing.badge" fallback key is gone (finding D6)
  - a deprecated migration shield strips legacy inline [review:xx] markers and
    WARNs on stderr -- the renderer never reads _review (section 2, Q1)
  - v9 section vocabulary: align, hero visual slot, logos, testimonials, skip
    link, <main id="ls-main">, header CTA, theme toggle (section 6)
  - assets/icons.json + icon_svg() (section 7)
  - every RENDERERS entry (including footer) shares the signature r_x(sec, c, site)

v10 changes (see spec/SPEC-v10.md):
  - every item of a CLAIM-BEARING section (logos, testimonials, evidence, state)
    is wrapped in <div class="ls-item" data-ls-item="{sec}.{n}"> with 1-based n
    matching site.json claims[n-1] (spec 2.3). The anchor is load-bearing:
    claims-check.py scopes a use/mention exemption to ONE item through it.
  - {id}.item{n}.relationship_note renders as <p class="ls-item__note"> inside
    that wrapper -- the per-locale sentence; the structural fact stays in site.json
  - a missing claims[n-1] prints a render-time WARN and still renders: the render
    is not the gate, Q-DECLARE is (spec 2.3)
  - new section types `evidence` and `state` (spec 3.1); .ls-fact__meta carries
    `{date} \u00b7 {grade}` read from site.json claims[n-1], never from a content file
  - the agent-authorship disclosure (spec 4.2): when the obligation is active the
    footer renders exactly one <p class="ls-disclosure"> before link{n}. Unlike
    every other chrome element this one is never silently omitted.
  - icon_svg() gains a second lookup source with a documented precedence:
    icon-map.json, then assets/icons.json, then the escaped literal (spec 5.6)

Usage:
  python render-page.py --site site.json --content content/en.json \\
      --tokens tokens.tokens.json --assets-dir assets --locale en \\
      --out dist/index.html [--fallback content/en.json] [--animate] \\
      [--icon-map icon-map.json]
"""
import argparse
import html
import json
import re
import sys
import unicodedata
from pathlib import Path

import importlib.util


def _load_tokens_to_css(assets_dir):
    here = Path(__file__).parent
    spec = importlib.util.spec_from_file_location("t2c", here / "tokens-to-css.py")
    mod = importlib.util.module_from_spec(spec)
    # Same guard claims-check.py, contrast-check.py and build-site.py use:
    # without it this import drops a scripts/__pycache__/ into the tree being
    # rendered, which then shows up in a packaged child's round-trip diff.
    prev = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.dont_write_bytecode = prev
    return mod


def esc(s):
    return html.escape(str(s), quote=True)


def locale_path(locale, default_locale):
    return "/" if locale == default_locale else f"/{locale}/"


def read(p):
    return Path(p).read_text(encoding="utf-8")


def first_grapheme(s):
    """Best-effort first grapheme: a base character plus any combining marks
    that immediately follow it. No third-party grapheme-segmentation library
    is used (Invariant: no third-party imports) -- this is an approximation
    good enough for an avatar initial."""
    s = s or ""
    if not s:
        return ""
    chars = list(s)
    out = chars[0]
    i = 1
    while i < len(chars) and unicodedata.combining(chars[i]):
        out += chars[i]
        i += 1
    return out


# ---------- section 2: deprecated [review:xx] migration shield (Q1) ----------
# `_review` is the only legal out-of-band review channel. This regex strips
# legacy v8 inline markers so a not-yet-migrated content file still renders
# clean copy; it warns on every strip. v9 announced its removal in v10 and
# v10 keeps it: fixture T1 requires a legacy project to render clean, so the
# shield is what closes that finding, and removing it would reopen it. The
# removal is deferred, not forgotten. The renderer NEVER reads the
# `_review` key itself.
REVIEW_RE = re.compile(r"\s*\[review:[a-z-]{2,12}\]")


# ---------- section 4.6: href scheme allow-list (finding C11) ----------
_SCHEME_RE = re.compile(r"^([a-zA-Z][a-zA-Z0-9+.\-]*):")


def safe_href(v, default="#", context=""):
    """Allow: absolute http/https, root-relative '/...', explicit relative
    './'/'../', a bare relative path with no scheme, or a fragment '#...'.
    Reject everything else -- javascript:, data:, vbscript:, file:, mailto:
    (CF4: no email-shaped strings in output), any other scheme, and the
    protocol-relative '//host' form (an external host masquerading as
    relative). A rejected value prints a WARN naming the context and falls
    back to `default`."""
    v2 = v.strip() if isinstance(v, str) else ""
    ok = False
    if v2 == "":
        ok = False
    elif v2.startswith("#"):
        ok = True
    elif v2.startswith("//"):
        ok = False
    elif v2.startswith("/"):
        ok = True
    elif v2.startswith("./") or v2.startswith("../"):
        ok = True
    else:
        m = _SCHEME_RE.match(v2)
        if m:
            ok = m.group(1).lower() in ("http", "https")
        else:
            ok = True  # bare relative path/anchor id, no scheme, no leading slash
    if ok:
        return v2
    where = f" in {context}" if context else ""
    print(f"WARN: rejected unsafe href '{v}'{where}; using fallback '{default}'", file=sys.stderr)
    return default


# ---------- section 7: icon set ----------
_ICON_ALLOWED_TAGS = {"path", "circle", "rect", "line", "polyline"}
_ICON_TAG_RE = re.compile(r"<\s*([A-Za-z][A-Za-z0-9-]*)")


def load_icons(assets_dir):
    """Load assets/icons.json and validate every entry contains only path-data
    elements (no <script>, no event handlers) so a tampered icons.json cannot
    inject. The icon markup is skill-owned and therefore trusted once
    validated -- icon_svg() does not re-escape it."""
    icons_path = Path(assets_dir) / "icons.json"
    if not icons_path.exists():
        return {}
    try:
        raw = json.loads(icons_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"WARN: assets/icons.json failed to parse ({e}); icon rendering disabled", file=sys.stderr)
        return {}
    if not isinstance(raw, dict):
        print("WARN: assets/icons.json is not a JSON object; icon rendering disabled", file=sys.stderr)
        return {}
    clean = {}
    for name, markup in raw.items():
        if not isinstance(name, str) or not isinstance(markup, str):
            print(f"WARN: assets/icons.json entry {name!r} is not a string pair; dropped", file=sys.stderr)
            continue
        tags = {t.lower() for t in _ICON_TAG_RE.findall(markup)}
        if not tags or not tags.issubset(_ICON_ALLOWED_TAGS):
            print(f"WARN: assets/icons.json entry '{name}' contains disallowed markup {sorted(tags)}; dropped",
                  file=sys.stderr)
            continue
        clean[name] = markup
    return clean


# ---------- spec 5.6: the icon bridge, a second lookup source ----------
# `icon-map.json` is written by scripts/icon-bridge.py when a design system is
# ingested, and read from the project root (beside site.json), the same rule
# gate.py uses for redlines.json. It is OPTIONAL input: a project that never
# ingested a design system has none and nothing about v9 rendering changes.
#
# Row shape (spec 5.6): {"concept": ..., "status": "mapped", "to": "ls:<name>"}
# | {"concept": ..., "status": "mapped", "to": "ds:<key>", "svg": "<path data>"}
# | {"concept": ..., "status": "unmapped-declared-absent"}.
_ICON_MAP_STATUSES = ("mapped", "unmapped-declared-absent")


def _icon_map_rows(raw):
    """Accept the row list either as a bare JSON list, under an "icons"/"rows"/
    "map" key, or as an object keyed by concept -- the renderer is a READER of
    a file another script owns, and a reader that hard-fails on a shape it could
    have understood turns a MINOR bridge into a broken build."""
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for key in ("icons", "rows", "map", "concepts"):
            if isinstance(raw.get(key), list):
                return raw[key]
        rows = []
        for concept, row in raw.items():
            if isinstance(row, dict):
                r = dict(row)
                r.setdefault("concept", concept)
                rows.append(r)
        return rows
    return []


def load_icon_map(path, required=False):
    """Read icon-map.json -> {concept: {"status", "to", "svg"}}. Every inline
    `svg` payload gets the SAME load-time element validation assets/icons.json
    gets (only <path>/<circle>/<rect>/<line>/<polyline>); a payload with any
    other tag is dropped with a WARN rather than trusted, because this file is
    generated from a third-party design system, not skill-owned."""
    p = Path(path)
    if not p.exists():
        if required:
            print(f"WARN: --icon-map {p} does not exist; the design-system icon bridge is disabled",
                  file=sys.stderr)
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"WARN: {p} failed to parse ({e}); the design-system icon bridge is disabled",
              file=sys.stderr)
        return {}
    clean = {}
    for row in _icon_map_rows(raw):
        if not isinstance(row, dict):
            print(f"WARN: {p} carries a non-object row; dropped", file=sys.stderr)
            continue
        concept = row.get("concept")
        if not isinstance(concept, str) or not concept:
            print(f"WARN: {p} carries a row with no 'concept' name; dropped", file=sys.stderr)
            continue
        status = row.get("status")
        if status not in _ICON_MAP_STATUSES:
            print(f"WARN: {p} row '{concept}' has unknown status {status!r}; dropped",
                  file=sys.stderr)
            continue
        to = row.get("to")
        entry = {"status": status, "to": to if isinstance(to, str) else "", "svg": ""}
        markup = row.get("svg")
        if status == "mapped" and isinstance(markup, str) and markup.strip():
            tags = {t.lower() for t in _ICON_TAG_RE.findall(markup)}
            if not tags or not tags.issubset(_ICON_ALLOWED_TAGS):
                print(f"WARN: {p} row '{concept}' carries disallowed markup {sorted(tags)}; "
                      f"its svg payload is dropped", file=sys.stderr)
            else:
                entry["svg"] = markup
        clean[concept] = entry
    return clean


def _icon_wrap(markup):
    """The one <svg> shell every icon source renders into. The markup inside is
    trusted only AFTER the load-time element check (load_icons/load_icon_map),
    so it is not re-escaped here -- escaping path data would break every icon."""
    return ('<svg class="ls-icon" viewBox="0 0 24 24" aria-hidden="true" fill="none" '
            'stroke="currentColor" stroke-width="1.75" stroke-linecap="round" '
            'stroke-linejoin="round">%s</svg>') % markup


def icon_svg(name, icons, icon_map=None):
    """Documented precedence (spec 5.6):
      1. icon-map.json  -- the ingested design system's own concept mapping
      2. assets/icons.json -- landing-studio's own 16 generic names
      3. the escaped literal string -- back-compat with v8 emoji/text icons
    A concept the map marks `unmapped-declared-absent` renders the escaped
    literal AND prints a WARN naming it as declared absent -- deliberately a
    DIFFERENT message from an unknown name (which stays silent, v9 behaviour),
    because "the design system says it cannot draw this" and "you typed
    something wrong" are different problems with different fixes."""
    if not name:
        return ""
    row = (icon_map or {}).get(name)
    if isinstance(row, dict):
        if row.get("status") == "unmapped-declared-absent":
            print("WARN: icon '%s' is declared absent by the design system" % name, file=sys.stderr)
            return esc(name)
        if row.get("svg"):
            return _icon_wrap(row["svg"])
        to = row.get("to") or ""
        if to.startswith("ls:"):
            target = to[3:]
            if icons.get(target) is not None:
                return _icon_wrap(icons[target])
            print("WARN: icon-map.json maps '%s' to '%s', which assets/icons.json does not "
                  "carry; falling through to the next lookup" % (name, to), file=sys.stderr)
        elif to:
            print("WARN: icon-map.json row '%s' names '%s' but carries no svg payload; "
                  "falling through to the next lookup" % (name, to), file=sys.stderr)
    markup = icons.get(name)
    if markup is None:
        return esc(name)
    return _icon_wrap(markup)


# ---------- section 6.1: hero visual slot ----------

def hero_frame_svg(alt):
    """Inline token-coloured SVG 'product frame' -- a window chrome bar plus
    abstract content blocks. Self-contained (Invariant 1): no external image."""
    return (
        '<svg viewBox="0 0 480 360" role="img" aria-label="%s" focusable="false">'
        '<rect x="1" y="1" width="478" height="358" rx="14" fill="var(--ls-color-surface)" '
        'stroke="var(--ls-color-border)" stroke-width="2"/>'
        '<rect x="1" y="1" width="478" height="40" rx="14" fill="var(--ls-color-surface-muted)"/>'
        '<circle cx="24" cy="21" r="6" fill="var(--ls-color-border)"/>'
        '<circle cx="44" cy="21" r="6" fill="var(--ls-color-border)"/>'
        '<circle cx="64" cy="21" r="6" fill="var(--ls-color-border)"/>'
        '<rect x="24" y="64" width="220" height="18" rx="4" fill="var(--ls-color-primary)"/>'
        '<rect x="24" y="96" width="320" height="12" rx="4" fill="var(--ls-color-text-muted)"/>'
        '<rect x="24" y="118" width="280" height="12" rx="4" fill="var(--ls-color-text-muted)"/>'
        '<rect x="24" y="152" width="140" height="90" rx="10" fill="var(--ls-color-surface-muted)" '
        'stroke="var(--ls-color-border)"/>'
        '<rect x="180" y="152" width="140" height="90" rx="10" fill="var(--ls-color-surface-muted)" '
        'stroke="var(--ls-color-border)"/>'
        '<rect x="336" y="152" width="120" height="90" rx="10" fill="var(--ls-color-primary)" opacity="0.15"/>'
        '<rect x="24" y="260" width="432" height="70" rx="10" fill="var(--ls-color-surface-muted)" '
        'stroke="var(--ls-color-border)"/>'
        '</svg>'
    ) % esc(alt)


# Static sun/moon inline SVG for the theme toggle (section 6.4). No dynamic
# content -- CSS (owned by the design lane) shows/hides the two icons based
# on the current [data-ls-theme] state.
THEME_TOGGLE_ICON = (
    '<svg class="ls-theme__icon ls-theme__icon--sun" viewBox="0 0 24 24" aria-hidden="true" fill="none" '
    'stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">'
    '<circle cx="12" cy="12" r="4"/>'
    '<path d="M12 2v3M12 19v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M2 12h3M19 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1"/>'
    '</svg>'
    '<svg class="ls-theme__icon ls-theme__icon--moon" viewBox="0 0 24 24" aria-hidden="true" fill="none" '
    'stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M20 14.5a8.5 8.5 0 1 1-9.5-9.4 7 7 0 0 0 9.5 9.4z"/>'
    '</svg>'
)


class Content:
    """Lookup with graceful fallback to the default-locale content.

    Every string value read out of the raw content JSON (t{} and meta{},
    including inside list values) is passed through the section-2 migration
    shield exactly once, at load time -- `get()`/`meta_get()` never see a
    `[review:xx]` marker. `strip_count` totals how many were removed, for the
    stderr WARN in main(). The renderer never reads `_review`."""

    def __init__(self, content, fallback):
        self.strip_count = 0
        self.t = self._clean(content.get("t", {}))
        self.meta = self._clean(content.get("meta", {}))
        fb = fallback or {}
        self.fb = self._clean(fb.get("t", {}))
        self.fb_meta = self._clean(fb.get("meta", {}))
        self.icons = {}      # populated by main() via load_icons()
        self.icon_map = {}   # populated by main() via load_icon_map() (spec 5.6)
        self.locale = ""     # populated by main(); named in disclosure WARNs (spec 4.2)

    def _clean(self, node):
        if isinstance(node, str):
            new, n = REVIEW_RE.subn("", node)
            self.strip_count += n
            return new
        if isinstance(node, list):
            return [self._clean(x) for x in node]
        if isinstance(node, dict):
            return {k: self._clean(v) for k, v in node.items()}
        return node

    def get(self, key, default=""):
        if key in self.t and self.t[key] not in (None, ""):
            return self.t[key]
        if key in self.fb and self.fb[key] not in (None, ""):
            return self.fb[key]
        return default

    def meta_get(self, key, default=""):
        """meta.title / meta.description go through the same default-locale
        fallback as t{} keys (finding C16)."""
        if key in self.meta and self.meta[key] not in (None, ""):
            return self.meta[key]
        if key in self.fb_meta and self.fb_meta[key] not in (None, ""):
            return self.fb_meta[key]
        return default

    def has(self, key):
        return key in self.t or key in self.fb


def align_modifier(sec):
    align = sec.get("align", "center")
    if align not in ("center", "start"):
        align = "center"
    return align


# ---------- section 8.2: spacing modifier (`.ls-section--tight` / `--flush`) ----------
# Same clamp-and-WARN discipline as align_modifier() above: an optional per-section
# `spacing` attribute in site.json, validated against the CSS-owned modifier set,
# unknown values fall back to "normal" (no modifier class) with a stderr WARN so the
# CSS agent's tight/flush rules are actually reachable instead of shipping dead
# (finding D8/D11 class of defect -- do not add a third instance).
def spacing_modifier(sec):
    spacing = sec.get("spacing", "normal")
    if spacing not in ("normal", "tight", "flush"):
        print("WARN: unknown spacing '%s' for section '%s'; falling back to 'normal'"
              % (spacing, sec.get("id", "?")), file=sys.stderr)
        spacing = "normal"
    return spacing


def section_classes(sec, *extra):
    """Build the full `ls-section ...` class list for a <section> element,
    applying the optional spacing modifier ahead of any type-specific classes."""
    parts = ["ls-section"]
    spacing = spacing_modifier(sec)
    if spacing != "normal":
        parts.append("ls-section--%s" % spacing)
    parts.extend(extra)
    return " ".join(parts)


# ---------- spec 2.3: the per-item anchor, the note slot, the fact meta ----------
# Every item of a claim-bearing section (`logos`, `testimonials`, `evidence`,
# `state`) is wrapped in <div class="ls-item" data-ls-item="{sec_id}.{n}">, with
# 1-based n matching site.json claims[n-1]. The wrapper is LOAD-BEARING, not
# cosmetic: claims-check.py scopes a use/mention exemption to one item through
# it, so a renderer that emits item markup without the anchor silently widens
# every exemption to the whole page. Never hand-write the attribute -- call
# item_open(), the single carrier of its shape.
#
# render-page.py deliberately holds NO list of which types are claim-bearing:
# each claim-bearing renderer emits its own wrapper, so there is no second copy
# of CLAIM_BEARING to drift from claims-check.py's (spec 13, cross-wave contract).


def claim_for(sec, n):
    """site.json claims[n-1] for 1-based item n, or None with a stderr WARN.

    The render is NOT the gate (spec 2.3): a missing declaration still renders,
    with the same clamp-and-WARN discipline align/spacing use, and Q-DECLARE is
    what refuses to ship it."""
    claims = sec.get("claims")
    entry = claims[n - 1] if isinstance(claims, list) and 1 <= n <= len(claims) else None
    if not isinstance(entry, dict):
        print("WARN: section '%s' item %d has no site.json claims[%d] entry; rendering it "
              "anyway -- the render is not the gate, Q-DECLARE is."
              % (sec.get("id", "?"), n, n - 1), file=sys.stderr)
        return None
    return entry


def item_open(sec, n, *extra):
    """Open tag for one claim-bearing item: `ls-item` plus any type-specific
    class, and the 1-based data-ls-item anchor. Both interpolations are escaped
    (findings C1/C10) -- the section id comes from site.json."""
    classes = " ".join(["ls-item"] + [x for x in extra if x])
    return '<div class="%s" data-ls-item="%s.%d">' % (esc(classes), esc(sec.get("id", "")), n)


def item_note(sec, c, n):
    """`{id}.item{n}.relationship_note` -> <p class="ls-item__note">, inside the
    item wrapper. Per-locale CONTENT (the human-readable sentence); the
    structural fact it describes lives in site.json claims[] so two locales
    cannot disagree about it (spec 2.2)."""
    note = c.get("%s.item%d.relationship_note" % (sec.get("id", ""), n))
    if not note:
        return ""
    return '<p class="ls-item__note">%s</p>' % esc(note)


def item_retraction(sec, c, n, claim):
    """`{id}.item{n}.retraction_text` -> `<p class="ls-retraction"
    data-ls-retracts="{row}">`, inside the item wrapper.

    A withdrawal is a structural fact, like every other assertion in this
    skill: `kind` is declared in `claims[]`, `date` and `grade` live in
    site.json, and neither is sniffed out of the copy. Retraction was the one
    assertion left as prose, and two rounds of narrowing a co-occurrence window
    (item scope, then sentence scope) failed to make prose-sniffing into
    detection -- ordinary compound copy exempted a claim nobody withdrew. So
    the withdrawal now gets a slot whose only purpose is to be a withdrawal,
    and the slot NAMES the register row it withdraws. `claims-check.py` asks
    whether that element exists for that row, not whether the sentence looks
    like a retraction.

    A declaration with no text renders nothing and prints a WARN: the render is
    not the gate (the sweep routes it to a reading record), but a silent
    omission here would look like a compliant page."""
    row = (claim or {}).get("retraction_of")
    if not row:
        return ""
    text = c.get("%s.item%d.retraction_text" % (sec.get("id", ""), n))
    if not text:
        print("WARN: %s.item%d declares retraction_of=%s but carries no "
              "%s.item%d.retraction_text; the sweep will require a reading record"
              % (sec.get("id", ""), n, row, sec.get("id", ""), n), file=sys.stderr)
        return ""
    return '<p class="ls-retraction" data-ls-retracts="%s">%s</p>' % (esc(row), esc(text))


def fact_meta(sec, n, claim):
    """`{date} \u00b7 {grade}` for an `evidence`/`state` item, read from site.json
    claims[n-1] and NEVER from a content file (spec 3.1): a date and a
    credibility grade are facts about the world, not translations."""
    parts = []
    if isinstance(claim, dict):
        for field in ("date", "grade"):
            v = claim.get(field)
            if v not in (None, ""):
                parts.append(str(v))
    if not parts:
        print("WARN: section '%s' item %d carries neither claims[%d].date nor .grade in "
              "site.json; no .ls-fact__meta is rendered -- Q-PROVENANCE is the gate."
              % (sec.get("id", "?"), n, n - 1), file=sys.stderr)
        return ""
    return '<span class="ls-fact__meta">%s</span>' % esc(" \u00b7 ".join(parts))


# ---------- spec 4.2: the agent-authorship disclosure chrome ----------

def first_footer_id(site):
    """Which footer section discharges the disclosure obligation when a site
    declares more than one. Q-DISCLOSE wants EXACTLY one .ls-disclosure per
    page, so the answer is the first footer in sections[] order -- computed from
    site.json, with no render-order state to get out of step."""
    for s in site.get("sections", []):
        if isinstance(s, dict) and s.get("type") == "footer":
            return s.get("id")
    return None


def disclosure_active(site):
    """Spec 4.1: active when authorship.agent_authored is true AND
    authorship.eu_residency is not "excluded"/"confirmed_non_eu" -- UNKNOWN
    carries the duty, mirroring RL-1's own rule that residency is a profile
    field. An absent authorship block leaves it inactive, so no v9 project
    turns red. Returns (active, reason) and the reason is always printable."""
    auth = site.get("authorship")
    if not isinstance(auth, dict):
        return False, "authorship absent"
    if not auth.get("agent_authored"):
        return False, "agent_authored=false"
    residency = auth.get("eu_residency", "unknown")
    if residency in ("excluded", "confirmed_non_eu"):
        return False, "eu_residency=%s" % residency
    return True, ""


def disclosure_html(site, c):
    """<p class="ls-disclosure">{disclosure.text}</p>, or "" when the obligation
    is inactive.

    Unlike every other chrome element in v9 -- header CTA, theme toggle, tagline,
    each of which disappears quietly when its key is absent -- this one is
    MANDATORY when active and never silently omitted: an obligation whose
    absence is silent is the shape of the defect, not its fix. So a missing
    `disclosure.text` prints a loud WARN naming the locale, and Q-DISCLOSE
    (BLOCKER while the obligation is active) is what refuses the page."""
    active, _reason = disclosure_active(site)
    if not active:
        return ""
    text = c.get("disclosure.text")
    if not text:
        print("WARN: the agent-authorship disclosure obligation is ACTIVE for this site "
              "(authorship.agent_authored=true, eu_residency=%s) but content key "
              "'disclosure.text' is MISSING for locale '%s' -- the page ships with no "
              "disclosure and Q-DISCLOSE (BLOCKER) will refuse it. This element is "
              "mandatory when active and is never silently omitted."
              % (site.get("authorship", {}).get("eu_residency", "unknown"), c.locale or "?"),
              file=sys.stderr)
        return ""
    return '<p class="ls-disclosure">%s</p>' % esc(text)


# ---------- section renderers -- uniform signature r_x(sec, c, site) (finding D9) ----------

def r_hero(sec, c, site):
    sid = sec["id"]
    align = align_modifier(sec)
    inner = ['<div class="ls-hero__inner">']
    eyebrow = c.get(f"{sid}.eyebrow")
    if eyebrow:
        inner.append('<p class="ls-eyebrow">%s</p>' % esc(eyebrow))
    inner.append('<h1 class="ls-h1">%s</h1>' % esc(c.get(f"{sid}.headline")))
    sub = c.get(f"{sid}.subhead")
    if sub:
        inner.append('<p class="ls-lead">%s</p>' % esc(sub))
    cta = c.get(f"{sid}.cta")
    cta2 = c.get(f"{sid}.cta_secondary")
    if cta or cta2:
        href = safe_href(sec.get("cta_href", "#cta"), "#cta", context=f"{sid}.cta_href")
        # The secondary action gets its own target. Until the v10 completion
        # pass both buttons rendered against `cta_href`, so a documented key
        # (`cta_secondary` copy) could not point anywhere else -- a second CTA
        # that cannot lead somewhere else is not a second CTA. `cta_secondary_href`
        # is optional and falls back to `cta_href`, so every existing project
        # renders byte-identically.
        href2 = safe_href(sec.get("cta_secondary_href", href), href,
                          context=f"{sid}.cta_secondary_href")
        inner.append('<div class="ls-cluster ls-hero__actions">')
        if cta:
            inner.append('<a class="ls-btn ls-btn--primary" href="%s">%s</a>' % (esc(href), esc(cta)))
        if cta2:
            inner.append('<a class="ls-btn ls-btn--ghost" href="%s">%s</a>' % (esc(href2), esc(cta2)))
        inner.append('</div>')
    note = c.get(f"{sid}.note")
    if note:
        inner.append('<p class="ls-muted ls-hero__note">%s</p>' % esc(note))
    inner.append('</div>')

    visual_cfg = sec.get("visual")
    if not isinstance(visual_cfg, dict):
        visual_cfg = {"kind": "frame"}
    kind = visual_cfg.get("kind", "frame")
    visual_block = ""
    if kind != "none":
        alt = c.get(f"{sid}.visual_alt", "Product preview")
        src = visual_cfg.get("src", "")
        if src:
            if isinstance(src, str) and src.startswith("data:"):
                body = '<img class="ls-hero__img" src="%s" alt="%s">' % (esc(src), esc(alt))
            else:
                print("WARN: hero visual src for section '%s' is not a data: URI; "
                      "falling back to the product frame (Invariant 1: self-contained)" % sid, file=sys.stderr)
                body = hero_frame_svg(alt)
        else:
            body = hero_frame_svg(alt)
        visual_block = '<div class="ls-hero__visual">%s</div>' % body

    cls = section_classes(sec, "ls-hero", "ls-hero--%s" % align)
    return ('<section class="%s" id="%s"><div class="ls-container">%s%s</div></section>'
            % (esc(cls), esc(sid), "".join(inner), visual_block))


def r_features(sec, c, site):
    sid = sec["id"]
    n = int(sec.get("items", 3))
    align = align_modifier(sec)
    head = ['<section class="%s" id="%s"><div class="ls-container">' % (esc(section_classes(sec, "ls-features")), esc(sid)),
            '<div class="ls-section__head ls-section__head--%s">' % esc(align),
            '<h2 class="ls-h2">%s</h2>' % esc(c.get(f"{sid}.title"))]
    subtitle = c.get(f"{sid}.subtitle")
    if subtitle:
        head.append('<p class="ls-lead">%s</p>' % esc(subtitle))
    head.append("</div>")
    cards = ['<div class="ls-grid ls-features__grid">']
    for i in range(1, n + 1):
        icon = c.get(f"{sid}.item{i}.icon", "")
        cards.append('<div class="ls-card">')
        if icon:
            cards.append('<div class="ls-card__icon" aria-hidden="true">%s</div>'
                         % icon_svg(icon, c.icons, c.icon_map))
        cards.append('<h3 class="ls-h3">%s</h3>' % esc(c.get(f"{sid}.item{i}.title")))
        cards.append('<div class="ls-card__body ls-muted">%s</div>' % esc(c.get(f"{sid}.item{i}.body")))
        cards.append("</div>")
    cards.append("</div></div></section>")
    return "\n".join(head + cards)


def r_pricing(sec, c, site):
    sid = sec["id"]
    n = int(sec.get("tiers", 3))
    featured = sec.get("featured")  # 1-based tier index, optional
    align = align_modifier(sec)
    head = ['<section class="%s" id="%s"><div class="ls-container">' % (esc(section_classes(sec, "ls-pricing")), esc(sid)),
            '<div class="ls-section__head ls-section__head--%s"><h2 class="ls-h2">%s</h2>'
            % (esc(align), esc(c.get(f"{sid}.title")))]
    subtitle = c.get(f"{sid}.subtitle")
    if subtitle:
        head.append('<p class="ls-lead">%s</p>' % esc(subtitle))
    head.append("</div>")
    grid = ['<div class="ls-grid ls-pricing__grid">']
    href = safe_href(sec.get("cta_href", "#cta"), "#cta", context=f"{sid}.cta_href")
    for i in range(1, n + 1):
        is_feat = (featured == i)
        cls = "ls-card ls-price ls-price--featured" if is_feat else "ls-card ls-price"
        grid.append('<div class="%s">' % cls)
        if is_feat:
            # finding D6: the only key is {sec.id}.badge -- no "pricing.badge" fallback.
            badge = c.get(f"{sid}.badge", "")
            if badge:
                grid.append('<span class="ls-badge">%s</span>' % esc(badge))
        grid.append('<h3 class="ls-h3">%s</h3>' % esc(c.get(f"{sid}.tier{i}.name")))
        grid.append('<div class="ls-price__amount">%s</div>' % esc(c.get(f"{sid}.tier{i}.price")))
        period = c.get(f"{sid}.tier{i}.period")
        if period:
            grid.append('<p class="ls-muted">%s</p>' % esc(period))
        feats = c.get(f"{sid}.tier{i}.features", [])
        if isinstance(feats, list) and feats:
            grid.append('<ul class="ls-price__features">')
            for f in feats:
                grid.append("<li>%s</li>" % esc(f))
            grid.append("</ul>")
        cta = c.get(f"{sid}.tier{i}.cta", c.get(f"{sid}.cta"))
        btn = "ls-btn ls-btn--primary ls-btn--block" if is_feat else "ls-btn ls-btn--ghost ls-btn--block"
        grid.append('<a class="%s" href="%s">%s</a>' % (btn, esc(href), esc(cta)))
        grid.append("</div>")
    grid.append("</div></div></section>")
    return "\n".join(head + grid)


def r_faq(sec, c, site):
    sid = sec["id"]
    n = int(sec.get("items", 4))
    align = align_modifier(sec)
    out = ['<section class="%s" id="%s"><div class="ls-container ls-faq__inner">' % (esc(section_classes(sec, "ls-faq-sec")), esc(sid)),
           '<div class="ls-section__head ls-section__head--%s"><h2 class="ls-h2">%s</h2></div>'
           % (esc(align), esc(c.get(f"{sid}.title"))),
           '<div class="ls-faq">']
    for i in range(1, n + 1):
        out.append("<details><summary>%s</summary><p>%s</p></details>" % (
            esc(c.get(f"{sid}.item{i}.q")), esc(c.get(f"{sid}.item{i}.a"))))
    out.append("</div></div></section>")
    return "\n".join(out)


def r_cta(sec, c, site):
    sid = sec["id"]
    align = align_modifier(sec)
    out = ['<section class="%s" id="%s"><div class="ls-container">' % (esc(section_classes(sec)), esc(sid)),
           '<div class="ls-cta"><div class="ls-cta__inner">',
           '<div class="ls-section__head ls-section__head--%s">' % esc(align)]
    eyebrow = c.get(f"{sid}.eyebrow")
    if eyebrow:
        out.append('<p class="ls-eyebrow">%s</p>' % esc(eyebrow))
    out.append('<h2 class="ls-h2">%s</h2>' % esc(c.get(f"{sid}.headline")))
    sub = c.get(f"{sid}.subhead")
    if sub:
        out.append('<p class="ls-lead">%s</p>' % esc(sub))
    out.append('</div>')
    button = c.get(f"{sid}.button")
    if button:
        href = safe_href(sec.get("cta_href", "#"), "#", context=f"{sid}.cta_href")
        out.append('<div class="ls-cluster ls-cta__actions">'
                   '<a class="ls-btn ls-btn--primary" href="%s">%s</a></div>' % (esc(href), esc(button)))
    out.append("</div></div></div></section>")
    return "\n".join(out)


def r_logos(sec, c, site):
    sid = sec["id"]
    n = int(sec.get("items", 6))
    out = ['<section class="%s" id="%s"><div class="ls-container">' % (esc(section_classes(sec, "ls-logos")), esc(sid))]
    title = c.get(f"{sid}.title")
    if title:
        out.append('<p class="ls-eyebrow ls-logos__title">%s</p>' % esc(title))
    out.append('<div class="ls-logos__grid">')
    for i in range(1, n + 1):
        name = c.get(f"{sid}.item{i}.name")
        if not name:
            continue
        # spec 2.3: a claim-bearing item -- declaration is checked, anchor is emitted.
        claim_for(sec, i)
        icon = c.get(f"{sid}.item{i}.icon", "")
        mark = icon_svg(icon, c.icons, c.icon_map) if icon else esc(name[:1])
        out.append(item_open(sec, i))
        out.append('<div class="ls-logo"><span class="ls-logo__mark">%s</span>'
                   '<span class="ls-logo__name">%s</span></div>' % (mark, esc(name)))
        note = item_note(sec, c, i)
        if note:
            out.append(note)
        retraction = item_retraction(sec, c, i, claim_for(sec, i))
        if retraction:
            out.append(retraction)
        out.append('</div>')
    out.append('</div></div></section>')
    return "\n".join(out)


def r_testimonials(sec, c, site):
    sid = sec["id"]
    n = int(sec.get("items", 3))
    out = ['<section class="%s" id="%s"><div class="ls-container">' % (esc(section_classes(sec, "ls-testimonials")), esc(sid))]
    title = c.get(f"{sid}.title")
    subtitle = c.get(f"{sid}.subtitle")
    if title or subtitle:
        out.append('<div class="ls-section__head ls-section__head--center">')
        if title:
            out.append('<h2 class="ls-h2">%s</h2>' % esc(title))
        if subtitle:
            out.append('<p class="ls-lead">%s</p>' % esc(subtitle))
        out.append('</div>')
    out.append('<div class="ls-grid ls-testimonials__grid">')
    for i in range(1, n + 1):
        quote = c.get(f"{sid}.item{i}.quote")
        name = c.get(f"{sid}.item{i}.name")
        if not quote or not name:
            continue
        role = c.get(f"{sid}.item{i}.role", "")
        avatar = esc(first_grapheme(name))
        # spec 2.3: a claim-bearing item -- declaration is checked, anchor is emitted.
        claim_for(sec, i)
        out.append(item_open(sec, i))
        out.append('<figure class="ls-quote">'
                   '<blockquote class="ls-quote__body">%s</blockquote>'
                   '<figcaption class="ls-quote__author">'
                   '<span class="ls-quote__avatar" aria-hidden="true">%s</span>'
                   '<span class="ls-quote__name">%s</span>' % (esc(quote), avatar, esc(name)))
        if role:
            out.append('<span class="ls-quote__role">%s</span>' % esc(role))
        out.append('</figcaption></figure>')
        note = item_note(sec, c, i)
        if note:
            out.append(note)
        retraction = item_retraction(sec, c, i, claim_for(sec, i))
        if retraction:
            out.append(retraction)
        out.append('</div>')
    out.append('</div></div></section>')
    return "\n".join(out)


def _r_fact_band(sec, c, site, kind):
    """Shared body for `evidence` and `state` (spec 3.1). The two types are
    IDENTICAL but for the two container classes -- one implementation, not two
    copies drifting apart. `evidence` is what is true and dated; `state` is the
    "what is not true yet" band: open defect count, zero-customer line, the red
    risk. Both are claim-bearing, so every item carries the data-ls-item anchor
    and its date/grade meta."""
    sid = sec["id"]
    n = int(sec.get("items", 0))
    align = align_modifier(sec)
    out = ['<section class="%s" id="%s"><div class="ls-container">'
           % (esc(section_classes(sec, "ls-%s" % kind)), esc(sid))]
    title = c.get(f"{sid}.title")
    subtitle = c.get(f"{sid}.subtitle")
    if title or subtitle:
        out.append('<div class="ls-section__head ls-section__head--%s">' % esc(align))
        if title:
            out.append('<h2 class="ls-h2">%s</h2>' % esc(title))
        if subtitle:
            out.append('<p class="ls-lead">%s</p>' % esc(subtitle))
        out.append('</div>')
    out.append('<div class="ls-grid ls-%s__grid">' % kind)
    for i in range(1, n + 1):
        claim = claim_for(sec, i)
        out.append(item_open(sec, i, "ls-fact"))
        out.append('<span class="ls-fact__value">%s</span>' % esc(c.get(f"{sid}.item{i}.value")))
        out.append('<span class="ls-fact__label">%s</span>' % esc(c.get(f"{sid}.item{i}.label")))
        meta = fact_meta(sec, i, claim)
        if meta:
            out.append(meta)
        note = item_note(sec, c, i)
        if note:
            out.append(note)
        retraction = item_retraction(sec, c, i, claim_for(sec, i))
        if retraction:
            out.append(retraction)
        out.append('</div>')
    out.append('</div></div></section>')
    return "\n".join(out)


def r_evidence(sec, c, site):
    return _r_fact_band(sec, c, site, "evidence")


def r_state(sec, c, site):
    return _r_fact_band(sec, c, site, "state")


def r_footer(sec, c, site):
    sid = sec["id"]
    out = ['<footer class="ls-footer" id="%s"><div class="ls-container"><div class="ls-footer__bar">' % esc(sid),
           '<div class="ls-footer__brand">']
    out.append('<span>%s</span>' % esc(c.get(f"{sid}.copyright", site.get("brand", {}).get("name", ""))))
    tagline = c.get(f"{sid}.tagline", "")
    if tagline:
        out.append('<span class="ls-footer__tagline ls-muted">%s</span>' % esc(tagline))
    out.append('</div>')
    # spec 4.2: the disclosure renders in the footer BEFORE link{n}. Only the
    # first footer section carries it, so a site declaring two footers still
    # emits exactly one .ls-disclosure per page, which is what Q-DISCLOSE wants.
    if sid == first_footer_id(site):
        disclosure = disclosure_html(site, c)
        if disclosure:
            out.append(disclosure)
    links = []
    for i in range(1, 9):  # extended from 5 to 8 slots
        label = c.get(f"{sid}.link{i}.label")
        if not label:
            continue
        href = safe_href(c.get(f"{sid}.link{i}.href", "#"), "#", context=f"{sid}.link{i}.href")
        links.append('<a href="%s">%s</a>' % (esc(href), esc(label)))
    if links:
        out.append('<nav class="ls-cluster" aria-label="Footer">%s</nav>' % "".join(links))
    out.append("</div></div></footer>")
    return "\n".join(out)


def r_prose(sec, c, site):
    sid = sec["id"]
    return ('<section class="%s" id="%s"><div class="ls-container ls-container--narrow ls-stack">'
            '<h2 class="ls-h2">%s</h2><p class="ls-muted">%s</p></div></section>') % (
        esc(section_classes(sec)), esc(sid), esc(c.get(f"{sid}.title")), esc(c.get(f"{sid}.body")))


# ---------- v2: the company home (row 28) ----------
# Four blocks and a footer, in the owner's order: AIVIS + the founder + the
# company; why SANKORD; the four courses; popular questions. Markup mirrors the
# design system's catalogue through data-component / data-variant / data-size
# attributes (conventions.md section 3). No inline style attribute is emitted
# anywhere: the page's CSP admits the two inline blocks by hash and nothing else.

NB = "‑"  # non-breaking hyphen marker in content; rendered as a nowrap span (DS R1-10)
_NBW = re.compile(r"[^\s‑]*‑[^\s‑]*(?:‑[^\s‑]*)*")
USED_ICONS = set()
# every page carries the same sprite subset (the C1 parity of ids between the locales and between the pages):
# the icons of the header, the footer and every page body of the site
COMMON_ICONS = ("arrow-right", "arrow-up-right", "bot", "check", "chevron-down", "info", "lock", "log-in", "menu",
                "moon", "rocket", "shield-check", "sparkles", "sun", "target", "x", "zap",
                "soc-telegram", "soc-mail", "soc-linkedin", "soc-x", "soc-medium")
CUR_LOCALE = [""]
FOOTER_TYPES = ("footer", "home_footer")


def T(s):
    """Escape, then keep compound terms (AI-agents, i-Vision) on one line; no-break space before a spaced dash,
    after a 1-3 letter word in Russian (prepositions, conjunctions) and between the last two words of a text of three or more."""
    s = re.sub("[ \u00a0]([\u2014\u2013]) ", "\u00a0\\1 ", s)
    if CUR_LOCALE[0] == "ru":
        s = re.sub(r"(?<![\w-])([^\W\d_]{1,2}|без|для|при|над|под|про|или|что|как|еще) (?=\S)", "\\1\u00a0", s)
    m = re.search(r"(\S+) (\S+)$", s)
    if m and len(s.split()) >= 3 and len(m.group(0)) <= 16:   # a short last pair only: a long chain would overflow a narrow column
        s = s[:m.start()] + m.group(1) + " " + m.group(2)
    return _NBW.sub(lambda m: '<span class="nw">%s</span>' % m.group(0).replace(NB, "-"), esc(s))


PAGE_PARTS = []   # directory parts of the page under its locale root: [] home, ["about"], ["about", "privacy"]


def lroot():
    """Relative path from this page's directory to its locale's root ('' for the locale home)."""
    return "../" * len(PAGE_PARTS)


def prefix_for(site, locale):
    """Relative path from this page's document to the site root."""
    return ("" if locale == site["default_locale"] else "../") + lroot()


# scr-counter-roll: the figure of a founder fact that is already in the text (20, 10 000) is wrapped in a span the
# motion script rolls; the text itself is unchanged. 2023 (a year) and the dates are never wrapped.
ROLL_FIGURES = {
    "founder.fact2": re.compile(r"\d+(?=\+?[  ])"),
    "founder.fact3": re.compile(r"\d{1,3}(?:[,\u00a0\u202f ]\d{3})+"),
}


def roll_figure(key, html):
    rx = ROLL_FIGURES.get(key)
    if not rx:
        return html
    return rx.sub(lambda m: '<span class="ls-mo-counter">%s</span>' % m.group(0), html, count=1)


def home_href():
    return lroot() or "./"


def ic(name, cls="icon", extra=""):
    USED_ICONS.add(name)
    return ('<svg class="%s"%s aria-hidden="true" focusable="false"><use href="#i-%s"/></svg>'
            % (esc(cls), extra, esc(name)))


def photo(site, c, alt):
    """The founder photograph: WebP and JPEG at 160 and 320 px, picked by srcset for the 104-144 px box."""
    p = prefix_for(site, c.locale) + "assets/img/aivis-one-founder-"
    sizes = "(min-width: 640px) 144px, 104px"
    return ('<picture><source type="image/webp" srcset="%s160.webp 160w, %s320.webp 320w" sizes="%s">'
            '<img src="%s320.jpg" srcset="%s160.jpg 160w, %s320.jpg 320w" sizes="%s" alt="%s" class="person__photo" '
            'width="144" height="144" decoding="async"></picture>' % (p, p, sizes, p, p, p, sizes, esc(alt)))


def img(site, c, name, alt="", cls="", w=None, h=None):
    p = prefix_for(site, c.locale)
    attrs = ' class="%s"' % esc(cls) if cls else ""
    if w and h:
        attrs += ' width="%d" height="%d"' % (w, h)
    return '<img src="%sassets/img/%s" alt="%s"%s>' % (p, esc(name), esc(alt), attrs)


def btn(label, href, variant="primary", size="lg", icon="arrow-right", external=False):
    rel = ' rel="noopener"' if external else ""
    href = safe_href(href, "#", context="button")
    icon_html = ic(icon, "icon icon--dir") if icon else ""
    return ('<a class="btn ls-mo-press ls-mo-lift" data-component="Button" data-variant="%s" data-size="%s" href="%s"%s>'
            '<span>%s</span>%s</a>' % (esc(variant), esc(size), esc(href), rel, T(label), icon_html))


def r_home_aivis(sec, c, site):
    """Block 1. Two cards on ONE mirrored scheme (his answer of 2026-10-02): label, big name, subtitle, list, button;
    the founder's photo and the colour AIVIS mark sit in the top-right corner at the same size (the mark here is his
    explicit exception to 'mark in the header only'); equal-height cards, buttons on one line at the bottom."""
    sid = sec["id"]
    g = lambda k: c.get("%s.%s" % (sid, k))
    facts = lambda keys: "".join('<li>%s<span>%s</span></li>' % (ic("check"), roll_figure(k, T(g(k)))) for k in keys)

    def card(cls, variant, label, name, sub, img_html, fact_keys, button):
        return ('<article class="card whocard %s" data-component="Card" data-variant="%s" data-size="lg">'
                '<div class="whocard__top"><div class="whocard__head"><p class="label">%s</p><p class="whocard__name">%s</p>'
                '<p class="whocard__sub">%s</p></div><div class="whocard__img">%s</div></div>'
                '<ul class="facts">%s</ul><div class="actions">%s</div></article>'
                % (cls, variant, T(label), T(name), T(sub), img_html, facts(fact_keys), button))

    base = sec.get("cta_href", "about/")
    return "\n".join([
        '<section class="block hero" id="%s" aria-labelledby="%s-h"><div class="wrap">' % (esc(sid), esc(sid)),
        '<p class="kicker">%s</p>' % T(g("kicker")),
        '<h1 id="%s-h" class="ls-mo-balance"><span class="h-main">%s</span> <span class="h-sub">%s</span></h1>'
        % (esc(sid), T(g("headline")), T(g("subtitle"))),
        '<p class="lead">%s</p>' % T(g("lead")),
        '<div class="who">',
        card("founder-card", "elevated", g("founder.label"), g("founder.name"), g("founder.sub"),
             photo(site, c, g("founder.photo_alt")), ["founder.fact1", "founder.fact2", "founder.fact3"],
             btn(g("founder.button"), base + "#founder")),
        card("company", "outlined", g("company.label"), g("company.name"), g("company.sub"),
             img(site, c, "aivis-mark.svg", "", "whocard__mark", 112, 112), ["company.fact1", "company.fact2"],
             btn(g("button"), base + "#company")),
        '</div></div></section>',
    ])


def r_home_sankord(sec, c, site):
    sid = sec["id"]
    g = lambda k: c.get("%s.%s" % (sid, k))
    hrefs = sec.get("cta_hrefs", {})
    href = hrefs.get(c.locale, hrefs.get(site["default_locale"], "https://sankord.com"))
    def tile(i, k):
        # ONE paragraph per card, same style in all three: a card with a second approved line (key + "b")
        # joins the two verbatim lines with a full stop (his word 2026-10-02, home v5).
        text = g(k)
        if g(k + "b"):
            text = text.rstrip(" .") + ". " + g(k + "b")
        return ('<li><span class="ic">%s</span><span class="tile__t"><span>%s</span></span></li>'
                % (ic(i), T(text)))
    tiles = "".join(tile(i, k) for i, k in (("shield-check", "fact1"), ("lock", "fact2"), ("zap", "fact3")))
    return "\n".join([
        '<section class="block sankord" id="%s" aria-labelledby="%s-h"><div class="wrap">' % (esc(sid), esc(sid)),
        '<header class="section-head"><h2 id="%s-h" class="ls-mo-balance">%s</h2><p class="lead">%s</p></header>'
        % (esc(sid), T(g("title")), T(g("story"))),
        '<div class="card statement" data-component="Card" data-variant="elevated" data-size="lg">',
        '<p class="statement__name">%s</p><h3 class="statement__promise ls-mo-balance">%s</h3><p class="statement__cat">%s</p></div>'
        % (T(g("name")), T(g("promise")), T(g("category"))),
        '<div class="for"><p class="label">%s</p><p class="for__lead">%s</p><p>%s</p></div>'
        % (T(g("for.label")), T(g("for.lead")), T(g("for.who"))),
        '<ul class="tiles">%s</ul>' % tiles,
        '<div class="alert stage" role="status" data-component="Alert" data-severity="info" data-variant="persistent">%s'
        '<p>%s %s</p></div>'
        % (ic("info"), T(g("stage")), T(g("stage.more"))),
        '<div class="actions">%s</div>'
        % btn(g("button"), href, "primary", "lg", "arrow-up-right", True),
        '</div></section>',
    ])


COURSE_ICONS = ("target", "sparkles", "bot", "rocket")


def r_home_courses(sec, c, site):
    sid = sec["id"]
    n = int(sec.get("items", 4))
    g = lambda k: c.get("%s.%s" % (sid, k))
    items = []
    for i in range(1, n + 1):
        items.append('<li class="card course" data-component="Card" data-variant="elevated" data-size="md">'
                     '<div class="course__top"><span class="num" aria-hidden="true">%02d</span>'
                     '<span class="course__ic" aria-hidden="true">%s</span></div>'
                     '<h3><span class="course__main">%s</span> <span class="course__sub">%s</span></h3><p>%s</p></li>'
                     % (i, ic(COURSE_ICONS[(i - 1) % len(COURSE_ICONS)]), T(g("item%d.title" % i)),
                        T(g("item%d.sub" % i)), T(g("item%d.body" % i))))
    return "\n".join([
        '<section class="block courses-sec" id="%s" aria-labelledby="%s-h">' % (esc(sid), esc(sid)),
        '<div class="wrap"><header class="section-head"><p class="kicker">%s</p>' % T(g("kicker")),
        '<h2 id="%s-h" class="ls-mo-balance">%s</h2><p class="lead">%s</p></header>' % (esc(sid), T(g("title")), T(g("lead"))),
        '<ol class="course-list ls-mo-stagger">%s</ol>' % "".join(items),
        '<div class="actions actions--call">%s<p class="call-note">%s</p></div>'
        % (btn(g("button"), sec.get("cta_href", "courses/")), T(g("note"))),
        '</div></section>',
    ])


def r_home_faq(sec, c, site):
    sid = sec["id"]
    n = int(sec.get("items", 4))
    g = lambda k: c.get("%s.%s" % (sid, k))
    items = []
    for i in range(1, n + 1):
        paras = "".join("<p>%s</p>" % T(c.get("%s.a%d%s" % (sid, i, s))) for s in "abc"
                        if c.get("%s.a%d%s" % (sid, i, s)))
        items.append('<details data-component="Accordion" data-orientation="vertical"><summary><span>%s</span>%s</summary>'
                     '<div class="ls-mo-accordion"><div class="ans">%s</div></div></details>'
                     % (T(g("q%d" % i)), ic("chevron-down", "icon chev"), paras))
    return "\n".join([
        '<section class="block questions" id="%s" aria-labelledby="%s-h"><div class="wrap">' % (esc(sid), esc(sid)),
        '<header class="section-head"><h2 id="%s-h" class="ls-mo-balance">%s</h2></header>' % (esc(sid), T(g("title"))),
        '<div class="faq">%s</div>' % "".join(items),
        '<div class="actions">%s</div>' % btn(g("button"), sec.get("cta_href", "faq/")),
        '</div></section>',
    ])


def r_faq_page(sec, c, site):
    """/faq/: the page heading, then one block per group (faq.g<n>.title), each an accordion of faq.g<n>.q<i>/a<i>,
    in the markup and styles of the home's questions block."""
    g = lambda k: c.get("faq." + k)
    out = ['<section class="block hero hero--page faq-intro" id="faq_intro"><div class="wrap">',
           '<h1 class="ls-mo-balance">%s</h1>' % T(g("h1")), '</div></section>']
    n = 1
    while g("g%d.title" % n):
        items = []
        i = 1
        while g("g%d.q%d" % (n, i)):
            ans = g("g%d.a%d" % (n, i))
            if not ans:   # an answer in parts (a<i>a, a<i>b, ...): each SANKORD part verbatim from statements.tsv
                parts = [g("g%d.a%d%s" % (n, i, s)) for s in "abcdef" if g("g%d.a%d%s" % (n, i, s))]
                ans = " ".join(x if x.rstrip()[-1:] in ".!?" else x + "." for x in parts)
            items.append('<details data-component="Accordion" data-orientation="vertical"><summary><span>%s</span>%s</summary>'
                         '<div class="ls-mo-accordion"><div class="ans"><p>%s</p></div></div></details>'
                         % (T(g("g%d.q%d" % (n, i))), ic("chevron-down", "icon chev"), rich(ans)))
            i += 1
        sid = "faq_g%d" % n
        out += ['<section class="block questions faq-group%s" id="%s" aria-labelledby="%s-h"><div class="wrap">'
                % (" alt" if n % 2 == 0 else "", sid, sid),
                '<header class="section-head"><h2 id="%s-h" class="ls-mo-balance">%s</h2></header>' % (sid, T(g("g%d.title" % n))),
                '<div class="faq">%s</div>' % "".join(items), '</div></section>']
        n += 1
    return "\n".join(out)


def r_courses_page(sec, c, site):
    """/courses/: the heading and the intro, then one card per course (title, 'course N . M slides', the two labelled
    lines, a button to the course page), then the closing line with its link to the licence page. The cards are the
    home's course cards (.card.course) with the text laid out in full; the course slugs come from site.json (`slugs`)."""
    g = lambda k: c.get("courses_page." + k)
    slugs = sec.get("slugs") or ["tasks", "skills", "agents", "projects"]
    items = []
    for i, slug in enumerate(slugs, 1):
        items.append(
            '<li class="card course course--full" data-component="Card" data-variant="elevated" data-size="md">'
            '<div class="course__top"><span class="num" aria-hidden="true">%02d</span>'
            '<span class="course__ic" aria-hidden="true">%s</span></div>'
            '<h3><span class="course__main">%s</span> <span class="course__sub">%s</span></h3>'
            '<p class="course__line"><span class="course__label">%s</span> %s</p>'
            '<p class="course__line"><span class="course__label">%s</span> %s</p>'
            '<div class="course__go">%s</div></li>'
            % (i, ic(COURSE_ICONS[(i - 1) % len(COURSE_ICONS)]), T(g("card%d.title" % i)), T(g("card%d.meta" % i)),
               T(g("learn.label")), T(g("card%d.learn" % i)), T(g("get.label")), T(g("card%d.get" % i)),
               btn(g("button"), page_href("courses/" + slug), "primary", "lg")))
    return "\n".join([
        '<section class="block hero hero--page courses-intro" id="courses_intro" aria-labelledby="courses_intro-h"><div class="wrap">',
        '<h1 id="courses_intro-h" class="ls-mo-balance">%s</h1>' % T(g("h1")),
        '<p class="lead">%s</p>' % T(g("lead")),
        '</div></section>',
        '<section class="block courses-sec courses-page" id="courses_list" aria-label="%s"><div class="wrap">' % esc(g("meta.title")),
        '<ol class="course-list ls-mo-stagger">%s</ol>' % "".join(items),
        '<p class="courses-page__below">%s</p>' % rich(g("below")),
        '</div></section>',
    ])


def lang_page_href(site, c, loc):
    """Link to the SAME page in a locale, by its clean directory URL (/, /ru/, /about/, /ru/about/privacy/)."""
    default = site["default_locale"]
    here = ([] if c.locale == default else [c.locale]) + PAGE_PARTS
    there = ([] if loc == default else [loc]) + PAGE_PARTS
    if here == there:
        return "./"
    n = 0
    while n < min(len(here), len(there)) and here[n] == there[n]:
        n += 1
    return "../" * (len(here) - n) + "".join(x + "/" for x in there[n:])


def lang_menu(site, c):
    """ONE language control: a round button with the current code, a dropdown of languages.
    Built from site.json locales / locale_labels / locale_names; a new locale there adds a row."""
    labels = site.get("locale_labels", {})
    names = site.get("locale_names", {})
    cur = labels.get(c.locale, c.locale.upper())
    rows = []
    for loc in site["locales"]:
        cur_attr = ' aria-current="true"' if loc == c.locale else ""
        rows.append('<li><a href="%s" hreflang="%s" lang="%s"%s><span class="lang__code">%s</span>'
                    '<span>%s</span></a></li>'
                    % (esc(lang_page_href(site, c, loc)), esc(loc), esc(loc), cur_attr,
                       esc(labels.get(loc, loc.upper())), esc(names.get(loc, labels.get(loc, loc)))))
    return ('<details class="lang" data-ls-lang><summary class="lang__btn" data-ls-lang-switch aria-label="%s: %s">'
            '<span aria-hidden="true">%s</span></summary><ul class="lang__list">%s</ul></details>'
            % (esc(c.get("nav.language", "Language")), esc(names.get(c.locale, cur)), esc(cur), "".join(rows)))


def brand_html(site, c, wide=True):
    return ('<a href="%s" aria-label="%s">%s%s</a>'
            % (esc(home_href()), esc(c.get("brand.alt", "AIVIS.ONE")),
               img(site, c, "aivis-mark.svg", "", "brand__mark", 26, 30),
               img(site, c, "aivis-wordmark.svg", c.get("brand.alt", "AIVIS.ONE"), "brand__word img-invert", 96, 20)))


def at(s):
    """Escape and write '@' as a character reference: the e-mail address is real, but no email-shaped string
    stands in the served HTML for a proxy to rewrite (CF4; the browser reads the reference as '@')."""
    return esc(s).replace("@", "&#64;")


def tile_link(href, icon, label, cls="icon icon--soc", rel="me noopener"):
    """ONE icon tile for every footer icon (networks and personal contacts): the same box, the same colour."""
    return ('<a class="social__a" href="%s" rel="%s" title="%s" aria-label="%s">%s</a>'
            % (href, rel, at(label), at(label), ic("soc-" + icon, cls + " icon--soc-" + esc(icon))))


def r_home_footer(sec, c, site):
    """The footer (footer.md section 3, restructured on his word of 2026-10-02): the single contentinfo, a
    direct child of body. TOP the information (brand, sections, legal); BELOW it ONE contacts block with two
    groups side by side, the company networks and 'write to me personally'; then the legal strip.
    Every one of the six icons is the same tile (.social__a) with a currentColor glyph of its own size."""
    sid = sec["id"]
    g = lambda k: c.get("%s.%s" % (sid, k))
    loc = c.locale
    L = lroot()

    def link(key, href=None, hint=False):
        h = safe_href(href if href is not None else g("link.%s.href" % key), "#", context="footer.%s" % key)
        ext = h.startswith("http")
        extra = ' rel="noopener"' if ext else ""
        tail = '<span class="foot__hint">%s</span>' % esc(g("link.%s.hint" % key)) if hint else ""
        cur = ' aria-current="page"' if h in CURRENT_HREFS else ""
        return '<li><a href="%s"%s%s><span>%s</span>%s</a></li>' % (esc(h), extra, cur, T(g("link.%s" % key)), tail)

    site_links = "".join([link("about", L + "about/"), link("courses", L + "courses/"),
                          link("questions", L + "faq/"), link("sankord", None, True), link("login", "/login")])
    legal_links = "".join([link("privacy", L + "about/privacy/"), link("terms", L + "about/terms/"),
                           link("imprint", L + "about/imprint/"), link("licence", L + "about/licence/"),
                           link("cookies", L + "about/cookies/")])
    me_tiles = [
        tile_link(esc(safe_href(g("me.telegram.href"), "#", context="footer.me.telegram")), "telegram",
                  "%s: %s" % (g("me.telegram"), g("me.telegram.handle"))),
        tile_link(at(g("me.mail.href")), "mail", "%s: %s" % (g("me.mail"), g("me.mail.handle")),
                  rel="noopener")]
    soc = []
    for item in site.get("social", []):
        name = item.get("names", {}).get(loc, item.get("name", ""))
        icon = item.get("icon", "")
        url = item.get("urls", {}).get(loc) or item.get("url", "")
        if not url:
            continue
        soc.append("<li>%s</li>" % tile_link(esc(safe_href(url, "#", context="social." + icon)), icon, name))
    return "\n".join([
        '<footer class="foot" id="%s"><div class="wrap">' % esc(sid),
        '<div class="foot__grid">',
        '<div class="foot__brand"><div class="brand">%s</div><p class="foot__tag">%s</p></div>'
        % (brand_html(site, c), T(c.get("aivis.subtitle"))),
        '<nav class="foot__nav foot__nav--site" aria-label="%s"><h2 class="foot__h">%s</h2><ul>%s</ul></nav>'
        % (esc(g("site.aria")), T(g("site.title")), site_links),
        '<nav class="foot__nav foot__nav--legal" aria-label="%s"><h2 class="foot__h">%s</h2><ul>%s</ul></nav>'
        % (esc(g("legal.aria")), T(g("legal.title")), legal_links),
        '</div>',
        '<div class="foot__contacts">',
        '<nav class="foot__group" aria-label="%s"><h2 class="foot__h">%s</h2><ul class="social">%s</ul></nav>'
        % (esc(g("social.aria")), T(g("social.title")), "".join(soc)),
        '<section class="foot__group foot__me" aria-labelledby="foot-me-h"><h2 class="foot__h" id="foot-me-h">%s</h2>'
        '<ul class="social">%s</ul><p class="foot__who">%s</p></section>'
        % (T(g("me.title")), "".join("<li>%s</li>" % x for x in me_tiles), T(g("me.name"))),
        '</div>',
        '<div class="foot__bottom"><p>%s</p><p>%s</p></div></div></footer>' % (T(g("company")), T(g("copyright"))),
    ])


CURRENT_HREFS = set()   # hrefs of the footer links that point at the page being rendered (aria-current)


# ---------- the /about/ page and the legal pages ----------

def page_href(slug):
    """Relative link from the page being rendered to a page of this locale (slug 'about/privacy')."""
    return lroot() + slug.strip("/") + "/"


_LINK_MARK = re.compile(r"\[\[(.+?)\|(.+?)\]\]")


def rich(s):
    """Escape a content string (with the no-break rules of T) and turn its [[text|href]] marks into links.
    An href of '~/x/' is a page of this locale; every '@' is written as a character reference (CF4)."""
    def link(m):
        txt, href = m.group(1), html.unescape(m.group(2))
        if href.startswith("~/"):
            href = lroot() + href[2:]
        if not href.startswith("mailto:"):
            href = safe_href(href, "#", context="rich link")
        ext = href.startswith("http")
        return '<a href="%s"%s>%s</a>' % (esc(href).replace("@", "&#64;"), ' rel="noopener"' if ext else "",
                                          txt.replace("@", "&#64;"))
    return _LINK_MARK.sub(link, T(s))


def r_about_article(sec, c, site):
    """/about/ as an article: the approved text, one section per heading, the founder's photograph by section 3,
    the SANKORD block (name, promise, category) inside section 5, the courses link, the company, the contacts."""
    g = lambda k: c.get("about." + k)
    P = lambda *keys: "".join("<p>%s</p>" % rich(g(k)) for k in keys)

    def sec_open(sid, cls, key, alt=False):
        return ('<section class="block about-sec %s%s" id="%s" aria-labelledby="%s-h"><div class="wrap about-grid">'
                '<h2 id="%s-h" class="about-h ls-mo-balance">%s</h2><div class="about-body">'
                % (cls, " alt" if alt else "", sid, sid, sid, T(g(key))))

    end = "</div></div></section>"
    out = [
        '<section class="block hero hero--page about-intro" id="about_intro" aria-labelledby="about_intro-h"><div class="wrap">',
        '<h1 id="about_intro-h" class="ls-mo-balance"><span class="h-main">%s</span> <span class="h-sub">%s</span></h1>'
        % (T(g("h1")), T(c.get("aivis.subtitle"))),
        '<p class="lead">%s</p>' % rich(g("lead")),
        '</div></section>',
        sec_open("name", "about-name", "name.title"), P("name.p1", "name.p2"), end,
        sec_open("founder", "about-founder", "founder.title", True),
        '<figure class="about-photo">%s</figure><div class="about-text">%s</div>'
        % (photo(site, c, g("founder.photo_alt")), P("founder.p1", "founder.p2")),
        end,
        sec_open("how", "about-how", "how.title"), P("how.p1", "how.p2", "how.p3"), end,
        sec_open("sankord", "about-sankord", "sankord.title", True),
        '<div class="card sankord-block" data-component="Card" data-variant="elevated" data-size="lg">'
        '<p class="statement__name">%s</p><h3 class="about-prom">%s</h3><p class="about-cat">%s</p></div>'
        % (T(g("sankord.name")), T(g("sankord.promise")), T(g("sankord.category"))),
        P("sankord.p1", "sankord.p2"),
        '<h3 class="about-sub">%s</h3><p class="about-who">%s</p>' % (T(g("sankord.who.label")), T(g("sankord.who"))),
        P("sankord.p3"), end,
        sec_open("courses", "about-courses", "courses.title"), P("courses.p1", "courses.p2", "courses.p3"),
        '<div class="actions">%s</div>' % btn(c.get("courses.button"), page_href("courses"), "primary", "lg"), end,
        sec_open("company", "about-company", "company.title", True), P("company.p1"), end,
        sec_open("contact", "about-contact", "contact.title"), P("contact.p1"), end,
    ]
    return "\n".join(out)


_EMAIL_RE = re.compile(r"([A-Za-z0-9._%+-]+)@([A-Za-z0-9-]+\.[A-Za-z0-9.-]+)")
_LINK_RE = re.compile(r'href="(/[^"]*)"')


def _rel_href(target):
    """A root-absolute internal link of a legal fragment (/about/privacy/, /ru/about/privacy/) -> relative to this page."""
    parts = [x for x in target.split("#")[0].strip("/").split("/") if x]
    frag = ("#" + target.split("#", 1)[1]) if "#" in target else ""
    here = ([CUR_LOCALE_DIR[0]] if CUR_LOCALE_DIR[0] else []) + PAGE_PARTS
    n = 0
    while n < min(len(here), len(parts)) and here[n] == parts[n]:
        n += 1
    rel = "../" * (len(here) - n) + "".join(x + "/" for x in parts[n:])
    return (rel or "./") + frag


CUR_LOCALE_DIR = [""]


def strip_dev_comments(html):
    """The published form carries no developer notes: CSS block comments, JS comment lines and HTML comments are
    removed from the page (the sources keep them). Runs BEFORE the CSP hashes are computed. The JS rules are
    deliberately narrow (a whole-line block or line comment, or a line comment after ; { or } with no quote in it),
    so a string or a regular expression is never touched."""
    def css(m):
        body = re.sub(r"/\*.*?\*/", "", m.group(2), flags=re.S)
        body = re.sub(r"\n[ \t]*(?=\n)", "", body)
        return m.group(1) + body + m.group(3)

    def js(m):
        if re.search(r"\bsrc\s*=|ld\+json|application/json", m.group(1)):
            return m.group(0)
        body = m.group(2)
        body = re.sub(r"(?m)^[ \t]*/\*.*?\*/[ \t]*\n?", "", body, flags=re.S)
        body = re.sub(r"(?m)^[ \t]*//[^\n]*\n", "", body)
        body = re.sub(r"(?m)([;{}])[ \t]+//[^\n'\"`]*$", r"\1", body)
        body = re.sub(r"\n[ \t]*(?=\n)", "", body)
        return m.group(1) + body + m.group(3)

    html = re.sub(r"(<style[^>]*>)(.*?)(</style>)", css, html, flags=re.S)
    html = re.sub(r"(<script[^>]*>)(.*?)(</script>)", js, html, flags=re.S)
    return re.sub(r"<!--(?!__CSP__).*?-->\n?", "", html, flags=re.S)


def r_legal_doc(sec, c, site, legal_root=None):
    """One legal document, rendered at BUILD time from legal-site/out/<lang>/<doc>.html (never copied into content):
    internal links become relative, e-mail addresses are written with a character
    reference, wide tables get a scroll region."""
    doc = sec["doc"]
    src = (ROOT / site.get("legal_dir", "../legal-site/out")) / c.locale / (doc + ".html")
    if not src.exists():
        raise SystemExit("FAIL: legal source missing: %s (run python sandbox/legal-site/build.py)" % src)
    h = _doc_fragment(read(src), c)
    crumb = ('<nav class="crumb" aria-label="%s"><a href="%s">‹ %s</a></nav>'
             % (esc(c.get("legalpage.crumb")), esc(page_href("about")), T(c.get("legalpage.back"))))
    return ('<section class="block legal-page"><div class="wrap legal-wrap">%s%s</div></section>' % (crumb, h))


def _doc_fragment(h, c):
    """A document fragment rendered at build time from a legal-site output: internal links become relative, e-mail
    addresses are written with a character reference, wide tables get a scroll region; heading levels never skip
    (a document whose sections start at h3 under its h1 is lifted to h2), and a spaced hyphen used as a dash in
    Russian text is written as an em dash."""
    h = _LINK_RE.sub(lambda m: 'href="%s"' % esc(_rel_href(m.group(1))), h)
    h = _EMAIL_RE.sub(lambda m: m.group(1) + "&#64;" + m.group(2), h)
    levels = sorted({int(x) for x in re.findall(r"<h([2-6])[ >]", h)})
    if levels and levels[0] > 2:
        shift = levels[0] - 2
        h = re.sub(r"<(/?)h([2-6])([ >])", lambda m: "<%sh%d%s" % (m.group(1), int(m.group(2)) - shift, m.group(3)), h)
    if c.locale == "ru":
        h = re.sub(r"(?<=[^\s<>]) - (?=[^\s<>])", " — ", h)
    h = h.replace("<table>", '<div class="legal-table" role="region" tabindex="0" aria-label="%s"><table>' % esc(c.get("legalpage.table")))
    return h.replace("</table>", "</table></div>")


def _invest_source(site, c, name):
    src = ROOT / site["invest_dir"] / c.locale / (name + ".html")
    if not src.exists():
        raise SystemExit("FAIL: investor document source missing: %s (run the invest build of the legal site)" % src)
    h = read(src)
    h = re.sub(r'<meta name="robots"[^>]*>\s*', "", h)
    return re.sub(r'\sdata-robots="[^"]*"', "", h)


def invest_doc_title(site, c, name):
    m = re.search(r"<h1[^>]*>(.*?)</h1>", _invest_source(site, c, name), re.S)
    return html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip() if m else name


def invest_index(site, c):
    """The section's documents in display order: [(id, title, ready)], from the legal site's index.json; a ready
    document takes its title from its own text, a placeholder carries its title in the index."""
    data = json.loads(read(ROOT / site["invest_index"]))
    rows = []
    for d in data["documents"]:
        if d["status"] == "ready":
            rows.append((d["id"], invest_doc_title(site, c, d["id"]), True))
        else:
            rows.append((d["id"], d["title"].get(c.locale) or d["title"].get(site["default_locale"]), False))
    return rows


def r_invest_gate(sec, c, site):
    """The entrance of the closed section: the full NDA text, the acceptance box, the button. The section's index
    sits in the same page, hidden; the page script (assets/invest.js) shows it once acceptance is stored."""
    g = lambda k: c.get("invest." + k)
    nda = _doc_fragment(_invest_source(site, c, "nda"), c)
    nda = nda.replace("<h1>", "<h2>").replace("</h1>", "</h2>", 1)
    title = re.search(r"<h1[^>]*>(.*?)</h1>", read(ROOT / site["invest_dir"] / c.locale / "index.html"), re.S)
    title = html.unescape(re.sub(r"<[^>]+>", "", title.group(1))).strip() if title else g("back")
    items = []
    for did, dtitle, ready in invest_index(site, c):
        if ready:
            items.append('<li class="docs-doc"><a class="docs-doc__t" href="%s">%s</a></li>' % (esc(did + "/"), T(dtitle)))
        else:
            items.append('<li class="docs-doc docs-doc--prep"><span class="docs-doc__t">%s</span>'
                         '<span class="badge" data-component="Badge" data-variant="info" data-style="subtle" data-size="md">%s</span></li>'
                         % (T(dtitle), T(g("prep"))))
    return "\n".join([
        '<div data-invest="gate">',
        '<section class="block legal-page docs-head"><div class="wrap legal-wrap">'
        '<h1 id="invest-h" class="docs-h" tabindex="-1">%s</h1></div></section>' % T(title),
        '<section class="block legal-page docs-view" id="invest-gate" data-invest-view="gate"><div class="wrap legal-wrap">',
        nda,
        '<div class="card docs-accept" data-component="Card" data-variant="outlined" data-size="lg">'
        '<label class="check"><input type="checkbox" id="invest-ok" data-invest-ok><span>%s</span></label>'
        '<button class="btn ls-mo-press ls-mo-lift" type="button" data-component="Button" data-variant="primary" data-size="lg" '
        'data-invest-enter disabled><span>%s</span></button>'
        '<noscript><p class="note">%s</p></noscript></div>'
        % (T(g("accept")), T(g("enter")), T(g("noscript"))),
        '</div></section>',
        '<section class="block legal-page docs-view" id="invest-index" data-invest-view="index" hidden><div class="wrap legal-wrap">',
        '<ul class="docs-list" aria-label="%s">%s</ul>' % (esc(g("list.aria")), "".join(items)),
        '</div></section>',
        '</div>',
    ])


def r_invest_doc(sec, c, site):
    """One document of the closed section, hidden until the page script finds the stored acceptance."""
    doc = sec["doc"]
    g = lambda k: c.get("invest." + k)
    body = _doc_fragment(_invest_source(site, c, doc), c)
    crumb = ('<nav class="crumb" aria-label="%s"><a href="%s">%s</a><span aria-hidden="true">/</span>'
             '<span aria-current="page">%s</span></nav>'
             % (esc(g("crumb")), esc(page_href("invest")), T(g("back")), T(invest_doc_title(site, c, doc))))
    dl = '<p class="docs-dl"><a class="btn ls-mo-press ls-mo-lift" data-component="Button" data-variant="ghost" data-size="sm" href="%s" download><span>%s</span></a></p>' % (
        esc(doc + ".markdown"), T(g("download")))
    return ('<section class="block legal-page" id="invest-doc" data-invest="doc" data-gate="%s">'
            '<div class="wrap legal-wrap">%s%s%s</div></section>' % (esc(page_href("invest")), crumb, body, dl))


ROOT = Path(__file__).resolve().parent.parent


# All types, including footer, share the r_x(sec, c, site) signature and are
# registered here -- there is exactly one call-site pattern (finding D9).
RENDERERS = {
    "hero": r_hero,
    "features": r_features,
    "pricing": r_pricing,
    "faq": r_faq,
    "cta": r_cta,
    "footer": r_footer,
    "logos": r_logos,
    "testimonials": r_testimonials,
    "evidence": r_evidence,
    "state": r_state,
    "prose": r_prose,
    "home_aivis": r_home_aivis,
    "home_sankord": r_home_sankord,
    "home_courses": r_home_courses,
    "home_faq": r_home_faq,
    "home_footer": r_home_footer,
    "about_article": r_about_article,
    "faq_page": r_faq_page,
    "courses_page": r_courses_page,
    "invest_gate": r_invest_gate,
    "invest_doc": r_invest_doc,
    "legal_doc": r_legal_doc,
}


def drawer_tools(site, c, login_href, theme_on):
    """The drawer carries what the header holds on a phone: the languages, the theme and the login (the header is inert while it is open)."""
    labels = site.get("locale_labels", {})
    names = site.get("locale_names", {})
    langs = "".join(
        '<a class="drawer__lang" href="%s" hreflang="%s" lang="%s"%s><span class="lang__code">%s</span><span>%s</span></a>'
        % (esc(lang_page_href(site, c, loc)), esc(loc), esc(loc), ' aria-current="true"' if loc == c.locale else "",
           esc(labels.get(loc, loc.upper())), esc(names.get(loc, loc))) for loc in site["locales"])
    out = ['<div class="drawer__tools"><p class="drawer__label">%s</p><div class="drawer__langs">%s</div>'
           % (esc(c.get("nav.language", "Language")), langs)]
    if theme_on:
        out.append('<button class="drawer__row" type="button" data-ls-theme-toggle aria-pressed="false" aria-label="%s">%s%s<span>%s</span></button>'
                   % (esc(c.get("nav.theme", "Toggle dark mode")), ic("moon", "icon icon--moon"), ic("sun", "icon icon--sun"), T(c.get("nav.theme", "Toggle dark mode"))))
    if login_href:
        out.append('<a class="drawer__row" href="%s">%s<span>%s</span></a>'
                   % (esc(login_href), ic("log-in", "icon"), T(c.get("nav.cta", "Log in"))))
    out.append("</div>")
    return "".join(out)


def nav_href(sid):
    """A header link: a same-page anchor on the home, an anchor on the locale home from any other page."""
    return "#" + sid if not PAGE_PARTS else lroot() + "#" + sid


def render_header(site, c, locale, has_dark_tokens):
    nav_items = site.get("nav", [])
    links = []
    for item in nav_items:
        sid = item if isinstance(item, str) else (item.get("section") or item.get("id")) if isinstance(item, dict) else None
        if not sid:
            raise SystemExit("FAIL: site.json nav entry %r has no section id." % (item,))
        links.append((sid, c.get("nav.%s" % sid, sid)))
    nav_html = ('<nav class="nav" aria-label="%s">%s</nav>'
                % (esc(c.get("nav.primary", "Primary")), "".join('<a href="%s">%s</a>' % (esc(nav_href(s)), T(l)) for s, l in links)))
    drawer_links = "".join('<a class="drawer__link" href="%s">%s</a>' % (esc(nav_href(s)), T(l)) for s, l in links)
    hc = site.get("header_cta")
    cta_label = c.get("nav.cta", "")
    login = ""
    login_href = ""
    if isinstance(hc, dict) and hc.get("href") and cta_label:
        href = safe_href(hc.get("href"), "#", context="header_cta.href")
        login_href = href
        login = ('<a class="theme-toggle login-btn" href="%s" aria-label="%s" title="%s">%s</a>'
                 % (esc(href), esc(cta_label), esc(cta_label), ic("log-in", "icon icon--login")))
    theme_html = ""
    if site.get("theme_toggle", True) is not False:
        theme_html = ('<button class="theme-toggle" type="button" data-ls-theme-toggle aria-label="%s" aria-pressed="false">%s%s</button>'
                      % (esc(c.get("nav.theme", "Toggle dark mode")), ic("moon", "icon icon--moon"), ic("sun", "icon icon--sun")))
    menu_label = esc(c.get("nav.menu", "Menu"))
    return (
        '<header class="site-header" data-ls-header><div class="wrap row">'
        '<span class="brand">%s</span>%s'
        '<div class="tools">%s%s%s'
        '<button class="menu-toggle" type="button" data-ls-menu-open aria-label="%s" aria-expanded="false" aria-controls="drawer">%s</button>'
        '</div></div></header>'
        '<div class="drawer" id="drawer" data-ls-drawer role="dialog" aria-modal="true" aria-label="%s">'
        '<div class="drawer__bar">'
        '<button class="drawer__close" type="button" data-ls-menu-close aria-label="%s">%s</button></div>'
        '%s%s</div>'
    ) % (brand_html(site, c), nav_html,
         lang_menu(site, c), theme_html, login,
         menu_label, ic("menu"),
         menu_label, esc(c.get("nav.close", "Close menu")), ic("x"),
         drawer_links, drawer_tools(site, c, login_href, bool(theme_html)))


def page_path(loc, default):
    return locale_path(loc, default) + "".join(x + "/" for x in PAGE_PARTS)


def build_hreflang(site, locale):
    base = site.get("base_url", "").rstrip("/")
    default = site["default_locale"]
    lines = []
    for loc in site["locales"]:
        href = base + page_path(loc, default)
        lines.append('<link rel="alternate" hreflang="%s" href="%s">' % (esc(loc), esc(href)))
    lines.append('<link rel="alternate" hreflang="x-default" href="%s">' % esc(base + page_path(default, default)))
    return "\n".join(lines)


def build_head_urls(site, locale):
    """The canonical link plus the hreflang set -- or an honest absence.

    Both are absolute-URL claims about where this page lives. With no
    `base_url` there is no honest value for either: `href="/en/"` in a
    canonical tag is not a relative convenience, it is a claim about an origin
    the project has not got yet, and a hreflang set built on it is worse -- the
    search-engine contract those tags carry is defined only for fully-qualified
    URLs.

    So the pre-launch page emits neither, and says so in the markup instead of
    inventing an origin. `build-site.py` refuses to write the sitemap and
    robots.txt for the same reason, and the deploy guide names it as the one
    thing to set before shipping. A declared-but-malformed `base_url` is still
    a hard failure: making the field optional must not make a wrong value
    legal."""
    base = site.get("base_url", "").rstrip("/")
    if not base:
        return ("<!-- PRE-LAUNCH: no base_url in site.json, so this page carries no canonical\n"
                "     link and no hreflang set. Both are absolute-URL claims, and inventing an\n"
                "     origin for them would ship a false one. Set base_url and rebuild before\n"
                "     the page is indexed. -->")
    return ('<link rel="canonical" href="%s">\n%s'
            % (esc(base + page_path(locale, site["default_locale"])),
               build_hreflang(site, locale)))


def build_og(c, site, locale, title="", desc=""):
    base = site.get("base_url", "").rstrip("/")
    title = title or c.meta_get("title", "")
    desc = desc or c.meta_get("description", "")
    img = c.meta_get("og_image", "")
    tags = [
        '<meta property="og:type" content="website">',
        '<meta property="og:title" content="%s">' % esc(title),
        '<meta property="og:description" content="%s">' % esc(desc),
        '<meta property="og:locale" content="%s">' % esc(locale),
    ]
    # og:url is the same absolute-URL claim as canonical (see build_head_urls):
    # omitted rather than invented when the project has no origin yet.
    if base:
        tags.insert(3, '<meta property="og:url" content="%s">'
                    % esc(base + page_path(locale, site["default_locale"])))
    if img:
        tags.append('<meta property="og:image" content="%s">' % esc(img))
        tags.append('<meta property="og:image:width" content="1200">')
        tags.append('<meta property="og:image:height" content="630">')
        alt = c.meta_get("og_image_alt", "")
        if alt:
            tags.append('<meta property="og:image:alt" content="%s">' % esc(alt))
        tags.append('<meta name="twitter:card" content="summary_large_image">')
        tags.append('<meta name="twitter:image" content="%s">' % esc(img))
        tags.append('<meta name="twitter:title" content="%s">' % esc(title))
        tags.append('<meta name="twitter:description" content="%s">' % esc(desc))
    return "\n".join(tags)


CANON = (
    "<!--\n"
    "__LS_CANON__:\n"
    "  builder: landing-studio\n"
    "  builder_version: 10.0.0\n"
    "  artifact: landing-page\n"
    "  locale: {locale}\n"
    "  checks: integrity i18n responsive cf-ready wcag-baseline contrast review orphan\n"
    "-->"
)


# ---------- section 4.1: single-pass templating (finding C1) ----------
PLACEHOLDER_RE = re.compile(r"\{\{([A-Z_]+)\}\}")


# ---------- v2: the document's inline blocks and the CSP over them ----------
FONT_LINE_SKIP = re.compile(r"noto-deva")


def ds_css(assets, prefix):
    """tokens (immutable) + fonts (urls rewritten to assets/fonts/) + extension layer."""
    tokens = read(assets / "ds" / "aivis-tokens.css").rstrip()
    fonts = []
    for line in read(assets / "ds" / "fonts" / "aivis-fonts.source.css").splitlines():
        if FONT_LINE_SKIP.search(line):          # Devanagari faces: no Hindi locale on this site
            continue
        fonts.append(line.replace("url('./", "url('%sassets/fonts/" % prefix))
    parts = [tokens, "\n".join(fonts), read(assets / "site.css").rstrip()]
    for name in ("bind.css", "micro.css", "polish.css", "reveal.css", "transitions.css"):
        parts.append(read(assets / "motion" / name).rstrip())
    parts.append(".sprite { position: absolute; inline-size: 0; block-size: 0; overflow: hidden; }")
    return "\n".join(parts)


def site_js(assets):
    parts = [read(assets / "motion" / "transitions.js").rstrip(), read(assets / "motion" / "scroll.js").rstrip(),
             read(assets / "motion" / "bind.js").rstrip(),
             read(assets / "site.js").rstrip()]
    return "\n".join(parts)


def icon_sprite(assets):
    """Inline sprite (R1-4), only the symbols the page uses, copied from the design system's own sprite."""
    src = read(assets / "ds" / "icons.svg")
    syms = []
    soc = json.loads(read(assets / "social-icons.json"))
    for name in sorted(USED_ICONS):
        if name.startswith("soc-"):
            slug = name[4:]
            syms.append('<symbol id="i-%s" viewBox="0 0 24 24"><path fill="currentColor" d="%s"/></symbol>' % (name, soc[slug]))
            continue
        m = re.search(r'<symbol id="i-%s".*?</symbol>' % re.escape(name), src, re.S)
        if not m:
            raise SystemExit("FAIL: icon '%s' is not in the design system sprite" % name)
        syms.append(m.group(0))
    return ('<svg class="sprite" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false">%s</svg>'
            % "".join(syms))


def inline_hashes(html_text):
    import base64
    import hashlib

    def h(body):
        return "'sha256-%s'" % base64.b64encode(hashlib.sha256(body.encode("utf-8")).digest()).decode("ascii")
    styles = [h(b) for b in re.findall(r"<style>(.*?)</style>", html_text, re.S)]
    scripts = [h(b) for b in re.findall(r"<script>(.*?)</script>", html_text, re.S)]
    return styles, scripts


def csp_policy(styles, scripts, for_header=False):
    d = ["default-src 'none'", "img-src 'self'", "font-src 'self'",
         "style-src " + " ".join(styles), "script-src " + " ".join(scripts),
         "connect-src 'none'", "base-uri 'none'", "form-action 'none'"]
    if for_header:
        d.append("frame-ancestors 'self'")   # not allowed in a meta policy
    return "; ".join(d)


def csp_meta(html_text):
    styles, scripts = inline_hashes(html_text)
    return '<meta http-equiv="Content-Security-Policy" content="%s">' % esc(csp_policy(styles, scripts))



def main(argv):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--site", required=True, type=Path)
    p.add_argument("--content", required=True, type=Path)
    p.add_argument("--tokens", required=True, type=Path)
    p.add_argument("--assets-dir", required=True, type=Path)
    p.add_argument("--locale", required=True)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--fallback", type=Path, default=None)
    p.add_argument("--page", default="", help="slug of a page in site.json pages (e.g. about/privacy); empty = the home")
    p.add_argument("--animate", action="store_true")
    p.add_argument("--icon-map", type=Path, default=None,
                   help="Design-system icon bridge produced by scripts/icon-bridge.py "
                        "(spec 5.6). Optional; defaults to icon-map.json beside site.json, "
                        "the same project-root rule gate.py uses for redlines.json.")
    args = p.parse_args(argv[1:])

    site = json.loads(read(args.site))
    content_raw = json.loads(read(args.content))
    fallback_raw = json.loads(read(args.fallback)) if args.fallback else content_raw
    c = Content(content_raw, fallback_raw)
    locale = args.locale
    direction = content_raw.get("dir", "ltr")
    assets = args.assets_dir

    page = None
    if args.page:
        page = next((x for x in site.get("pages", []) if x["slug"] == args.page), None)
        if page is None:
            raise SystemExit("FAIL: page %r is not in site.json pages" % args.page)
        PAGE_PARTS[:] = args.page.strip("/").split("/")
        CURRENT_HREFS.add(lroot() + args.page.strip("/") + "/")
    page_sections = page["sections"] if page else [x for x in site["sections"] if x.get("type") not in FOOTER_TYPES]

    c.icons = load_icons(assets)
    # spec 5.6: the second lookup source. Optional input -- absent means v9
    # behaviour exactly. Explicitly named but missing is a WARN, because an
    # operator who typed --icon-map meant to use one.
    c.icon_map = load_icon_map(args.icon_map if args.icon_map else args.site.parent / "icon-map.json",
                               required=args.icon_map is not None)
    c.locale = locale
    CUR_LOCALE[0] = locale
    CUR_LOCALE_DIR[0] = "" if locale == site["default_locale"] else locale

    # spec 4.2: the disclosure is rendered by the footer renderer. A site whose
    # obligation is active but which declares no footer section has nowhere to
    # put it -- say so here rather than letting Q-DISCLOSE report a missing
    # element with no explanation of why nothing could have rendered it.
    _active, _reason = disclosure_active(site)
    if _active and first_footer_id(site) is None:
        print("WARN: the agent-authorship disclosure obligation is ACTIVE but site.json "
              "declares no 'footer' section, so no <p class=\"ls-disclosure\"> can be "
              "rendered for locale '%s'; Q-DISCLOSE (BLOCKER) will refuse the page."
              % locale, file=sys.stderr)

    # Section 2: the migration shield already stripped every [review:xx]
    # marker while building `c` above. Warn once per page if it had to.
    if c.strip_count > 0:
        print(
            "WARN: stripped %d inline [review:] marker(s) from locale %s -- legacy v8 format; "
            "run scripts/migrate-review.py to convert to the _review channel. "
            "This shield is deprecated; migrate rather than rely on it." % (c.strip_count, locale),
            file=sys.stderr,
        )

    # v2: the CSS is the design system's own stylesheet (assets/ds/aivis-tokens.css,
    # byte for byte), the font stylesheet with its urls pointed at assets/fonts/,
    # then the extension layer assets/site.css. tokens.tokens.json stays as the
    # input of the contrast gate only.
    prefix = prefix_for(site, locale)
    USED_ICONS.clear()
    USED_ICONS.update(COMMON_ICONS)
    has_dark_tokens = True

    # Section 6.4: skip link is the first element in <body>, followed by the
    # header, then <main id="ls-main"> wrapping every non-footer section.
    body_parts = ['<a class="ls-skip" href="#ls-main">%s</a>' % esc(c.get("nav.skip", "Skip to content"))]
    body_parts.append(render_header(site, c, locale, has_dark_tokens))
    body_parts.append('<main id="ls-main">')
    for sec in page_sections:
        fn = RENDERERS.get(sec.get("type"), r_prose)
        body_parts.append(fn(sec, c, site))
    body_parts.append('</main>')
    for sec in site["sections"]:
        if sec.get("type") in FOOTER_TYPES:
            fn = RENDERERS.get(sec.get("type"), r_prose)
            body_parts.append(fn(sec, c, site))
    body = "\n".join(body_parts)

    base = site.get("base_url", "").rstrip("/")
    template = read(assets / "page-template.html")
    page_title = c.get(page["title_key"]) if page and page.get("title_key") else ""
    page_desc = c.get(page["desc_key"]) if page else ""
    if page and page.get("invest_doc"):
        page_title = invest_doc_title(site, c, page["invest_doc"]) + " | AIVIS.ONE"
    has_invest = bool(page) and any(x.get("type", "").startswith("invest_") for x in page_sections)

    values = {
        "LANG": esc(locale),
        "DIR": esc(direction),
        # finding C16: title/description go through Content.meta_get(), never c.meta raw.
        "TITLE": esc(page_title or c.meta_get("title", site.get("project", ""))),
        "DESCRIPTION": esc(page_desc or c.meta_get("description", "")),
        "ROBOTS": ('<meta name="robots" content="%s">' % esc(page.get("robots", "noindex, follow"))) if page and not page.get("indexable", True) else "",
        "HEAD_URLS": build_head_urls(site, locale),
        "OG": build_og(c, site, locale, page_title, page_desc),
        # TOKENS_CSS is CSS-context content, not HTML-context: it is embedded
        # verbatim inside <style>, so it must NOT be html.escape()'d (that
        # would corrupt valid CSS). Its safety is tokens-to-css.py's job
        # (section 4.3: reject any value containing '<','>',';','{','}','@',
        # '/*','*/','url(' or a newline) -- by the time it reaches here it is
        # expected to already be safe CSS text.
        "DS_CSS": ds_css(assets, prefix),
        "BODY": body,
        "PREBOOT_JS": read(assets / "preboot.js").rstrip(),
        "SITE_JS": site_js(assets) + (("\n" + read(assets / "invest.js").rstrip()) if has_invest else ""),
        "ICON_SPRITE": icon_sprite(assets),
        "ASSETS_PREFIX": prefix,
        "CSP_META": "<!--__CSP__-->",
        # finding C10 (CRITICAL): in v8 this was CANON.format(locale=locale) --
        # the ONE interpolation site in this file that skipped esc(), letting
        # a crafted --locale value close the HTML comment and inject a
        # <script>. esc() here is load-bearing; do not remove it.
        "CANON": CANON.format(locale=esc(locale)),
    }

    # Single pass: re.sub scans the ORIGINAL template exactly once and never
    # rescans substituted text, so a value containing a literal "{{OTHER}}"
    # cannot be re-expanded (finding C1). Compare to v8's str.replace() chain,
    # which re-scanned the whole growing string on every .replace() call.
    out = PLACEHOLDER_RE.sub(lambda m: values.get(m.group(1), ""), template)
    out = strip_dev_comments(out)
    out = out.replace("<!--__CSP__-->", csp_meta(out))

    # Residue discipline. Single-pass substitution replaces EVERY template
    # placeholder, so the template itself can never leave residue -- which means
    # a blanket "no double braces" assert only ever fires on legitimate copy that
    # happens to contain them, and crashes a valid render (trial defect 6).
    # The two real bug classes are checked instead:
    #   (a) the template declares a placeholder main() never supplied -> hard error
    #   (b) content supplies double-brace text -> harmless (it is HTML-escaped and
    #       never re-expanded, finding C1), so warn and pass it through
    declared = set(PLACEHOLDER_RE.findall(template))
    missing = sorted(declared - set(values))
    if missing:
        print("FAIL: template declares placeholder(s) with no value: %s"
              % ", ".join("{{%s}}" % k for k in missing), file=sys.stderr)
        return 1
    stray = sorted(set(PLACEHOLDER_RE.findall(out)))
    if stray:
        print("WARN: rendered page carries literal double-brace text from content "
              "(%s) -- escaped and inert, but Q-INTEGRITY reports it; remove it from "
              "the copy if unintended." % ", ".join("{{%s}}" % k for k in stray),
              file=sys.stderr)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(out, encoding="utf-8")
    print(f"OK: wrote {args.out} ({args.out.stat().st_size} bytes) locale={locale} dir={direction}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
