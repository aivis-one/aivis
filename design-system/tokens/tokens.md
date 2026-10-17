> WHAT THIS IS:  how the AIVIS tokens are named, layered and chosen, and where each value lives.
> FOR WHOM:      anyone building a page of the site or a cabinet screen.
> WHEN:          before choosing a colour, size, space, radius, shadow or duration.
> WHO WRITES:    the navigator of Agent-Aivis.one.

# Tokens

252 tokens, one source for the site (`landing/`) and the cabinets (`frontend/src/`). The values are in `tokens.css` (day) and `tokens-dark.css` (night); `tokens-resolved.json` holds every token resolved to a literal per theme and is the value authority; `type-recipe.json` holds the families, the scale and the font faces; `contrast.json` holds the measured pairs.

## Layers

| Layer | Meaning | Bind from it? |
|---|---|---|
| primitive | the five colour ramps (azure, emerald, amber, neutral, red), theme independent | no, they feed the role tokens |
| semantic | a colour role in the interface, re-bound for the night theme | yes, always |
| scale | sizes, spaces, radii, shadows, durations, widths, type | yes |

## Themes

`tokens.css` states the day theme on `:root`. `tokens-dark.css` re-binds the same names under `[data-theme="dark"]` (a chosen theme) and under the system setting when no theme is chosen (`:root:not([data-theme])`). A page sets `data-theme="light"` or `"dark"` on the root, or sets none and follows the system.

## Colour roles

| Token | Role |
|---|---|
| `--bg-page` | the page ground |
| `--bg-surface` | a raised surface on the page: white in the day theme |
| `--bg-subtle` | the card ground: quieter panels, tiles, table bands |
| `--bg-inset` | a sunken area |
| `--bg-emphasis` | an inverse block |
| `--text-primary` | body text and headings |
| `--text-secondary` | supporting text; on the day page ground and the day card ground it stands instead of tertiary; with `--text-primary` the only text colours on a pattern or the mark |
| `--text-tertiary` | quiet text: captions, hints, meta lines; by day it stands on white surfaces only; by night it stands on every night ground |
| `--text-on-brand` | text on a brand fill; in the night theme it is `--on-primary` (`#04243E`) |
| `--text-inverse` | text on bg-emphasis |
| `--border-subtle` | hairlines and card borders; card borders are unchanged |
| `--border-default` | borders of dividers and of parts that are not inputs; it was the input border before `--border-input` |
| `--border-strong` | borders that must read |
| `--border-input` | the border of every input: `#7F97AE` by day, `#506579` by night; inputs only, and the controls that read as inputs: the secondary button, the filter chip and the toggle track on hover |
| `--border-input-hover` | the border of an input on hover: `#6B7785` by day, `#9BA8B6` by night (4.56 and 7.51 against the surface) |
| `--primary` | the brand action colour (azure) |
| `--primary-hover` | its hover |
| `--primary-active` | its pressed state |
| `--primary-subtle` | a tinted ground for primary |
| `--primary-subtle-text` | text on primary-subtle |
| `--on-primary` | text on primary: `#FFFFFF` by day, `#04243E` on every primary button by night |
| `--success` | success status |
| `--success-subtle` | tinted ground |
| `--success-subtle-text` | text on it |
| `--on-success` | text on success |
| `--accent` | the amber accent: an icon, a border or a fill; as text on white and on the page ground, never on the card ground |
| `--accent-hover` | its hover: amber-700 `#9A4410` by day |
| `--accent-subtle` | tinted ground |
| `--accent-subtle-text` | text on it |
| `--on-accent` | text on accent |
| `--info` | information status |
| `--info-subtle` | tinted ground |
| `--info-subtle-text` | text on it |
| `--on-info` | text on info: `#FFFFFF` by day, `#04243E` by night (the `--on-primary` pair; 6.11 and 5.85) |
| `--warning` | warning status; as text it follows the accent: never on the card ground |
| `--warning-subtle` | tinted ground |
| `--warning-subtle-text` | text on it |
| `--on-warning` | text on warning: an alias of `--on-accent` in both themes (`#FFFFFF` by day, `#3A1905` by night; 4.91 and 6.73) |
| `--danger` | error and destructive status |
| `--danger-hover` | its hover |
| `--danger-subtle` | tinted ground |
| `--danger-subtle-text` | text on it |
| `--on-danger` | text on danger |
| `--focus-ring` | the focus outline colour: azure-500 by day, azure-300 by night; never the accent; the outline is `--focus-width` solid with `--focus-offset` offset |
| `--toggle-track` | switch track (the same in both themes) |
| `--toggle-knob` | switch knob |
| `--icon-primary` | icon default |
| `--icon-secondary` | icon supporting |
| `--icon-disabled` | icon disabled |
| `--icon-brand` | icon in the brand colour |
| `--telegram`, `--telegram-hover` | the Telegram button's fill and its hover: `#2AABEE` and `#229ED9`, the same in both themes; the one brand exception (`../reference/refusals.md`) |
| `--on-telegram` | text on the Telegram button: `#FFFFFF` in both themes |

The tinted grounds (`*-subtle`) are opaque in the day theme and translucent in the night theme.

## Text on grounds

Measured contrast of a text colour on each ground in the day theme (the formula of `contrast.json`); the floor for text is 4.5.

| Text colour | White `#FFFFFF` | Page `#F6F8FA` | Card ground `#EDF1F5` | Where it stands |
|---|---|---|---|---|
| `--text-primary` | 18.19 | 17.09 | 16.03 | every ground |
| `--text-secondary` | 7.37 | 6.92 | 6.49 | every ground; the quiet text of the page ground and the card ground |
| `--text-tertiary` | 4.56 | 4.29 | 4.02 | white surfaces only |
| `--accent`, `--warning` | 4.91 | 4.61 | 4.32 | white and the page ground; never the card ground |
| `--success` | 6.30 | 5.91 | 5.55 | every ground |
| `--danger` | 7.86 | 7.38 | 6.92 | every ground |
| `--info` | 6.11 | 5.74 | 5.39 | every ground |

In the night theme every text colour is 4.81 or better on every ground (the lowest is tertiary on the card ground), and tertiary text stands on every night ground (the owner's decision of 2026-10-17 (small points on the focus and border page)). The sources of these rules are in `../reference/refusals.md`.

## Inputs and focus

`--border-input` is `#7F97AE` by day: 3.03 against white, 2.84 against the page, 2.67 against the card ground; by night `#506579`: 3.01 against the night surface, 3.29 against the page, 2.81 against the card ground. `--focus-ring` is `#217AB6` by day: 4.64 against white, 4.36 against the page, 4.09 against the card ground; by night `#37A6E6`: 6.72 against the surface, 7.33 against the page, 6.27 against the card ground. The input border is `--border-input-width` (1 px) wide. The focus indicator is a `--focus-width` (2 px) solid outline in `--focus-ring` with a `--focus-offset` (2 px) offset, and no `--shadow-focus` halo (the owner's decision of 2026-10-17 (small points on the focus and border page)).

## Scales

| Family | Tokens |
|---|---|
| Gradients, hex edges, depth, numerals | `--grad-azure`, `--grad-emerald`, `--grad-amber`, `--grad-brand`, `--hex-azure-face`, `--hex-azure-edge`, `--hex-emerald-face`, `--hex-emerald-edge`, `--hex-amber-face`, `--hex-amber-edge`, `--hex-neutral-face`, `--hex-neutral-edge`, `--connector-stroke`, `--connector-width`, `--numeral-display`, `--numeral-mega` |
| Focus and input border | `--focus-width`, `--focus-offset`, `--border-input-width` |
| Elevation | `--shadow-1`, `--shadow-2`, `--shadow-3`, `--shadow-deep`, `--shadow-inset-hex`, `--shadow-focus` |
| Typography | `--font-display`, `--font-body`, `--font-mono`, `--fs-3xs`, `--fs-xs`, `--fs-sm`, `--fs-body`, `--fs-body-lg`, `--fs-h4`, `--fs-lg`, `--fs-xl`, `--fs-h3`, `--fs-2xl`, `--fs-3xl`, `--fs-4xl`, `--fs-h2`, `--fs-h1`, `--fs-display`, `--fs-hero`, `--lh-tight`, `--lh-snug`, `--lh-normal`, `--tracking-tighter`, `--tracking-tight`, `--tracking-normal`, `--tracking-wide`, `--tracking-mega` |
| Spacing | `--space-1`, `--space-2`, `--space-3`, `--space-4`, `--space-5`, `--space-6`, `--space-7`, `--space-8`, `--space-9`, `--space-4-lg`, `--space-5-lg`, `--space-6-lg`, `--space-component-sm`, `--space-component-md`, `--space-component-lg`, `--space-section-sm`, `--space-section-md`, `--space-section-lg`, `--space-gutter-web`, `--space-gutter-mobile`, `--space-safe-top`, `--space-safe-right`, `--space-safe-bottom`, `--space-safe-left` |
| Radius | `--radius-xs`, `--radius-sm`, `--radius-md`, `--radius-lg`, `--radius-xl`, `--radius-pill`, `--radius-control`, `--radius-card`, `--radius-modal` |
| Motion | `--dur-instant`, `--dur-fast`, `--dur-base`, `--dur-slow`, `--dur-slower`, `--ease-standard`, `--ease-entrance`, `--ease-exit`, `--ease-spring`, `--motion-micro`, `--motion-quick`, `--motion-moderate`, `--motion-deliberate`, `--motion-ambient` |
| Widths and breakpoints | `--bp-sm`, `--bp-md`, `--bp-lg`, `--bp-xl`, `--maxw`, `--maxw-wide`, `--maxw-prose`, `--maxw-form`, `--maxw-form-wide`, `--header-height` |
| Sizes, touch and icons | `--touch-min`, `--touch-comfortable`, `--tap-min`, `--control-height-sm`, `--control-height-md`, `--control-height-lg`, `--size-2xs`, `--size-xs`, `--size-sm`, `--size-md`, `--size-lg`, `--size-xl`, `--size-2xl`, `--size-3xl`, `--size-4xl`, `--tile-min`, `--tile-max`, `--center-sm`, `--center-md`, `--center-lg`, `--icon-size-sm`, `--icon-size-md`, `--icon-size-lg`, `--icon-size-xl` |
| Decoration | `--deco-ink`, `--deco-opacity`, `--deco-line-width`, `--deco-mark-line-width`, `--deco-divider-width`, `--tick-length`, `--tick-thickness`, `--tick-cut`, `--tick-azure-start`, `--tick-azure-end`, `--tick-emerald-start`, `--tick-emerald-end`, `--tick-amber-start`, `--tick-amber-end` |

## Widths

The four widths are 480, 640, 880 and 1120 pixels (`--bp-sm`, `--bp-md`, `--bp-lg`, `--bp-xl`). A custom property cannot be read inside a media condition, so a query writes the number: `@media (min-width: 640px)`. `--maxw` (1080) and `--maxw-wide` (1240) are content measures inside a page, `--maxw-prose` caps running text, `--maxw-form` and `--maxw-form-wide` cap a form column.

## Direction

Layout uses logical properties: `margin-inline`, `padding-block`, `inset-inline-start`, `border-inline-end`, `text-align: start`, `inline-size`. A physical property appears only where the geometry is not direction-aware, with its reason beside it. `Noto Sans Arabic` stands after the Latin family in each font stack, so an Arabic string renders without a second set of tokens.

## Lookup

| Need | Do this |
|---|---|
| the value of one token, both themes | find the name in `tokens-resolved.json` |
| where a value came from | find the name in `../reference/sources.md` |
| the measured contrast of a pair | find it in `contrast.json` |
