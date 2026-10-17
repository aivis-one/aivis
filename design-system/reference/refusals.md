> WHAT THIS IS:  every "never" of the AIVIS design system, each with the correct answer, its reason and its source.
> FOR WHOM:      an agent or a person who has just built a page, a screen or a component and must check it.
> WHEN:          after building, before showing; and whenever a line of `conventions.md` is in doubt.
> WHO WRITES:    the navigator of Agent-Aivis.one.

# refusals

A prohibition without a replacement sends work back to guessing, so every row names one. The source tags are those of `conventions.md`; a contrast figure is the day-theme ratio of `../tokens/contrast.json` unless the row says night.

## Colour and text

| Do not | Instead | Why | Source |
|---|---|---|---|
| set amber (`--accent`, `--warning`, `#B1581B`) as text on the card ground `#EDF1F5` | use amber as an icon or a border there; set the text in `--text-secondary` | 4.32 on the card ground, under the 4.5 text floor | Q 2jvykpm7 A; M |
| set grey (`--text-tertiary`, `#6B7785`) as text on the day card ground | `--text-secondary` | 4.02 on the card ground | Q 2jvykpm7 A; M |
| set `--text-tertiary` on the day page ground `#F6F8FA` | `--text-secondary` (6.92) | tertiary is 4.29 on the page ground; by day it stands on white surfaces only (4.56) | SP 4b; M |
| set `--text-tertiary` on a pattern or on the mark | `--text-primary` or `--text-secondary` | on a pattern or the mark only primary and secondary text stand; the contrast of tertiary there is under 4.5 | P4 |
| use the cabinet's old values `#606A77` for tertiary or amber-700 `#9A4410` for the accent by day | `--text-tertiary` `#6B7785`, `--accent` `#B1581B` | the owner chose the site's lighter values everywhere | Q 16qygyq6 B |
| use amber-800 `#652C0A` as the hover of the accent by day | `--accent-hover`, amber-700 `#9A4410` | the cabinet's amber-800 was not carried | SP 4a |
| set white text on a primary button in the night theme | `--on-primary`, `#04243E` (5.85 on `#37A6E6`) | white on the night primary is 2.71 | SP 4c; M |
| write a literal hex, rgb or pixel size in a component | bind the role token chosen per `../tokens/tokens.md` | a literal does not follow a theme change | `../INDEX.md` |
| recall a token value from memory | find the token name in `../tokens/tokens-resolved.json` | a recalled value is a guess | `../tokens/tokens.md` |

## Inputs and focus

| Do not | Instead | Why | Source |
|---|---|---|---|
| draw an input with `--border-default` | `--border-input` (`#7F97AE` day, `#506579` night) | the input border is the stronger one: 3.03 against white by day and 3.01 against the night surface | SP 4d; M |
| use `--border-input` on a card or a divider | `--border-default` or `--border-subtle` | the input border is for inputs only; card borders are unchanged | SP 4d |
| draw the focus ring in the accent colour | `--focus-ring` (azure-500 day, azure-300 night) | the accent also marks primary actions and warnings, so focus and action would blur together | Q xja37czs A |
| draw the focus ring in azure-300 by day | `--focus-ring`, azure-500 `#217AB6` by day (4.09 at the lowest) | azure-300 measures 2.38 to 2.71 by day, under the 3:1 floor for a focus indicator | Q xja37czs A; M |
| draw the focus indicator as a halo (`--shadow-focus`) | the 2 px outline: `outline: var(--focus-width) solid var(--focus-ring); outline-offset: var(--focus-offset)` | the focus indicator is an outline, with no halo | the owner's decision of 2026-10-17 (small points on the focus and border page) |
| draw an input border of a width other than 1 px | `--border-input-width` | the input border is 1 px | the owner's decision of 2026-10-17 (small points on the focus and border page) |
| draw the hover border of an input in another colour than `--border-input-hover` | `--border-input-hover` (`#6B7785` day, `#9BA8B6` night) | one hover colour for every input and for the controls that read as inputs | the owner's decision of 2026-10-17 (P5.1 small point h) |
| draw the secondary button, the filter chip or the toggle track on hover with `--border-strong` or `--border-default` | `--border-input` | these controls read as inputs and the border must reach 3:1 (3.03 day, 3.01 night) | the owner's decision of 2026-10-17 (P5.1 small point g) |

## Brand exception

| Do not | Instead | Why | Source |
|---|---|---|---|
| restyle the Telegram button, or hold it to the 4.5 text floor | the `telegram` button variant, bound to `--telegram`, `--telegram-hover` and `--on-telegram` as they stand: the one brand exception of the system | white on `#2AABEE` is 2.57 and on `#229ED9` 3.02, under 4.5; kept because Telegram's brand is not ours to restyle; no other component carries a brand colour | the owner's answer of 2026-10-17, question m5twqis7 A; frontend/src/styles/variables.css:386, 387, 395 |

## Typefaces

| Do not | Instead | Why | Source |
|---|---|---|---|
| name a family in a component | bind `--font-display`, `--font-body` or `--font-mono` | the stacks hold the Arabic family and the system fallbacks | `../tokens/type-recipe.json` |
| use a typeface outside Commissioner, Inter, JetBrains Mono and Noto Sans Arabic, including Plus Jakarta Sans and Manrope | the three families by role | the owner replaced the former pair | owner's decision of 2026-10-17 |
| add a weight or a script slice that is not in `../fonts/fonts.css` | the shipped faces: Commissioner 700 and 800, Inter 400, 600 and 700, JetBrains Mono 400 and 700 | only the faces in use are kept | faces in use |
| ship Devanagari | none | the Devanagari slices are not carried | faces in use |

## Icons

| Do not | Instead | Why | Source |
|---|---|---|---|
| use an icon from outside the set, or a second icon set | a key of `../components/icons/icons.json` | one set is the owner's decision | P1 icons |
| draw an icon with a fill, a gradient, an opacity or a hard-coded colour, or with a stroke other than 1.5, round caps and joins | the rules of `../components/icons/STYLE-P1.md` | the set is one style | P1 icons |
| show the rocket or the spark icon below 24 pixels | 24 pixels or larger | the rocket is dense and the spark reads as a spinner at 16 pixels | SP 4e |
| draw an icon from the hexagon of the logo | the P1 rules | the hexagon is the logo and the decorative elements, never a rule for the icons | the owner's decision of 2026-10-16 (Q gorvrzo8) |

## Decoration

| Do not | Instead | Why | Source |
|---|---|---|---|
| put the tick on a form, a dialog, a table, an alert or a single summary card | no tick | rule 3 of the tick | P4 |
| put the tick on a card that is not an item of a list (a course, a module, a project, a lesson) | no tick | rule 1 of the tick | P4 |
| put a tick on a list of one card | no tick | rule 6 of the tick | P4 |
| put more than one tick on a card, or make it other than 88 by 3 pixels from the left edge of the card text | one tick, `--tick-length` by `--tick-thickness` | rule 4 of the tick | P4 |
| let the tick carry a status or an action, or let its colour mean something | show status and action another way; the colours follow the list order, azure, emerald, amber, then again | rules 2 and 5 of the tick | P4 |
| draw the mark on the grid unfilled, or off the grid | fill its pieces with the ground colour, centre it on a hexagon centre with its outer points on grid points | the mark stands in front of the lattice | P4 (the owner's word on 2026-10-17) |
| give the mark's outline a different weight from the grid line | `--deco-mark-line-width` against `--deco-line-width` (1.09 against 1 px by day, 1.63 against 1.5 px by night) | the two must look equally heavy | P4 (the owner's word on 2026-10-17) |
| draw the pattern at 1 px in the night theme | 1.5 px by night, 1 px by day; the divider is 1 px in both | the owner's decision of 2026-10-17 on line weight | P4 |
| draw the line mark with its inner facet lines, or change the colour logo | the line mark of `../elements/` (outer pieces only); the colour logo stays as it is | only the mark drawn in lines loses the inner lines | the owner's decision of 2026-10-17 (Q 148jakgc) |

## Layout and language

| Do not | Instead | Why | Source |
|---|---|---|---|
| write a breakpoint other than 480, 640, 880 or 1120 pixels | one of the four | the four widths are the owner's decision | Q zmtkqznm A |
| use a physical property (`margin-left`, `padding-right`, `left`, `text-align: left`) in layout | the logical property | the structure is right-to-left ready | Q nwyyoilh |
| mirror a layout now | keep the layout as built; use logical properties so a later mirror is free | nothing is mirrored now | Q nwyyoilh |
| write a list of languages in a screen | take the languages from the shared setting | the owner's decision | the owner's decision of 2026-10-16 (language setting) |
| write copy in a language outside English and Russian as a live string | keep it in the translation tables | only English and Russian are live | Q nwyyoilh |
