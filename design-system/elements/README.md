> WHAT THIS IS:  the decorative elements of AIVIS: the lattice pattern, the line mark on the grid, the divider, the cube hexagon and the card tick, with how each is built and placed.
> FOR WHOM:      anyone building a page or screen that carries decoration.
> WHEN:          before placing a pattern, a mark, a divider, a hexagon bullet or a tick.
> WHO WRITES:    the maintainers of the AIVIS design system.

# elements

The decorative parts of the AIVIS system. One lattice of hexagons carries every part: the pattern is the lattice, the mark sits on its grid, the small hexagon is one cell drawn as a cube, the divider and the tick take their weight and tone from it.

## The files

| File | What it is |
|---|---|
| `pattern-lattice-light.svg`, `pattern-lattice-dark.svg` | pattern 2: the hexagon lattice with cubes, one tile of 80 by 138.56 px; line 1 px (day), 1.5 px (night) |
| `mark-line-light.svg`, `mark-line-dark.svg` | the clean line mark: the six outer pieces of the AIVIS mark without the inner facet lines; line 1.09 px (day), 1.63 px (night), the weight that equals the grid line in mean rendered weight at display scale 2.2 |
| `divider-ornament.svg` | the divider ornament: the line mark at 0.36 scale, 36 by 34 px, line 1 px in both themes |
| `cube-hexagon-light.svg`, `cube-hexagon-dark.svg` | the small hexagon as a cube: a hexagon and three edges from its centre to three vertices, 24 by 28 viewBox; line 1 px (day), 1.5 px (night) |

## File form

- Every file is a mask. Its black is never shown: the page draws a part with `background-color` set to a token and `mask-image: url(...)` set to the file. This is the one place where files carry a literal colour; the colour of the part is always a token.
- Strokes are `vector-effect: non-scaling-stroke` where the file is scaled by the page, so a line keeps its weight at any size. Caps and joins are round.
- The day file and the night file differ only in line weight; a page picks the file of its theme.
- The lattice geometry is fixed: circumradius R = 23.094 px, cell width W = R times the square root of 3, pointy-top hexagons, rows 1.5R apart, every second row shifted by W/2. The tile is 2W wide and 6R high. Cubes stand in the cells where (column mod 2, row mod 4) is (0, 1) or (1, 3).

## How each part is built and placed

**Pattern.** A layer that fills its section: `position: absolute; inset: 0`, `background-color: var(--deco-ink)`, `opacity: var(--deco-opacity)`, `mask-image` the lattice file, `mask-size: 80px 138.56px`, `mask-repeat: repeat`. The layer sits under the content (`z-index: 0`, content above it).

**Fades.** The pattern layer sits inside a wrapper with `mask-image: linear-gradient(115deg, rgba(0,0,0,.2) 0%, #000 55%)`, so the pattern starts faint at the start corner and is full toward the far side.

**Mark on the grid.** The line mark is drawn as an inline SVG of its six pieces, laid in the same coordinates as the pattern tile. The grid fit: the mark is scaled so that its circumradius is 2R or 4R (scale = kR divided by the measured circumradius 40.508 of the mark's hexagon), its centre is set on the centre of a lattice hexagon, and its six outer points fall on lattice vertices. The pieces are filled with the ground (`var(--bg-surface)`) so the lattice does not show through them; the outline uses `var(--deco-ink)`, `var(--deco-opacity)` and `var(--deco-mark-line-width)`. The mark is not under the fade. Placements used, with the largest distance of an outer point from its nearest lattice vertex:

| Place | Circumradius | Column | Row | Centre (x, y) in px | Scale | Largest vertex error |
|---|---|---|---|---|---|---|
| first screen of the site, desktop | 4R = 92.38 px | 15 | 5 | 620.00, 173.21 | 2.2805 | 0.014 px |
| first screen of the site, phone | 2R = 46.19 px | 7 | 9 | 300.00, 311.77 | 1.1402 | 0.007 px |
| cabinet header, desktop | 2R = 46.19 px | 16 | 2 | 640.00, 69.28 | 1.1402 | 0.007 px |
| cabinet header, phone | 2R = 46.19 px | 7 | 2 | 280.00, 69.28 | 1.1402 | 0.007 px |
| single tile | 2R = 46.19 px | 2 | 2 | 80.00, 69.28 | 1.1402 | 0.007 px |

**Divider.** A row of three parts: a line, the ornament, a line. Each line is `flex: 1` and `block-size: var(--deco-divider-width)` with `linear-gradient(90deg, transparent, var(--border-default) 45%)`, the right one mirrored (`270deg`). The ornament is `inline-size: 36px; block-size: 34px; background-color: var(--border-default)` with `divider-ornament.svg` as its mask; the mark and the line have the same weight and the same tone.

**Cube hexagon.** A bullet before a feature title: 16 by 18 px, `background-color: var(--deco-ink)`, the file of the theme as its mask.

**Tick.** A bar on the top edge of a card that is an item of a list. 88 by 3 px (`--tick-length`, `--tick-thickness`), starting at the inline start of the card text (the card border plus its padding: 25 px for a card with a 1 px edge and 24 px padding), centred on the card's top edge (`top: -1px`). Its end is cut by a slope of `--tick-cut` (5.2 px, the 30 degree slope of the hexagon): `clip-path: polygon(0 0, 100% 0, calc(100% - var(--tick-cut)) 100%, 0 100%)`. Its fill is a gradient from the light stop to the dark stop of one of the three logo facet colours (`--tick-azure-*`, `--tick-emerald-*`, `--tick-amber-*`), light to dark from the start to the end, the colours in turn down a list: azure, emerald, amber, then again. In the night theme the same stops are used: they are the logo's own gradient stops.

The card is an outer line of `var(--border-subtle)` 1 px with an inner surface of `var(--bg-surface)`, radii 6 px and 5 px.

## Tokens

`--deco-ink` (the colour of the pattern, the mark outline and the bullets), `--deco-opacity` (the pattern and the mark outline), `--deco-line-width`, `--deco-mark-line-width`, `--deco-divider-width`, `--tick-length`, `--tick-thickness`, `--tick-cut` and the six `--tick-*` colours are in `../tokens/tokens.css` and, where the night value differs, in `../tokens/tokens-dark.css`. The opacity is the largest that keeps primary text at 8.27 and secondary text at 4.6 or better against the ground under the pattern, solved per theme.

## Usage rules

**Правило применения:** на узоре и на знаке-водяном стоят только основной и вторичный текст (контраст не ниже 9,3 и 4,6); мелкие подписи третичным серым никогда не ставятся на узор или знак, там их контраст ниже 4,5.

### Правила применения засечки

1. Засечка стоит на карточке, которая есть элемент списка: курс, модуль, проект, урок.
2. Цвет по порядку в списке: лазурь, изумруд, янтарь, дальше по кругу; цвет ничего не обозначает.
3. Засечки нет на формах, диалогах, таблицах, предупреждениях и одиночных сводных карточках.
4. Не больше одной засечки на карточке: 88 px, 3 px, от левого края текста карточки.
5. Засечка ничего не несёт: статус и действие показываются иначе, убрать её можно без потери смысла.
6. В списке из одной карточки засечку не ставим.

## Adding an element

1. Draw it as a mask on the file form above and save `elements/<name>.svg`; one file per theme where the line weight differs.
2. Add its row to the table of files and its placement to the section above.
3. Add a tile to `../examples/elements.html`.
