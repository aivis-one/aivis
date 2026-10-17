> WHAT THIS IS:  the index of the AIVIS design system: what each folder holds and how to build from it.
> FOR WHOM:      anyone building the site, a cabinet screen or a document for AIVIS.
> WHEN:          first, before any page or screen is built.
> WHO WRITES:    the navigator of Agent-Aivis.one; every change to a folder updates this index in the same commit.

# AIVIS design system: index

One tree. Every file exists once. Open this file first; every folder below has one job.

## What is where

| Folder | What it holds |
|---|---|
| `tokens/` | The values. `tokens.css` (day, default) and `tokens-dark.css` (night) as CSS variables; `tokens-resolved.json` every token resolved to a literal per theme, the value authority; `type-recipe.json` the families, the scale and the font faces; `contrast.json` the measured pairs in both themes; `tokens.md` how to choose a token by role |
| `fonts/` | Plus Jakarta Sans (headings), Manrope (text), JetBrains Mono (figures) and Noto Sans Arabic as woff2 slices, `fonts.css` the @font-face declarations, `LICENSE.md` and `OFL.txt` |
| `brand/` | The mark (colour, mono, ghost, glints), the wordmark and the logo lockup |
| `components/icons/` | The icon set: `icons.svg` the sprite of 93 icons in style P1, `icons.json` the key inventory, `STYLE-P1.md` the drawing rules |
| `reference/` | `sources.md`: every token and asset against the file and line it was taken from, the places where the site and the cabinet disagreed and how each was settled, and what is not carried |
| `examples/` | `foundations.html`: colours with contrast, type, spacing, widths, radii, shadows, motion, day and night side by side, and the icons at 16, 24 and 48 pixels |

## Build a page from the system

1. Link, in this order: `fonts/fonts.css`, `tokens/tokens.css`, `tokens/tokens-dark.css`. Set `data-theme="light"` or `"dark"` on the root, or set none and follow the system.
2. Take each value by token name from `tokens/tokens-resolved.json`, chosen by role per `tokens/tokens.md`. Do not write a hex in a component.
3. Icons: inline `components/icons/icons.svg` once, or reference it, and use `<use href="#i-key">` for a key listed in `components/icons/icons.json`. They draw in `currentColor`.
4. Logo: files from `brand/`.
5. Widths: the four widths are 480, 640, 880 and 1120 pixels; a media query writes the number.
6. Direction: use logical properties.

## Extend the system

| New | Goes to | Also |
|---|---|---|
| a token | `tokens/tokens.css` (and both blocks of `tokens/tokens-dark.css` if it differs at night) | its row in `tokens/tokens-resolved.json`, its role in `tokens/tokens.md`, its source in `reference/sources.md`; `tokens/contrast.json` if it is a colour pair |
| an icon | its symbol in `components/icons/icons.svg`, drawn by `components/icons/STYLE-P1.md`, and its key in `components/icons/icons.json` | a cell in `examples/foundations.html` |
| a font face | the file in `fonts/` and its line in `fonts/fonts.css` | `tokens/type-recipe.json` |
| a brand file | `brand/` | `reference/sources.md` |

## The rules in short

- No literal hex, rgb or pixel size in a component: bind a token.
- One icon set, drawn on a 24 by 24 grid with a 1.5 stroke, round caps and joins, in `currentColor`.
- Three families for Latin and Cyrillic text, one for Arabic; no other face.
- Logical properties for every layout rule.
- Day and night come from the same token names.
