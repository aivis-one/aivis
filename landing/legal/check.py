#!/usr/bin/env python3
"""Structure and consistency check of the legal documents (public/ and cabinet/).

Prints, per document, the blocks it holds in each language and every problem found. Exit 1 on any
problem. Checks: a text file per language for every document, the same structure in every language
(blocks, lists, heading anchors), unknown or malformed placeholders, facts that lack a language, forbidden
text (counsel and review markers, version stamps, draft words) in any published text, quote style (Russian
text uses angle quotes, English text none), the registry, and that the local-storage keys named in
facts.json (site.storage.*) are exactly the keys the site's scripts use (the scripts folder is read only;
skipped with a note when it is absent).

Usage:
  python check.py                     check the live tree
  python check.py --assets DIR        scripts folder to scan for storage keys
  python check.py --self-test         plant defects in a copy and prove each one fires
"""
import argparse
import json
import re
import shutil
import sys
from html.parser import HTMLParser
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build  # noqa: E402

DEFAULT_ASSETS = HERE.parent / "site" / "assets"
KEY_LITERAL = re.compile(r"localStorage\s*\.\s*(?:getItem|setItem|removeItem)\s*\(\s*['\"]([^'\"]+)['\"]")
KEY_CONST = re.compile(r"\b[A-Z_]*KEY[A-Z_]*\s*=\s*['\"]([^'\"]+)['\"]")


def scan_storage_keys(assets):
    """Keys the shipped scripts use. assets/v1 is a retired pack that no built page references,
    so it is skipped; the built pages in the sibling dist/ are scanned for inline scripts too."""
    found = {}
    files = [f for f in Path(assets).rglob("*.js")
             if "v1" not in f.relative_to(assets).parts]
    dist = Path(assets).parent / "dist"
    if dist.is_dir():
        files += list(dist.rglob("*.html"))
    for f in sorted(files):
        txt = f.read_text(encoding="utf-8", errors="replace")
        if "localStorage" not in txt:
            continue
        for rx in (KEY_LITERAL, KEY_CONST):
            for m in rx.finditer(txt):
                found.setdefault(m.group(1), set()).add(f.name)
    return found


class _Metas(HTMLParser):
    """the same reading of <meta name content> and <title> as the seeder's _MetadataParser"""

    def __init__(self):
        super().__init__()
        self.meta, self.title, self._in_title = {}, "", False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta" and a.get("name"):
            self.meta[a["name"]] = a.get("content") or ""
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data


def p_title(path):
    p = _Metas()
    p.feed(path.read_text(encoding="utf-8"))
    return p.title


def all_names(world):
    return list(world["docs"])


def style_errors(world):
    errs = []
    for name in all_names(world):
        for lang, parsed in world["docs"][name]["md"].items():
            for n, v in enumerate(build.doc_texts(parsed)):
                if lang == "ru" and '"' in v:
                    errs.append(f"{name}/{lang}:{n}: straight double quote in Russian text, use angle quotes")
                if lang == "en" and ("«" in v or "»" in v):
                    errs.append(f"{name}/{lang}:{n}: angle quotes in English text")
                if "  " in v:
                    errs.append(f"{name}/{lang}:{n}: double space")
    return errs


def storage_errors(world, assets):
    node = world["facts"].get("site", {}).get("storage", {})
    declared = {v for v in node.values() if isinstance(v, str)}
    if not Path(assets).is_dir():
        return [], f"storage keys: scripts folder {assets} not found, not checked"
    found = scan_storage_keys(assets)
    errs = []
    for k in sorted(set(found) - declared):
        errs.append(f"storage: the site scripts use localStorage key {k!r} ({', '.join(sorted(found[k]))}) "
                    f"that facts.json site.storage does not declare, so the cookie notice would omit it")
    for k in sorted(declared - set(found)):
        errs.append(f"storage: facts.json declares key {k!r} that no site script uses")
    return errs, f"storage keys in scripts {sorted(found)} / declared {sorted(declared)}"


# Text that must never appear in a published document, in any language (rule A1 of the home).
FORBIDDEN = [
    ("[COUNSEL", re.compile(r"\[COUNSEL", re.I)),
    ("[REVIEW", re.compile(r"\[REVIEW", re.I)),
    ("REVIEW-GATE", re.compile(r"REVIEW-GATE", re.I)),
    ("Версия 0.", re.compile(r"Версия 0\.")),
    ("Version 0.", re.compile(r"Version 0\.")),
    ("draft", re.compile(r"\bdraft", re.I)),
    ("черновик", re.compile(r"черновик", re.I)),
    ("Questions for counsel", re.compile(r"Questions for counsel", re.I)),
]


def forbidden_errors(world):
    """Scan what is published: every document rendered in every language (markdown and html), plus the
    shared facts. The sources are scanned too, so a marker in any text is found."""
    errs = []

    def scan(where, text):
        for label, rx in FORBIDDEN:
            if rx.search(text):
                errs.append(f"{where}: forbidden text '{label}' in the published text")

    for name in all_names(world):
        for lang in world["langs"]:
            if lang not in world["docs"][name]["md"]:
                continue
            try:
                md, ht, _, _ = build.render_doc(world, name, lang, True)
            except Exception as exc:  # a broken tree is reported by the other checks
                errs.append(f"{name}/{lang}: could not be rendered for the forbidden-text scan: {exc}")
                continue
            scan(f"{name}/{lang} (rendered)", md + "\n" + ht)
        for lang, parsed in world["docs"][name]["md"].items():
            for n, v in enumerate(build.doc_texts(parsed)):
                scan(f"{name}/{lang}:{n}", v)
    scan("facts.json", json.dumps(world["facts"], ensure_ascii=False))
    scan("registry.json", json.dumps(world["labels"], ensure_ascii=False))
    return errs


def report(root, assets, quiet=False):
    world = build.load_world(root)
    errs = build.collect_errors(world) + style_errors(world) + forbidden_errors(world)
    serr, note = storage_errors(world, assets) if assets else ([], "storage keys: not checked")
    errs += serr
    if not quiet:
        langs = world["langs"]
        print("languages: " + ", ".join(langs))
        print("%-12s %-8s " % ("doc", "where") + "  ".join("%-14s" % (l + " blocks/texts") for l in langs))
        for name in all_names(world):
            doc = world["docs"][name]
            cells = []
            for l in langs:
                p = doc["md"].get(l)
                cells.append("%-14s" % (f"{len(p['blocks'])}/{len(build.doc_texts(p))}" if p else "missing"))
            print("%-12s %-8s " % (name, "public" if doc["scope"] == "site" else "cabinet") + "  ".join(cells))
        print(note)
        print("CHECK OK" if not errs else "CHECK FAILED: %d problem(s)" % len(errs))
        for e in errs:
            print("  - " + e)
    return errs


# ---------------------------------------------------------------- self test

def _copy(root, dest):
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(root, dest, ignore=shutil.ignore_patterns("out", "out-public", ".selftest", "__pycache__"))


def _edit(path, fn):
    d = json.loads(path.read_text(encoding="utf-8"))
    fn(d)
    path.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _md(t, doc, lang):
    return t / "public" / doc / f"{doc}.{lang}.md"


def _body_index(lines):
    """index of the third plain paragraph line of a text file (a body text, not the title or a heading)"""
    plain = [i for i, x in enumerate(lines) if i > 0 and x.strip() and not re.match(r"^(#|- |\d+\. |\|)", x)]
    return plain[2]


def _plant(path, fn):
    """rewrite one body line of a text file (a paragraph or a list line): fn(old line) -> new line.
    Used only to append text, so a list line stays a list line."""
    lines = path.read_text(encoding="utf-8").split("\n")
    body = [i for i, x in enumerate(lines) if i > 0 and x.strip() and not re.match(r"^(#|\|)", x)]
    i = body[2]
    lines[i] = fn(lines[i])
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def _drop_paragraph(path):
    lines = path.read_text(encoding="utf-8").split("\n")
    i = _body_index(lines)
    del lines[i:i + 2]
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def self_test(root):
    root = Path(root)
    work = root / ".selftest"
    results = []

    def case(label, mutate, expect, via_build=False):
        t = work / "case"
        _copy(root, t)
        mutate(t)
        if via_build:
            import io
            import contextlib
            err, outp = io.StringIO(), t / "out"
            with contextlib.redirect_stderr(err):
                rc = build.run(t, outp)
            fired = rc != 0 and not outp.exists() and expect in err.getvalue()
        else:
            errs = report(t, None, quiet=True)
            fired = any(expect in e for e in errs)
        results.append((label, fired))
        print(("PASS  " if fired else "FAIL  ") + label)

    def add_cabinet(t, langs=("en", "ru")):
        for lang in langs:
            p = t / "cabinet" / "nda" / f"nda.{lang}.md"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("# Non-Disclosure Agreement\n\n## Parties {#nda-parties}\n\nThe parties are {company.name}.\n"
                         if lang == "en" else
                         "# Соглашение о неразглашении\n\n## Стороны {#nda-parties}\n\nСтороны: {company.name}.\n",
                         encoding="utf-8", newline="\n")

    try:
        # control: the unmodified copy must be clean, or no later PASS means anything
        t = work / "case"
        _copy(root, t)
        clean = report(t, None, quiet=True)
        results.append(("control: unmodified copy has no problems", not clean))
        print(("PASS  " if not clean else "FAIL  ") + "control: unmodified copy has no problems" + ("" if not clean else f" ({clean[:2]})"))

        case("a missing language file is caught", lambda t: _md(t, "privacy", "ru").unlink(),
             "privacy: no text file for language ru")
        case("a paragraph missing in ru is caught (structure differs)", lambda t: _drop_paragraph(_md(t, "privacy", "ru")),
             "privacy/ru: the structure differs")
        case("an extra block in en is caught (structure differs)",
             lambda t: _md(t, "imprint", "en").write_text(_md(t, "imprint", "en").read_text(encoding="utf-8") + "\nAn extra paragraph.\n",
                                                          encoding="utf-8", newline="\n"),
             "imprint/ru: the structure differs")
        case("a heading without its title line is caught",
             lambda t: _md(t, "terms", "en").write_text("No title here\n", encoding="utf-8", newline="\n"),
             "line 1 must be")
        case("unknown placeholder is caught", lambda t: _plant(_md(t, "cookies", "ru"), lambda s: s + " {company.nonexistent}"),
             "unknown placeholder {company.nonexistent}")
        case("malformed placeholder is caught", lambda t: _plant(_md(t, "licence", "en"), lambda s: s + " {Company Name}"),
             "malformed placeholder")
        case("a planted counsel marker in the published text is caught",
             lambda t: _plant(_md(t, "privacy", "en"), lambda s: s + " [COUNSEL C99: planted]"), "forbidden text '[COUNSEL'")
        case("a planted review banner is caught", lambda t: _plant(_md(t, "terms", "ru"), lambda s: s + " [REVIEW-GATE]"),
             "forbidden text 'REVIEW-GATE'")
        case("a planted version stamp (Russian) is caught", lambda t: _plant(_md(t, "cookies", "ru"), lambda s: s + " Версия 0.1, 1 января."),
             "forbidden text 'Версия 0.'")
        case("a planted version stamp (English) is caught", lambda t: _plant(_md(t, "licence", "en"), lambda s: s + " Version 0.2 of the text."),
             "forbidden text 'Version 0.'")
        case("a planted draft word is caught", lambda t: _plant(_md(t, "imprint", "en"), lambda s: s + " This is a draft text."),
             "forbidden text 'draft'")
        case("a planted draft word (Russian) is caught", lambda t: _plant(_md(t, "imprint", "ru"), lambda s: s + " Это черновик."),
             "forbidden text 'черновик'")
        case("fact lacking a language is caught", lambda t: _edit(t / "facts.json", lambda d: d["company"]["address"].pop("ru")),
             "company.address has no value for language ru")
        case("straight quotes in Russian text are caught", lambda t: _plant(_md(t, "terms", "ru"), lambda s: s + ' Он сказал "так"'),
             "straight double quote")
        case("a document missing from the registry is caught",
             lambda t: _edit(t / "registry.json", lambda d: d["documents"].remove(next(e for e in d["documents"] if e["id"] == "terms"))),
             "document terms is missing from the registry")
        case("a registry title that differs from the document is caught",
             lambda t: _edit(t / "registry.json", lambda d: d["documents"][0]["title"].update({"en": "Other title"})),
             "title for en differs")
        case("a cabinet document with one language only is caught", lambda t: add_cabinet(t, ("en",)),
             "nda: no text file for language ru")
        case("build refuses on a document missing from the registry and writes nothing",
             lambda t: _edit(t / "registry.json", lambda d: d["documents"].remove(next(e for e in d["documents"] if e["id"] == "terms"))),
             "document terms is missing from the registry", via_build=True)
        case("build refuses on a missing language file and writes nothing", lambda t: _md(t, "privacy", "ru").unlink(),
             "privacy: no text file for language ru", via_build=True)
        case("build refuses on an unknown placeholder",
             lambda t: _plant(_md(t, "cookies", "en"), lambda s: s + " {no.such.fact}"),
             "unknown placeholder {no.such.fact}", via_build=True)

        def add_lang(t):
            for f in list((t / "public").glob("*/*.en.md")):
                if f.parent.name != "privacy":
                    shutil.copy(f, f.with_name(f.name.replace(".en.md", ".de.md")))
        case("a new language missing from one document is caught", add_lang, "privacy: no text file for language de")

        # the cabinet output: off by default, written only when asked
        import io
        import contextlib
        t = work / "case"
        _copy(root, t)
        add_cabinet(t)
        sink = io.StringIO()
        with contextlib.redirect_stdout(sink):
            rc0 = build.run(t, t / "out")
        off = rc0 == 0 and not build.default_cabinet_out(t).exists() and not (t / "out" / "en" / "nda.html").exists()
        results.append(("cabinet output is off by default", off))
        print(("PASS  " if off else "FAIL  ") + "cabinet output is off by default")
        dest = work / "cab-out"
        with contextlib.redirect_stdout(sink):
            rc1 = build.run(t, t / "out", cabinet=True, cabinet_out=dest)
        got = (dest / "en" / "nda.html").is_file() and (dest / "ru" / "nda.html").is_file() \
            and "AIVIS.ONE LLC" in (dest / "en" / "nda.html").read_text(encoding="utf-8") and not (dest / "en" / "privacy.html").exists()
        results.append(("cabinet output is written when switched on, the cabinet documents only", rc1 == 0 and got))
        print(("PASS  " if rc1 == 0 and got else "FAIL  ") + "cabinet output is written when switched on, the cabinet documents only")

        # the seeder's reader (backend/scripts/seed_documents.py _parse_metadata): type and language metas required
        # and the language meta equal to the folder; roles optional. A page the seeder would skip fails here.
        def seeder_meta(path, folder_lang):
            p = _Metas()
            p.feed(path.read_text(encoding="utf-8"))
            if not (p.meta.get("aivis-document-type") or "").strip():
                return None
            if (p.meta.get("aivis-language") or "").strip() != folder_lang:
                return None
            return p.meta

        meta_en = seeder_meta(dest / "en" / "nda.html", "en")
        meta_ru = seeder_meta(dest / "ru" / "nda.html", "ru")
        ok = bool(meta_en and meta_ru and meta_en["aivis-document-type"] == "nda" and "aivis-required-for-roles" not in meta_en
                  and "Non-Disclosure Agreement" in (p_title(dest / "en" / "nda.html")))
        results.append(("a cabinet page carries the metas the seeder reads (type, language equal to its folder, title)", ok))
        print(("PASS  " if ok else "FAIL  ") + "a cabinet page carries the metas the seeder reads (type, language equal to its folder, title)")
        _edit(t / "registry.json", lambda d: d["documents"].append(
            {"id": "nda", "scope": "cabinet", "title": {"en": "Non-Disclosure Agreement", "ru": "Соглашение о неразглашении"},
             "edition": 1, "date": "2026-10-13", "roles": ["investor", "agent"]}))
        dest2 = work / "cab-out2"
        with contextlib.redirect_stdout(sink):
            rc2 = build.run(t, t / "out", cabinet=True, cabinet_out=dest2)
        m2 = seeder_meta(dest2 / "en" / "nda.html", "en")
        ok2 = rc2 == 0 and bool(m2) and m2.get("aivis-required-for-roles") == "investor,agent"
        results.append(("the roles of a cabinet entry in registry.json reach the aivis-required-for-roles meta", ok2))
        print(("PASS  " if ok2 else "FAIL  ") + "the roles of a cabinet entry in registry.json reach the aivis-required-for-roles meta")
        # control: the old bare fragment would be skipped by the same reader
        bare = work / "bare.html"
        bare.write_text('<article class="legal" lang="en" data-doc="nda">\n<h1>x</h1>\n</article>\n', encoding="utf-8")
        ok3 = seeder_meta(bare, "en") is None
        results.append(("control: a bare article fragment is skipped by the seeder's rule", ok3))
        print(("PASS  " if ok3 else "FAIL  ") + "control: a bare article fragment is skipped by the seeder's rule")
    finally:
        if work.exists():
            shutil.rmtree(work)
    bad = [l for l, ok in results if not ok]
    print("SELF-TEST " + ("PASSED: %d of %d checks fired as planned" % (len(results), len(results)) if not bad
                          else "FAILED: " + "; ".join(bad)))
    return 0 if not bad else 1


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=str(HERE))
    ap.add_argument("--assets", default=str(DEFAULT_ASSETS))
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    if a.self_test:
        return self_test(a.root)
    return 1 if report(a.root, a.assets) else 0


if __name__ == "__main__":
    sys.exit(main())
