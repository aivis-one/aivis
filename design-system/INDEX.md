> WHAT THIS IS:  the index of the AIVIS design system: what each folder holds and how to build from it.
> FOR WHOM:      anyone building the site, a cabinet screen or a document for AIVIS.
> WHEN:          first, before any page or screen is built.
> WHO WRITES:    the maintainers of the AIVIS design system; every change to a folder updates this index in the same commit.

# AIVIS design system: index

One tree. Every file exists once. Open this file first; every folder below has one job.

## What is where

| Folder | What it holds |
|---|---|
| `tokens/` | The values. `tokens.css` (day, default) and `tokens-dark.css` (night) as CSS variables; `tokens-resolved.json` every token resolved to a literal per theme, the value authority; `type-recipe.json` the families, the scale and the font faces; `contrast.json` the measured pairs in both themes; `tokens.md` how to choose a token by role |
| `fonts/` | Commissioner (headings), Inter (text), JetBrains Mono (figures) and Noto Sans Arabic as woff2 slices, `fonts.css` the @font-face declarations, `LICENSE.md` and `OFL.txt` |
| `brand/` | The mark (colour, mono, ghost, glints), the wordmark and the logo lockup |
| `components/` | The components: `components.css` the styles (tokens only), `components.js` the behaviour markup cannot carry, `components.json` one entry per component (variants, sizes, states, tokens, accessibility), `components.md` how to choose and use each, `markup/` the markup of each; Button, Text field, Radio, Toggle, Checkbox, Card, Stat tile, Hero, Badge, Alert, Tabs, Filter chip, Toast, Progress, Loader, App shell and navigation, Tooltip, Pager, Skeleton, Row list, Key-value list, Empty state, Table, Accordion, Segmented control, Nav tile, OTP input, Date picker, File input, Combobox, Avatar, Chat thread and composer, Reorder list, Structured payout form, Auth shell, Action menu, Stepper and schedule list, Dialog, Document sheet and viewer, Document row with download, Copyable value, Invoice and QR block, Timeline, Booking card and Bar chart with a text alternative so far, and the four shared text parts (`.ds-section-title`, `.ds-note`, `.ds-amount`, `.ds-label`) |
| `components/icons/` | The icon set: `icons.svg` the sprite of 97 icons in style P1, `icons.json` the key inventory, `STYLE-P1.md` the drawing rules |
| `elements/` | The decorative elements: the lattice pattern, the line mark, the divider ornament and the cube hexagon as masks, in a day and a night file where the line weight differs, `README.md` how each is built and placed (the grid fit, the fades, the card tick) and the usage rules |
| `reference/` | The documents an agent builds from: `conventions.md` the decided values with their sources, `refusals.md` every "never" with its replacement, reason and source, `build-screen.md` and `build-component.md` the order of work |
| `examples/` | `components-1.html`, `components-2.html`, `components-3.html`, `components-4.html`, `components-5.html` and `components-6.html`: every component of `components/` in use (batches 1, 2, 3 and 4, the pieces added for the cabinets in `components-5.html`, and the pieces the cabinets' screens still needed in `components-6.html`), in every state, day and night, desktop and the 480 phone width; `foundations.html` and `elements.html`: colours with contrast, type, spacing, widths, radii, shadows, motion, day and night side by side, and the icons at 16, 24 and 48 pixels; the decorative elements on a site screen, a cabinet screen and a phone, in both themes |

## Build a page from the system

Read `reference/conventions.md`, `reference/refusals.md` and `reference/build-screen.md` (a component: `reference/build-component.md`) first; the steps below are their short form.

1. Link, in this order: `fonts/fonts.css`, `tokens/tokens.css`, `tokens/tokens-dark.css`, and for components `components/components.css` (and `components/components.js` at the end of the body). Set `data-theme="light"` or `"dark"` on the root, or set none and follow the system.
2. Take each value by token name from `tokens/tokens-resolved.json`, chosen by role per `tokens/tokens.md`. Do not write a hex in a component.
3. Icons: inline `components/icons/icons.svg` once, or reference it, and use `<use href="#i-key">` for a key listed in `components/icons/icons.json`. They draw in `currentColor`.
4. Logo: files from `brand/`.
5. Widths: the four widths are 480, 640, 880 and 1120 pixels; a media query writes the number.
6. Direction: use logical properties.

## Extend the system

| New | Goes to | Also |
|---|---|---|
| a token | `tokens/tokens.css` (and both blocks of `tokens/tokens-dark.css` if it differs at night) | its row in `tokens/tokens-resolved.json`, its role in `tokens/tokens.md`; `tokens/contrast.json` if it is a colour pair |
| an icon | its symbol in `components/icons/icons.svg`, drawn by `components/icons/STYLE-P1.md`, and its key in `components/icons/icons.json` | a cell in `examples/foundations.html` |
| a font face | the file in `fonts/` and its line in `fonts/fonts.css` | `tokens/type-recipe.json` |
| a brand file | `brand/` | - |
| a decorative element | `elements/<name>.svg` and its row in `elements/README.md` | a tile in `examples/elements.html` |
| a component | its rules in `components/components.css`, its entry in `components/components.json`, its section in `components/components.md` and `components/markup/<name>.html` | a block in `examples/components-1.html`, `examples/components-2.html`, `examples/components-3.html`, `examples/components-4.html`, `examples/components-5.html` or `examples/components-6.html` with every state, day and night, desktop and phone |

## The rules in short

- No literal hex, rgb or pixel size in a component: bind a token.
- One icon set, drawn on a 24 by 24 grid with a 1.5 stroke, round caps and joins, in `currentColor`.
- Three families for Latin, Cyrillic and Greek text, one for Arabic; no other face.
- Logical properties for every layout rule.
- Day and night come from the same token names.
