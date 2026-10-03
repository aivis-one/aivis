#!/usr/bin/env python3
"""AIVIS.ONE courses -- scripts/build: one template + one content file per language -> one page per language.

For every course folder here (a folder holding template.html and content/<locale>.json; `_shared/` is not a course):
    <dist>/courses/<slug>/index.html          the default locale (from site.json)
    <dist>/<locale>/courses/<slug>/index.html every other locale
plus the shared files (<dist>/courses/_shared/{assets,downloads}/) and each course's own downloads
(<dist>/courses/<slug>/downloads/), and the CSP of <dist>/_headers.

Languages: read from <site>/content/site.json (`locales`, `default_locale`, `locale_labels`, `locale_names`, `base_url`).
A new language needs its locale in site.json and one content/<locale>.json in every course folder; nothing else.

Placeholders in template.html (one regex pass, so inserted text is never re-scanned):
    {{t:KEY}}        content value, inserted as HTML as it is (the accepted text, with its own <b>, <span class="grad"> ...)
    {{a:KEY}}        content value as plain text, HTML-escaped (attributes, title)
    {{@href:/p/}}    the page address of /p/ in this page's language;  {{@abs:/p/}} the same with the site origin (base_url)
    {{@lang}} {{@lang_name}} {{@lang_cur}} {{@lang_items}} {{@description}} {{@alternates}} {{@boot}} {{@style}} {{@script}}
                     built here: <html lang>, the language control (a list of plain links with hreflang), the description
                     meta (none when meta.desc is empty), canonical + hreflang links, the inline theme script, the inline
                     stylesheet (fonts + tokens + course.css + the course's extra.css), the inline course script.

CSP: the site serves `Content-Security-Policy: ... style-src <hashes>; script-src <hashes>` for every path, and the pages
are self-contained: style and script are INLINE and this build adds their sha256 to that policy in <dist>/_headers
(no 'unsafe-inline', no 'self' added). No style attribute and no inline event handler is left in a page: the
style attributes of the accepted pages are classes in the course's extra.css.

Usage (run after the site build, which recreates dist/ and its _headers):
    cd landing/site && python scripts/build-site.py --site content/site.json --content-dir content --tokens tokens.tokens.json --assets-dir assets --out dist
    python landing/courses/build.py [--strict]
"""
import argparse
import base64
import hashlib
import html
import json
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SITE_DIR = HERE.parent / "site"
PLACEHOLDER = re.compile(r"\{\{(t:|a:|@)([^{}]*)\}\}")
HASH_MARK = "# courses-hashes:"


def sha(body):
    return "'sha256-%s'" % base64.b64encode(hashlib.sha256(body.encode("utf-8")).digest()).decode("ascii")


def read(p):
    return Path(p).read_text(encoding="utf-8")


def write(p, text):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(text.encode("utf-8"))


def prefix(loc, default):
    return "" if loc == default else "/" + loc


def load_site(path):
    site = json.loads(read(path))
    locales, default = site["locales"], site["default_locale"]
    assert default in locales, "default_locale is not in locales"
    return site, locales, default


def load_courses(locales):
    courses = []
    for d in sorted(HERE.iterdir()):
        if not d.is_dir() or d.name.startswith("_") or not (d / "template.html").is_file():
            continue
        tpl = read(d / "template.html")
        content = {}
        for loc in locales:
            f = d / "content" / (loc + ".json")
            if not f.is_file():
                sys.exit("FAIL: %s has no content/%s.json" % (d.name, loc))
            content[loc] = json.loads(read(f))
        keysets = {loc: set(c) for loc, c in content.items()}
        ref = keysets[locales[0]]
        for loc in locales[1:]:
            if keysets[loc] != ref:
                sys.exit("FAIL: %s keys differ between %s and %s: only-in-%s=%s only-in-%s=%s" % (
                    d.name, locales[0], loc, locales[0], sorted(ref - keysets[loc])[:5], loc, sorted(keysets[loc] - ref)[:5]))
        used = {m.group(2) for m in PLACEHOLDER.finditer(tpl) if m.group(1) in ("t:", "a:")}
        missing = used - ref
        if missing:
            sys.exit("FAIL: %s template uses keys with no content: %s" % (d.name, sorted(missing)[:5]))
        unused = {k for k in ref - used if not k.startswith("meta.")}
        if unused:
            sys.exit("FAIL: %s content keys no template placeholder uses: %s" % (d.name, sorted(unused)[:5]))
        courses.append((d, tpl, content))
    if not courses:
        sys.exit("FAIL: no course folder found")
    return courses


def render(slug, tpl, content, loc, locales, default, site, shared):
    c = content[loc]
    base = (site.get("base_url") or "").rstrip("/")
    labels, names = site.get("locale_labels", {}), site.get("locale_names", {})

    def page(l):
        return prefix(l, default) + "/courses/%s/" % slug

    items = []
    for l in locales:
        cur = ' aria-current="true"' if l == loc else ""
        items.append('        <li><a class="lang__opt" href="%s" hreflang="%s" lang="%s"%s><span class="lang__code">%s</span><span>%s</span></a></li>'
                     % (page(l), l, l, cur, html.escape(labels.get(l, l.upper())), html.escape(names.get(l, l))))
    alternates = ""
    if base:
        alternates = '<link rel="canonical" href="%s">\n' % (base + page(loc))
        for l in locales:
            alternates += '<link rel="alternate" hreflang="%s" href="%s">\n' % (l, base + page(l))
        alternates += '<link rel="alternate" hreflang="x-default" href="%s">\n' % (base + page(default))
    desc = c.get("meta.desc", "")
    built = {
        "lang": loc,
        "lang_name": html.escape(names.get(loc, loc)),
        "lang_cur": html.escape(labels.get(loc, loc.upper())),
        "lang_items": "\n".join(items),
        "description": ('<meta name="description" content="%s">\n' % html.escape(desc, quote=True)) if desc else "",
        "alternates": alternates,
        "boot": shared["boot"],
        "style": shared["style"] + "\n" + shared["extra"][slug],
        "script": shared["script"],
    }

    def sub(m):
        kind, key = m.group(1), m.group(2)
        if kind == "t:":
            return c[key]
        if kind == "a:":
            return html.escape(c[key], quote=True)
        if key.startswith("href:"):
            return prefix(loc, default) + key[5:]
        if key.startswith("abs:"):
            return base + prefix(loc, default) + key[4:]
        return built[key]

    out = PLACEHOLDER.sub(sub, tpl)
    if "{{" in out.replace(shared["script"], "").replace(shared["style"], ""):
        left = re.findall(r"\{\{[^{}]*\}\}", out.replace(shared["script"], "").replace(shared["style"], ""))
        sys.exit("FAIL: %s/%s unresolved placeholder %s" % (slug, loc, left[:3]))
    return out


def csp_lint(text):
    """What a hash-only policy (no 'self' for script or style, no unsafe-inline, no unsafe-hashes) would block."""
    bad = []
    if re.search(r"<script[^>]*\ssrc=", text, re.I):
        bad.append("external script")
    if re.search(r"<link[^>]*rel=[\"']stylesheet", text, re.I):
        bad.append("external stylesheet")
    if re.search(r"<(?!/)[a-zA-Z][^>]*\sstyle=", text):
        bad.append("style attribute")
    if re.search(r"<[a-zA-Z][^>]*\son[a-z]+=", text):
        bad.append("inline event handler")
    if re.search(r"<(?:script|style)\s", text, re.I):
        bad.append("script/style tag with attributes (not matched by a bare-tag hash)")
    if re.search(r"javascript:", text, re.I):
        bad.append("javascript: url")
    return bad


def inline_hashes(text):
    styles = [sha(b) for b in re.findall(r"<style>(.*?)</style>", text, re.S)]
    scripts = [sha(b) for b in re.findall(r"<script>(.*?)</script>", text, re.S)]
    return styles, scripts


def patch_headers(path, styles, scripts):
    """Add the pages' inline hashes to the policy; hashes a previous run added are removed first (listed on a comment line)."""
    lines = read(path).split("\n")
    prev = []
    for i, ln in enumerate(lines):
        if ln.startswith(HASH_MARK):
            prev = ln[len(HASH_MARK):].split()
            lines[i] = None
    lines = [x for x in lines if x is not None]
    for i, ln in enumerate(lines):
        if ln.strip().startswith("Content-Security-Policy:"):
            def fix(directive, add):
                nonlocal ln
                m = re.search(r"(%s )([^;]*)" % directive, ln)
                if not m:
                    sys.exit("FAIL: _headers CSP has no %s directive" % directive)
                have = [h for h in m.group(2).split() if h not in prev]
                for h in add:
                    if h not in have:
                        have.append(h)
                ln = ln[:m.start(2)] + " ".join(have) + ln[m.end(2):]
            fix("style-src", styles)
            fix("script-src", scripts)
            lines[i] = ln
            break
    else:
        sys.exit("FAIL: no Content-Security-Policy line in %s" % path)
    added = sorted(set(styles) | set(scripts))
    while lines and lines[-1] == "":
        lines.pop()
    lines.append(HASH_MARK + " " + " ".join(added))   # a rerun removes exactly these from the policy first
    write(path, "\n".join(lines) + "\n")


def check_links(dist, pages):
    """Every root-absolute or relative src/href of a built page that is a local path must be a file (or a page folder) in dist."""
    missing = []
    for pg in pages:
        text = read(pg)
        for m in re.finditer(r'(?:href|src)="([^"]*)"', text):
            u = m.group(1)
            if not u or u.startswith(("#", "http://", "https://", "mailto:", "data:")):
                continue
            u = u.split("#")[0].split("?")[0]
            target = dist / u.lstrip("/") if u.startswith("/") else pg.parent / u
            if target.is_dir():
                target = target / "index.html"
            if not target.is_file():
                missing.append((str(pg.relative_to(dist)), u))
    return missing


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site", type=Path, default=SITE_DIR / "content" / "site.json")
    ap.add_argument("--dist", type=Path, default=SITE_DIR / "dist")
    ap.add_argument("--strict", action="store_true", help="exit 1 when a built page links a local file that does not exist")
    args = ap.parse_args(argv[1:])
    dist = args.dist
    if not (dist / "_headers").is_file():
        sys.exit("FAIL: %s has no _headers -- run the site build first" % dist)
    site, locales, default = load_site(args.site)
    courses = load_courses(locales)

    sh = HERE / "_shared"
    fonts_css = read(sh / "aivis-fonts.css")
    for f in re.findall(r"url\('/assets/fonts/([^']+)'\)", fonts_css):
        if not (dist / "assets" / "fonts" / f).is_file():
            sys.exit("FAIL: font /assets/fonts/%s is not in %s (the site build ships it)" % (f, dist))
    shared = {
        "boot": read(sh / "theme-boot.js"),
        "style": "\n".join([fonts_css, read(sh / "aivis-tokens.css"), read(sh / "course.css")]),
        "script": read(sh / "course.js"),
        "extra": {d.name: read(d / "extra.css") if (d / "extra.css").is_file() else "" for d, _, _ in courses},
    }
    for k in ("boot", "script"):
        if "</script" in shared[k].lower():
            sys.exit("FAIL: shared %s contains </script" % k)
    if "</style" in shared["style"].lower():
        sys.exit("FAIL: shared style contains </style")

    # clean what a previous run wrote
    shutil.rmtree(dist / "courses", ignore_errors=True)
    for loc in locales:
        if loc != default:
            shutil.rmtree(dist / loc / "courses", ignore_errors=True)

    pages, styles, scripts = [], [], []
    for d, tpl, content in courses:
        slug = d.name
        for loc in locales:
            out = render(slug, tpl, content, loc, locales, default, site, shared)
            bad = csp_lint(out)
            if bad:
                sys.exit("FAIL: %s/%s would not run under a hash-only CSP: %s" % (slug, loc, bad))
            dst = dist / prefix(loc, default).lstrip("/") / "courses" / slug / "index.html"
            write(dst, out)
            pages.append(dst)
            st, sc = inline_hashes(out)
            styles += [x for x in st if x not in styles]
            scripts += [x for x in sc if x not in scripts]
        if (d / "downloads").is_dir():
            shutil.copytree(d / "downloads", dist / "courses" / slug / "downloads")
    shutil.copytree(sh / "assets", dist / "courses" / "_shared" / "assets")
    shutil.copytree(sh / "downloads", dist / "courses" / "_shared" / "downloads")
    patch_headers(dist / "_headers", styles, scripts)

    missing = check_links(dist, pages)
    print("built %d pages: %s" % (len(pages), ", ".join(str(p.relative_to(dist)) for p in pages)))
    print("CSP: %d inline style hash(es), %d inline script hash(es) added to %s" % (len(styles), len(scripts), dist / "_headers"))
    for pg, u in missing:
        print("MISSING LOCAL FILE: %s -> %s" % (pg, u))
    if missing and args.strict:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
