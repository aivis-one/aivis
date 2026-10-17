> WHAT THIS IS:  the components of batch 1 of the AIVIS design system: what each is for, how to choose and use it, its states, its tokens and its accessibility contract.
> FOR WHOM:      an agent or a person with no memory of earlier work, building a screen or a component.
> WHEN:          before using or changing Button, Text field, Radio, Toggle, Card, Badge, Alert, Tabs, Filter chip, Toast, Progress or Loader.
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
