---
name: ecosystem
description: "v1.8.0 | Multi-mockup ecosystem with shared CSS/JS and index hub"
---

# Ecosystem

Multi-mockup architecture: shared CSS/JS files + index hub entry point.

---

## When to Use

| Mode | When | Output |
|------|------|--------|
| **Standalone** | 1 mockup, quick prototype | Single HTML file (all inline) |
| **Ecosystem** | 2+ mockups, shared brand | Shared CSS/JS + index.html + N mockup files |

Use ecosystem when:
- Project has multiple roles/flows (e.g., investor, agent, admin)
- Brand tokens must be consistent across mockups
- Changes to design system should propagate to all mockups

---

## File Structure

```
mockups/
├── index.html                 ← Hub (entry point)
├── css/
│   ├── variables.css          ← Design tokens (:root)
│   ├── components.css         ← Shared UI (buttons, cards, forms)
│   ├── shell.css              ← Device preview frame
│   └── nav-map.css            ← Navigation map popup
├── js/
│   ├── shell.js               ← Device controller + zoom + keyboard
│   ├── navigation.js          ← navigateTo, switchTab, toast, navMap
│   ├── theme.js              ← Theme toggle (dark/light/auto)
│   └── i18n.js               ← Language switcher (RU/EN)
├── auth-flow/
│   └── mockup.html            ← Mockup content only
├── investor-shell/
│   └── mockup.html
└── ...
```

---

## Index Hub Template

```html
<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{PROJECT} — Live Mockups</title>
  <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    /* Hub-specific styles — dark theme, card grid */
  </style>
</head>
<body>
  <div class="hub">
    <h1>{PROJECT}</h1>
    <p class="hub-subtitle">Interactive Mockups · {N} screens</p>
    <div class="hub-grid">
      <!-- One card per mockup -->
      <a href="{folder}/mockup.html" class="hub-card">
        <span class="hub-icon">{emoji}</span>
        <h2>{Title}</h2>
        <p>{Description}</p>
        <div class="hub-meta">
          <span class="hub-screens">{N} screens</span>
          <span class="hub-badge">{Mobile|Web|Flow}</span>
        </div>
      </a>
    </div>
    <div class="hub-hints">
      <span>1/2/3 — devices</span>
      <span>+/− — zoom</span>
      <span>M — map</span>
    </div>
  </div>
</body>
</html>
```

---

## Mockup HTML Template (Ecosystem Mode)

```html
<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{MOCKUP} — Live Mockup</title>
  <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <!-- Shared CSS -->
  <link rel="stylesheet" href="../css/variables.css">
  <link rel="stylesheet" href="../css/components.css">
  <link rel="stylesheet" href="../css/shell.css">
  <link rel="stylesheet" href="../css/nav-map.css">
  <style>
    /* === MOCKUP-SPECIFIC STYLES === */
    /* Only styles unique to this mockup */
  </style>
</head>
<body>
  <!-- TOOLBAR (same structure, uses shell.css) -->
  <!-- DEVICE FRAME (same structure, uses shell.css) -->
  <!-- SCREENS (mockup content) -->
  <!-- NAVIGATION MAP (same structure, uses nav-map.css) -->

  <!-- Shared JS -->
  <script src="../js/theme.js"></script>
  <script src="../js/i18n.js"></script>
  <script src="../js/shell.js"></script>
  <script src="../js/navigation.js"></script>
  <script>
    /* === MOCKUP-SPECIFIC JS === */
    /* Only handlers unique to this mockup */
  </script>
</body>
</html>
```

---

## CSS File Contents

### variables.css
- Copy `:root` block from reference/brand-cbs.md
- Include dark mode @media query
- Include shell theme variables (--shell-bg, --shell-surface, etc.)

### components.css
- Buttons (.btn, .btn-primary, .btn-secondary, .btn-sm, .btn-link)
- Cards (.card, .stat-card, .product-card)
- Forms (.form-group, .form-label, .form-input, .form-select)
- Lists (.list-item, .tx-item, .comm-item)
- Tables (.table)
- Badges (.badge, .doc-status)
- Flex chain (.mockup-content, .screen, .main)
- Clickability fix (pointer-events: none on onclick children)
- Screen transitions (@keyframes fadeIn)

### shell.css
- Toolbar (.preview-toolbar, .device-switcher, .zoom-control, .map-btn)
- Device frames (.device-frame.phone/tablet/desktop, .device-screen, .device-notch)
- Preview container (.preview-container with align-items: flex-start)
- Mobile toolbar adaptations (@media max-width: 768px, 480px)

### nav-map.css
- Overlay (.nav-map-overlay)
- Map panel (.nav-map)
- Stats grid (.nav-map-stats)
- Legend (.nav-map-legend)
- Tree items (.nav-map-item — chip layout, no .nav-map-level wrappers)
- Section collapse (.nav-map-section, .collapsed)
- Traffic light dots (.status-dot, .legend-dot)
- Level badges (.level-badge)

---

## JS File Contents

### shell.js
- DevicePreview object with init(), setDevice(), changeZoom(), handleKeyboard()
- DOMContentLoaded listener
- Keyboard shortcuts: 1/2/3 (devices), +/- (zoom), 0 (reset), M (map)

### navigation.js
- navigateTo(screenId) with aggressive scroll reset
- switchTab(el, screenId) with closest() for safe event handling
- showToast(message, type) reading CSS variables via getComputedStyle
- openNavMap() / closeNavMap() / closeNavMapOnOverlay(event)
- navMapGo(screenId) / navMapEndpoint(name, parent) / navMapTab(name, screen)
- toggleSection(headerEl)

---

## Migration: Standalone → Ecosystem

1. Create `css/` and `js/` directories
2. Extract `:root` block → `css/variables.css`
3. Extract component styles → `css/components.css`
4. Extract shell styles → `css/shell.css`
5. Extract nav-map styles → `css/nav-map.css`
6. Extract DevicePreview → `js/shell.js`
7. Extract navigation functions → `js/navigation.js`
8. In each mockup.html: replace inline CSS/JS with `<link>` and `<script>` tags
9. Create `index.html` hub
10. Test all links work

---

*ecosystem v1.8.0*
