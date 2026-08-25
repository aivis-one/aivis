# checks/ — static checks on the frontend source

```bash
python checks/run.py            # run them; exit 0 = all pass
python checks/run.py --selftest # prove each one can FAIL, then that it passes
```

Standard library only. No pip install, no node. Python is already a project
dependency (`backend/pyproject.toml`), so this adds no toolchain.

## What this is

Five checks on `frontend/src` that the type checker and the unit tests cannot
express, because each is a property of the CSS or the router **as a whole**
rather than of one module.

Every one of them exists because the product actually had the defect it looks
for. None of them is a style preference.

| check | what it asserts | the defect it was written for |
|---|---|---|
| `breakpoints.py` | the declared `--bp-*` set and the widths actually in use are the SAME set — every width in a `@media` query is declared, AND every declared token is used by something | seven different breakpoints lived in 31 media queries across 22 files and only two were named anywhere. The converse direction was added later, after `--bp-tier-lg` sat declared-and-unused while the one rule keyed to its value carried a bare literal |
| `shell_layout.py` | the shell chrome has one source; the storefront stays outside the tier system; the tab-bar hide rule keeps its specificity; StaffShell keeps its own content cap | four shells carried the same `@media (min-width: 820px)` block byte for byte — a tier change had to be made in four places |
| `tokens.py` | every `var(--x)` that paints resolves to a declared token | an undeclared custom property does not error and does not warn; the declaration is silently dropped |
| `routes.py` | every route is named, every name is unique, and the table parses as the tree it is | a duplicate route name does not throw — Vue Router keeps the last one and every `push({ name })` for the shadowed route goes somewhere else |
| `preauth.py` | every route with no width breakpoint anywhere in its closure carries a declared, non-empty reason for being fixed-width, and the set of such routes is re-derived from the router on every run | twelve pre-auth screens looked like twelve missing breakpoints and were not one — they cap with a design token and centre, and a `max-width` on a centred card is width behaviour. The defect was the SILENCE: nothing said the narrowness was deliberate, so the next reader would have “fixed” it |

## Why `--selftest` matters as much as the checks

A check that cannot fail passes forever and proves nothing.

`--selftest` plants the exact defect each check is meant to catch — in a
throwaway copy of `frontend/src`, never in the real tree — asserts the check
rejects it, restores, and asserts it accepts again. **Nineteen distinct plants,
reported over eighteen lines, across all five checks.** The two totals
differ because `tokens.py` plants three bad `var()` uses in one probe file and
reports them on two lines. **Each figure says which measure it is.** This line
read “Nine planted defects in total” until 2026-08-25, and **that figure was
right when it was written** — nine distinct defects over eight lines at
`c8e5646`. It went stale in two later commits that nobody thought of as
touching it: `77e57c9` added the survival plant, `41490fa` added `preauth.py`'s
four. **An unlabelled count is how that happens invisibly — a reader cannot
tell whether the number moved or the thing under it did.**

**If you change a check, run the selftest before you trust a green run.** Two
of these checks were wrong on their first version and their own selftest is
what caught it.

**`breakpoints.py` gained its second direction on 2026-08-25, and the hole it
closed is worth stating.** Asserting that every width IN USE is declared says
nothing about a token declared and used by NOTHING — `--bp-tier-lg` sat exactly
there, a tier that existed only in this stylesheet's opinion of itself, while
the single rule keyed to its value carried a bare literal. Three plants guard
the new direction: an orphan token is caught; **the same token named only inside
a comment is still caught**, because prose is not use and if the masker stopped
working this half could never fail; and a token a script reads by name SURVIVES,
because the check must not punish a legitimate use. The control that proves it:
neuter the branch and the new selftest goes red while the old one stays green.

**`routes.py` was the exception until 2026-08-25, and it is worth naming rather
than quietly repairing.** Its selftest parsed the live route table and exercised
the tree-walker on a synthetic string — both of which pass on a tree that is
fine — and never called `run()` at all, so neither of its two failure branches
had ever been shown to fire. Both are now planted and both fire. **The check had
been correct the whole time; its selftest simply did not say so, and those are
two different statements.** The control that proves the repair is not the
obvious one: `run()` is unchanged, so the new selftest passes against the old
file either way. What bites is neutering each branch of `run()` in a throwaway
copy — the new selftest goes red on both, the old one stays green on both.

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

## Wired into `npm run gate`, 2026-08-25

The shake-out period is over and it was not ceremonial: three defects were found
INSIDE these checks during it, each by a selftest or by a second reader. Two
lines in `frontend/package.json`:

```json
"checks": "python ../checks/run.py",
"gate":   "npm run checks && npm run type-check && npm run test && npm run audit && npm run build"
```

**The checks run FIRST, not last.** They are stdlib-only and take under a second;
the build is the expensive step, and failing fast is the whole reason to have
them in the chain at all.

### The two premises under that recipe, both measured rather than assumed

**The relative path.** `../checks/run.py` only works if the script's working
directory is the package directory. It is, in BOTH invocations this repository
actually uses — measured with a probe script that printed `process.cwd()`:

| invocation | script cwd |
|---|---|
| `npm --prefix frontend run gate` from the repo root | `…/aivis/frontend` |
| `npm run gate` from inside `frontend/` | `…/aivis/frontend` |

They agree, so the relative path stands. Had they differed, the fix would have
been to make the path independent of cwd rather than to pick a winner.

**The interpreter.** The script says `python`, and that is a real dependency on a
name nobody voted for, so here is exactly what was measured on the machine this
was wired on (Windows 11, via npm's own shell, not via a POSIX shell):

| name | resolves to |
|---|---|
| `python` | Python 3.13.13, `C:\Program Files\Python313\python.exe` |
| `python3` | Python 3.14.5, the WindowsApps shim |

Both run, and they are **not the same interpreter**. `python` was kept because it
resolves to a real installation rather than a Store shim and because every run in
this project's record was made with it. **The known limit, stated rather than
hidden: on a POSIX box where only `python3` exists, this line needs to say
`python3`.** Nothing here needs pip — standard library only — and Python is
already a project dependency via `backend/pyproject.toml`.

### What the wiring control proved

A gate that NAMES the checks but would go green if they failed is worse than no
wiring, because everyone believes it. So the wiring has its own control: plant an
undeclared `777px` breakpoint in the real tree, **assert the break is LIVE**
(`checks/run.py` alone fails and names 777) before believing anything about the
gate, then read the gate's exit code **without a pipe** — a pipe gives you the
last command's code, which has produced a false zero here twice.

```
checks pass on the untouched tree                 exit 0
THE BREAK IS LIVE: checks fail and name 777       exit 1
gate NON-ZERO from the repo root (--prefix)       exit 1
the gate's output names the planted width         777 present
gate NON-ZERO from inside frontend/               exit 1
checks pass again after restore                   exit 0
gate ZERO again after restore                     exit 0
the victim file is byte-identical                 sha256 match
```

The plant is restored in a `finally`, so a crash mid-run cannot leave the tree
broken, and the file's sha256 is compared before and after.

## Adding a check

Give the module a `run(root) -> (ok, lines)` and a `selftest(root) -> lines`,
add it to `CHECKS` in `run.py`, and make the selftest plant a real defect. A
check whose selftest only asserts that the current tree passes is not tested —
it is just running.
