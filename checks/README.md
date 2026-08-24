# checks/ — static checks on the frontend source

```bash
python checks/run.py            # run them; exit 0 = all pass
python checks/run.py --selftest # prove each one can FAIL, then that it passes
```

Standard library only. No pip install, no node. Python is already a project
dependency (`backend/pyproject.toml`), so this adds no toolchain.

## What this is

Four checks on `frontend/src` that the type checker and the unit tests cannot
express, because each is a property of the CSS or the router **as a whole**
rather than of one module.

Every one of them exists because the product actually had the defect it looks
for. None of them is a style preference.

| check | what it asserts | the defect it was written for |
|---|---|---|
| `breakpoints.py` | every width in a `@media` query is one of the `--bp-*` values declared in `variables.css` | seven different breakpoints lived in 31 media queries across 22 files and only two were named anywhere |
| `shell_layout.py` | the shell chrome has one source; the storefront stays outside the tier system; the tab-bar hide rule keeps its specificity; StaffShell keeps its own content cap | four shells carried the same `@media (min-width: 820px)` block byte for byte — a tier change had to be made in four places |
| `tokens.py` | every `var(--x)` that paints resolves to a declared token | an undeclared custom property does not error and does not warn; the declaration is silently dropped |
| `routes.py` | every route is named, every name is unique, and the table parses as the tree it is | a duplicate route name does not throw — Vue Router keeps the last one and every `push({ name })` for the shadowed route goes somewhere else |

## Why `--selftest` matters as much as the checks

A check that cannot fail passes forever and proves nothing.

`--selftest` plants the exact defect each check is meant to catch — in a
throwaway copy of `frontend/src`, never in the real tree — asserts the check
rejects it, restores, and asserts it accepts again. Nine planted defects in
total.

**If you change a check, run the selftest before you trust a green run.** Two
of these checks were wrong on their first version and their own selftest is
what caught it.

## Two things in here that are easy to get wrong

**Comments are masked, never stripped.** Deleting a comment shifts every line
below it, so any `file:line` a check reports would be off. `mask_comments`
overwrites a comment with spaces and keeps its newlines, so offsets stay exact.

**A `.vue` file is three languages.** `<template>` is HTML, `<script>` is
TypeScript, `<style>` is CSS, and each needs a different comment rule — one
masker over a whole SFC lets a `/*` inside a `//` comment swallow the template.
Which surfaces a check reads is a property of the QUESTION, not of the file
type: a rule census reads `<style>` only, while a check on what actually paints
must also read inline `style=` attributes.

## Not wired into `npm run gate` yet

Deliberate. Adding a Python step to a JavaScript build is a decision for
whoever owns the pipeline, and these are being shaken out by hand first. When
that call is made it is one line in `frontend/package.json`:

```json
"checks": "python ../checks/run.py"
```

and adding `&& npm run checks` to the `gate` script.

## Adding a check

Give the module a `run(root) -> (ok, lines)` and a `selftest(root) -> lines`,
add it to `CHECKS` in `run.py`, and make the selftest plant a real defect. A
check whose selftest only asserts that the current tree passes is not tested —
it is just running.
