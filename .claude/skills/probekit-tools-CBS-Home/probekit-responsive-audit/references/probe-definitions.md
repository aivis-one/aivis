# Responsive Audit — Probe Definitions

CBS HOME responsive layout probes. Device breakpoints: phone (≤480px), tablet (481-1024px), desktop (>1024px).
Read severity from `probekit-core/references/severity-format.md`.

## P1: Viewport Meta (CRITICAL)

Verify `index.html` has correct viewport meta tag.

**Required:**
```html
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover" />
```

**Checks:**
- `width=device-width` present
- `initial-scale=1.0` present
- `viewport-fit=cover` present (for notch devices)
- No `maximum-scale=1.0` or `user-scalable=no` (accessibility violation)

## P2: Safe Area (HIGH)

Verify safe-area-inset usage for notch/home-indicator devices.

**Checks:**
- `env(safe-area-inset-top)` in header/toolbar
- `env(safe-area-inset-bottom)` in tab bar / bottom nav
- Body padding includes safe-area in `global.css`

**Detection:**
```bash
grep -rn 'safe-area' src/ --include='*.vue' --include='*.css'
```

## P3: Touch Target Size (HIGH)

Verify interactive elements meet 44x44px minimum (WCAG 2.5.5).

**Checks:**
- Buttons: min-height 44px (or padding achieves it)
- Tab bar items: min-height 44px
- Input fields: min-height 44px
- Links in text: adequate padding

**Detection:**
```bash
grep -rn 'height.*[0-3][0-9]px\|min-height.*[0-3][0-9]px' src/components/ --include='*.vue'
```

## P4: Flex/Grid Layout (MEDIUM)

Verify responsive patterns.

**Checks:**
- Shells use `display: flex; flex-direction: column`
- Content area uses `overflow-y: auto` (not `overflow: scroll`)
- No fixed widths > 390px on mobile elements
- Grid layouts use `auto-fit` or `auto-fill` for responsiveness

## P5: Sticky vs Fixed (HIGH)

Verify headers and tab bars use `position: sticky`, NOT `position: fixed`.

**Exception:** Only the shell wrapper may use fixed positioning.

**Detection:**
```bash
grep -rn 'position:\s*fixed' src/components/ --include='*.vue'
```

## P6: RTL Layout (MEDIUM)

Verify RTL compatibility for Arabic locale.

**Checks:**
- Flex direction respected (no hardcoded `margin-left` without RTL override)
- Text alignment uses `start`/`end` not `left`/`right` where possible
- `[dir="rtl"]` selectors present for directional components

**Detection:**
```bash
grep -rn 'margin-left\|padding-left\|text-align:\s*left' src/components/ --include='*.vue'
```

## P7: Breakpoint Consistency (MEDIUM)

If media queries used, verify breakpoints match CBS HOME device specs.

**CBS HOME breakpoints (from livemockup-studio):**
- Phone: ≤ 480px
- Tablet: 481px – 1024px
- Desktop: > 1024px

**Detection:**
```bash
grep -rn '@media' src/ --include='*.vue' --include='*.css'
```

## P8: dvh Units (LOW)

Verify `100dvh` used instead of `100vh` for mobile viewport.

**Detection:**
```bash
grep -rn '100vh' src/ --include='*.vue' | grep -v '100dvh'
```
