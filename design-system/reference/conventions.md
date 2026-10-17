> WHAT THIS IS:  the conventions of the AIVIS design system: how names, tokens, themes, direction, languages, widths, type, icons and decoration are fixed, each with its source.
> FOR WHOM:      an agent or a person building a page, a screen or a component with no memory of earlier work.
> WHEN:          first, before `build-screen.md` or `build-component.md`.
> WHO WRITES:    the navigator of Agent-Aivis.one.

# conventions

Every line below is a decision of the owner, a measurement, or a value of the foundation he accepted on 2026-10-17 (aivis 452a095), and names its source. A value is read from `../tokens/tokens-resolved.json`, never recalled.

## Sources

| Tag | Meaning |
|---|---|
| Q `<id>` | a closed question of the owner, answered 2026-10-16 or 2026-10-17; the letter is the option he chose |
| SP 4a to 4e | the five small points the owner agreed on 2026-10-17: 4a the hover of the accent, 4b where quiet text stands, 4c night text on primary, 4d the input border, 4e the rocket and spark icons |
| P4 | the decorative page the owner accepted on 2026-10-17 (`index.html` sha256 `fa48b9d3e109849da64fbdbb1da9f056cbaa1a484d60423f7c0214f06e17fa3f`), carried into `../elements/` |
| P1 icons | the icon set the owner accepted on 2026-10-16: 93 icons, `../components/icons/STYLE-P1.md` |
| M | a measured contrast in `../tokens/contrast.json`, by the formula named there |
| faces in use | the owner's word of 2026-10-16 that only the faces in use are kept |

## Conventions

| Field | Value | Source |
|---|---|---|
| layers | primitives (five colour ramps) feed role tokens; a component binds a role token or a scale token and never a primitive | `../tokens/tokens.md` |
| value lookup | find the token name in `../tokens/tokens-resolved.json`; its `light` and `dark` fields are final | `../tokens/tokens.md` |
| literal values | no hex, rgb or pixel size in a component; the token is bound | `../INDEX.md` |
| themes | day on `:root`, night under `[data-theme="dark"]` and under the system setting when no theme is chosen; the same names in both | `../tokens/tokens-dark.css` |
| languages live | English and Russian | Q nwyyoilh |
| language lists | no language list is written in a screen; languages come from one shared setting, and a tool adds further languages | the owner's decision of 2026-10-16 (language setting) |
| direction | right-to-left ready from the start; nothing is mirrored now; layout uses logical properties (`margin-inline`, `padding-block`, `inset-inline-start`, `text-align: start`, `inline-size`) | Q nwyyoilh |
| Arabic script | `Noto Sans Arabic` follows the Latin family in each of the three font stacks | Q nwyyoilh; `../tokens/tokens.css` |
| families | headings `Commissioner`, text `Inter`, figures `JetBrains Mono` | owner's decision of 2026-10-17 (Q g39kslro, uvapj8hy, w4g8sqfr) |
| faces | Commissioner 700 and 800, Inter 400, 600 and 700, JetBrains Mono 400 and 700, each in latin, latin-ext, cyrillic, cyrillic-ext and greek; Noto Sans Arabic; no other face | owner's decision of 2026-10-17; faces in use |
| type roles | display Commissioner 800; h1 to h4 Commissioner 700; text Inter 400; the smallest step Inter 600 | `../tokens/type-recipe.json` |
| widths | 480, 640, 880 and 1120 pixels, `--bp-sm`, `--bp-md`, `--bp-lg`, `--bp-xl`; a media query writes the number because a custom property cannot be read in a media condition | Q zmtkqznm A; `../tokens/tokens.md` |
| content measures | `--maxw` 1080, `--maxw-wide` 1240, `--maxw-prose` 680, `--maxw-form` 360, `--maxw-form-wide` 400 | `../reference/sources.md` |
| accent and warning | `#B1581B` by day (amber-600) | Q 16qygyq6 B |
| accent hover | amber-700 `#9A4410` by day | SP 4a |
| quiet text | `--text-tertiary` `#6B7785`; by day it stands on white surfaces only; on the day page ground and the day card ground `--text-secondary` stands instead; the night theme was not put to him (night tertiary measures 4.81 or better on every ground) | Q 16qygyq6 B; SP 4b; Q 2jvykpm7 A; M |
| amber and grey as text | never on the card ground `#EDF1F5`; amber stays as an icon or a border there | Q 2jvykpm7 A; M 4.32 and 4.02 |
| text on primary | `--on-primary`: `#FFFFFF` by day, `#04243E` on every primary button by night; `--text-on-brand` follows it | SP 4c; M 5.85 by night |
| input border | `--border-input`: `#7F97AE` by day, `#506579` by night; inputs only; card borders stay as they are (`--border-subtle`, as on the 4d page and in `../elements/README.md`) | SP 4d; M 3.03 and 3.01 |
| focus ring | `--focus-ring`: azure-500 `#217AB6` by day, azure-300 `#37A6E6` by night; never the accent | Q xja37czs A; M 4.09 at the lowest by day |
| icons | one set, 93 icons, drawn on a 24 by 24 grid, stroke 1.5, round caps and joins, nothing filled, `currentColor`; symbol id `i-<name>`; a key of `../components/icons/icons.json` only | P1 icons |
| rocket and spark | used from 24 pixels up | SP 4e |
| the hexagon | the hexagon is the logo and the decorative elements; it is never a rule for the icons | the owner's decision of 2026-10-16 (Q gorvrzo8) |
| brand marks | the colour logo is unchanged; the mark drawn in lines has no inner facet lines | the owner's decision of 2026-10-17 (Q 148jakgc) |
| decoration | pattern, mark on the grid, divider, cube hexagon and card tick as in `../elements/README.md`; line weight 1 px by day and 1.5 px by night, divider 1 px in both | P4 |
| ground under decoration | primary and secondary text only on a pattern or the mark | P4 |
