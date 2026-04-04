---
name: build
description: "v1.6.1 | L2 - Generate HTML mockup with device shell"
---

# build

## Purpose

Generate working HTML mockup with device preview shell.

| Creates | mockup.html |
|---------|-------------|
| Layer | L2 (Walls) |
| Output | Single HTML file with shell + content |

---

## Pre-read

| # | Read | Why |
|---|------|-----|
| 1 | reference/shell.md | Device Preview + clickability fix + flex chain |
| 2 | reference/components.md | UI patterns |
| 3 | reference/brand-cbs.md | CBS HOME tokens + i18n key naming |
| 4 | reference/ecosystem.md | Shared CSS/JS architecture |

---

## Step 1: HTML Structure

### Ecosystem mode (default)

For multi-mockup projects with shared CSS/JS files.

```html
<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{Project} — Live Mockup</title>
  <!-- Flash prevention: MUST be before CSS -->
  <script>
    (function(){var t=localStorage.getItem('cbs-theme');if(t==='dark'||t==='light')document.documentElement.setAttribute('data-theme',t);var l=localStorage.getItem('cbs-lang');if(l)document.documentElement.lang=l;})();
  </script>
  <!-- Favicon -->
  <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><rect width='100' height='100' rx='16' fill='%23E8651A'/><text x='50' y='72' font-size='60' font-weight='800' font-family='Arial' fill='white' text-anchor='middle'>U</text></svg>">
  <!-- Fonts -->
  <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <!-- Shared CSS -->
  <link rel="stylesheet" href="../css/variables.css">
  <link rel="stylesheet" href="../css/components.css">
  <link rel="stylesheet" href="../css/shell.css">
  <link rel="stylesheet" href="../css/nav-map.css">
  <style>
    /* === MOCKUP-SPECIFIC STYLES ONLY === */
  </style>
</head>
<body>
  <!-- TOOLBAR with theme toggle + lang switcher -->
  <!-- DEVICE FRAME -->
  <!-- SCREENS -->
  <!-- NAVIGATION MAP -->

  <!-- Scripts (ORDER MATTERS) -->
  <script src="https://unpkg.com/lucide@latest/dist/umd/lucide.min.js"></script>
  <script src="../js/theme.js"></script>
  <script src="../js/i18n.js"></script>
  <script src="../js/shell.js"></script>
  <script src="../js/navigation.js"></script>
  <script>
    /* === MOCKUP-SPECIFIC HANDLERS === */
    if (typeof lucide !== 'undefined') lucide.createIcons();
  </script>
</body>
</html>
```

### Standalone mode (legacy)

For single mockups without ecosystem. All CSS/JS inline. See ecosystem.md for multi-mockup projects.

```html
<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{Project} — Live Mockup</title>
  <script>
    (function(){var t=localStorage.getItem('cbs-theme');if(t==='dark'||t==='light')document.documentElement.setAttribute('data-theme',t);var l=localStorage.getItem('cbs-lang');if(l)document.documentElement.lang=l;})();
  </script>
  <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    /* === ALL STYLES INLINE === */
    /* Shell CSS from reference/shell.md */
    /* Clickability Fix from reference/shell.md */
    /* Design Tokens from design.md */
    /* Component Styles from reference/components.md */
    /* Mockup Content Styles */
  </style>
</head>
<body>
  <!-- TOOLBAR with theme toggle + lang switcher -->
  <!-- DEVICE FRAME + SCREENS -->
  <!-- NAVIGATION MAP -->
  <script src="https://unpkg.com/lucide@latest/dist/umd/lucide.min.js"></script>
  <script>
    // ThemeManager (inline from theme.js)
    // I18N (inline from i18n.js)
    // DevicePreview Controller (inline from shell.js)
    // Navigation Map (inline from navigation.js)
    // Mockup Interactions
    if (typeof lucide !== 'undefined') lucide.createIcons();
  </script>
</body>
</html>
```

---

## Step 2: Build Screens

### Screen Container

```html
<div class="screen active" id="screen-{id}">
  <header class="header">...</header>
  <main class="main">...</main>
  <nav class="tab-bar">...</nav>
</div>
```

### Screen Visibility

```css
.screen { display: none; flex-direction: column; min-height: 100%; }
.screen.active { display: flex; flex: 1; }
```

### Navigation JS

```javascript
function navigateTo(screenId) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  document.getElementById(screenId).classList.add('active');
  // Aggressive scroll reset — see reference/shell.md
  const screen = document.getElementById('deviceScreen');
  screen.scrollTop = 0;
  screen.scrollTo({ top: 0, behavior: 'instant' });
  requestAnimationFrame(() => screen.scrollTop = 0);
}
```

---

## Step 3: Apply Shell Patterns

Apply these from **reference/shell.md** (do NOT skip):

1. **Flex Layout Chain** — device-screen -> mockup-content -> screen -> main
2. **Clickability Fix** — pointer-events: none on onclick children
3. **Container Alignment** — align-items: flex-start + margin: auto
4. **Navigation Map** — Map button + popup
5. **Adaptive Toolbar** — mobile CSS

---

## Step 3.5: Toolbar Controls

Add theme toggle and language switcher to toolbar-right:

```html
<div class="toolbar-right">
  <!-- Theme toggle -->
  <button class="theme-toggle" onclick="ThemeManager.cycle()" title="Theme">
    <i data-lucide="monitor"></i>
  </button>
  <!-- Language switcher -->
  <div class="lang-switcher">
    <button class="lang-btn active" data-lang="ru" onclick="I18N.setLocale('ru')">RU</button>
    <button class="lang-btn" data-lang="en" onclick="I18N.setLocale('en')">EN</button>
  </div>
  <!-- Map button -->
  <button class="map-btn" onclick="openNavMap()">
    <i data-lucide="map-pin"></i> <span class="map-label">Map</span>
  </button>
  <!-- Zoom -->
  <div class="zoom-control">
    <button class="zoom-btn" data-zoom="-10">-</button>
    <span class="zoom-value">100%</span>
    <button class="zoom-btn" data-zoom="+10">+</button>
  </div>
</div>
```

### Lucide Icons

Theme toggle uses Lucide icons via `data-lucide` attribute:
- `monitor` — auto theme (system preference)
- `sun` — light theme
- `moon` — dark theme

ThemeManager._updateIcon() swaps the icon automatically on cycle.

---

## Step 4: Forms Pattern

```html
<!-- USE div + button, NOT form + submit -->
<div class="form">
  <button type="button" onclick="handleLogin()">Войти</button>
</div>
```

Form submit handlers are unreliable in device preview.

**Why:** Device preview wraps content in an iframe-like container. The default form submit causes page reload, breaking the preview. `div` + `onclick` keeps everything in-page.

---

## Step 5: Add Components

Use components from design.md + reference/components.md:

| Component | Position |
|-----------|----------|
| Header | `sticky top: 0` |
| Tab Bar | `sticky bottom: 0` |
| Cards, Forms, Buttons | Inside main |

**Never** use `position: fixed` inside device-screen!

---

## Step 6: Placeholder Data

Use patterns from reference/data.md. Final data filled in polish phase.

---

## Step 7: Basic Interactions

Add hover effects from reference/interactions.md.

---

## Step 7.5: i18n Attributes

Add `data-i18n` to translatable elements:

- Nav Map: title, legend, stats, section names, item names
- Tab bar: labels
- Screen headings and buttons
- Form labels

Pattern: `<h1 data-i18n="auth.login.title">Вход в аккаунт</h1>`

See reference/brand-cbs.md -> i18n section for key naming conventions.

---

## Step 8: Checklist Before Polish

| Check | |
|-------|-|
| Shell renders | |
| Device switching works | |
| All screens present | |
| Flex chain complete | |
| Clickability fix added | |
| Tab bar at bottom | |
| Navigation Map works | |
| Components styled | |
| Theme toggle cycles auto/light/dark | |
| Lang switcher toggles RU/EN | |
| Lucide icons render | |
| Flash prevention script in head | |
| data-i18n on translatable text | |

---

*build v1.6.1*
