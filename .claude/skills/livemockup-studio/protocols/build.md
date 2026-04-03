---
name: build
description: "v1.4.0 | L2 - Generate HTML mockup with device shell"
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
| 3 | reference/brand-cbs.md | CBS HOME tokens |

---

## Step 1: HTML Structure

```html
<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{Project} — Live Mockup</title>
  <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    /* === SHELL STYLES === from reference/shell.md */
    /* === CLICKABILITY FIX === from reference/shell.md */
    /* === DESIGN TOKENS === from design.md */
    /* === COMPONENT STYLES === from reference/components.md */
    /* === MOCKUP CONTENT STYLES === custom */
  </style>
</head>
<body>
  <!-- SHELL: Toolbar from reference/shell.md -->
  <!-- SHELL: Preview Container -->
  <div class="preview-container">
    <div class="device-frame phone" id="deviceFrame">
      <div class="device-notch"></div>
      <div class="device-screen" id="deviceScreen">
        <div class="mockup-content">
          {screens from brief.md}
        </div>
      </div>
      <div class="device-home-indicator"></div>
    </div>
  </div>
  <!-- SHELL: Navigation Map from reference/shell.md -->
  <script>
    // Device Preview Controller from reference/shell.md
    // Mockup Interactions
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

1. **Flex Layout Chain** — device-screen → mockup-content → screen → main
2. **Clickability Fix** — pointer-events: none on onclick children
3. **Container Alignment** — align-items: flex-start + margin: auto
4. **Navigation Map** — Map button + popup
5. **Adaptive Toolbar** — mobile CSS

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

---

*build v1.4.0*
