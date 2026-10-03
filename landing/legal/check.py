#!/usr/bin/env python3
"""Key parity and consistency check of the public legal documents.

Prints, per document, the keys the template needs and how many each language holds, then every
problem found. Exit 1 on any problem. Checks: key parity (missing / orphan keys per language),
unknown or malformed placeholders, facts that lack a language, forbidden text (counsel and review
markers, version stamps, draft words) in any published text, quote style (Russian text uses angle quotes, English text none), and that the
local-storage keys named in facts.json (site.storage.*) are exactly the keys the site's scripts
use (the scripts folder is read only; skipped with a note when it is absent).

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


def style_errors(world):
    errs = []
    for name in ["_common"] + world["order"]:
        i18n = world["common"]["i18n"] if name == "_common" else world["docs"][name]["i18n"]
        for lang, table in i18n.items():
            for k, v in table.items():
                if not isinstance(v, str):
                    continue
                if lang == "ru" and '"' in v:
                    errs.append(f"{name}/{lang}:{k}: straight double quote in Russian text, use angle quotes")
                if lang == "en" and ("«" in v or "»" in v):
                    errs.append(f"{name}/{lang}:{k}: angle quotes in English text")
                if "  " in v:
                    errs.append(f"{name}/{lang}:{k}: double space")
    return errs


def storage_errors(world, assets):
    declared = set()
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
    shared facts. The sources are scanned too, so a marker hidden in a key the template does not use
    is still found."""
    errs = []

    def scan(where, text):
        for label, rx in FORBIDDEN:
            if rx.search(text):
                errs.append(f"{where}: forbidden text '{label}' in the published text")

    for lang in world["langs"]:
        for name in world["order"]:
            try:
                md, ht, _, _ = build.render_doc(world, name, lang, True)
            except Exception as exc:  # a broken tree is reported by the other checks
                errs.append(f"{name}/{lang}: could not be rendered for the forbidden-text scan: {exc}")
                continue
            scan(f"{name}/{lang} (rendered)", md + "\n" + ht)
    for name in ["_common"] + world["order"]:
        i18n = world["common"]["i18n"] if name == "_common" else world["docs"][name]["i18n"]
        for lang, table in i18n.items():
            for k, v in table.items():
                if isinstance(v, str):
                    scan(f"{name}/{lang}:{k}", v)
    scan("facts.json", json.dumps(world["facts"], ensure_ascii=False))
    return errs


def report(root, assets, quiet=False):
    world = build.load_world(root)
    errs = build.collect_errors(world) + style_errors(world) + forbidden_errors(world)
    serr, note = storage_errors(world, assets) if assets else ([], "storage keys: not checked")
    errs += serr
    if not quiet:
        langs = world["langs"]
        print("languages: " + ", ".join(langs))
        print("%-10s %6s  " % ("doc", "keys") + "  ".join("%-12s" % (l + " have") for l in langs) + "  missing  orphan")
        for name in ["_common"] + world["order"]:
            req = list(dict.fromkeys(build.required_keys(world, name)))
            i18n = world["common"]["i18n"] if name == "_common" else world["docs"][name]["i18n"]
            have, miss, orph = [], 0, 0
            for l in langs:
                t = i18n.get(l, {})
                have.append("%-12d" % sum(1 for k in req if k in t))
                miss += sum(1 for k in req if k not in t)
                orph += sum(1 for k in t if k not in req)
            print("%-10s %6d  " % (name, len(req)) + "  ".join(have) + "  %7d  %6d" % (miss, orph))
        print(note)
        print("PARITY OK" if not errs else "PARITY FAILED: %d problem(s)" % len(errs))
        for e in errs:
            print("  - " + e)
    return errs


# ---------------------------------------------------------------- self test

def _copy(root, dest):
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(root, dest, ignore=shutil.ignore_patterns("out", "out-public", ".selftest", "__pycache__"))


def _edit(path, fn):
    import json
    d = json.loads(path.read_text(encoding="utf-8"))
    fn(d)
    path.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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

    def drop_key(doc, lang, key):
        return lambda t: _edit(t / doc / "i18n" / f"{lang}.json", lambda d: d.pop(key))

    try:
        # control: the unmodified copy must be clean, or no later PASS means anything
        t = work / "case"
        _copy(root, t)
        clean = report(t, None, quiet=True)
        results.append(("control: unmodified copy has no problems", not clean))
        print(("PASS  " if not clean else "FAIL  ") + "control: unmodified copy has no problems" + ("" if not clean else f" ({clean[:2]})"))

        first_key = lambda doc: build.template_keys(build.load_json(root / doc / "template.json"))[1]
        k = first_key("privacy")
        case("missing key in ru is caught", drop_key("privacy", "ru", k), f"privacy/ru: missing key {k}")
        case("missing key in en is caught", drop_key("terms", "en", first_key("terms")),
             f"terms/en: missing key {first_key('terms')}")
        case("orphan key is caught", lambda t: _edit(t / "imprint" / "i18n" / "en.json", lambda d: d.update({"zz.orphan": "x"})),
             "key zz.orphan is not used")
        case("unknown placeholder is caught",
             lambda t: _edit(t / "cookies" / "i18n" / "ru.json", lambda d: d.update({d_key(d): "Текст {company.nonexistent}"})),
             "unknown placeholder {company.nonexistent}")
        case("malformed placeholder is caught",
             lambda t: _edit(t / "licence" / "i18n" / "en.json", lambda d: d.update({d_key(d): "Text {Company Name}"})),
             "malformed placeholder")
        case("a planted counsel marker in the published text is caught",
             lambda t: _edit(t / "privacy" / "i18n" / "en.json", lambda d: d.update({d_key(d): d[d_key(d)] + " [COUNSEL C99: planted]"})),
             "forbidden text '[COUNSEL'")
        case("a planted review banner key is caught",
             lambda t: _edit(t / "terms" / "i18n" / "ru.json", lambda d: d.update({d_key(d): "[REVIEW-GATE] Текст"})),
             "forbidden text 'REVIEW-GATE'")
        case("a planted version stamp (Russian) is caught",
             lambda t: _edit(t / "cookies" / "i18n" / "ru.json", lambda d: d.update({d_key(d): "Версия 0.1, 1 января"})),
             "forbidden text 'Версия 0.'")
        case("a planted version stamp (English) is caught",
             lambda t: _edit(t / "licence" / "i18n" / "en.json", lambda d: d.update({d_key(d): "Version 0.2 of the text"})),
             "forbidden text 'Version 0.'")
        case("a planted draft word is caught",
             lambda t: _edit(t / "imprint" / "i18n" / "en.json", lambda d: d.update({d_key(d): "This is a draft text"})),
             "forbidden text 'draft'")
        case("a planted draft word (Russian) is caught",
             lambda t: _edit(t / "imprint" / "i18n" / "ru.json", lambda d: d.update({d_key(d): "Это черновик"})),
             "forbidden text 'черновик'")
        case("fact lacking a language is caught",
             lambda t: _edit(t / "facts.json", lambda d: d["company"]["address"].pop("ru")),
             "company.address has no value for language ru")
        case("straight quotes in Russian text are caught",
             lambda t: _edit(t / "terms" / "i18n" / "ru.json", lambda d: d.update({d_key(d): 'Он сказал "так"'})),
             "straight double quote")
        case("a document missing from the registry is caught",
             lambda t: _edit(t / "registry.json", lambda d: d["documents"].remove(next(e for e in d["documents"] if e["id"] == "terms"))),
             "document terms is missing from the registry")
        case("a registry title that differs from the document is caught",
             lambda t: _edit(t / "registry.json", lambda d: d["documents"][0]["title"].update({"en": "Other title"})),
             "title for en differs")
        case("build refuses on a document missing from the registry and writes nothing",
             lambda t: _edit(t / "registry.json", lambda d: d["documents"].remove(next(e for e in d["documents"] if e["id"] == "terms"))),
             "document terms is missing from the registry", via_build=True)
        case("build refuses on a missing key and writes nothing", drop_key("privacy", "ru", k), f"privacy/ru: missing key {k}", via_build=True)
        case("build refuses on an unknown placeholder",
             lambda t: _edit(t / "cookies" / "i18n" / "en.json", lambda d: d.update({d_key(d): "Text {no.such.fact}"})),
             "unknown placeholder {no.such.fact}", via_build=True)
        # a new language with no translation must be refused, not silently skipped
        def add_lang(t):
            for f in list(t.glob("*/i18n/en.json")):
                if f.parent.parent.name in ("privacy",):
                    continue
                shutil.copy(f, f.with_name("de.json"))
        case("a new language missing from one document is caught", add_lang, "privacy: no i18n file for language de")
    finally:
        if work.exists():
            shutil.rmtree(work)
    bad = [l for l, ok in results if not ok]
    print("SELF-TEST " + ("PASSED: %d of %d checks fired as planned" % (len(results), len(results)) if not bad
                          else "FAILED: " + "; ".join(bad)))
    return 0 if not bad else 1


def d_key(d):
    """a body-text key (not the first, not a marker carrier) to plant a defect in"""
    return [k for k in d if not k.endswith(".title")][2]


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
