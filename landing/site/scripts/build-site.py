#!/usr/bin/env python3
"""landing-studio v10.0.0 -- scripts/build-site.py

Orchestrate the full Cloudflare Pages package from site.json + content/ + tokens.
For each locale, render one self-contained page (default locale -> /index.html,
others -> /{lang}/index.html). Then emit the deploy package:
  - sitemap index + per-locale sitemaps (hreflang lives here at scale; Invariant 3)
  - _redirects (static; .pages.dev canonicalization placeholder)
  - _headers (cache + security)
  - robots.txt
  - cloudflare-redirect-rule.txt (OPTIONAL Accept-Language auto-detect snippet for the dashboard)

Default locale is a project-level choice (Q3) -- English is a convention, not a
rule; the code is fully parameterized on site.json's `default_locale`.
Skill does not push to Cloudflare -- it produces the deployable tree.

Atomic build (v9 / findings C6, C7, C21):
  - Every locale is rendered into a FRESH TEMP DIRECTORY, never the real `dist/`.
  - A per-locale render failure is caught: the failing locale and the child
    process's stderr are printed, and the function returns 1 WITHOUT touching
    the real `dist/` at all (it was never written to).
  - Only on full success (every locale rendered + every package file written)
    is the temp directory swapped into place as `dist/`, via a same-filesystem
    rename so the swap is atomic and a stale/partial `dist/` can never survive
    a rebuild. Dropping a locale and rebuilding therefore leaves no orphan
    page or sitemap -- the old tree is replaced wholesale, never merged into.
  - `--keep-dist` opts out of the swap-and-prune (for debugging): the rendered
    tree is left in its temporary location and the real `dist/` is untouched.
  - `base_url` PRESENT but not http(s) fails BEFORE any rendering starts.
  - `base_url` ABSENT builds in PRE-LAUNCH mode: the pages render, and every
    artifact that would have to state an origin is omitted rather than invented
    -- no canonical link, no hreflang set, no og:url, no sitemap, no robots.txt.
    The pre-launch case (a project with no domain yet) is exactly what this
    release is built around; requiring a field with no honest value forced the
    operator to invent one to build at all.

`locale_path` SSOT (finding D3): imported from render-page.py, never redefined
here. build-site.py only depends on that one function plus the ability to
invoke render-page.py as a subprocess -- it does not import or rely on any
other internals of that module (render-page.py is owned/edited elsewhere).

Usage:
  python build-site.py --site site.json --content-dir content --tokens tokens.tokens.json \\
      --assets-dir assets --out dist [--animate] [--keep-dist]
"""
import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BASE_URL_RE = re.compile(r"^https?://", re.IGNORECASE)


def _load_render_module(here):
    """Import locale_path from render-page.py (the SSOT -- finding D3). This
    is the ONLY thing build-site.py takes from that module; render-page.py is
    owned and edited by a different agent, so nothing else about its internals
    is assumed here."""
    render_page_path = here / "render-page.py"
    spec = importlib.util.spec_from_file_location("renderpage_for_buildsite", render_page_path)
    mod = importlib.util.module_from_spec(spec)
    # Same guard claims-check.py and contrast-check.py use: without it this
    # import drops a scripts/__pycache__/ into the tree being built, which then
    # shows up as an untracked directory in a packaged child's round-trip diff.
    prev = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.dont_write_bytecode = prev
    return mod


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def sitemap_for(site, locale, locale_path):
    """One <url> per INDEXABLE page of the locale (the home, then every page of site.json pages not marked
    indexable:false), each with the hreflang set of that page; the noindex legal pages stay out until approved."""
    base = site.get("base_url", "").rstrip("/")
    default = site["default_locale"]
    slugs = [""] + [x["slug"].strip("/") + "/" for x in site.get("pages", []) if x.get("indexable", True)]
    out = []
    for slug in slugs:
        url = base + locale_path(locale, default) + slug
        alts = "".join(
            '\n    <xhtml:link rel="alternate" hreflang="%s" href="%s"/>' % (loc, base + locale_path(loc, default) + slug)
            for loc in site["locales"])
        alts += '\n    <xhtml:link rel="alternate" hreflang="x-default" href="%s"/>' % (base + locale_path(default, default) + slug)
        out.append('  <url>\n    <loc>%s</loc>%s\n  </url>\n' % (url, alts))
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
            'xmlns:xhtml="http://www.w3.org/1999/xhtml">\n' + "".join(out) + '</urlset>\n')


def sitemap_index(site):
    base = site.get("base_url", "").rstrip("/")
    items = "".join('  <sitemap><loc>%s/sitemap-%s.xml</loc></sitemap>\n' % (base, loc) for loc in site["locales"])
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n%s</sitemapindex>\n' % items)


def redirects_file(site):
    # Static _redirects: trailing-slash normalization for locale roots. Accept-Language
    # detection is NOT done here (static file cannot read headers) -- see the dashboard snippet.
    lines = ["# landing-studio _redirects -- static rules only.",
             "# Accept-Language auto-detect = Cloudflare Redirect Rule (see cloudflare-redirect-rule.txt).",
             "# Do NOT add header-based logic here; _redirects is static."]
    for loc in site["locales"]:
        if loc == site["default_locale"]:
            continue
        lines.append(f"/{loc} /{loc}/ 301")
    return "\n".join(lines) + "\n"


def headers_file(csp=None):
    lines = ["# AIVIS.ONE _headers -- security baseline. Pages are self-contained documents; fonts, marks and",
             "# the photograph are served from /assets/. The CSP admits the inline style and script blocks by",
             "# sha256 only (no unsafe-inline) and no host but the site itself.",
             "/*",
             "  X-Content-Type-Options: nosniff",
             "  Referrer-Policy: strict-origin-when-cross-origin",
             "  X-Frame-Options: SAMEORIGIN",
             "  Strict-Transport-Security: max-age=31536000; includeSubDomains",
             "  Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=(), usb=(), interest-cohort=()",
             "  Cross-Origin-Opener-Policy: same-origin"]
    if csp:
        lines.append("  Content-Security-Policy: " + csp)
    lines += ["/assets/*", "  Cache-Control: public, max-age=31536000, immutable",
              "# the closed investor section: never indexed, never followed",
              "/invest/*", "  X-Robots-Tag: noindex, nofollow",
              "/ru/invest/*", "  X-Robots-Tag: noindex, nofollow"]
    return "\n".join(lines) + "\n"


def robots_file(site):
    base = site.get("base_url", "").rstrip("/")
    return "User-agent: *\nAllow: /\n\nSitemap: %s/sitemap.xml\n" % base


def redirect_rule_snippet(site):
    default = site["default_locale"]
    non_default = [l for l in site["locales"] if l != default]
    lines = [
        "Cloudflare Redirect Rule (OPTIONAL) -- Accept-Language auto-detect at root.",
        "Dashboard: Rules -> Redirect Rules -> Create. Apply ONLY to the bare root path to avoid loops.",
        "When incoming request URI Path equals \"/\" AND accepted_languages matches, redirect to /{lang}/.",
        "",
        "Expression examples (one rule per non-default locale):",
    ]
    for loc in non_default:
        lines.append(
            '  (http.request.uri.path eq "/" and '
            'any(starts_with(http.request.accepted_languages[*], "%s")))  ->  /%s/  (302)' % (loc, loc)
        )
    lines += [
        "",
        "Guards: scope to path eq \"/\" only (never /{lang}/), use 302 (not 301) so users can switch,",
        "and leave the default locale (%s) served at root with no rule (prevents infinite redirects)." % default,
    ]
    return "\n".join(lines) + "\n"


def _render_all_locales(site, args, here, tmp_dist, locale_path):
    """Render every locale into tmp_dist. Returns (rendered_list, None) on
    success, or (None, error_message) on the first failure -- the caller is
    responsible for never having touched the real dist/ up to this point."""
    default = site["default_locale"]
    fallback = args.content_dir / f"{default}.json"
    rendered = []
    for loc in site["locales"]:
        content = args.content_dir / f"{loc}.json"
        if not content.exists():
            return None, f"missing content for locale '{loc}': {content}"
        rel = "index.html" if loc == default else f"{loc}/index.html"
        out_page = tmp_dist / rel
        cmd = [sys.executable, str(here / "render-page.py"),
               "--site", str(args.site), "--content", str(content),
               "--tokens", str(args.tokens), "--assets-dir", str(args.assets_dir),
               "--locale", loc, "--out", str(out_page), "--fallback", str(fallback)]
        if args.animate:
            cmd.append("--animate")
        jobs = [(out_page, [])] + [
            ((tmp_dist / ("" if loc == default else loc) / pg["slug"].strip("/") / "index.html"), ["--page", pg["slug"]])
            for pg in site.get("pages", [])]
        for out_one, extra in jobs:
            cmd_one = [x if x != str(out_page) else str(out_one) for x in cmd] + extra
            proc = subprocess.run(cmd_one, capture_output=True, text=True)
            if proc.returncode != 0:
                stderr = proc.stderr.strip() or "(no stderr output)"
                return None, f"render failed for locale '{loc}' {extra} (exit {proc.returncode}):\n{stderr}"
            if proc.stderr.strip():
                print(f"WARN: locale '{loc}' {extra}:\n{proc.stderr.strip()}", file=sys.stderr)
        rendered.append(loc)
    return rendered, None


def main(argv):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--site", required=True, type=Path)
    p.add_argument("--content-dir", required=True, type=Path)
    p.add_argument("--tokens", required=True, type=Path)
    p.add_argument("--assets-dir", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--animate", action="store_true")
    p.add_argument("--keep-dist", action="store_true",
                    help="Render into a temp dir but do not swap it into place; "
                         "leaves the real dist/ untouched (for debugging).")
    args = p.parse_args(argv[1:])

    here = Path(__file__).parent
    try:
        render_mod = _load_render_module(here)
        locale_path = render_mod.locale_path
    except Exception as e:
        print(f"FAIL: could not import locale_path from render-page.py (SSOT): {e}", file=sys.stderr)
        return 1

    try:
        site = json.loads(Path(args.site).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"FAIL: cannot read/parse site file '{args.site}': {e}", file=sys.stderr)
        return 1

    default = site.get("default_locale")
    if default not in site.get("locales", []):
        print(f"FAIL: default_locale '{default}' is not in locales {site.get('locales')}; "
              f"add it so the default locale is rendered at root '/'.", file=sys.stderr)
        return 1

    # finding C21, revised in the v10 completion pass: a base_url that is
    # PRESENT must be absolute http(s) -- a malformed origin is still a hard
    # failure before any rendering. An ABSENT base_url is the pre-launch case
    # and builds, with every origin-dependent artifact omitted rather than
    # invented (see the docstring, and build_head_urls in render-page.py).
    base_url = (site.get("base_url") or "").strip()
    if base_url and not BASE_URL_RE.match(base_url):
        print(f"FAIL: site.json base_url is present but not http(s): {base_url!r}. Remove the "
              f"key entirely to build in pre-launch mode, or give it an absolute origin.",
              file=sys.stderr)
        return 1
    pre_launch = not base_url

    dist = args.out
    dist.parent.mkdir(parents=True, exist_ok=True)

    # Render + package into a fresh temp dir on the SAME filesystem as dist's
    # parent, so the final swap is a single atomic rename (findings C6/C7).
    tmp_dir = Path(tempfile.mkdtemp(prefix=".ls-build-", dir=str(dist.parent)))
    try:
        rendered, err = _render_all_locales(site, args, here, tmp_dir, locale_path)
        if err is not None:
            print(f"FAIL: {err}", file=sys.stderr)
            print(f"NOTE: the real '{dist}' was not touched.", file=sys.stderr)
            return 1

        # Locale routing, headers and the redirect snippet are origin-free, so
        # they are written in both modes. The sitemaps and robots.txt are not:
        # every URL they carry would have to be absolute.
        write(tmp_dir / "_redirects", redirects_file(site))
        styles, scripts = [], []
        for page in sorted(tmp_dir.rglob("*.html")):
            st, sc = render_mod.inline_hashes(page.read_text(encoding="utf-8"))
            styles += [x for x in st if x not in styles]
            scripts += [x for x in sc if x not in scripts]
        write(tmp_dir / "_headers", headers_file(render_mod.csp_policy(styles, scripts, for_header=True)))
        # static files the pages reference: fonts (design-system woff2) and the marks / photograph
        fonts_out = tmp_dir / "assets" / "fonts"
        fonts_out.mkdir(parents=True, exist_ok=True)
        for f in sorted((args.assets_dir / "ds" / "fonts").glob("*.woff2")):
            if "noto-deva" not in f.name:
                shutil.copy2(f, fonts_out / f.name)
        img_out = tmp_dir / "assets" / "img"
        img_out.mkdir(parents=True, exist_ok=True)
        for f in sorted((args.assets_dir / "img").iterdir()):
            if f.is_file():
                shutil.copy2(f, img_out / f.name)
        write(tmp_dir / "cloudflare-redirect-rule.txt", redirect_rule_snippet(site))
        # the investor documents' Markdown, offered as a template next to each document page
        for loc in site["locales"]:
            for pg in site.get("pages", []):
                doc = pg.get("invest_doc")
                if doc:
                    src = Path(__file__).resolve().parent.parent / site["invest_dir"] / loc / (doc + ".md")
                    dst = tmp_dir / ("" if loc == default else loc) / pg["slug"].strip("/") / (doc + ".markdown")
                    if not src.exists():
                        print(f"FAIL: investor document source missing: {src}", file=sys.stderr)
                        return 1
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
        if pre_launch:
            print("PRE-LAUNCH: site.json carries no base_url, so this build omitted the "
                  "canonical link, the hreflang set, og:url, sitemap-*.xml, sitemap.xml and "
                  "robots.txt. The pages are complete and deployable; they are not indexable "
                  "until base_url is set and the site is rebuilt.")
        else:
            for loc in site["locales"]:
                write(tmp_dir / f"sitemap-{loc}.xml", sitemap_for(site, loc, locale_path))
            write(tmp_dir / "sitemap.xml", sitemap_index(site))
            write(tmp_dir / "robots.txt", robots_file(site))

        if args.keep_dist:
            kept = dist.parent / (dist.name + ".new")
            if kept.exists():
                shutil.rmtree(kept)
            tmp_dir.rename(kept)
            tmp_dir = None  # already moved; skip cleanup in finally
            print(f"OK: built {len(rendered)} locales into {kept} (--keep-dist set; "
                  f"real '{dist}' left untouched).")
            return 0

        # Atomic swap: rename the old dist/ aside, move the new tree into
        # place, then remove the old one. If the second rename fails for any
        # reason, put the old tree back so dist/ is never left missing.
        old_backup = None
        if dist.exists():
            old_backup = dist.parent / (dist.name + f".old-{os.getpid()}")
            if old_backup.exists():
                shutil.rmtree(old_backup)
            dist.rename(old_backup)
        try:
            tmp_dir.rename(dist)
            tmp_dir = None  # moved; skip cleanup in finally
        except Exception:
            if old_backup is not None:
                old_backup.rename(dist)
            raise
        if old_backup is not None:
            shutil.rmtree(old_backup, ignore_errors=True)

        pkg = ("pages + _redirects + _headers + redirect-rule snippet (PRE-LAUNCH: no sitemap, "
               "no robots.txt)" if pre_launch else
               "pages + sitemap index + _redirects + _headers + robots.txt + redirect-rule snippet")
        print(f"OK: built {len(rendered)} locales into {dist} (default '{default}' at root). "
              f"Package: {pkg}.")
        return 0
    finally:
        if tmp_dir is not None and tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
