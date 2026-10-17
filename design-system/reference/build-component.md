> WHAT THIS IS:  the order of work for authoring one component of AIVIS inside the design system.
> FOR WHOM:      an agent or a person who has no memory of earlier work.
> WHEN:          at every request that adds or changes a component for the site or a cabinet.
> WHO WRITES:    the navigator of Agent-Aivis.one.

# build-component

**Purpose:** write one component that stays inside the system.

**Input:** the component's name and the roles it plays.

**Output:** the component's markup and style, bound to tokens, with its states and both themes covered.

This tree holds tokens, fonts, brand, icons and decorative elements; it holds no component catalogue yet. A component is therefore authored from tokens alone, as follows.

## Gate-in

| Source | Extract |
|---|---|
| the roles of colour | `../tokens/tokens.md`, the table "Colour roles" and the table "Text on grounds" |
| the values | `../tokens/tokens-resolved.json`, the `light` and `dark` fields of each token bound |
| the decided values | `conventions.md` |
| the refusals | `refusals.md` |

## Steps

1. Bind, do not measure. Every colour, size, space, radius, shadow and duration takes a token by role; a literal in the output is a defect (`conventions.md`: literal values).
2. Name the states the component has and bind a token to each: rest, hover, pressed and focus. The hover and pressed colours exist as `--primary-hover`, `--primary-active`, `--accent-hover` and `--danger-hover`; focus is a `--focus-width` solid outline in `--focus-ring` with a `--focus-offset` offset.
3. A component that carries text puts it on a ground that its text colour is allowed on (`../tokens/tokens.md`, "Text on grounds"); the text on `--primary` is `--on-primary`, white by day and `#04243E` by night.
4. An input takes `--border-input` at `--border-input-width` and no other border token; a card keeps its border as it is, `--border-subtle` (`refusals.md`: Inputs and focus; `../elements/README.md`).
5. Draw every icon from `../components/icons/icons.svg` by a key of `../components/icons/icons.json`, in `currentColor`; the rocket and the spark from 24 pixels up.
6. Lay out with logical properties and with the four widths 480, 640, 880 and 1120; nothing is mirrored (`conventions.md`: direction, widths).
7. Take the typeface from the role tokens `--font-display`, `--font-body` and `--font-mono`.
8. Check the contrast of every text and non-text pair of the component in `../tokens/contrast.json`, in the day and the night theme; a pair that is not in the file is computed with the formula named there.
9. Re-read `refusals.md` against the component and quote every row it trips.

## Gate-out

| Check | Pass condition |
|---|---|
| literals | none; every value is a token |
| states | rest, hover, pressed and focus each bound to a token |
| themes | the component viewed in both |
| contrast | every pair at 4.5 or better for text and 3.0 or better for a non-text part, or the pair listed with its ratio |
| refusals | no row of `refusals.md` tripped |
