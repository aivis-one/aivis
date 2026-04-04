---
name: brand-cbs
description: "v1.8.0 | CBS HOME design tokens — single source of truth"
---

# CBS HOME Design Tokens

Single source of truth for CBS HOME brand in mockups.
Canonical source: `mockups/css/variables.css` (element-map-v2 derived).

---

## Brand Identity

| Field | Value |
|-------|-------|
| Brand | CBS HOME (Compound Building System) |
| Archetype | The Engineer — data-driven, precise, trustworthy |
| Aesthetic | Clean, rectangular, industrial, no hype |
| Font | Montserrat (web) |
| Primary UI | Teal #1A6B6A (`--t-700`) |
| Accent UI | Orange #E8651A (`--o-accent`) |
| Logo bg | #cc3203 (`--logo-icon-bg` / `--o-primary`) |
| Logo text | #084456 (`--logo-text`) |

---

## Color Architecture

Three-tier system: **Orange Triad** → **Teal System** → **Semantic Aliases**.

### Orange Triad

| Token | Hex | Usage |
|-------|-----|-------|
| `--o-primary` | #cc3203 | Logo icon bg, hero mark, U-icon |
| `--o-accent` | #E8651A | CTA buttons, badges, active indicators |
| `--o-accent-hover` | #D45A16 | Button hover states |
| `--o-light` | #EFB44C | Soft backgrounds, progress bars, secondary accent |
| `--o-tint-8` | rgba(232,101,26,0.08) | Light orange overlay |
| `--o-tint-15` | rgba(232,101,26,0.15) | Medium orange overlay |
| `--o-light-tint-8` | rgba(239,180,76,0.08) | Light gold overlay |
| `--o-light-tint-15` | rgba(239,180,76,0.15) | Medium gold overlay |

### Teal System

| Token | Hex | Usage |
|-------|-----|-------|
| `--t-500` | #228B8A | Light accent, links, dark-mode primary |
| `--t-600` | #1E7A79 | Hover states, secondary buttons |
| `--t-700` | #1A6B6A | **Primary UI color** (= `--primary`) |
| `--t-800` | #15565A | Hero bg, header bg |
| `--t-900` | #0E3D42 | Footer, dark sections |
| `--t-950` | #0A2A2E | Deepest dark backgrounds |
| `--t-tint-8` | rgba(26,107,106,0.08) | Light teal overlay |
| `--t-tint-15` | rgba(26,107,106,0.15) | Medium teal overlay |

### Semantic Aliases

| Token | Value | Maps to |
|-------|-------|---------|
| `--primary` | #1A6B6A | = `--t-700` |
| `--primary-dark` | #0E3D42 | = `--t-900` |
| `--primary-light` | #228B8A | = `--t-500` |
| `--accent` | #E8651A | = `--o-accent` |
| `--accent-dark` | #D45A16 | = `--o-accent-hover` |
| `--logo-icon-bg` | #cc3203 | = `--o-primary` |
| `--logo-text` | #084456 | Dark teal for "CBS HOME" text |

---

## Color Palette — Copy-paste `:root`

```css
:root {
  /* === Orange Triad === */
  --o-primary: #cc3203;
  --o-accent: #E8651A;
  --o-accent-hover: #D45A16;
  --o-light: #EFB44C;
  --o-tint-8: rgba(232,101,26,0.08);
  --o-tint-15: rgba(232,101,26,0.15);
  --o-light-tint-8: rgba(239,180,76,0.08);
  --o-light-tint-15: rgba(239,180,76,0.15);

  /* === Teal System === */
  --t-500: #228B8A;
  --t-600: #1E7A79;
  --t-700: #1A6B6A;
  --t-800: #15565A;
  --t-900: #0E3D42;
  --t-950: #0A2A2E;
  --t-tint-8: rgba(26,107,106,0.08);
  --t-tint-15: rgba(26,107,106,0.15);

  /* === Semantic Aliases === */
  --primary: #1A6B6A;
  --primary-dark: #0E3D42;
  --primary-light: #228B8A;
  --accent: #E8651A;
  --accent-dark: #D45A16;
  --logo-icon-bg: #cc3203;
  --logo-text: #084456;

  /* === Neutrals === */
  --bg: #FFFFFF;
  --bg-subtle: #F5F5F5;
  --bg-elevated: #EEF3F6;
  --text: #1A1A1A;
  --text-secondary: #525252;
  --text-tertiary: #A3A3A3;
  --border: #D4D4D4;

  /* === Semantic Status === */
  --success: #16A34A;
  --success-dim: rgba(22, 163, 74, 0.15);
  --error: #DC2626;
  --error-dim: rgba(220, 38, 38, 0.1);
  --warning: #f59e0b;
  --warning-dim: rgba(245, 158, 11, 0.15);
  --danger: #DC2626;
  --danger-dim: rgba(220, 38, 38, 0.1);

  /* === Shadows === */
  --shadow-sm: 0 1px 3px rgba(0,0,0,0.08);
  --shadow-md: 0 4px 12px rgba(0,0,0,0.10);
  --shadow-lg: 0 8px 24px rgba(0,0,0,0.12);
  --shadow-xl: 0 16px 48px rgba(0,0,0,0.14);
  --shadow-focus: 0 0 0 3px rgba(232,101,26,0.4);

  /* === Border Radius === */
  --radius-sm: 4px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --radius-full: 9999px;

  /* === Spacing (8px base) === */
  --space-xs: 4px;
  --space-sm: 8px;
  --space-md: 16px;
  --space-lg: 24px;
  --space-xl: 32px;
  --space-2xl: 48px;
  --space-3xl: 64px;
  --space-4xl: 96px;

  /* === Font === */
  --font: 'Montserrat', system-ui, sans-serif;

  /* === Telegram === */
  --telegram: #2AABEE;
  --telegram-dark: #229ED9;
}
```

---

## Dark Mode

Two mechanisms: manual toggle (`[data-theme="dark"]`) and system preference (`@media`).

```css
/* Manual toggle */
[data-theme="dark"] {
  --bg: #121212;
  --bg-subtle: #1E1E1E;
  --bg-elevated: #0A2A2E;
  --text: #E5E5E5;
  --text-secondary: #A3A3A3;
  --text-tertiary: #737373;
  --border: #3A3A3A;
  --primary: #228B8A;
  --accent: #E8651A;
  --shadow-sm: 0 1px 3px rgba(0,0,0,0.3);
  --shadow-md: 0 4px 12px rgba(0,0,0,0.4);
  --shadow-lg: 0 8px 24px rgba(0,0,0,0.5);
  --o-tint-8: rgba(232,101,26,0.12);
  --o-tint-15: rgba(232,101,26,0.2);
  --t-tint-8: rgba(34,139,138,0.12);
  --t-tint-15: rgba(34,139,138,0.2);
  --success-dim: rgba(22,163,74,0.2);
  --warning-dim: rgba(245,158,11,0.2);
  --danger-dim: rgba(220,38,38,0.15);
}

/* System preference (when no manual toggle set) */
@media (prefers-color-scheme: dark) {
  html:not([data-theme]) {
    /* Same overrides as [data-theme="dark"] above */
  }
}
```

---

## Typography

```css
body {
  font-family: 'Montserrat', system-ui, sans-serif;
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

White "U" on **--logo-icon-bg** (#cc3203) square.

```html
<div class="cbs-logo-icon">U</div>
```

```css
.cbs-logo-icon {
  width: 36px;
  height: 36px;
  background: var(--logo-icon-bg);
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
- Background = `var(--logo-icon-bg)` (#cc3203), never `var(--accent)`
- Never recolor or distort
- Minimum clear space = half icon width
- Sizes: 24, 32, 36, 48px

---

## Focus States

```css
/* Inputs: teal focus ring */
.form-input:focus {
  outline: none;
  border-color: var(--primary);
  box-shadow: var(--shadow-focus);
}

/* Buttons/CTAs: orange focus ring */
.btn-primary:focus-visible {
  box-shadow: var(--shadow-focus);
}
```

---

## Icon System

**Library:** Lucide Icons (lucide.dev) — outline SVG, 1.5px stroke
**CDN:** `https://unpkg.com/lucide@latest/dist/umd/lucide.min.js`

Usage:
```html
<i data-lucide="icon-name"></i>
<script>lucide.createIcons();</script>
```

Rules:
- Use `currentColor` (inherits text color from parent)
- Never hardcode icon color — use text color tokens
- Sizes: 16/20/24/32/48px via `.icon-sm` through `.icon-2xl` classes
- Colored containers: `.icon-box.teal`, `.icon-box.orange`, `.icon-box.green`
- See reference/components.md → Lucide Icons for full icon map

---

## Favicon

Inline SVG favicon (no external file needed):

```html
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><rect width='100' height='100' rx='16' fill='%23cc3203'/><text x='50' y='72' font-size='60' font-weight='800' font-family='Arial' fill='white' text-anchor='middle'>U</text></svg>">
```

---

## Button Styles

| Variant | Background | Color | Border | Hover |
|---------|-----------|-------|--------|-------|
| Primary (CTA) | var(--accent) | white | none | var(--accent-dark) |
| Secondary | white | var(--primary) | 2px var(--primary) | bg: var(--primary) |
| Outline | transparent | var(--text-secondary) | 2px var(--border) | border: var(--primary) |
| Telegram | var(--telegram) | white | none | var(--telegram-dark) |

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

## Theme Toggle

Three-state theme switching: Auto → Light → Dark

### ThemeManager API

| Method | Description |
|--------|-------------|
| `ThemeManager.init()` | Read localStorage, apply theme, render icon. Call on DOMContentLoaded. |
| `ThemeManager.set(mode)` | Set theme to `'auto'`, `'light'`, or `'dark'`. Saves to localStorage. |
| `ThemeManager.cycle()` | Rotate: auto → light → dark → auto. |
| `ThemeManager.getEffective()` | Returns the resolved theme (`'light'` or `'dark'`), resolving `'auto'` via `prefers-color-scheme`. |

### Three States & Icons

| State | Lucide Icon | `data-theme` attr | Behavior |
|-------|-------------|-------------------|----------|
| auto | `monitor` | (removed) | Follows system `prefers-color-scheme` |
| light | `sun` | `light` | Forces light mode |
| dark | `moon` | `dark` | Forces dark mode |

### localStorage Key

`'cbs-theme'` — stores `'auto'`, `'light'`, or `'dark'`.

### HTML

```html
<!-- Toolbar button -->
<button class="theme-toggle" onclick="ThemeManager.cycle()" title="Theme">
  <i data-lucide="monitor"></i>
</button>
```

```javascript
ThemeManager.set('light');  // Force light
ThemeManager.set('dark');   // Force dark
ThemeManager.set('auto');   // Follow system
ThemeManager.cycle();       // Rotate: auto → light → dark
```

Keyboard shortcut: `T`

### Flash Prevention

**Why:** Without this, a user who set dark mode will see a white flash on reload because the browser renders HTML before JS runs. The inline script in `<head>` reads localStorage synchronously and sets `data-theme` before any paint occurs.

Add inline script in `<head>` BEFORE CSS imports:
```html
<script>
  (function(){var t=localStorage.getItem('cbs-theme');
  if(t==='dark'||t==='light')document.documentElement.setAttribute('data-theme',t);})();
</script>
```

---

## i18n (Internationalization)

RU/EN/DE language switching via `data-i18n` attributes. 242 keys covering all 5 mockups.

### I18N API

| Method | Description |
|--------|-------------|
| `I18N.t(key, params)` | Translate key. Optional `params` object for interpolation (`{name}` patterns). |
| `I18N.setLocale(lang)` | Set locale to `'ru'`, `'en'`, or `'de'`. Saves to localStorage, calls `applyI18n()`. |
| `I18N.toggleLocale()` | Cycle: RU → EN → DE → RU. |
| `I18N.applyI18n()` | Sweep all `[data-i18n]` elements and update their text/attributes. Call after DOM changes. |
| `I18N._locales` | Array `['ru', 'en', 'de']` — supported locales. |

### localStorage Key

`'cbs-lang'` — stores `'ru'`, `'en'`, or `'de'`. Default: `'ru'`.

### data-i18n Patterns

```html
<!-- Static text: replaces textContent -->
<h1 data-i18n="auth.login.title">Вход в аккаунт</h1>

<!-- Attribute: replaces the named attribute instead of textContent -->
<input data-i18n="common.email" data-i18n-attr="placeholder" placeholder="Email">

<!-- Toolbar switcher (3 buttons) -->
<div class="lang-switcher">
  <button class="lang-btn active" data-lang="ru" onclick="I18N.setLocale('ru')">RU</button>
  <button class="lang-btn" data-lang="en" onclick="I18N.setLocale('en')">EN</button>
  <button class="lang-btn" data-lang="de" onclick="I18N.setLocale('de')">DE</button>
</div>
```

### Dictionary Format

Each key is an object with `ru`, `en`, `de` fields:

```javascript
'auth.login.title': { ru: 'Вход в аккаунт', en: 'Sign In', de: 'Anmelden' },
'nav.endpoint':     { ru: '📌 {name} — финальная точка', en: '📌 {name} — endpoint', de: '📌 {name} — Endpunkt' },
```

### Key Namespaces (242 keys total)

| Namespace | Count | Coverage |
|-----------|-------|----------|
| `auth.*` | ~55 | Login, register, verify, profile, role, KYC, docs |
| `inv.*` | ~60 | Dashboard, portfolio, market, detail, purchase, installment, balance, docs, settings |
| `tab.*` | ~20 | Tab bars for all 4 roles |
| `nav.*` | ~80 | Nav map sections, items, legend, stats, toasts |
| `theme.*` | 3 | Theme toggle labels |

### Usage in JS

```javascript
I18N.t('auth.login.title');           // → "Вход в аккаунт" (ru) / "Sign In" (en) / "Anmelden" (de)
I18N.t('nav.endpoint', {name: 'X'});  // → "📌 X — финальная точка"
I18N.setLocale('de');                  // Switch to German
I18N.toggleLocale();                   // Cycle: RU → EN → DE → RU
```

Keyboard shortcut: `L`

### i18n Coverage Rule

**ALL visible screen text must have `data-i18n` attributes** — not just tab bars and nav-maps. This includes:
- Stat card labels (`.stat-label`)
- Section titles (`.section-title`)
- Balance card labels (`.balance-label`, `.balance-sub-label`)
- Button text (wrap in `<span data-i18n="...">`)
- Settings row labels
- Filter tab labels
- Header titles (`.header-title`)

Default text in HTML must be Russian. i18n.js handles the switching.

### Icon Rule

**Never use emoji in UI.** Always use Lucide icons via `<i data-lucide="icon-name"></i>`. This includes:
- Device buttons: `smartphone`/`tablet`/`monitor`
- Hub card icons: Lucide in `.icon-box` containers
- Map button: `map-pin` Lucide icon
- Home button: `layout-grid` Lucide icon

*brand-cbs v1.8.0*
