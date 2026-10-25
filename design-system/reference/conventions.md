> WHAT THIS IS:  the conventions of the AIVIS design system: how names, tokens, themes, direction, languages, widths, type, icons and decoration are fixed, each with its source.
> FOR WHOM:      an agent or a person building a page, a screen or a component with no memory of earlier work.
> WHEN:          first, before `build-screen.md` or `build-component.md`.
> WHO WRITES:    the maintainers of the AIVIS design system.

# conventions

Every line below is a decision of the owner with its date, a measurement, or a value of the foundation the owner accepted on 2026-10-17, and names its basis. A value is read from `../tokens/tokens-resolved.json`, never recalled.

## Conventions

| Field | Value | Source |
|---|---|---|
| layers | primitives (five colour ramps) feed role tokens; a component binds a role token or a scale token and never a primitive | `../tokens/tokens.md` |
| value lookup | find the token name in `../tokens/tokens-resolved.json`; its `light` and `dark` fields are final | `../tokens/tokens.md` |
| literal values | no hex, rgb or pixel size in a component; the token is bound | `../INDEX.md` |
| themes | day on `:root`, night under `[data-theme="dark"]` and under the system setting when no theme is chosen; the same names in both | `../tokens/tokens-dark.css` |
| languages live | English and Russian | decided by the owner, 2026-10-16 |
| language lists | no language list is written in a screen; languages come from one shared setting, and a tool adds further languages | decided by the owner, 2026-10-16 |
| direction | right-to-left ready from the start; nothing is mirrored now; layout uses logical properties (`margin-inline`, `padding-block`, `inset-inline-start`, `text-align: start`, `inline-size`) | decided by the owner, 2026-10-16 |
| Arabic script | `Noto Sans Arabic` follows the Latin family in each of the three font stacks | decided by the owner, 2026-10-16; `../tokens/tokens.css` |
| families | headings `Commissioner`, text `Inter`, figures `JetBrains Mono` | decided by the owner, 2026-10-17 |
| faces | Commissioner 700 and 800, Inter 400, 600 and 700, JetBrains Mono 400 and 700, each in latin, latin-ext, cyrillic, cyrillic-ext and greek; Noto Sans Arabic; no other face | decided by the owner, 2026-10-16, 2026-10-17 |
| type roles | display Commissioner 800; h1 to h4 Commissioner 700; text Inter 400; the smallest step Inter 600 | `../tokens/type-recipe.json` |
| widths | 480, 640, 880 and 1120 pixels, `--bp-sm`, `--bp-md`, `--bp-lg`, `--bp-xl`; a media query writes the number because a custom property cannot be read in a media condition | decided by the owner, 2026-10-16; `../tokens/tokens.md` |
| content measures | `--maxw` 1080, `--maxw-wide` 1240, `--maxw-prose` 680, `--maxw-form` 360, `--maxw-form-wide` 400, `--maxw-doc` 800 | `../tokens/tokens.md` |
| accent and warning | `#B1581B` by day (amber-600) | decided by the owner, 2026-10-16 |
| accent hover | amber-700 `#9A4410` by day | decided by the owner, 2026-10-17 |
| quiet text | `--text-tertiary` `#6B7785`; by day it stands on white surfaces only; on the day page ground and the day card ground `--text-secondary` stands instead; by night tertiary text stands on every night ground (4.81 or better on every ground) | decided by the owner, 2026-10-16, 2026-10-17; measured (`../tokens/contrast.json`) |
| amber and grey as text | never on the card ground `#EDF1F5`; amber stays as an icon or a border there | decided by the owner, 2026-10-17; measured (`../tokens/contrast.json`) |
| text on primary | `--on-primary`: `#FFFFFF` by day, `#04243E` on every primary button by night; `--text-on-brand` follows it | decided by the owner, 2026-10-17; measured (`../tokens/contrast.json`) |
| input border | `--border-input`: `#7F97AE` by day, `#506579` by night; inputs only; card borders stay as they are (`--border-subtle`, as in `../elements/README.md`) | decided by the owner, 2026-10-17; measured (`../tokens/contrast.json`) |
| input border width | `--border-input-width`, 1 px | decided by the owner, 2026-10-17 |
| focus ring | `--focus-ring`: azure-500 `#217AB6` by day, azure-300 `#37A6E6` by night; never the accent; the focus indicator is a `--focus-width` (2 px) solid outline in `--focus-ring` with a `--focus-offset` (2 px) offset, and no `--shadow-focus` halo | decided by the owner, 2026-10-17; measured (`../tokens/contrast.json`) |
| icons | one set, 97 icons, drawn on a 24 by 24 grid, stroke 1.5 screen pixels at every icon size (non-scaling), round caps and joins, nothing filled, `currentColor`; symbol id `i-<name>`; a key of `../components/icons/icons.json` only | decided by the owner, 2026-10-16, 2026-10-18, 2026-10-25 |
| rocket, spark and qr | used from 24 pixels up | decided by the owner, 2026-10-17, 2026-10-18 |
| the hexagon | the hexagon is the logo and the decorative elements; it is never a rule for the icons | decided by the owner, 2026-10-16 |
| brand marks | the colour logo is unchanged; the mark drawn in lines has no inner facet lines | decided by the owner, 2026-10-17 |
| decoration | pattern, mark on the grid, divider, cube hexagon and card tick as in `../elements/README.md`; line weight 1 px by day and 1.5 px by night, divider 1 px in both | decided by the owner, 2026-10-17 |
| ground under decoration | primary and secondary text only on a pattern or the mark | decided by the owner, 2026-10-17 |
| button looks | `primary`, `accent`, `secondary` (bordered, `--border-input`), `ghost` (no border; the quiet and the link-style action), `danger`, and `telegram` (the brand exception); no other name | decided by the owner, 2026-10-17 |
| button and field sizes | `sm` 32, `md` 38, `lg` 44 on `--control-height-*`; every interactive part is at least `--touch-min` high at the 480 width; an icon-only button is kept and takes an `aria-label` | decided by the owner, 2026-10-17 |
| status names | `danger` and `info` in the badge, the alert and the toast (the progress carries success, warning and danger); there is no `error` status and no status called `primary` (the field's invalid-message part keeps the part name `.ds-field__error`) | decided by the owner, 2026-10-17 |
| text on info and warning | `--on-info` (`#FFFFFF` day, `#04243E` night); `--on-warning` is `--on-accent` | decided by the owner, 2026-10-17 |
| input hover border | `--border-input-hover`: `#6B7785` day, `#9BA8B6` night | decided by the owner, 2026-10-17 |
| badge radius | `--radius-sm` | decided by the owner, 2026-10-17 |
| tabs | the focus is an outline outside the tab at `--focus-offset`, with the strip's padding; on a phone the strip scrolls sideways | decided by the owner, 2026-10-17 |
| the Telegram button | kept as the cabinet has it, bound to `--telegram`, `--telegram-hover`, `--on-telegram`; the one brand exception | decided by the owner, 2026-10-17; `refusals.md` |
