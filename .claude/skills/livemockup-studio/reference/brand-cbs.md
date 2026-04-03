---
name: brand-cbs
description: "v1.4.0 | CBS HOME design tokens — single source of truth"
---

# CBS HOME Design Tokens

Single source of truth for CBS HOME brand in mockups.

---

## Brand Identity

| Field | Value |
|-------|-------|
| Brand | CBS HOME (Compound Building System) |
| Archetype | The Engineer — data-driven, precise, trustworthy |
| Aesthetic | Clean, rectangular, industrial, no hype |
| Font | Montserrat (web) |
| Primary | Teal #1A6B6A |
| Accent | Orange #E8651A |

---

## Color Palette

### Copy-paste ready `:root` block

```css
:root {
  /* === CBS HOME Brand Colors === */
  --primary: #1A6B6A;
  --primary-dark: #0E3D42;
  --primary-light: #2A9B9A;
  --primary-800: #15565A;
  --accent: #E8651A;
  --accent-dark: #D45A16;
  --accent-700: #B94D13;

  /* === Neutrals === */
  --bg: #FFFFFF;
  --bg-subtle: #F5F5F5;
  --bg-elevated: #EEFAFA;
  --text: #1A1A1A;
  --text-secondary: #525252;
  --text-tertiary: #A3A3A3;
  --border: #D4D4D4;

  /* === Semantic === */
  --success: #22c55e;
  --success-dim: rgba(34, 197, 94, 0.15);
  --warning: #f59e0b;
  --warning-dim: rgba(245, 158, 11, 0.15);
  --danger: #ef4444;
  --danger-dim: rgba(239, 68, 68, 0.1);

  /* === Tint Overlays === */
  --tint-teal: rgba(26, 107, 106, 0.08);
  --tint-orange: rgba(232, 101, 26, 0.08);

  /* === Shadows === */
  --shadow-sm: 0 1px 3px rgba(0,0,0,0.08);
  --shadow-md: 0 4px 12px rgba(0,0,0,0.10);
  --shadow-lg: 0 8px 24px rgba(0,0,0,0.12);
  --shadow-focus: 0 0 0 3px rgba(232, 101, 26, 0.4);
  --shadow-focus-teal: 0 0 0 3px rgba(26, 107, 106, 0.3);

  /* === Border Radius (rectangular aesthetic) === */
  --radius-sm: 4px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --radius-xl: 24px;

  /* === Spacing (8px base) === */
  --space-xs: 4px;
  --space-sm: 8px;
  --space-md: 16px;
  --space-lg: 24px;
  --space-xl: 32px;
  --space-2xl: 48px;
  --space-3xl: 64px;
  --space-4xl: 96px;
}
```

---

## Dark Mode

```css
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #121212;
    --bg-subtle: #1E1E1E;
    --bg-elevated: #0A2A2E;
    --text: #E5E5E5;
    --text-secondary: #A3A3A3;
    --text-tertiary: #737373;
    --border: #3A3A3A;
    --primary: #2A9B9A;
    --accent: #E8651A;
    --shadow-sm: 0 1px 3px rgba(0,0,0,0.3);
    --shadow-md: 0 4px 12px rgba(0,0,0,0.4);
    --shadow-lg: 0 8px 24px rgba(0,0,0,0.5);
  }
}
```

---

## Typography

```css
body {
  font-family: 'Montserrat', -apple-system, BlinkMacSystemFont, sans-serif;
}
```

Google Fonts import:
```html
<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700;800&display=swap" rel="stylesheet">
```

### Scale

| Element | Size | Weight | Line-height | Letter-spacing |
|---------|------|--------|-------------|----------------|
| Display | 48px | 800 | 1.1 | -0.02em |
| H1 | 32px | 700 | 1.1 | 0 |
| H2 | 24px | 700 | 1.2 | 0 |
| H3 | 18px | 600 | 1.2 | 0 |
| Body | 16px | 400 | 1.5 | 0 |
| Small | 14px | 500 | 1.5 | 0 |
| Caption | 12px | 400 | 1.5 | 0 |
| Section Label | 12px | 700 | 1.5 | 0.15em (ALL CAPS) |

---

## U-Icon

The core brand mark: white "U" on orange square.

```html
<div class="cbs-logo-icon">U</div>
```

```css
.cbs-logo-icon {
  width: 36px;
  height: 36px;
  background: var(--accent);
  color: #FFFFFF;
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 800;
  font-size: 18px;
  flex-shrink: 0;
}
```

Rules:
- Never recolor the orange background
- Never distort proportions
- Minimum clear space = half icon width
- Sizes: 24, 32, 36, 48px

---

## Focus States

**All focus rings use accent orange, NOT teal:**

```css
.form-input:focus {
  outline: none;
  border-color: var(--primary);
  box-shadow: var(--shadow-focus-teal);
}

.btn-primary:focus-visible {
  box-shadow: var(--shadow-focus);
}
```

---

## Button Styles

| Variant | Background | Color | Border | Hover |
|---------|-----------|-------|--------|-------|
| Primary (CTA) | var(--accent) | white | none | var(--accent-dark) |
| Secondary | white | var(--primary) | 2px var(--primary) | bg: var(--primary) |
| Outline | transparent | var(--text-secondary) | 2px var(--border) | border: var(--primary) |
| Telegram | #2AABEE | white | none | #229ED9 |

Telegram is the **only** non-variable color allowed (external brand).

---

## Gradient Classes

Instead of inline gradients, use CSS classes:

```css
.gradient-primary { background: linear-gradient(135deg, var(--primary), var(--primary-light)); }
.gradient-deep { background: linear-gradient(135deg, var(--primary-dark), var(--primary)); }
.gradient-accent { background: linear-gradient(135deg, var(--accent), var(--accent-dark)); }
```

---

## Navigation Map Status Colors

Use CSS variables, not hardcoded hex:

```css
.status-dot.green { background: var(--success); }
.status-dot.yellow { background: var(--warning); }
.status-dot.red { background: var(--danger); }

.legend-dot.green { background: var(--success); }
.legend-dot.yellow { background: var(--warning); }
.legend-dot.red { background: var(--danger); }

.level-badge.hub { background: rgba(59, 130, 246, 0.3); color: #60A5FA; }
.level-badge.tab { background: var(--warning-dim); color: var(--warning); }
.level-badge.end { background: var(--danger-dim); color: var(--danger); }
```

---

## Data Conventions

| Field | Format | Example |
|-------|--------|---------|
| Currency | EUR (€) | €5 200 |
| Price format | Space-separated | €1 000 000 |
| Date | DD.MM.YYYY | 01.04.2026 |
| Time | HH:MM | 14:30 |
| Relative time | Russian | 5 мин назад |
| Names | Russian + German mix | Sergej Seider, Анна Петрова |
| Products | Official names | IPI AG, Immo-Pro-Invest, CBS Home Franchise |
| Roles | 4 types | Инвестор, Агент, Компания, Staff |

---

## Voice Rules (for mockup text)

- Professional, data-driven tone
- Max 25 words per sentence
- No hype words: "революционный", "game-changer", "disruptiv"
- Use: "инновационный", "zukunftsweisend", "kosteneffizient"
- Section labels: ALL CAPS with tracking-wide

---

*brand-cbs v1.4.0*
