#!/usr/bin/env python3
"""Renders the legal documents of AIVIS.ONE from Markdown, one output per language.

Layout (relative to this file):
  facts.json                         shared facts, inserted by {path.to.value}
  registry.json                      edition number and date of every document, the two shared labels
  public/<doc>/<doc>.{en,ru}.md      the site's pages (privacy, terms, imprint, cookies, licence)
  cabinet/<doc>/<doc>.{en,ru}.md     the cabinet's documents (none yet; the folder holds a README only)
Text file form: line 1 "# <title>"; then blocks separated by blank lines: "## <heading> {#id}" (also ###; the
{#id} is the anchor of the heading), paragraphs, "- " lists, "1. " lists, definition lists of "- **Term:** text"
lines, and pipe tables. Inline: [text](url) and **bold**. {path.to.value} is a fact of facts.json.
Output: out/<lang>/<doc>.md and <doc>.html (semantic HTML fragments) for the public documents: the published form,
the only one the site build reads (site.json legal_dir). The edition line comes from registry.json.
The cabinet documents are written as full HTML pages (title, aivis-document-type, aivis-language and, from the
registry entry's "roles", aivis-required-for-roles metas: what backend/scripts/seed_documents.py reads) to
frontend/public/legal/<lang>/<doc>.html ONLY with --cabinet (off by default); --cabinet-out DIR writes them to DIR.

REFUSES (exit 1, nothing written) when a language file is missing for a document, two languages of a document do
not have the same structure (blocks, lists, headings and their anchors), a placeholder is unknown or malformed,
a text is empty, a fact lacks a language or the registry disagrees with the documents. Open points never go into
a document: they live in the questions file.
--public  accepted and ignored: the published form is the only output.

Usage: python build.py [--root DIR] [--out DIR] [--public] [--cabinet [--cabinet-out DIR]]
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
    """Every document must stand in registry.json with a title per language, an edition number and
    a date; the title must equal the document's own title (the first line of its text file)."""
    errs = []
    reg = world["registry"]
    ids = [e.get("id") for e in reg if e.get("scope") == "site"]
    for name in world["order"]:
        if name not in ids:
            errs.append(f"registry.json: document {name} is missing from the registry")
    for e in reg:
        i = e.get("id")
        scope = e.get("scope")
        if scope not in ("site", "cabinet"):
            errs.append(f"registry.json: {i}: scope must be site or cabinet")
        if "roles" in e and not (isinstance(e["roles"], list) and all(isinstance(x, str) and x for x in e["roles"])):
            errs.append(f"registry.json: {i}: roles must be a list of role names")
        if scope == "site" and i not in world["docs"]:
            errs.append(f"registry.json: entry {i} names no document")
        if scope == "cabinet" and i not in world["cabinet_order"]:
            errs.append(f"registry.json: entry {i} names no cabinet document")
        if not isinstance(e.get("edition"), int) or e["edition"] < 1:
            errs.append(f"registry.json: {i}: edition must be a whole number from 1")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(e.get("date", ""))):
            errs.append(f"registry.json: {i}: date must be YYYY-MM-DD")
        d = world["docs"].get(i)
        if scope in ("site", "cabinet") and d is not None and d["scope"] == scope:
            for lang in world["langs"]:
                parsed = d["md"].get(lang)
                have = (e.get("title") or {}).get(lang)
                if have is None:
                    errs.append(f"registry.json: {i}: no title for language {lang}")
                elif parsed is not None:
                    shown = substitute(parsed["title"], world["facts"], lang, f"registry:{i}/{lang}", [])
                    if shown != have:
                        errs.append(f"registry.json: {i}: title for {lang} differs from the document's title")
    labels = world["labels"]
    for key in ("edition", "related"):
        for lang in world["langs"]:
            if not isinstance((labels.get(key) or {}).get(lang), str):
                errs.append(f"registry.json: labels.{key} has no value for language {lang}")
    return errs


# ---------------------------------------------------------------- reading a text file

HEADING = re.compile(r"^(#{2,3}) (.+?)(?:\s+\{#([A-Za-z][\w-]*)\})?$")
DLROW = re.compile(r"^- \*\*(.+?):\*\* (.+)$")
OLROW = re.compile(r"^(\d+)\. (.+)$")
PIPE = re.compile(r"(?<!\\)\|")


def split_row(line):
    cells = PIPE.split(line.strip())
    if cells and cells[0] == "":
        cells = cells[1:]
    if cells and cells[-1] == "":
        cells = cells[:-1]
    return [c.strip().replace("\\|", "|") for c in cells]


def parse_md(path, errors):
    """-> {"title": str, "blocks": [...]}; a block is a dict with "t" in h2 h3 p ul ol dl table."""
    where = f"{path.parent.name}/{path.name}"
    lines = path.read_text(encoding="utf-8").split("\n")
    if not lines or not lines[0].startswith("# ") or not lines[0][2:].strip():
        errors.append(f"{where}: line 1 must be '# <title>'")
        return {"title": "", "blocks": []}
    out = {"title": lines[0][2:].strip(), "blocks": []}
    groups, buf = [], []
    for ln in lines[1:] + [""]:
        if ln.strip() == "":
            if buf:
                groups.append(buf)
                buf = []
        else:
            buf.append(ln.rstrip())
    n_head = 0
    for g in groups:
        first = g[0]
        if first.startswith("#"):
            m = HEADING.match(first) if len(g) == 1 else None
            if not m:
                errors.append(f"{where}: malformed heading {first!r}")
                continue
            n_head += 1
            out["blocks"].append({"t": f"h{len(m.group(1))}", "text": m.group(2).strip(),
                                  "id": m.group(3) or f"{path.parent.name}-s{n_head}"})
        elif all(x.startswith("- ") for x in g):
            rows = [DLROW.match(x) for x in g]
            if all(rows):
                out["blocks"].append({"t": "dl", "rows": [(r.group(1), r.group(2)) for r in rows]})
            else:
                out["blocks"].append({"t": "ul", "items": [x[2:] for x in g]})
        elif all(OLROW.match(x) for x in g):
            nums = [int(OLROW.match(x).group(1)) for x in g]
            if nums != list(range(1, len(g) + 1)):
                errors.append(f"{where}: numbered list does not run 1, 2, 3 ...: {first!r}")
            out["blocks"].append({"t": "ol", "items": [OLROW.match(x).group(2) for x in g]})
        elif all(x.startswith("|") for x in g):
            if len(g) < 3 or not re.fullmatch(r"\|(?:\s*:?-+:?\s*\|)+", g[1].strip()):
                errors.append(f"{where}: a table needs a header row, a separator row and rows: {first!r}")
                continue
            head = split_row(g[0])
            rows = [split_row(x) for x in g[2:]]
            if any(len(r) != len(head) for r in rows):
                errors.append(f"{where}: a table row has a different number of cells than its header: {first!r}")
            out["blocks"].append({"t": "table", "head": head, "rows": rows})
        else:
            out["blocks"].append({"t": "p", "text": " ".join(x.strip() for x in g)})
    return out


def block_texts(block):
    """every text of a block, in order"""
    t = block["t"]
    if t in ("h2", "h3", "p"):
        return [block["text"]]
    if t in ("ul", "ol"):
        return list(block["items"])
    if t == "dl":
        return [x for row in block["rows"] for x in row]
    if t == "table":
        return list(block["head"]) + [c for r in block["rows"] for c in r]
    return []


def doc_texts(parsed):
    texts = [parsed["title"]]
    for b in parsed["blocks"]:
        texts += block_texts(b)
    return texts


def shape(parsed):
    """the structure of a document without its words: used to prove two languages say the same thing"""
    out = []
    for b in parsed["blocks"]:
        t = b["t"]
        if t in ("h2", "h3"):
            out.append((t, b["id"]))
        elif t in ("ul", "ol"):
            out.append((t, len(b["items"])))
        elif t == "dl":
            out.append((t, len(b["rows"])))
        elif t == "table":
            out.append((t, len(b["head"]), len(b["rows"])))
        else:
            out.append((t,))
    return out


# ---------------------------------------------------------------- loading

def load_world(root):
    root = Path(root)
    reg_file = root / "registry.json"
    reg_json = load_json(reg_file) if reg_file.is_file() else None
    world = {"root": root, "facts": load_json(root / "facts.json"), "docs": {}, "errors": [],
             "registry": reg_json["documents"] if reg_json else None,
             "labels": (reg_json or {}).get("labels", {})}
    cabinet = []
    for scope, folder in (("site", "public"), ("cabinet", "cabinet")):
        base = root / folder
        if not base.is_dir():
            continue
        for d in sorted(p for p in base.iterdir() if p.is_dir()):
            name = d.name
            if name in world["docs"]:
                world["errors"].append(f"{folder}/{name}: a document of this name exists in public/ and in cabinet/")
                continue
            md = {}
            for f in sorted(d.glob(f"{name}.*.md")):
                lang = f.name[len(name) + 1:-3]
                if not re.fullmatch(r"[a-z]{2}", lang):
                    world["errors"].append(f"{folder}/{name}/{f.name}: the language in the file name must be two lower-case letters")
                    continue
                md[lang] = parse_md(f, world["errors"])
            world["docs"][name] = {"scope": scope, "md": md}
            if scope == "cabinet":
                cabinet.append(name)
    site = [n for n, d in world["docs"].items() if d["scope"] == "site"]
    reg_order = [e.get("id") for e in (world["registry"] or []) if e.get("scope") == "site" and e.get("id") in site]
    world["order"] = reg_order + sorted(n for n in site if n not in reg_order)
    world["cabinet_order"] = sorted(cabinet)
    langs = set()
    for d in world["docs"].values():
        langs |= set(d["md"])
    world["langs"] = sorted(langs)
    return world


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
    errs = list(world["errors"]) + list(facts_errors(world))
    if world["registry"] is None:
        errs.append("registry.json: the register of documents is missing")
    else:
        errs += registry_errors(world)
    for name, doc in world["docs"].items():
        folder = "public" if doc["scope"] == "site" else "cabinet"
        for lang in world["langs"]:
            if lang not in doc["md"]:
                errs.append(f"{name}: no text file for language {lang} ({folder}/{name}/{name}.{lang}.md)")
        ref_lang = next((lg for lg in world["langs"] if lg in doc["md"]), None)
        for lang in world["langs"]:
            parsed = doc["md"].get(lang)
            if parsed is None:
                continue
            if ref_lang and lang != ref_lang and shape(parsed) != shape(doc["md"][ref_lang]):
                a, b = shape(parsed), shape(doc["md"][ref_lang])
                at = next((n for n in range(max(len(a), len(b))) if (a[n:n + 1] or [None]) != (b[n:n + 1] or [None])), 0)
                errs.append(f"{name}/{lang}: the structure differs from {ref_lang} at block {at + 1} "
                            f"({(a[at:at + 1] or ['end'])[0]} against {(b[at:at + 1] or ['end'])[0]})")
            for n, text in enumerate(doc_texts(parsed)):
                if not text.strip():
                    errs.append(f"{name}/{lang}: empty text at position {n}")
                substitute(text, world["facts"], lang, f"{name}/{lang}:{n}", errs)
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
    parsed = doc["md"][lang]
    errs = []

    def T(text):
        return typo(substitute(text, facts, lang, f"{name}/{lang}", errs), lang)

    md, hh = [], []
    counsel = []

    title = T(parsed["title"])
    md.append(f"# {inline_md(title, public)}\n")
    hh.append(f'<h1>{inline_html(title, public)}</h1>')
    reg = registry_entry(world, name) if doc["scope"] == "site" else next(
        (e for e in world["registry"] or [] if e.get("scope") == "cabinet" and e.get("id") == name), None)
    if reg is not None:
        edition = world["labels"]["edition"][lang].replace("%D", edition_date(reg["date"], lang))
        md.append(f"{edition}\n")
        hh.append(f'<p class="edition">{html.escape(edition, quote=False)}</p>')

    for b in parsed["blocks"]:
        t = b["t"]
        if t in ("h2", "h3"):
            lv = int(t[1])
            txt = T(b["text"])
            md.append(f"{'#' * lv} {inline_md(txt, public)}\n")
            hh.append(f'<{t} id="{html.escape(b["id"])}">{inline_html(txt, public)}</{t}>')
        elif t == "p":
            txt = T(b["text"])
            md.append(inline_md(txt, public) + "\n")
            hh.append(f"<p>{inline_html(txt, public)}</p>")
        elif t in ("ul", "ol"):
            items = [T(x) for x in b["items"]]
            for n, it in enumerate(items, 1):
                md.append(f"{'-' if t == 'ul' else str(n) + '.'} {inline_md(it, public)}")
            md.append("")
            hh.append(f"<{t}>" + "".join(f"<li>{inline_html(it, public)}</li>" for it in items) + f"</{t}>")
        elif t == "dl":
            rows = [(T(a), T(v)) for a, v in b["rows"]]
            for a, v in rows:
                md.append(f"- **{a}:** {inline_md(v, public)}")
            md.append("")
            hh.append("<dl>" + "".join(f"<dt>{inline_html(a, public)}</dt><dd>{inline_html(v, public)}</dd>" for a, v in rows) + "</dl>")
        elif t == "table":
            head = [T(x) for x in b["head"]]
            rows = [[T(x) for x in r] for r in b["rows"]]
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

    # related documents (the site's pages only)
    if doc["scope"] == "site":
        head = world["labels"]["related"][lang]
        md.append(f"## {head}\n")
        hh.append(f'<h2 id="common-related">{html.escape(head, quote=False)}</h2>')
        li_md, li_hh = [], []
        for n in world["order"]:
            if n == name:
                continue
            label = typo(substitute(world["docs"][n]["md"][lang]["title"], facts, lang, f"{n}/{lang}:title", errs), lang)
            url = fact_value(facts, f"site.path.{n}", lang)
            li_md.append(f"- [{label}]({url})")
            li_hh.append(f'<li><a href="{html.escape(url)}">{html.escape(label, quote=False)}</a></li>')
        md.extend(li_md + [""])
        hh.append("<ul>" + "".join(li_hh) + "</ul>")

    article = (f'<article class="legal" lang="{lang}" data-doc="{name}">\n'
               + "\n".join(hh) + "\n</article>\n")
    return "\n".join(md).rstrip() + "\n", article, counsel, errs


# ---------------------------------------------------------------- run

def default_cabinet_out(root):
    """where the cabinet's documents go when --cabinet is given: the frontend's public/legal folder"""
    return Path(root).resolve().parent.parent / "frontend" / "public" / "legal"


def cabinet_page(world, name, lang, article):
    """The full page backend/scripts/seed_documents.py reads: the metas aivis-document-type, aivis-language and
    (when the document's registry entry gives roles) aivis-required-for-roles, the title, then the article."""
    title = typo(substitute(world["docs"][name]["md"][lang]["title"], world["facts"], lang, f"{name}/{lang}:title", []), lang)
    entry = next((e for e in world["registry"] or [] if e.get("scope") == "cabinet" and e.get("id") == name), {})
    roles = entry.get("roles")
    roles = ",".join(roles) if isinstance(roles, list) else (roles or "")
    metas = [f'  <meta name="aivis-document-type" content="{html.escape(name)}">',
             f'  <meta name="aivis-language" content="{lang}">']
    if roles:
        metas.append(f'  <meta name="aivis-required-for-roles" content="{html.escape(roles)}">')
    return ("<!DOCTYPE html>\n" + f'<html lang="{lang}">\n<head>\n  <meta charset="utf-8">\n'
            + f"  <title>{html.escape(title, quote=False)}</title>\n" + "\n".join(metas) + "\n</head>\n<body>\n"
            + article + "</body>\n</html>\n")


def run(root=HERE, out=None, public=True, cabinet=False, cabinet_out=None):
    root = Path(root)
    out = Path(out) if out else root / "out"
    world = load_world(root)
    errs = collect_errors(world)
    if errs:
        print("BUILD REFUSED: %d problem(s)" % len(errs), file=sys.stderr)
        for e in errs:
            print("  - " + e, file=sys.stderr)
        return 1
    results, cab = {}, {}
    for lang in world["langs"]:
        for name in world["order"]:
            md, ht, counsel, e = render_doc(world, name, lang, public)
            errs += e
            results[(lang, name)] = (md, ht)
        if cabinet:
            for name in world["cabinet_order"]:
                md, ht, counsel, e = render_doc(world, name, lang, public)
                errs += e
                cab[(lang, name)] = cabinet_page(world, name, lang, ht)
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
    if cabinet:
        dest = Path(cabinet_out) if cabinet_out else default_cabinet_out(root)
        for (lang, name), ht in cab.items():
            (dest / lang).mkdir(parents=True, exist_ok=True)
            (dest / lang / f"{name}.html").write_text(ht, encoding="utf-8", newline="\n")
        print(f"CABINET OK: {len(world['cabinet_order'])} documents x {len(world['langs'])} languages "
              f"= {len(cab)} files in {dest}" if cab else "CABINET: no cabinet documents yet, nothing written")
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
    ap.add_argument("--cabinet", action="store_true",
                    help="also write the cabinet documents as HTML to frontend/public/legal/<lang>/<doc>.html (off by default)")
    ap.add_argument("--cabinet-out", help="write the cabinet documents to this folder instead (implies --cabinet)")
    a = ap.parse_args(argv)
    return run(a.root, a.out, a.public, a.cabinet or bool(a.cabinet_out), a.cabinet_out)


if __name__ == "__main__":
    sys.exit(main())
