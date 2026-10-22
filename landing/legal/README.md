# landing/legal -- every legal text of AIVIS.ONE, one source

The one place of the legal texts. Edits are made only here; the site and the cabinet are built from here and no copy
of a legal text lives anywhere else. English is the main text; Russian follows the meaning. English and Russian only.

## The tree

```
landing/legal/
  README.md                         this file
  facts.json                        the company facts: name, number, address, director, e-mail, site paths, storage key
  registry.json                     edition number and date of every document, and the two shared labels
  build.py                          reads the .md tree, writes out/ (and, only when asked, the cabinet's HTML)
  check.py                          checks the tree; --self-test plants defects and proves each one fires
  public/                           the public pages of aivis.one
    privacy/privacy.{en,ru}.md      privacy policy          -> /about/privacy/, /ru/about/privacy/
    terms/terms.{en,ru}.md          terms of use            -> /about/terms/, /ru/about/terms/
    imprint/imprint.{en,ru}.md      company details         -> /about/imprint/, /ru/about/imprint/
    cookies/cookies.{en,ru}.md      cookie and local storage notice -> /about/cookies/, /ru/about/cookies/
    licence/licence.{en,ru}.md      course licence          -> /about/licence/, /ru/about/licence/
  cabinet/                          the documents of the cabinet (README.md lists them)
    <type>/<type>.{en,ru}.md
  out/{en,ru}/<doc>.{md,html}       built; the published form the site build reads (tracked, never edited by hand)
```

## The text file form

Line 1 is `# <title>`. Then blocks separated by a blank line: `## <heading> {#anchor}` (also `###`; the `{#anchor}` is
the heading's link target and the same in both languages), paragraphs, `- ` lists, `1. ` lists, definition lists of
`- **Term:** text` lines and pipe tables. Inline: `[text](url)` and `**bold**`. `{path.to.value}` is a fact of
`facts.json` and is replaced at build time. The edition line ("Updated 2 October 2026") is not typed: it comes from
`registry.json`.

## The rule

- Every document folder holds both `<doc>.en.md` and `<doc>.ru.md`, with the same blocks, lists and anchors.
- Every text is a clean final: no draft banner, review or counsel marker, version stamp, internal note or source mark.
- A company fact is changed in `facts.json` first, then in the texts that name it.
- A new edition of a document: raise its `edition` and set its `date` in `registry.json`, nowhere else.
- `out/` is built, never edited. The wording of a document is changed in its `.md` and rebuilt.

## The build, in order

1. Edit the `.md` (or `facts.json`, or `registry.json`).
2. `cd landing/legal && python check.py` -- refuses a missing language file, a different structure between the
   languages, an unknown or malformed placeholder, a marker, a quote-style fault, a registry disagreement, a storage key
   that the site scripts use and `facts.json` does not declare.
3. `cd landing/legal && python build.py` -- writes `out/{en,ru}/<doc>.md` and `.html`. This runs BEFORE the site build,
   which reads `out/` (`legal_dir` in `landing/site/content/site.json`).
4. `cd landing/legal && python build.py --cabinet` writes each one as a full HTML page to
   `frontend/public/legal/{en,ru}/<type>.html` (`--cabinet-out DIR` writes elsewhere). This runs BEFORE the frontend
   build, which ships `frontend/public/` as it stands. Off unless asked; it writes only the cabinet's own files and never
   touches the other languages' files already in that folder.
5. `cd landing/site && python scripts/build-site.py ...` (see `landing/README.md`), then the frontend build.
6. `python check.py --self-test` after any change to the builder or the checker.

## Who reads which folder

| Folder | Read by |
|---|---|
| `public/` | `build.py` -- writes `out/`, which `landing/site/scripts/render-page.py` reads as `<legal_dir>/<lang>/<doc>.html` |
| cabinet/ | build.py --cabinet -- writes frontend/public/legal/<lang>/<type>.html, a full page with the aivis-document-type, aivis-language and aivis-required-for-roles metas; backend/scripts/seed_documents.py reads that folder into the documents table and skips a page without them |
| `facts.json`, `registry.json` | `build.py` and `check.py` |
| `out/` | the site build; nothing else |
