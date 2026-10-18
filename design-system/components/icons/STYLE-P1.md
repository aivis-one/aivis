> WHAT THIS IS:  the rules of icon style P1 "Мягкий контур" (soft outline), the one AIVIS icon set chosen by the owner 2026-10-16.
> FOR WHOM:      whoever draws or checks an AIVIS icon (site and cabinets).
> WHEN:          before drawing any icon, and when judging a batch.
> WHO WRITES:    the maintainers of the AIVIS design system.

# P1 rules

1. Canvas: viewBox `0 0 24 24`; the live area is 3..21 (keyline square 18x18), padding 3 on every side. Large shapes may reach 2.5..21.5 (the card, the image frame, the banknote).
2. Keylines: circle diameter 17 (r 8.5) centred at 12,12; square 16-18 (rx 3); portrait rectangle 14 x 18; landscape rectangle 19 x 14 (x 2.5..21.5). Shapes are centred optically, not by bounding box.
3. Stroke: `stroke-width` 1.5, `stroke-linecap` round, `stroke-linejoin` round, `fill="none"`, `stroke="currentColor"`. Nothing is filled. A dot is a zero-length round-capped segment (`h.01`), never a filled circle.
4. Corners: outer corners of closed shapes are rounded with radius 2 to 3 (rect `rx` 2.5 or 3; small parts 1 to 1.5). Open strokes (arrows, chevrons, check, cross) have no corner radius, the round join does it. A corner that is the object's own point (a pencil's tip, a bell's skirt, a ghost's hem, a wallet's flap, the edges of a box, a stack of layers, a folded map, a gem, a cup's rim or a bolt) keeps the round join alone, and its slope follows the object rather than 45 degrees.
5. Curves: true circles and true arcs (`circle`, `rect rx`, `A` commands); no free-form curves where a circle fits.
6. Angles: arrowheads and chevrons are 45 degrees. A chevron's arms run 6.5 on each axis (chevron-right, chevron-down, chevron-up); an arrowhead's arms run 4.5 to 5.5 on each axis (log-in 4.5, arrow-left 5.5); a caret inside a frame runs 4.5 (terminal); an arrow's or a cross's diagonals use 45 degrees.
7. Gaps: no two stroke centre lines closer than 2.5 (1 clear after the stroke width); inner details (lines of a document, slots of a card) sit 4 apart.
8. Weight balance: an icon carries at most about three details beyond its outline; round forms are drawn 0.5 larger than squares, thin forms (pencil, arrows) run to the edge of the live area.
9. Colour: only `currentColor`; no hard-coded colour, no opacity, no gradient.
10. Naming: symbol id `i-<name>`, name in kebab-case as counted by compare/count.py (lowercase Lucide names, aliases normalised).
11. Direction: left/right pairs are exact mirrors (arrow-left and arrow-right); the pointing tip sits at 4.5 or 19.5.
12. Size: the rocket, the spark and the qr are used from 24 px up; the qr is three finder squares and dots that fill in at 16 px.
