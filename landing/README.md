# AIVIS.ONE company site

A static multilingual site (EN at the root, RU under `/ru/`), built from text files; no framework, no
third-party scripts, a strict Content-Security-Policy.

## Folders

- `site/` -- the site: `content/site.json` (pages, locales, settings), `content/<locale>.json` (all text, one
  file per language), `tokens.tokens.json` (design tokens), `assets/` (styles, scripts, fonts, images, icons),
  `scripts/` (build and checks).
- `legal/` -- the legal pages (imprint, privacy, terms, cookies, licence): sources per document and language,
  `build.py` renders them into `legal/out/`, which the site build reads.
- `courses/` -- the four courses: per course `template.html` and `content/<locale>.json`, shared files in
  `_shared/`; `courses/build.py` writes `site/dist/courses/<slug>/` and `site/dist/<locale>/courses/<slug>/`
  after the site build and adds the pages' inline hashes to `site/dist/_headers`.
- `guides/` -- the testing guide and `run-checks.py`, the automated page checks.

## Build

```
cd landing/legal && python build.py
cd landing/site && python scripts/build-site.py --site content/site.json --content-dir content --tokens tokens.tokens.json --assets-dir assets --out dist
cd landing && python courses/build.py
```

`dist/` is the deployable site (ignored by Git).

## Check

```
cd landing/legal && python check.py
cd landing/site && python scripts/gate.py --site content/site.json --content-dir content --dist dist --tokens tokens.tokens.json
cd landing && python guides/run-checks.py --self-test
cd landing && python guides/run-checks.py <page URLs of a served dist/>
```

## Add a language

Add the locale to `locales` in `site/content/site.json`, add `site/content/<locale>.json` with every key of
`en.json`, add the legal sources for that language, add `courses/<slug>/content/<locale>.json` for each course, and
rebuild.
