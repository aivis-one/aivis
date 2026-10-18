> WHAT THIS IS:  the order of work for building one page or screen of AIVIS inside the design system.
> FOR WHOM:      an agent or a person who has no memory of earlier work.
> WHEN:          at every request that emits a page or a screen for the site or a cabinet.
> WHO WRITES:    the navigator of Agent-Aivis.one.

# build-screen

**Mode:** BUILD-SCREEN, one page or screen of the site or of a cabinet, inside the design system.

**Inputs:** the purpose of the screen, its content in English and Russian, the themes in scope.

**Outputs:** page code that binds tokens, passes `refusals.md` and shows correctly in the day and the night theme.

## Pre-read

| # | Read | Why |
|---|---|---|
| 1 | `../INDEX.md` | what each folder holds and the order in which a page links the files |
| 2 | `conventions.md` | the decided values and their sources |
| 3 | `../tokens/tokens.md` | which token to bind by role, and which text stands on which ground |
| 4 | `refusals.md` | every "never", with the correct answer |
| 5 | `../elements/README.md` | only when the screen carries decoration |

## Steps

1. Link, in this order: `../fonts/fonts.css`, `../tokens/tokens.css`, `../tokens/tokens-dark.css` (`../INDEX.md`). Set `data-theme="light"` or `"dark"` on the root, or set none and follow the system.
2. Lay out with the four widths 480, 640, 880 and 1120 pixels and with logical properties only (`conventions.md`: widths, direction).
3. Choose every colour by role from `../tokens/tokens.md`, then find each token name in `../tokens/tokens-resolved.json` to confirm the value in both themes. Bind the name in code; the looked-up value is for checking.
4. Choose the text colour for each ground by the table "Text on grounds" of `../tokens/tokens.md`: by day quiet text stands on white surfaces only, and on the day page ground and the day card ground `--text-secondary` stands instead; by night tertiary text stands on every ground; amber never as text on the card ground.
5. Set type with `--font-display` for headings, `--font-body` for text and `--font-mono` for figures; the sizes come from the scale of `../tokens/type-recipe.json`.
6. Draw an input with a `--border-input-width` (1 px) border in `--border-input`; show focus as a `--focus-width` (2 px) solid outline in `--focus-ring` with a `--focus-offset` (2 px) offset and no `--shadow-focus` halo (the owner's decision of 2026-10-17 (small points on the focus and border page)); a primary button takes `--on-primary` for its text (`conventions.md`).
7. Take every icon from `../components/icons/icons.svg` by a key of `../components/icons/icons.json`; the rocket, the spark and the qr from 24 pixels up (`min_size_px` in `icons.json`).
8. Add decoration only from `../elements/`, in the way its README places each part; read the tick rules before putting a tick on a card.
9. Take every string from the product's shared language setting (it lives in the site and cabinet code, not in this tree), English and Russian; write no language list in the screen.
10. Look the contrast of each text and non-text pair up in `../tokens/contrast.json`; a pair that is not in the file is computed with the formula named there, in both themes.
11. Open the screen in the day theme and in the night theme, at 375 pixels and at a desktop width, with Russian text; every Cyrillic and Greek letter must be drawn by the family of its role.
12. Re-read `refusals.md` against what was written and quote every row that the screen trips.

## Gate-out

| Check | Pass condition |
|---|---|
| tokens | no literal hex, rgb or pixel size in the screen |
| text on grounds | no amber text on the card ground; by day no tertiary text on the page ground or the card ground; no tertiary text on a pattern or the mark |
| widths | the only breakpoints are 480, 640, 880 and 1120 |
| direction | no physical left or right property in layout |
| icons | every icon is a key of `icons.json`; rocket, spark and qr at 24 pixels or larger |
| decoration | every part follows `../elements/README.md`; no tick on a form, a dialog, a table, an alert, a single card or a card that is not a list item |
| focus | every interactive part shows a `--focus-width` solid outline in `--focus-ring` with a `--focus-offset` offset |
| themes | both themes viewed |
