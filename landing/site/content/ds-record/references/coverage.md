# references/coverage.md

**Role:** what this design system hands over and what it does not. Every category is either delivered
— with the payload file that carries it named — or declared absent with a reason a reader can
evaluate and disagree with. Neither state is a defect. The third state, silence, is.

**Why this file exists.** Before it, six categories were neither delivered nor declared. A consumer
could not tell a missing icon set from one nobody wanted: both read as zero errors, and the consumer
was the one who had to decide whether to invent it.

**How to read a row.** `delivered` means grep the named file and use what is there. `partial` means
some of it is there and the rest is named as a gap — read the gap before building on the part.
`declared absent` means it is not in this system, and the reason says why; building it is a project
decision, not something to improvise mid-screen.

---

## The twelve categories

| Category | State | Where it lives, or why it is not here |
|---|---|---|
| Token graph | delivered | `assets/tokens-resolved.json`. Both themes, every alias chain expanded. Rules in `references/tokens.md` |
| Component matrix | delivered | `assets/components.json`. Axes, evidence, per-component a11y duty, status. Rules in `references/components.md` |
| Brand marks | delivered | `assets/assets-manifest.json`. A reference record per mark — role, declared path, format, viewBox, polygon count. The bytes stay in the project repo by design; see the note below |
| Icon set | partial | `assets/icons.svg` carries the sprite, `assets/icons.json` the key inventory and the binding rule. **The gap: no concept-to-key mapping, and no record of the concepts this set cannot express.** Read the gap clause below before choosing an icon |
| Responsive layer | delivered | Four `bp-` primitives in the token payload; the rule, the two surfaces, and where a breakpoint does and does not belong, in `references/layout.md` |
| Theme switch | delivered | `references/tokens.md`, "Theme model" — the attribute, where it is set, the default order, the relation to `prefers-color-scheme`, and the explicit statement that no platform switch exists |
| Contrast evidence | delivered | `assets/contrast.json`. 38 pairs, both themes, translucent fills composited. **Six rows read FAIL** — see below; a live finding, not a historical note |
| Type recipe | partial | `assets/type-recipe.json` carries each family's declared name, its stack, the script split and the `@font-face` binding shape. **The gap: no binary is named for any script slot, and no path, subset range, metric override or licence travelled** — the project's font stylesheet was not among the sources this tree was frozen from |
| Microcopy rules | declared absent | **There are no microcopy rules in this design system.** Button case, error tone, empty-state phrasing and the prohibitions were never captured, so they reproduce only by an agent copying whatever surface it happens to see. Capture them at the next re-emit; until then match the surrounding surface and say that you did |
| Density | declared absent | **There are no density tokens and no density axis.** Spacing has one scale, control heights one three-step scale, and neither carries a comfortable/compact pair. A screen needing tighter rows has no token for it, and the honest move is to raise the gap rather than borrow a smaller spacing step and call it density |
| Writing direction | delivered | `references/layout.md`, "Writing direction" — LTR only, no RTL locale supported or measured, logical properties required regardless, with the refusal and its escape |
| Print | declared absent | **No print rule exists in this design system and none was captured.** It matters more here than in most systems, because half the output is decks and documents that get printed, and the dark theme has no print behaviour declared — a dark deck sent to a printer is undefined. Treat any print request as a gap to raise before building |

---

## The four gaps, each with what to do about it

**Icon concept mapping (category 4).** The sprite has 45 keys and they are named for what they draw,
not for what they mean in this product. `wallet`, `coins` and `trending-up` read straight through;
`sparkles`, `layers`, `bot` and `navigation` do not, and which product concept each carries is a
product decision that was never recorded. Choosing one by resemblance is a guess that looks like a
lookup. **Do:** pick the key whose drawn subject you can defend out loud, say in the code notes which
concept you mapped it to, and raise the mapping as missing. **Do not:** invent a key that is not in
`icons.json` — the sprite is the only icon source (hard rule R1-4 and the forbidden-dependency list
in `conventions.md`), so a key that is not there is a symbol that will not render.

**Font binaries and paths (category 8).** `type-recipe.json` states each family's declared name, its
stack order, and what the `@font-face` block has to look like. It does not state which binary fills
which script slot, nor where any file is, because the project's font stylesheet was not among the
sources this tree was frozen from. **Do:** read the slot assignments and paths from that stylesheet
and bind there; declare `@font-face` under the family's own name, never under a fallback name, or the
token's first stack entry resolves to nothing while the page still paints. **Do not:** reach for a
CDN — that breaks hard rule R1-3 — and do not substitute a system font for the display face, which is
the one that carries the split by script.

**Microcopy (category 9).** Nothing to look up. **Do:** match the tone of the surrounding surface,
keep button labels consistent with the buttons already on that screen, and name the choice as an
assumption per R7-3 rather than presenting it as system behaviour.

**Print and density (categories 10 and 12).** Both are constraints, not oversights. **Do:** say so
before building, in the same breath as the estimate. A screen that needs a density axis or a print
sheet is a system change, and the cost belongs in the conversation that precedes the work, not in the
review that follows it.

---

## The contrast finding

`assets/contrast.json` measures 38 pairs. Thirty-two pass. **All six failures are the same shape:**
the three border roles against the surface, in both themes.

| Pair | Light | Dark | Threshold |
|---|---|---|---|
| `--border-default` on `--bg-surface` | 1.57 | 1.57 | 3.0 |
| `--border-strong` on `--bg-surface` | 2.42 | 2.19 | 3.0 |
| `--border-subtle` on `--bg-surface` | 1.28 | 1.27 | 3.0 |

**What this does and does not mean.** The non-text threshold applies to a visual indicator that
identifies a control or its state. A hairline separating two blocks of content is decoration and owes
nothing — `--border-subtle` is almost certainly in that class. `--border-default` is not: it is the
control border, and where it is the only thing that says "this is an input", 1.57 is a WCAG 2.2 AA
failure and it is identical in both themes, so no theme is the safe one.

**Until the system resolves it:** do not let a border be a control's only boundary. Give the control
a filled background that differs from the surface, or a label and a focus ring that carry the
identification, and keep the border as reinforcement. The focus ring itself measures 4.36 light and
7.33 dark against the page and clears its floor comfortably, so focus is not part of this problem.

**This is a system-level fix, not a screen-level one.** Raise it; do not patch it per screen with a
darker literal, which is both an R2-1 violation and a second source for a value that has one owner.

---

## Two findings that were seen and judged, not missed

A later reader re-running the producer's mechanical checks against this tree will get two GAP lines.
Both were inspected at 1.1.0 and left standing deliberately, so that re-running the checks confirms a
judgement rather than re-opening a question.

**Orphan tokens (P-13) is reading the screen scope, not a defect.** The `tokens` array on a component
row is derived from that component's own style block, so it can only ever record component-scope
bindings. A token bound by a *screen* — the page background, section spacing, gutters, container
widths, gradients, the viewport height — has no component block to be derived from, and therefore
reads as unreferenced. Every token the check names is in that class. Declaring them `atomic_library`
would quiet the line by asserting something false: they are not a library of spare values, they are
roles that screens bind. The ones that genuinely *are* a library — the colour ramps and the spacing,
radius, type, motion, icon-size, breakpoint and facet scales — carry the declaration, and the count of
each group is a filter on the payload rather than a number written here.

**Prose naming several components on one line (P-14) fires on `composition.md`.** The check guards
against prose re-listing what the payload holds. What those rows carry is the archetype-to-slot
mapping, which the payload does **not** hold — nothing in it says which components a Form is composed
from. Removing the names would delete the only place that mapping exists. What the rows must not do is
restate *status*, and they do not: each sends the reader to `assets/components.json` for that, and the
file says so at the top.

Neither line blocks. Both are recorded here because a finding that is silently ignored is
indistinguishable from a finding that was never read.

---

## Why no bytes ship

Categories 3 and 8 deliver **records**, not files. A produced skill is loaded into an agent that
cannot render a font binary or an SVG; what the agent needs is the path, the format and the rule for
binding them, and all three are text. The bytes stay where the build already reads them, which also
keeps them from becoming a second copy with no owner. The same reasoning governs the two token
stylesheets — see `assets/README.md`.

---

## Anchor

[*] coverage.md * 12 categories * 7 delivered, 2 partial with named gaps, 3 absent with reasons * the contrast finding is live
