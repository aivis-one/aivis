> WHAT THIS IS:  the components of batches 1, 2 and 3 of the AIVIS design system: what each is for, how to choose and use it, its states, its tokens and its accessibility contract.
> FOR WHOM:      an agent or a person with no memory of earlier work, building a screen or a component.
> WHEN:          before using or changing Button, Text field, Radio, Toggle, Card, Badge, Alert, Tabs, Filter chip, Toast, Progress, Loader, App shell, Tooltip, Pager, Skeleton, Row list, Table, Accordion, Segmented control, Nav tile, OTP input, Date picker, File input, Combobox, Reorder list, Payout form or Auth shell.
> WHO WRITES:    the navigator of Agent-Aivis.one.

# components, batch 1

Files: `components.css` (all styles, tokens only), `components.js` (the behaviour that markup cannot carry: tabs keys, chip toggle, dismiss, password reveal), `components.json` (one entry per component: id, variants, sizes, states, tokens, accessibility), `markup/<name>.html` (the markup of each, copy it), `../examples/components-1.html` (every component in use, in every state, day and night, desktop and the 480 phone width).

## Use

1. Link in this order: `../fonts/fonts.css`, `../tokens/tokens.css`, `../tokens/tokens-dark.css`, `components.css`; load `components.js` at the end of the body.
2. Inline `icons/icons.svg` once in the page; draw an icon as `<svg class="ds-icon" aria-hidden="true" viewBox="0 0 24 24"><use href="#i-key"/></svg>`, a key of `icons/icons.json`. `.ds-icon--md` is 24 px. Icons draw in `currentColor`.
3. Every class starts with `ds-`. A state is never a class: hover, pressed and focus are the pseudo-classes, disabled is the attribute, an invalid value is `aria-invalid`, selected is `aria-selected` or `aria-pressed`, loading is `aria-busy`.
4. Sizes are `data-size="sm|md|lg"` (md when absent), the heights 32, 38 and 44 of `--control-height-*`; they serve buttons and text fields alike. At a viewport of 480 or less every interactive part is at least `--touch-min` high and fields are 16 px text.
5. A text a screen shows, and every `aria-label`, comes from the translation tables (English and Russian); the English strings in `markup/` are examples.
6. Status words are `danger` and `info` (with `success` and `warning`) in the badge, the alert and the toast (the progress carries success, warning and danger).

## K01 Button

Markup: `markup/button.html`.

| Part | Rule |
|---|---|
| looks | `primary` (azure, `--on-primary`): the one action of a view; `accent` (amber, `--on-accent`): a deliberate second action; `secondary` (surface, `--border-input` border): the quiet alternative; `ghost` (no border, azure label): the link-style action and the quietest one; `danger` (`--danger`, `--on-danger`): an irreversible action, which confirms; `telegram` (`--telegram`, `--on-telegram`): the one brand exception |
| sizes | `sm` 32, `md` 38, `lg` 44; `--block` is full width; `--icon` is a square the height of its size and needs `aria-label` |
| states | rest, hover (`--primary-hover`, `--accent-hover`, `--danger-hover`, `--telegram-hover`, a tint for ghost, `--bg-subtle` for secondary), pressed (the hover colour plus `--shadow-inset-hex`; `--primary-active` for primary), focus, disabled (`disabled`, 0.55 opacity), loading (`aria-busy="true"`, spinner before the label, the label stays) |
| tokens | `--primary*`, `--accent*`, `--danger*`, `--telegram*`, `--on-*`, `--border-input`, `--control-height-*`, `--radius-control`, `--space-*`, `--shadow-inset-hex`, `--dur-fast`, `--focus-*` |

The Telegram button is kept as the cabinet has it (white on `#2AABEE`, 2.57, under the 4.5 text floor): Telegram's brand is not ours to restyle. It is the one component that carries a brand colour (`../reference/refusals.md`, "Brand exception"); use it only for the Telegram sign-in or WebApp action. The set has no Telegram icon, so it carries a label only.

## K03 Text field

Markup: `markup/text-field.html`. A field is `.ds-field` (label, control, hint, message); the control is `.ds-input` on an input, a textarea or a select (the select sits in `.ds-select` with the chevron icon).

| Part | Rule |
|---|---|
| label | `<label for>` always, visible; "optional" is marked, "required" is the default |
| hint | `.ds-field__hint`, `--text-secondary`; format and example go here, not in the placeholder |
| invalid | `.ds-field__error` holds the message with the `alert-triangle` icon and a sentence; the control gets `aria-invalid="true"` and `aria-describedby` naming the message (and the hint) |
| sizes | `data-size` sm 32, md 38, lg 44 on `.ds-field` or on the control |
| states | rest, hover (`--border-input-hover`), focus, invalid, disabled, read-only |
| border | `--border-input` at `--border-input-width`; invalid `--danger`; never another border token on an input |
| amounts | `.ds-input--num`: the mono family, tabular figures |
| password | `.ds-input-wrap` + `.ds-input--reveal` + `.ds-input-reveal` with `data-label-show` and `data-label-hide` from the translation tables; the button carries no `aria-pressed`, its name switches |

## K05 Radio

`fieldset.ds-fieldset` + `legend.ds-fieldset__legend`, each option `label.ds-radio` holding the native `input.ds-radio__input`, `span.ds-radio__dot` and the text (`.ds-radio__hint` for a second line). States: unselected, hover (`--border-input-hover`), pressed, selected, focus (outline on the dot), disabled, invalid. Two to five options visible together; more use a select. Markup: `markup/radio.html`.

## K06 Toggle

`label.ds-toggle` with the text first, then `input.ds-toggle__input[type=checkbox][role=switch]`, then `span.ds-toggle__track`. States: off, on, hover (the off track takes `--border-input`), pressed, focus, disabled. A setting that applies at once is a toggle; a choice confirmed by Save is a checkbox. Markup: `markup/toggle.html`.

## K07 Card

`.ds-card` is outlined; `--flat` (card ground), `--elevated` (`--shadow-1`), `--interactive` (the title holds the single `a.ds-card__link`). `data-size` sm, md, lg sets the padding. Slots: `.ds-card__head`, `.ds-card__title`, `.ds-card__body`, `.ds-card__foot`. The tick is not part of the card (`../elements/README.md` places it, and not on a form, an alert or a single summary card). Markup: `markup/card.html`.

## K08 Badge

A status label with text, one size, radius `--radius-sm`. Variants: neutral (no modifier), `success`, `warning`, `danger`, `info`; no accent badge (its colours equal the warning badge's), a mark such as "Public" takes the neutral badge; one size and the subtle style only (the owner's answer of 2026-10-17). Each uses the status subtle ground with its subtle text; amber and grey text are never set on the card ground, which this pairing respects. Markup: `markup/badge.html`.

## K09 Alert

`.ds-alert--info|success|warning|danger`. Parts: `.ds-alert__icon` (a disc in the status colour with the glyph in the on-status colour: `--on-info`, `--on-success`, `--on-warning`, `--on-danger`), `.ds-alert__content` with `.ds-alert__title` and `.ds-alert__text`, optional `.ds-alert__actions` and `.ds-alert__close`. `role="status"` for info and success, `role="alert"` for warning and danger. Icons by severity: `info`, `check`, `alert-triangle`, `shield-alert`. Markup: `markup/alert.html`.

## K12 Tabs

`.ds-tabs[role=tablist]`, `.ds-tab[role=tab]` (`aria-selected`, `aria-controls`, `tabindex` 0 on the selected one only), `.ds-tabpanel[role=tabpanel]` (`aria-labelledby`, `tabindex=0`, `hidden` when not selected). Left and Right, Home and End move between tabs (`components.js`, direction aware). The focus is the system outline outside the tab; the strip carries the padding that keeps it from being clipped. On a phone the strip scrolls sideways. A tab changes a view in place; the five shell tabs are navigation and are the shell's batch. Markup: `markup/tabs.html`.

## K13 Filter chip

`button.ds-chip[aria-pressed]` holding the `check` icon (`.ds-chip__check`, shown when pressed), the label and an optional `.ds-chip__count`; `.ds-chip-row` lays a group out and carries `role="group"` with an `aria-label`. The border is `--border-input`. Removable: `span.ds-chip.ds-chip--removable` with `button.ds-chip__remove` and its own `aria-label`. Markup: `markup/filter-chip.html`.

## Kit fixes

| ID | Fix | Contract |
|---|---|---|
| K16 Toast | live region | `.ds-toast-region[aria-live=polite]` exists from the start and holds the toasts; a danger toast has `role="alert"`; a dismiss button; the toast ground is opaque (`markup/toast.html`) |
| K18 Progress | progressbar role | `.ds-progress__track[role=progressbar]` with `aria-valuenow`, `aria-valuemin`, `aria-valuemax` and a name; indeterminate has no `aria-valuenow`; fills `primary` (default), `success`, `warning`, `danger` (`markup/progress.html`) |
| K20 Loader | status role | `.ds-loader[role=status]` with a visible or `.ds-sr-only` text (`markup/loader.html`) |
| K40 CAppControls | labels through i18n | contract below |

### K40 contract (CAppControls)

The cabinet code is not changed by this batch; this is what the component must take from i18n. In `frontend/src/components/ui/CAppControls.vue` two names are English literals (`'Language: ' + currentShort` and `'Switch to light theme' / 'Switch to dark theme'`).

1. The language button's accessible name comes from one key with a placeholder for the current language: `common.language.current` = "Language: {name}" (Russian: "Язык: {name}"), filled with the language's own name, not its two-letter code.
2. The theme button's accessible name comes from two keys: `common.theme.toLight` = "Switch to light theme" and `common.theme.toDark` = "Switch to dark theme", with the Russian pair.
3. The listbox has an accessible name from `common.language.label` = "Language"; each option's visible text is the language's own name from the shared language setting (no list written in the component).
4. The theme button names the action, not the state; the visible icon changes with the state and the label names the action.
5. The icon-only buttons use the `--icon` button with `aria-label`; the focus indicator is the system outline; the hit area is at least `--touch-min`.

## Tokens used

Every value is a token (`components.json` lists them per component). Tokens added with this batch: `--on-info`, `--on-warning` (an alias of `--on-accent`), `--border-input-hover`, `--telegram`, `--telegram-hover`, `--on-telegram` (`../tokens/tokens.md`, `../reference/sources.md`).

No hairline-width token exists: a one-pixel line is the keyword `thin`, a double line is `calc(var(--border-input-width) * 2)`.

# components, batch 2

Batch 2 adds K25 App shell and navigation, K15 Tooltip, K17 Pager, K19 Skeleton, K23 Row list, K24 Table, K27 Accordion, K31 Segmented control and K34 Nav tile to the same files: `components.css` (after its batch 2 banner), `components.js` (the tooltip block at its end), `components.json` (one entry each, the same schema), `markup/<name>.html` (`app-shell`, `tooltip`, `pager`, `skeleton`, `row-list`, `table`, `accordion`, `segmented`, `nav-tile`) and `../examples/components-2.html` (every component in use on cabinet-like fragments, in every state, day and night, left-to-right and right-to-left, desktop and the 480 phone frame). Everything under "Use" for batch 1 holds. Every focus is the system outline outside the part; a part inside a clipping box gets padding for it.

## K25 App shell and navigation

Markup: `markup/app-shell.html`. `.ds-shell` is a grid of `.ds-header` (a `header` with one `h1.ds-header__title` and `.ds-header__actions`), `main.ds-shell__main` and one `nav.ds-nav[aria-label]` holding `ul.ds-nav__list > li > a.ds-navitem` (icon `.ds-icon--md` and `.ds-navitem__label`). The current item is `aria-current="page"`; in the tab bar it is coloured `--primary` with the kit's `--accent` dot below; in the rails it is tinted `--primary-subtle` with a 2 line `--primary` bar at the start; never colour alone. The items are links, not `role="tab"`: a tab changes a view in place (Tabs, K12), the shell navigates.

| Part | Rule |
|---|---|
| tier | the attribute `data-tier` on `.ds-shell`: `bar` (the tab bar under the content, sticky, with the safe-area insets), `rail` (the icon rail, 72 wide; the labels stay as accessible names, visually hidden), `wide` (the rail with labels, 232 wide). Header and nav swap places by grid areas. A product screen never sets the attribute: its tier follows the viewport (next row); `data-tier` forces one only in a specimen, a shell drawn inside a page narrower than the tier it shows (the examples pages) |
| tier widths | the tab bar below 880 (`--bp-lg`), the icon rail from 880, the labelled rail from 1120 (`--bp-xl`), written as `min-width` media queries on a shell with no `data-tier` (the owner's answer, question ej1wo930 A; the cabinets' own tiers were 820 and 1472, `frontend/src/styles/variables.css` lines 212 to 214) |
| header | sticky, `--header-height` or more, `--bg-surface`, a hairline below; its icon buttons are `.ds-button--ghost.ds-button--icon` with `aria-label` |
| item sizes | 56 in the bar (48 at the 480 width and below, never under `--touch-min`), 48 in the rails |
| states | rest, hover (`--bg-subtle`), pressed (`--primary-subtle`), focus (the outline outside, inside the nav's padding), current, disabled (`aria-disabled="true"`, 0.55 opacity) |
| tokens | `--bg-surface`, `--bg-page`, `--bg-subtle`, `--primary*`, `--text-*`, `--border-subtle`, `--size-3xl`, `--size-4xl`, `--header-height`, `--space-safe-*`, `--focus-*` |

The rail width has no token: it is composed from `--size-4xl` and `--space-4` (72, the kit's rail) and `--size-4xl` times four plus `--space-2` (232, the kit's labelled rail), kept as two custom properties on `.ds-shell`.

## K15 Tooltip

Markup: `markup/tooltip.html`. `span.ds-tooltip-anchor` holds the trigger (`button.ds-tooltip-trigger`, usually `.ds-button--ghost.ds-button--icon` with the `info` icon and an `aria-label`) and `span.ds-tooltip[role=tooltip][id]`; the trigger carries `aria-describedby` naming it. It opens on hover, on focus and, on a phone, by a tap. A tooltip is one short sentence of text; a link, a button or a field makes it a popover, which this batch does not have.

| Part | Rule |
|---|---|
| opens | on hover (only for a pointer that can hover), on keyboard focus, and on a tap: `components.js` toggles `data-open="true"` on the anchor for a touch pointer; a tap elsewhere closes it |
| closes | Escape closes it and sets `data-dismissed` until the pointer or the focus leaves; losing the hover or the focus closes it |
| position | `data-pos` `top` (default), `bottom`, `start`, `end`; `data-align` `start` or `end` moves a top or bottom tooltip off the centre so it stays on a narrow screen; right-to-left is handled by `:dir(rtl)` |
| ground | `--bg-emphasis` with `--text-inverse` (17.09 both themes), `--shadow-2`, `--radius-sm`, at most `--center-lg` wide; the showcase arrow is not drawn |
| hover delay | none: it opens at once on hover, focus and tap (the owner's answer) |
| states | the trigger's own (rest, hover, pressed, focus, disabled: a disabled trigger cannot open it) |

The hint is never the only place a needed fact lives: on a phone it opens only by a tap.

## K17 Pager

Markup: `markup/pager.html`. `nav.ds-pager[aria-label]` with `ul.ds-pager__list`; each item is `a.ds-pager__item` (number, `chevron-left`, `chevron-right`) or `span.ds-pager__gap[aria-hidden]`. The current page is `aria-current="page"`, filled `--primary` with `--on-primary`. A number carries `aria-label="Page n"`, previous and next their own labels; a disabled end has `aria-disabled="true"` and no `href`. States: rest (`--border-default` on `--bg-surface`, `--text-secondary`), hover (`--border-strong`, `--text-primary`), pressed (`--primary-subtle`), focus, current, disabled. 38 high, `--touch-min` at the 480 width and below. Links, not buttons: a page is an address. Show the first, the last, the current and its neighbours with a gap between.

## K19 Skeleton

Markup: `markup/skeleton.html`. `.ds-skeleton` with `--text`, `--title`, `--avatar`, `--block`; `.ds-skeleton-stack` stacks text lines and `.ds-skeleton-row` is a row-list placeholder. Every skeleton part is `aria-hidden="true"`; the region that will hold the content has `aria-busy="true"` and one `.ds-sr-only[role=status]` text from the translation tables; when the content arrives both go. The fill is the AIVIS showcase shimmer: a band of `--bg-inset` running over `--bg-subtle`, `--radius-xs`, once every `--dur-slower` times 2.5; it stops under reduced motion. Match the shape and the count of the real content; a short wait uses the Loader (K20).

## K23 Row list

Markup: `markup/row-list.html`. `ul.ds-rows` of `li.ds-row`: `.ds-row__lead` (an icon box), `.ds-row__body` (`.ds-row__title`, `.ds-row__meta`), `.ds-row__trail` (`.ds-row__value`, a badge, the chevron). A row that opens a screen holds ONE `a.ds-row__link` on its title; its `::after` stretches the hit area over the whole row, so the row and not the anchor is the touch target, and the focus outline is drawn around the row. A row with no link is plain; `aria-disabled="true"` on the `li` dims one that cannot be opened. Title `--text-primary`, meta `--text-tertiary` on the white `--bg-surface` of the row only (his SP 4b; a row never takes a fill), figures mono and tabular. States: rest, hover (`--border-default`), pressed (`--border-input-hover`), focus, disabled. 48 high, `--touch-min` at the 480 width and below. No tick: a list of rows is not a list of cards. Use a table (K24) when the reader compares columns.

## K24 Table

Markup: `markup/table.html`. `.ds-table-wrap` (a `role="region"` named by the caption, `tabindex="0"`, scrolls sideways) around `table.ds-table`: `caption.ds-table__caption` (visible), `th scope="col"`, the first cell of a row `th scope="row"`, numbers `.ds-table__num` (end-aligned, mono). A link in a cell is `a.ds-table__link`. States: rest, row hover (`--bg-subtle`), link rest, hover and focus, disabled row (`aria-disabled="true"` on the `tr`), focus of the scroll region. The header is `--text-secondary` on `--bg-subtle` (the card ground, where secondary stands).

On a phone (the 480 width and below) the table collapses to rows (his agreed P5.2, "rows on phone"). Every `td` carries `data-label` (the column name). `ds-table--phone-stack` on the table: each row is a block, the row header its title, each cell a label and value pair; a table turned to blocks loses its semantics in some browsers, so its markup carries explicit roles (`table`, `rowgroup`, `row`, `columnheader`, `rowheader`, `cell`). Use a table for three or more columns the reader compares; fewer, or one fact per record, is a row list.

## K27 Accordion

Markup: `markup/accordion.html`. Native `details.ds-accordion__item` with `summary.ds-accordion__summary` (the title and the `chevron-down` icon `.ds-accordion__chev`) and `div.ds-accordion__panel`; no script. The summary is the button: Enter and Space toggle it; the browser announces the open state. The chevron turns 180 degrees when open, as the site FAQ does (`landing/site/assets/site.css` lines 150 to 167, of which this is the port, with the chevron in `--icon-secondary`). The same `name` on the `details` lets one open at a time. States: closed, hover (`--bg-subtle`), pressed (`--bg-inset`), focus, expanded (`--shadow-1`). The summary is `--touch-comfortable` high. Do not hide what a reader must see to act, and do not nest one in another.

## K31 Segmented control

Markup: `markup/segmented.html`. `fieldset.ds-segmented` with a legend (visible, or `.ds-sr-only`) and one `label.ds-segmented__option` per choice holding a native `input.ds-segmented__input[type=radio]` with one `name`: the arrow keys move and choose, the group is one tab stop, the checked radio is the selected choice. Two to five short labels; sizes `data-size` `sm` 32, `md` 38, `lg` 44 on the fieldset, `--touch-min` at the 480 width and below. A control that switches panels is Tabs (K12); more than five options is a select; a setting that applies at once is a Toggle. States: rest, hover, pressed, focus (outline outside the option), selected, disabled.

The look (the owner's answer) is a track on `--bg-subtle` with an `--border-input` border, the chosen one raised on `--bg-surface` with a `--primary` border and `--primary-subtle-text`.

## K34 Nav tile

Markup: `markup/nav-tile.html`. `.ds-navtiles` (a grid) of `a.ds-navtile`: `.ds-navtile__icon` (an icon box), `.ds-navtile__text` (`.ds-navtile__title`, `.ds-navtile__desc`), an optional `.ds-navtile__badge` (a badge, in the row before the chevron) and `.ds-navtile__go` (the chevron at the end). The whole tile is one anchor; one that cannot be opened has `aria-disabled="true"` and no `href`. States: rest, hover (`--border-default`, `--shadow-2`), pressed (`--bg-inset`), focus, disabled. At least `--touch-min` high. Title `--text-primary`, description `--text-secondary`. Use a row list (K23) when each destination carries a value or a status. No tick.

The tile is wide (the owner's answer): the icon at the start, the title and one line of text, the chevron at the end, one column on a phone (the grid takes columns of `--tile-max` and wraps).

## Tokens used, batch 2

Every value is a token (`components.json` lists them per component). No token was added. The literal numbers are the widths of the four media queries that carry one -- `max-width: 480px` twice, and `min-width: 880px` (`--bp-lg`) and `min-width: 1120px` (`--bp-xl`) for the shell tiers -- because a custom property cannot be read in a media condition, as in batch 1; besides them the shell's `100dvh` (no dynamic-viewport-height token exists although P5.0 names one), box percentages, the shimmer's `90deg` and its gradient stops, the disabled `0.55` opacity of batch 1 and the chevron's `180deg`. Needed and not present as tokens: a rail width (72) and a labelled rail width (232).

# components, batch 3

Batch 3 adds K28 OTP input, K29 Date picker, K30 File input, K38 Combobox, K39 Reorder list, K35 Structured payout form and K33 Auth shell to the same files: `components.css` (after its batch 3 banner), `components.js` (the batch 3 block at its end), `components.json` (one entry each, the same schema), `markup/<name>.html` (`otp-input`, `date-picker`, `file-input`, `combobox`, `reorder-list`, `payout-form`, `auth-shell`) and `../examples/components-3.html` (every component in use on cabinet-like fragments, in every state, day and night, left-to-right and right-to-left, desktop and the 480 phone frame). The owner's decisions of 2026-10-17 are built in (below: the native date input, the file input as a button, the auth form on a surface panel that starts from the top on a phone, the OTP digits in the mono face). Everything under "Use" for batch 1 holds. The behaviour is in `components.js`, by delegation: no network, no storage; every text it shows comes from `data-*` attributes the page fills from the translation tables, and file sizes come from Intl in the page language. Each component fires its own events (`ds-otp-change`, `ds-otp-complete`, `ds-file-select`, `ds-file-reject`, `ds-file-remove`, `ds-combobox-query`, `ds-combobox-select`, `ds-reorder-change`); none of them submits, uploads or saves.

## K28 OTP input

Markup: `markup/otp-input.html`. `div.ds-field.ds-otp[role=group]` named by a visible label, holding `.ds-otp__cells` and six `input.ds-otp__cell`, a hint and an error. The first cell has `autocomplete="one-time-code"`, every cell `inputmode="numeric"` and an accessible name "Digit n of 6" from the translation tables. Typing advances; Backspace on an empty cell steps back; Left, Right, Home and End move (the group is a left-to-right island: `direction: ltr`, so digits and arrows keep their order in a right-to-left page); a paste, or an autofill into one cell, fills every cell. The component never submits and never auto-submits: the screen listens for `ds-otp-complete` and its Verify button stays (the cabinet verifies by a button). The resend control and its countdown are the screen's (a ghost button).

| Part | Rule |
|---|---|
| cell | `--size-3xl` by `--size-4xl`, `--radius-md`, `--fs-h3` 700 in the mono family (the owner's decision; the size, weight and radius are the cabinet's cell, VerifyEmailView.vue lines 283 to 307, which sets its digit in the body face), on `--bg-surface`; the border is `--border-input` at `--border-input-width`, hover `--border-input-hover`, invalid `--danger` |
| states | rest, hover, focus (the system outline), filled (`data-filled`; the digit is the state, no look of its own), complete, invalid (`aria-invalid` on every cell and a message with an icon and text), verifying (`aria-busy`, the digits quiet in `--text-secondary`), disabled |
| phone | the cells shrink to fit (`minmax(0, --size-3xl)` columns), 56 high, above `--touch-min` |

## K29 Date picker

Markup: `markup/date-picker.html`. The browser's own date input, drawn as a Text field: `.ds-field` with a visible label, `input.ds-input[type=date]` (the mono family for the figures, `color-scheme` following the theme, so the browser's picker is dark by night), the allowed period as `min` and `max` and written in the hint (`aria-describedby`), an invalid value with `aria-invalid="true"` and a message with an icon and text. The picker that opens and its keys are the browser's. States: rest, hover, focus, filled, invalid, disabled, read-only (those of K03). A period is two inputs; the screen sets the second's `min` from the first. The component has no script.

## K30 File input

Markup: `markup/file-input.html`. `.ds-field.ds-file` holds the visible label, the control (`label.ds-button.ds-button--secondary.ds-file__pick` around the real `input.ds-file__input[type=file]`), the hint with the limits as text (JPG or PNG, up to 8 MB: never only in `accept`) and `ul.ds-file__list`. The page fills `data-accept`, `data-max-size` (bytes) and the messages (`data-msg-type`, `data-msg-size` with `{name}` and `{max}`, `data-msg-ready`, `data-msg-done`, `data-label-remove` with `{name}`). A file that fails the type or the size check is listed as an error item whose message is a `role="alert"` paragraph with an icon. An item (`li.ds-file__item[data-state]`: selected, uploading, done, error) has a thumb (a local preview for an image, an icon otherwise), the name, a status line (size and state, `--text-tertiary` on the white item), a remove button named "Remove <name>", and for uploading a Progress (`role=progressbar` named by the file) set through `AivisDS.file.progress(item, pct)`, `.done(item)` and `.fail(item, message)`. A field without `multiple` keeps one file. States: rest, hover, focus, selected, uploading, done, error, disabled (`data-disabled`). The item takes the Row list's look.

## K38 Combobox / user picker

Markup: `markup/combobox.html`. The ARIA 1.2 combobox: `input.ds-combobox__input[role=combobox]` with `aria-expanded`, `aria-controls`, `aria-autocomplete="list"` and `aria-activedescendant`; `ul[role=listbox]` of `li.ds-combobox__option[role=option]` (an `id`, `aria-selected`, `data-value`); a polite `role=status` for the count (`data-msg-count`, `data-msg-none` with `{n}`); an empty message as text; after a choice a chip (`.ds-combobox__chip`) with the option's avatar, name and detail and a Clear button. Focus stays in the input; Down opens and moves, Up moves back, Home and End go to the ends while open, Enter chooses, Escape closes and then empties the text. `data-filter="local"` filters the options in the page, otherwise the app replaces them on `ds-combobox-query`; `data-min-chars` is the shortest search the app wants. The active option is a `--bg-subtle` tint and a 2 line `--primary` bar at the start, never colour alone. The look is the cabinet's picker (UserPicker.vue lines 190 to 275): a bordered result list, a 32 initials disc in `--primary`, name `--fs-sm` 600, detail `--text-secondary`, a chip on `--bg-subtle`. States: rest, hover, focus, open, active option, selected option, no result, busy (`aria-busy`), chosen, disabled.

## K39 Reorder list

Markup: `markup/reorder-list.html`. `ol.ds-reorder` named by a heading; each `li.ds-reorder__item` has two buttons (`.ds-reorder__move[data-dir]`, names from `data-label-up` and `data-label-down` with `{name}`), a position figure (`aria-hidden`) and the title and meta; the button that cannot move is disabled. A move keeps the focus on the same button (or the other when this one is now at an end), marks the row `data-moved` until the focus leaves it and writes the polite status (`data-msg-moved` with `{name}`, `{n}`, `{total}`) into the element `data-live` names. No drag is built. The look is the cabinet's roadmap (CompanyRoadmapView.vue lines 564 to 583 and 899 to 925: a small button pair at the start, 1 px border, `--radius-sm`, a `--text-secondary` glyph, primary on hover) on the Row list's surface. States: rest, hover, pressed, focus, moved, first and last, disabled row. The move button border is `--border-input`, the system's outlined-button border (P5.1 small point g), 3.03 by day and 3.01 by night against white; the cabinet's own `--border-default` (1.57) is not used.

## K35 Structured payout form

Markup: `markup/payout-form.html`. `form.ds-payout` named by its heading, with a fieldset and legend per group (`.ds-payout__group`, `.ds-payout__legend`), a field grid (`.ds-payout__grid`: one column on a phone, two where each column can be `--center-lg` wide), labelled Text fields with hints and messages in `aria-describedby`, an error summary Alert (`role=alert`) naming how many fields need a look, a lock Alert (`role=status`) with disabled fieldsets while a withdrawal is open, and the actions. Saving sets `aria-busy` on the form and the Button. No limit, fee, price or payment term is written into the component: the hint points to the platform settings and the screen shows the numbers. Which fields a payout needs, and in which order, is the app's payout schema; the page's fields are an example.

## K33 Auth shell

Markup: `markup/auth-shell.html`. `.ds-auth` is a column of `header.ds-auth__header` (the logo at the start, `.ds-auth__controls` at the end: the language and theme ghost icon buttons) and `main.ds-auth__main` holding `.ds-auth__panel`: an optional `.ds-auth__icon`, one `h1.ds-auth__title`, `p.ds-auth__subtitle`, `form.ds-auth__form`, `.ds-auth__foot` with links. The panel is a surface panel: `--bg-surface` (white by day, the night surface) with a `--border-subtle` border and `--radius-card`, over the page ground (`--bg-page`), its content at most `--maxw-form` wide (the cabinet's auth content, VerifyEmailView.vue lines 226 to 265); on it the input border measures 3.03 by day and 3.01 by night. Text on the panel is `--text-primary`, `--text-secondary`, `--primary` and `--danger`. Phone rules (the cabinet has none, 0 `@media` in its auth files): gutter `--space-gutter-mobile`, the header padded by the safe-area insets, every link and control at least `--touch-min` high. On a phone the panel starts from the top, on every auth screen; at desktop widths it is centred. The logo is the cabinet's (AivisLogo.vue): the colour mark `../brand/aivis-mark.svg` as an image, `--size-sm` square and unchanged, then the wordmark of `../brand/aivis-wordmark.svg` inline in `currentColor` (`--text-primary`), half that height, `--space-3` apart, so the lettering follows the theme; the stacked lockup image is not used in the shell because its lettering has no fill and goes dark at night. The pair is one `role=img` named "AIVIS.ONE".

## Tokens used, batch 3

Every value is a token (`components.json` lists them per component). No token was added. The literal numbers of the batch 3 css, besides those already listed above for batches 1 and 2: `100dvh` on the auth shell (as the app shell); `1 / -1` grid lines; the disabled `0.55` opacity again; the hidden file input's `opacity: 0` and `clip-path: inset(50%)`; halves and doubles of tokens (`/ 2`, `* 2`); the keyword `thin`; one more `@media (max-width: 480px)`. Needed and not present as tokens: none.
