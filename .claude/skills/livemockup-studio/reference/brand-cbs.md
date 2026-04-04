---
name: brand-cbs
description: "v1.6.1 | CBS HOME design tokens — single source of truth"
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
  --shadow-focus-teal: 0 0 0 3px rgba(26, 107, 106, 0.3);
  --shadow-accent-focus: 0 0 0 3px rgba(232, 101, 26, 0.4);

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

**Focus rings by element type:**

```css
/* Inputs: teal focus ring */
.form-input:focus {
  outline: none;
  border-color: var(--primary);
  box-shadow: var(--shadow-focus-teal);
}

/* Buttons/CTAs: orange focus ring */
.btn-primary:focus-visible {
  box-shadow: var(--shadow-accent-focus);
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
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><rect width='100' height='100' rx='16' fill='%23E8651A'/><text x='50' y='72' font-size='60' font-weight='800' font-family='Arial' fill='white' text-anchor='middle'>U</text></svg>">
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

RU/EN language switching via `data-i18n` attributes.

### I18N API

| Method | Description |
|--------|-------------|
| `I18N.t(key, params)` | Translate key. Optional `params` object for interpolation (`{name}` patterns). |
| `I18N.setLocale(lang)` | Set locale to `'ru'` or `'en'`. Saves to localStorage, calls `applyI18n()`. |
| `I18N.toggleLocale()` | Toggle RU ↔ EN. |
| `I18N.applyI18n()` | Sweep all `[data-i18n]` elements and update their text/attributes. Call after DOM changes. |

### localStorage Key

`'cbs-lang'` — stores `'ru'` or `'en'`. Default: `'ru'`.

### data-i18n Patterns

```html
<!-- Static text: replaces textContent -->
<h1 data-i18n="auth.login.title">Вход в аккаунт</h1>

<!-- Attribute: replaces the named attribute instead of textContent -->
<input data-i18n="common.email" data-i18n-attr="placeholder" placeholder="Email">

<!-- Toolbar switcher -->
<div class="lang-switcher">
  <button class="lang-btn active" data-lang="ru" onclick="I18N.setLocale('ru')">RU</button>
  <button class="lang-btn" data-lang="en" onclick="I18N.setLocale('en')">EN</button>
</div>
```

### Example Dictionary Entries

```javascript
I18N._dict = {
  ru: {
    'auth.login.title': 'Вход в аккаунт',
    'auth.login.subtitle': 'Войдите через Telegram',
    'nav.home': 'Главная',
    'nav.portfolio': 'Портфель',
    'nav.market': 'Маркетплейс',
    'nav.settings': 'Настройки',
    'nav.endpoint': '📌 {name} — финальная точка',
    'common.email': 'Email',
    'common.save': 'Сохранить',
    'common.cancel': 'Отмена',
  },
  en: {
    'auth.login.title': 'Sign In',
    'auth.login.subtitle': 'Sign in with Telegram',
    'nav.home': 'Home',
    'nav.portfolio': 'Portfolio',
    'nav.market': 'Marketplace',
    'nav.settings': 'Settings',
    'nav.endpoint': '📌 {name} — endpoint',
    'common.email': 'Email',
    'common.save': 'Save',
    'common.cancel': 'Cancel',
  }
};
```

### Usage in JS

```javascript
I18N.t('auth.login.title');           // → "Вход в аккаунт" (ru) or "Sign In" (en)
I18N.t('nav.endpoint', {name: 'X'});  // → "📌 X — финальная точка"
I18N.setLocale('en');                  // Switch to English
I18N.toggleLocale();                   // Toggle RU ↔ EN
```

Keyboard shortcut: `L`

*brand-cbs v1.6.1*
