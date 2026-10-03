#!/usr/bin/env python3
"""landing-studio v10.0.0 -- scripts/i18n-check.py

i18n completeness + correctness gate. `scripts/gate.py`'s Q-I18N (BLOCKER)
delegates to this script over its CLI -- this file is the one and only
implementation of every check below; do not duplicate any of this logic
inside gate.py or any doc.

v10 adds two checks (spec 7.2) and folds BOTH into this same script under the
existing Q-I18N id -- no new gate id, no new script. Why here, and why not
somewhere that might look more natural:

  * The authorship contradiction is a statement ABOUT `_review`, and this file
    already owns `_review` bookkeeping (SPEC-v9.md section 3, item 5). A locale
    claiming to be hand-authored while carrying preview-grade review debt is a
    contradiction only the counter of that debt can see, so it is checked where
    the debt is counted -- or nowhere.
  * `disclosure.text` coverage is checked here rather than in Q-DISCLOSE
    because a missing translation is a COVERAGE error, and coverage is this
    script's job. Q-DISCLOSE checks the rendered artifact carries exactly one
    non-empty .ls-disclosure; it never grows a second, drifting copy of the
    required-key list.

A second carrier of the same fact is the defect class v9 spent its whole
release closing, and a gate id per fact-carrier is how that class gets in.

Verifies:
  1.  every locale's content covers every key present in the default locale
      (missing = listed, not silent)
  2.  dead-key detection: keys present in a locale but ABSENT from the
      default locale are listed too, not just the reverse (finding C15)
  3.  empty-value detection: a `t` key present with ""/None/whitespace-only,
      or a list containing such an item, is a FAIL naming the locale and key
      (finding C14)
  4.  `meta.title` / `meta.description` coverage: every locale must have both,
      non-empty (finding C16)
  5.  `_review` reporting: a per-locale count is printed as a NOTE (never
      fails); a `_review` entry naming a key that does not exist in that
      locale's `t`/`meta` is a FAIL (section 2)
  6.  in-value marker detection: a literal `[review:` substring surviving
      inside any `t`/`meta` VALUE is a FAIL -- this is the section-2 inversion
      of v8, where the marker in the copy was a non-blocking NOTE (finding T1)
  7.  `base_url`: PRESENT but not `http(s)://` is a FAIL (finding C21).
      ABSENT is pre-launch mode: the pages carry no canonical link and no
      hreflang set, so checks 9/10 are skipped and the run says so -- an
      unchecked URL layer reported as unchecked, never as correct
  8.  each rendered page declares `<html lang>` and a non-empty `dir`, found
      via two INDEPENDENT attribute searches (not one order/quote-sensitive
      regex, so a future template attribute reorder can't silently blind
      this check)
  9.  hreflang is present, symmetric (each page links every locale incl.
      itself) with x-default, AND the total `<link rel="alternate"` count on
      the page equals len(locales) + 1 (catches a duplicate/missing entry
      that the symmetry substring test alone could miss)
  10. the default locale is served at the site root (English is a
      convention, not a rule -- Q3; whatever `default_locale` names)
  11. `dist/` orphan scan (only when --dist is given): any `*/index.html` or
      `sitemap-*.xml` under `dist/` whose locale is not in site.json's
      locales is a FAIL (finding C6)
  12. `authorship` (spec 7.1/7.2): a content file DECLARING
      `"authorship": "authored"` while carrying a non-empty `_review` is a
      FAIL naming the locale and the entry count; such a locale is also left
      out of the review-debt reporting entirely, because an authored locale
      carries no preview-grade debt by definition. A value outside
      {"authored", "machine-translated"} is its own FAIL naming the locale and
      the bad value. The field is OPTIONAL and its ABSENCE changes nothing:
      v9's semantics are unchanged (spec 8.3) -- the default locale reads as
      authored and every other locale as machine-translated, and neither the
      contradiction check nor the review-debt exclusion fires on an
      undeclared locale. Only a written claim is checked, because only a
      written claim can be wrong.
  13. `disclosure.text` (spec 4.2): when site.json's disclosure obligation is
      ACTIVE (`authorship.agent_authored` true AND `authorship.eu_residency`
      neither "excluded" nor "confirmed_non_eu"), the content key
      `disclosure.text` is required and non-empty in EVERY locale, exactly as
      `meta.title`/`meta.description` are -- a missing one is a FAIL naming
      the locale. When the obligation is inactive it is an ordinary optional
      key and nothing here fires.

Exit 0 = PASS, 1 = FAIL (a structural i18n defect), 2 = usage/setup error.

Usage:
  python i18n-check.py --site site.json --content-dir content [--dist dist]
"""
import argparse
import json
import re
import sys
from pathlib import Path

REVIEW_MARKER_RE = re.compile(r"\[review:")
BASE_URL_RE = re.compile(r"^https?://", re.IGNORECASE)

# Section 3 item 9: two independent attribute searches instead of the single
# order/quote-sensitive `<html lang="X" dir="Y">` regex v8 used. Each search
# tolerates the other attributes being present, in either order, and either
# quote style, so a template change that reorders attributes cannot silently
# blind this check (unlike a single regex anchored to one exact sequence).
HTML_TAG_RE = re.compile(r"<html\b[^>]*>", re.IGNORECASE | re.DOTALL)


def find_html_attr(tag_text, attr):
    """Search only within an already-extracted `<html ...>` tag string for
    `attr="value"` or `attr='value'`, independent of attribute order or which
    quote style the template uses. Returns the value or None."""
    m = re.search(attr + r'\s*=\s*"([^"]*)"', tag_text, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(attr + r"\s*=\s*'([^']*)'", tag_text, re.IGNORECASE)
    if m:
        return m.group(1)
    return None


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def is_empty_scalar(v):
    return v is None or (isinstance(v, str) and v.strip() == "")


def check_empty_values(t, loc, fails):
    """Finding C14: a key present with ''/None/whitespace-only, or a list
    containing such an item, is a FAIL naming the locale and key."""
    for k, v in t.items():
        if isinstance(v, list):
            for i, item in enumerate(v):
                if is_empty_scalar(item):
                    fails.append(f"locale '{loc}' key '{k}[{i}]' is empty")
        elif is_empty_scalar(v):
            fails.append(f"locale '{loc}' key '{k}' is empty")


def find_marker_in_value(v):
    """Return True if `[review:` survives inside this value (str) or any
    item of it (list). Section 2 / finding T1: this is now a hard FAIL,
    never a non-blocking note -- the inverse of v8's behaviour."""
    if isinstance(v, str):
        return bool(REVIEW_MARKER_RE.search(v))
    if isinstance(v, list):
        return any(isinstance(x, str) and REVIEW_MARKER_RE.search(x) for x in v)
    return False


def review_key_exists(data, key):
    """Does a `_review`-listed key actually exist in this locale's t/meta?
    Namespace per section 2: plain dot keys live in `t`; `meta.title` and
    `meta.description` are the two literal meta keys."""
    if key in ("meta.title", "meta.description"):
        return key.split(".", 1)[1] in data.get("meta", {})
    return key in data.get("t", {})


# spec 7.1: the two values `content/{locale}.json authorship` may take. The
# FIELD is the one carrier of a locale's authorship state (spec 10) -- this
# tuple is only the vocabulary it is checked against, held once here rather
# than spelled out in a message string and again in a condition.
AUTHORSHIP_VALUES = ("authored", "machine-translated")

# spec 4.2: the content key that becomes required when the obligation is
# active. Held once; the list is not restated in any message below.
DISCLOSURE_KEY = "disclosure.text"


def declared_authorship(data, loc, fails):
    """Return the DECLARED authorship of this locale, or None when the file
    declares none.

    Absence is not a value: spec 8.3 keeps v9's semantics exactly for a file
    with no `authorship` field -- the default locale reads as authored, every
    other locale as machine-translated -- and neither v10 check fires on an
    undeclared locale. Only a written claim can contradict the `_review` list,
    so only a written claim is checked; inferring "authored" for an undeclared
    default locale would turn a green v9 project red for a field it never had.

    A value outside the vocabulary is its own FAIL naming the locale and the
    bad value, and is treated as no declaration for every check downstream:
    a claim nobody can read is not a claim to check against."""
    if "authorship" not in data:
        return None
    value = data.get("authorship")
    if value not in AUTHORSHIP_VALUES:
        fails.append(f"locale '{loc}': authorship={value!r} is not one of "
                     f"{', '.join(AUTHORSHIP_VALUES)}")
        return None
    return value


def disclosure_active(site):
    """Spec 4.1: the agent-authorship disclosure obligation is ACTIVE when
    `authorship.agent_authored` is true AND `authorship.eu_residency` is
    neither "excluded" nor "confirmed_non_eu" -- UNKNOWN carries the duty.
    An absent `authorship` block leaves it inactive, so no v9 project turns
    red for a block it never declared.

    site.json is the one carrier of this fact (spec 10); each reader derives
    the answer from it over its own CLI rather than importing a shared copy
    across a wave boundary (spec 13's frozen cross-wave contract), so there is
    no second stored carrier to drift."""
    auth = site.get("authorship")
    if not isinstance(auth, dict):
        return False, "authorship absent"
    if not auth.get("agent_authored"):
        return False, "agent_authored=false"
    residency = auth.get("eu_residency", "unknown")
    if residency in ("excluded", "confirmed_non_eu"):
        return False, f"eu_residency={residency}"
    return True, ""


def scan_dist_orphans(dist, locales, fails):
    """Finding C6: walk dist/ (one level for locale pages, top level for
    sitemaps) rather than trusting site.json alone -- a stale page or
    sitemap left over from a dropped locale must be caught even though
    site.json itself looks perfectly fine. Only runs when --dist is given."""
    if not dist.exists():
        return
    for child in sorted(dist.iterdir()):
        if child.is_dir() and (child / "index.html").exists():
            loc = child.name
            if loc not in locales:
                fails.append(f"dist orphan: '{child}/index.html' belongs to locale "
                              f"'{loc}', which is not in site.json locales {locales}")
    for sm in sorted(dist.glob("sitemap-*.xml")):
        loc = sm.stem[len("sitemap-"):]
        if loc not in locales:
            fails.append(f"dist orphan: '{sm}' belongs to locale '{loc}', "
                          f"which is not in site.json locales {locales}")


def main(argv):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--site", required=True, type=Path)
    p.add_argument("--content-dir", required=True, type=Path)
    p.add_argument("--dist", type=Path, default=None)
    args = p.parse_args(argv[1:])

    try:
        site = load(args.site)
    except (OSError, json.JSONDecodeError) as e:
        print(f"FAIL: cannot read/parse site file '{args.site}': {e}", file=sys.stderr)
        return 2

    default = site.get("default_locale")
    locales = site.get("locales", [])
    fails, notes = [], []

    if default not in locales:
        fails.append(f"default_locale '{default}' is not listed in locales {locales}; "
                     f"it must be (the default locale is served at root '/').")

    # finding C21, revised in the v10 completion pass: a base_url that is
    # PRESENT but not http(s) is still a FAIL -- that is the silent
    # relative-URL bug C21 was about. An ABSENT base_url is the pre-launch
    # mode build-site.py builds in: the page deliberately carries no canonical
    # link and no hreflang set, so this gate must not demand them. It says so
    # instead of passing quietly, because "the URL layer is unchecked" and
    # "the URL layer is correct" are different results.
    base_url = str(site.get("base_url") or "").strip()
    pre_launch = not base_url
    if base_url and not BASE_URL_RE.match(base_url):
        fails.append(f"site.json 'base_url' is present but not http(s): {base_url!r}. Remove the "
                     f"key to build pre-launch, or give it an absolute origin.")
    if pre_launch:
        notes.append("PRE-LAUNCH: no base_url, so canonical, hreflang and x-default are not "
                     "checked on any page -- the pages carry none by design. Set base_url and "
                     "re-run before the site is indexed.")

    # 13 / spec 4.2: is `disclosure.text` a required key on this run? Read once
    # from site.json, before the locale loop, so every locale is judged against
    # the same answer.
    disc_active, disc_reason = disclosure_active(site)
    if disc_active:
        notes.append(f"NOTE: the agent-authorship disclosure obligation is ACTIVE, so "
                     f"'{DISCLOSURE_KEY}' is a required key in every locale (spec 4.2).")

    # 1/2/3/4/5/6: per-locale content checks against the default locale.
    base_path = args.content_dir / f"{default}.json"
    if not base_path.exists():
        fails.append(f"default-locale content file is missing: {base_path}")
        base_t = {}
    else:
        base_data = load(base_path)
        base_t = base_data.get("t", {})
    base_keys = set(base_t.keys())

    review_total = 0
    for loc in locales:
        cf = args.content_dir / f"{loc}.json"
        if not cf.exists():
            fails.append(f"missing content file for locale '{loc}'")
            continue
        data = load(cf)
        t = data.get("t", {})
        meta = data.get("meta", {})

        # 1. missing keys vs default locale.
        missing = sorted(base_keys - set(t.keys()))
        if missing:
            fails.append(f"locale '{loc}' missing {len(missing)} key(s): "
                         f"{missing[:6]}{' ...' if len(missing) > 6 else ''}")

        # 2. dead keys: present in this locale but absent from the default
        # locale (finding C15 -- v8 only ever reported base - locale, never
        # the reverse direction).
        if loc != default:
            dead = sorted(set(t.keys()) - base_keys)
            if dead:
                fails.append(f"locale '{loc}' has {len(dead)} dead key(s) absent from "
                             f"default locale '{default}': {dead[:6]}{' ...' if len(dead) > 6 else ''}")

        if not data.get("dir"):
            fails.append(f"locale '{loc}' content has no 'dir' field")

        # 3. empty-value detection (finding C14), including list items.
        check_empty_values(t, loc, fails)

        # 4. meta.title / meta.description coverage (finding C16).
        for mk in ("title", "description"):
            if is_empty_scalar(meta.get(mk)):
                fails.append(f"locale '{loc}' meta.{mk} is missing or empty")

        # 13. `disclosure.text` coverage while the obligation is active
        # (spec 4.2), treated EXACTLY as meta.title/meta.description above:
        # required and non-empty in every locale, named when missing. A
        # missing translation of a mandatory disclosure is a coverage error,
        # which is this script's job -- Q-DISCLOSE checks the rendered
        # artifact and holds no copy of this key list. Inactive obligation =
        # an ordinary optional key, checked by nothing here.
        if disc_active and is_empty_scalar(t.get(DISCLOSURE_KEY)):
            fails.append(f"locale '{loc}' is missing required key '{DISCLOSURE_KEY}' "
                         f"(the agent-authorship disclosure obligation is active; "
                         f"the key is required and non-empty in every locale)")

        # 6. in-value [review:] marker detection -- FAIL, not a note
        # (finding T1 / section 2 inversion of v8's non-blocking behaviour).
        marker_keys = [k for k, v in t.items() if find_marker_in_value(v)]
        for mk in ("title", "description", "og_image"):
            if mk in meta and find_marker_in_value(meta[mk]):
                marker_keys.append(f"meta.{mk}")
        if marker_keys:
            fails.append(f"locale '{loc}' has {len(marker_keys)} value(s) still carrying an "
                         f"inline [review:] marker (must be out-of-band in _review): "
                         f"{sorted(marker_keys)[:6]}{' ...' if len(marker_keys) > 6 else ''}")

        # 5 + 12. _review reporting and the authorship contradiction, in one
        # place because they are one fact: `_review` is preview-grade debt, and
        # `authorship: "authored"` is a claim that this locale has none.
        #
        # The count is an OCCURRENCE count -- entries in `_review`, never lines
        # of anything (the v9 rule, findings C8/C9/T10).
        review_list = data.get("_review", []) or []
        authorship = declared_authorship(data, loc, fails)
        if authorship == "authored" and review_list:
            fails.append(f"locale '{loc}': authorship=authored but _review has "
                         f"{len(review_list)} entries.")
        if review_list and authorship != "authored":
            # An authored locale is left out of the review-debt reporting
            # entirely (spec 7.2): it carries no preview-grade debt by
            # definition, and a debt line that counts a locale which cannot
            # owe is a number nobody can act on. An UNDECLARED locale is
            # counted exactly as v9 counted it -- including the default
            # locale, whose implicit authored-ness is v9 semantics, not a
            # written claim.
            notes.append(f"NOTE: locale '{loc}' has {len(review_list)} key(s) flagged for "
                         f"human review in _review (non-blocking).")
            review_total += len(review_list)
        bad_review_keys = [k for k in review_list if not review_key_exists(data, k)]
        if bad_review_keys:
            fails.append(f"locale '{loc}' _review lists {len(bad_review_keys)} key(s) that do "
                         f"not exist in its t/meta: {sorted(bad_review_keys)}")

    # 8/9/10: rendered pages (if dist provided).
    if args.dist:
        for loc in locales:
            rel = "index.html" if loc == default else f"{loc}/index.html"
            page = args.dist / rel
            if not page.exists():
                fails.append(f"rendered page missing for '{loc}': {page}")
                continue
            html_text = page.read_text(encoding="utf-8")

            tag_m = HTML_TAG_RE.search(html_text)
            tag_text = tag_m.group(0) if tag_m else ""
            lang_val = find_html_attr(tag_text, "lang")
            dir_val = find_html_attr(tag_text, "dir")
            if not lang_val:
                fails.append(f"page '{rel}' missing <html lang=...>")
            if not dir_val:
                fails.append(f"page '{rel}' missing <html dir=...> (or it is empty)")

            if pre_launch:
                # The page carries no URL claims at all; asserting symmetry over
                # an empty set would be a vacuous pass, so it is skipped and
                # reported instead (the NOTE above names it once for the run).
                stray = re.findall(r'<link rel="alternate"', html_text)
                if stray:
                    fails.append(f"page '{rel}' carries {len(stray)} alternate link(s) with no "
                                 f"base_url to build them from")
            else:
                for other in locales:
                    if f'hreflang="{other}"' not in html_text:
                        fails.append(f"page '{rel}' hreflang not symmetric: missing '{other}'")
                if 'hreflang="x-default"' not in html_text:
                    fails.append(f"page '{rel}' missing x-default")

            # 9. total alternate-link count must equal len(locales) + 1
            # (one per locale plus x-default) -- catches a duplicate or a
            # count mismatch the substring-presence test alone would miss.
            alt_count = len(re.findall(r'<link rel="alternate"', html_text))
            expected = len(locales) + 1
            if not pre_launch and alt_count != expected:
                fails.append(f"page '{rel}' has {alt_count} <link rel=\"alternate\"> tag(s), "
                             f"expected {expected} (locales + x-default)")

        root = args.dist / "index.html"
        if not root.exists():
            fails.append("root index.html is missing; the default locale must be served at root '/'")
        else:
            root_text = root.read_text(encoding="utf-8")
            root_tag_m = HTML_TAG_RE.search(root_text)
            root_lang = find_html_attr(root_tag_m.group(0), "lang") if root_tag_m else None
            if root_lang != default:
                fails.append(f"root index.html is not the default locale '{default}' "
                             f"(found lang={root_lang!r})")

        # 11. dist/ orphan scan (finding C6).
        scan_dist_orphans(args.dist, locales + [x["slug"].split("/")[0] for x in site.get("pages", [])], fails)

    print("=== i18n-check ===")
    for n in notes:
        print(n)
    if fails:
        print(f"FAIL ({len(fails)}):")
        for f in fails:
            print(f"  - {f}")
        return 1
    print(f"PASS: {len(locales)} locale(s) complete; {review_total} review flag(s) (non-blocking).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
