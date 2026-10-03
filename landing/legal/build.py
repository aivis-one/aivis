#!/usr/bin/env python3
"""Renders the public legal documents of AIVIS.ONE, one output per language.

Layout (relative to this file):
  facts.json                     shared facts, inserted by {path.to.value}
  _common/template.json, i18n/   strings shared by every document (headings)
  <doc>/template.json            ordered structure of one document: blocks that point at keys
  <doc>/i18n/<lang>.json         key -> text, one file per language
Output: out/<lang>/<doc>.md and <doc>.html (semantic HTML fragments): the published form, the only one.
A language is added by copying en.json to <lang>.json in every <doc>/i18n and _common/i18n and
translating it; no other file changes.

REFUSES (exit 1, nothing written) when a key is missing in any language, a key is not used by
the template, a placeholder is unknown or malformed, a fact lacks a language or a language
lacks a document. Open points never go into a document: they live in the questions file.
--public  accepted and ignored: the published form is the only output.

Usage: python build.py [--root DIR] [--out DIR] [--public]
"""
import argparse
import html
import json
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLACEHOLDER = re.compile(r"\{([a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*)\}")
ANY_BRACE = re.compile(r"\{[^{}]*\}")
LINK = re.compile(r"\[([^\]]+)\]\(((?:https?://|/)[^)\s]*)\)")
BOLD = re.compile(r"\*\*([^*]+)\*\*")
RU_PREP = re.compile(
    r"(?<![\w])(в|к|с|о|у|и|а|на|по|за|от|до|из|не|но|ни|об|во|со|ко|для|при|над|под|без|как|что)\s+",
    re.IGNORECASE)


def load_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


MONTHS = {
    "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September",
           "October", "November", "December"],
    "ru": ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября",
           "октября", "ноября", "декабря"],
}


def edition_date(iso, lang):
    y, m, d = (int(x) for x in iso.split("-"))
    return f"{d} {MONTHS[lang][m - 1]} {y}"


def registry_entry(world, name):
    return next((e for e in world["registry"] if e.get("scope") == "site" and e.get("id") == name), None)


def registry_errors(world):
    """Every document of the site must stand in registry.json with a title per language, an
    edition number and a date; the title must equal the document's own title."""
    errs = []
    reg = world["registry"]
    ids = [e.get("id") for e in reg if e.get("scope") == "site"]
    for name in world["order"]:
        if name not in ids:
            errs.append(f"registry.json: document {name} is missing from the registry")
    for i in ids:
        if i not in world["docs"]:
            errs.append(f"registry.json: entry {i} names no document")
    for e in reg:
        i = e.get("id")
        if not isinstance(e.get("edition"), int) or e["edition"] < 1:
            errs.append(f"registry.json: {i}: edition must be a whole number from 1")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(e.get("date", ""))):
            errs.append(f"registry.json: {i}: date must be YYYY-MM-DD")
        if e.get("scope") == "site" and i in world["docs"]:
            d = world["docs"][i]
            for lang in world["langs"]:
                want = d["i18n"].get(lang, {}).get(d["template"]["title"])
                have = (e.get("title") or {}).get(lang)
                if have is None:
                    errs.append(f"registry.json: {i}: no title for language {lang}")
                elif want is not None:
                    shown = substitute(want, world["facts"], lang, f"registry:{i}/{lang}", [])
                    if shown != have:
                        errs.append(f"registry.json: {i}: title for {lang} differs from the document's title")
    return errs


# ---------------------------------------------------------------- loading

def load_world(root):
    root = Path(root)
    reg_file = root / "registry.json"
    world = {"root": root, "facts": load_json(root / "facts.json"), "docs": {}, "common": None, "errors": [],
             "registry": load_json(reg_file)["documents"] if reg_file.is_file() else None}
    ctpl = root / "_common" / "template.json"
    world["common"] = {"template": load_json(ctpl), "i18n": read_i18n(root / "_common" / "i18n")}
    for tpl in sorted(root.glob("*/template.json")):
        name = tpl.parent.name
        if name.startswith("_"):
            continue
        t = load_json(tpl)
        world["docs"][name] = {"template": t, "i18n": read_i18n(tpl.parent / "i18n")}
    world["order"] = sorted(world["docs"], key=lambda n: (world["docs"][n]["template"].get("order", 99), n))
    langs = set(world["common"]["i18n"])
    for d in world["docs"].values():
        langs |= set(d["i18n"])
    world["langs"] = sorted(langs)
    return world


def read_i18n(folder):
    out = {}
    if folder.is_dir():
        for f in sorted(folder.glob("*.json")):
            out[f.stem] = load_json(f)
    return out


# ---------------------------------------------------------------- template walking

def block_keys(block):
    t = block["t"]
    if t in ("h2", "h3", "p"):
        return [block["k"]]
    if t in ("ul", "ol"):
        return list(block["keys"])
    if t == "dl":
        return [k for row in block["rows"] for k in row]
    if t == "table":
        return list(block["head"]) + [k for row in block["rows"] for k in row]
    return []


def template_keys(tpl):
    keys = [tpl["title"]]
    for b in tpl["blocks"]:
        keys += block_keys(b)
    return keys


def required_keys(world, name):
    if name == "_common":
        return list(world["common"]["template"]["keys"])
    return template_keys(world["docs"][name]["template"])


# ---------------------------------------------------------------- facts and text

def fact_value(facts, path, lang):
    node = facts
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    if isinstance(node, dict):
        return node.get(lang)
    return node if isinstance(node, str) else None


def substitute(text, facts, lang, where, errors):
    for m in ANY_BRACE.finditer(text):
        if not PLACEHOLDER.fullmatch(m.group(0)):
            errors.append(f"{where}: malformed placeholder {m.group(0)!r}")

    def repl(m):
        v = fact_value(facts, m.group(1), lang)
        if v is None:
            errors.append(f"{where}: unknown placeholder {{{m.group(1)}}} for language {lang}")
            return m.group(0)
        return v

    return PLACEHOLDER.sub(repl, text)


def is_langobj(node):
    return bool(isinstance(node, dict) and node
                and all(isinstance(k, str) and len(k) == 2 and k.islower() and isinstance(v, str)
                        for k, v in node.items()))


def facts_errors(world):
    """Every fact that is a {lang: text} object must carry every language."""
    errs = []

    def walk(node, path):
        if is_langobj(node):
            for lang in world["langs"]:
                if lang not in node:
                    errs.append(f"facts.json: {path} has no value for language {lang}")
        elif isinstance(node, dict):
            for k, v in node.items():
                if not k.startswith("_"):
                    walk(v, f"{path}.{k}" if path else k)

    walk(world["facts"], "")
    return errs


def typo(text, lang):
    if lang == "ru":
        text = text.replace(" — ", " — ")
        text = RU_PREP.sub(lambda m: m.group(1) + " ", text)
    return text



# ---------------------------------------------------------------- validation

def collect_errors(world):
    errs = list(facts_errors(world))
    if world["registry"] is None:
        errs.append("registry.json: the register of documents is missing")
    else:
        errs += registry_errors(world)
    names = ["_common"] + world["order"]
    for name in names:
        i18n = world["common"]["i18n"] if name == "_common" else world["docs"][name]["i18n"]
        req = required_keys(world, name)
        for lang in world["langs"]:
            if lang not in i18n:
                errs.append(f"{name}: no i18n file for language {lang}")
                continue
            table = i18n[lang]
            for k in dict.fromkeys(req):
                if k not in table:
                    errs.append(f"{name}/{lang}: missing key {k}")
                elif not isinstance(table[k], str) or not table[k].strip():
                    errs.append(f"{name}/{lang}: empty text for key {k}")
            for k in table:
                if k not in req:
                    errs.append(f"{name}/{lang}: key {k} is not used by the template")
            for k, v in table.items():
                if isinstance(v, str):
                    substitute(v, world["facts"], lang, f"{name}/{lang}:{k}", errs)
    for name in world["order"]:
        k = f"site.path.{name}"
        for lang in world["langs"]:
            if fact_value(world["facts"], k, lang) is None:
                errs.append(f"facts.json: no {k} for language {lang} (related-document links)")
    return errs


# ---------------------------------------------------------------- inline rendering

def inline_html(text, public=True):
    s = html.escape(text, quote=False)
    s = LINK.sub(lambda m: f'<a href="{html.escape(m.group(2), quote=True)}">{m.group(1)}</a>', s)
    s = BOLD.sub(r"<strong>\1</strong>", s)
    return s


def inline_md(text, public=True):
    return text


def render_doc(world, name, lang, public=True):
    facts = world["facts"]
    doc = world["docs"][name]
    tpl = doc["template"]
    table = doc["i18n"][lang]
    common = world["common"]["i18n"][lang]
    errs = []

    def T(key, src=table):
        return typo(substitute(src[key], facts, lang, f"{name}/{lang}:{key}", errs), lang)

    md, hh = [], []
    counsel = []

    def C(key):
        return T(key, common)

    def emit_text(key, src=table):
        return T(key, src)

    title = emit_text(tpl["title"])
    md.append(f"# {inline_md(title, public)}\n")
    hh.append(f'<h1>{inline_html(title, public)}</h1>')
    reg = registry_entry(world, name)
    edition = C("common.edition").replace("%D", edition_date(reg["date"], lang))
    md.append(f"{edition}\n")
    hh.append(f'<p class="edition">{html.escape(edition, quote=False)}</p>')

    for b in tpl["blocks"]:
        t = b["t"]
        if t in ("h2", "h3"):
            lv = int(t[1])
            txt = emit_text(b["k"])
            md.append(f"{'#' * lv} {inline_md(txt, public)}\n")
            hh.append(f'<{t} id="{html.escape(b["k"].replace(".", "-"))}">{inline_html(txt, public)}</{t}>')
        elif t == "p":
            txt = emit_text(b["k"])
            md.append(inline_md(txt, public) + "\n")
            hh.append(f"<p>{inline_html(txt, public)}</p>")
        elif t in ("ul", "ol"):
            items = [emit_text(k) for k in b["keys"]]
            for n, it in enumerate(items, 1):
                md.append(f"{'-' if t == 'ul' else str(n) + '.'} {inline_md(it, public)}")
            md.append("")
            hh.append(f"<{t}>" + "".join(f"<li>{inline_html(it, public)}</li>" for it in items) + f"</{t}>")
        elif t == "dl":
            rows = [(emit_text(a), emit_text(v)) for a, v in b["rows"]]
            for a, v in rows:
                md.append(f"- **{a}:** {inline_md(v, public)}")
            md.append("")
            hh.append("<dl>" + "".join(f"<dt>{inline_html(a, public)}</dt><dd>{inline_html(v, public)}</dd>" for a, v in rows) + "</dl>")
        elif t == "table":
            head = [emit_text(k) for k in b["head"]]
            rows = [[emit_text(k) for k in r] for r in b["rows"]]
            md.append("| " + " | ".join(head) + " |")
            md.append("|" + "---|" * len(head))
            for r in rows:
                md.append("| " + " | ".join(inline_md(c, public).replace("|", "\\|") for c in r) + " |")
            md.append("")
            hh.append("<table><thead><tr>" + "".join(f'<th scope="col">{inline_html(h, public)}</th>' for h in head)
                      + "</tr></thead><tbody>" + "".join("<tr>" + "".join(f"<td>{inline_html(c, public)}</td>" for c in r) + "</tr>" for r in rows)
                      + "</tbody></table>")
        else:
            errs.append(f"{name}: unknown block type {t!r}")

    # related documents
    rel = [(n, world["docs"][n]) for n in world["order"] if n != name]
    md.append(f"## {C('common.related.head')}\n")
    hh.append(f'<h2 id="common-related">{html.escape(C("common.related.head"), quote=False)}</h2>')
    li_md, li_hh = [], []
    for n, d in rel:
        label = typo(substitute(d["i18n"][lang][d["template"]["title"]], facts, lang, f"{n}/{lang}:title", errs), lang)
        url = fact_value(facts, f"site.path.{n}", lang)
        li_md.append(f"- [{label}]({url})")
        li_hh.append(f'<li><a href="{html.escape(url)}">{html.escape(label, quote=False)}</a></li>')
    md.extend(li_md + [""])
    hh.append("<ul>" + "".join(li_hh) + "</ul>")


    article = (f'<article class="legal" lang="{lang}" data-doc="{name}">\n'
               + "\n".join(hh) + "\n</article>\n")
    return "\n".join(md).rstrip() + "\n", article, counsel, errs


# ---------------------------------------------------------------- run

def run(root=HERE, out=None, public=True):
    root = Path(root)
    out = Path(out) if out else root / "out"
    world = load_world(root)
    errs = collect_errors(world)
    if errs:
        print("BUILD REFUSED: %d problem(s)" % len(errs), file=sys.stderr)
        for e in errs:
            print("  - " + e, file=sys.stderr)
        return 1
    results = {}
    for lang in world["langs"]:
        for name in world["order"]:
            md, ht, counsel, e = render_doc(world, name, lang, public)
            errs += e
            results[(lang, name)] = (md, ht)
    if errs:
        print("BUILD REFUSED: %d problem(s)" % len(errs), file=sys.stderr)
        for e in errs:
            print("  - " + e, file=sys.stderr)
        return 1
    if out.exists():
        shutil.rmtree(out)
    for (lang, name), (md, ht) in results.items():
        d = out / lang
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{name}.md").write_text(md, encoding="utf-8", newline="\n")
        (d / f"{name}.html").write_text(ht, encoding="utf-8", newline="\n")
    print(f"BUILD OK: {len(world['order'])} documents x {len(world['langs'])} languages ({', '.join(world['langs'])}) "
          f"= {len(results) * 2} files in {out}")
    return 0


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=str(HERE))
    ap.add_argument("--out")
    ap.add_argument("--public", action="store_true")
    a = ap.parse_args(argv)
    return run(a.root, a.out, a.public)


if __name__ == "__main__":
    sys.exit(main())
