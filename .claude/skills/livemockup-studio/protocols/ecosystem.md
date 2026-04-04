---
name: ecosystem
description: "v1.6.1 | Create multi-mockup ecosystem with shared CSS/JS + theme + i18n"
---

# ecosystem

## Purpose

Convert standalone mockups into ecosystem with shared CSS/JS and index hub.

| Creates | css/, js/, index.html |
|---------|----------------------|
| Layer | L5 (Infrastructure) |
| Output | Shared files + hub |

---

## Pre-read

| # | Read | Why |
|---|------|-----|
| 1 | reference/ecosystem.md | File structure + templates |
| 2 | reference/brand-cbs.md | Design tokens for variables.css |
| 3 | reference/components.md | Component styles |
| 4 | reference/shell.md | Shell + nav-map styles and JS |
| 5 | reference/cbs-patterns.md | CBS-specific UI patterns |

---

## Step 1: Create Directory Structure

```
mockups/css/  — create if not exists
mockups/js/   — create if not exists
  js/theme.js
  js/i18n.js
```

## Step 2: Extract variables.css

From reference/brand-cbs.md → copy `:root` block with ALL tokens:
- CBS HOME colors (primary, accent, neutrals, semantic)
- Spacing tokens
- Shadow tokens
- Border-radius tokens
- Shell theme variables
- Dark mode @media query
- Include the dark mode `@media (prefers-color-scheme: dark)` block.

## Step 3: Extract components.css

From reference/components.md → extract all component CSS:
- Reset (*, body)
- Buttons, cards, forms, lists, tables
- Clickability fix
- Flex chain (.mockup-content, .screen, .main)
- Screen animations

## Step 4: Extract shell.css

From reference/shell.md → extract shell CSS:
- Toolbar
- Device frames (phone/tablet/desktop)
- Preview container
- Mobile adaptations

## Step 5: Extract nav-map.css

From reference/shell.md → extract Navigation Map CSS:
- Overlay, panel, header
- Stats, legend, tree
- Sections, items, badges, dots

## Step 6: Extract shell.js

From reference/shell.md → extract DevicePreview JS:
- DevicePreview object
- DOMContentLoaded init

## Step 6.5: Extract theme.js

From reference/brand-cbs.md → ThemeManager:
- ThemeManager object: init(), set(), cycle(), getEffective()
- Three states: auto, light, dark
- localStorage persist: 'cbs-theme'
- Dynamic Lucide icon updates (monitor/sun/moon)

## Step 6.6: Extract i18n.js

From reference/brand-cbs.md → I18N:
- I18N object: _dict, t(), setLocale(), toggleLocale(), applyI18n()
- Translation dictionary (~150 keys for CBS HOME)
- data-i18n attribute sweeper
- localStorage persist: 'cbs-lang'

## Step 7: Extract navigation.js

From reference/shell.md + interactions.md → extract:
- navigateTo, switchTab
- showToast (with CSS variable reading)
- Navigation Map functions
- toggleSection

## Step 8: Create index.html

From reference/ecosystem.md → hub template:
- Project title + subtitle
- Card per mockup with link
- Keyboard hints
- Dark theme
- Include flash prevention script in `<head>` of index.html too

## Step 9: Refactor Mockups

For each mockup.html:
1. Remove all inline CSS that's now in shared files
2. Add `<link>` tags to shared CSS
3. Remove all inline JS that's now in shared files
4. Add `<script>` tags to shared JS
5. Keep only mockup-specific styles and handlers
6. Verify links resolve correctly (../css/, ../js/)
7. Add flash prevention inline script in `<head>` (before CSS)
8. Add theme toggle + lang switcher to toolbar-right
9. Add data-i18n attributes to nav map items, tab bars, headings
10. Add Lucide CDN script before other JS

## Step 10: Test

1. Serve from project root: `npx serve mockups -l 3100`
2. Open index.html → all cards visible
3. Click each card → mockup loads
4. In each mockup: device switching, nav map, toasts all work
5. No 404 in browser console

---

## Quick Checklist

| Check | Status |
|-------|--------|
| css/ directory exists | |
| js/ directory exists | |
| variables.css has :root | |
| components.css has buttons + cards | |
| shell.css has device frames | |
| nav-map.css has overlay + tree | |
| shell.js has DevicePreview | |
| navigation.js has navigateTo + toast | |
| index.html has all mockup cards | |
| Each mockup uses shared files | |
| No 404 on CSS/JS imports | |
| All screens render correctly | |
| Lucide CDN loaded before JS | |
| theme.js loads before shell.js | |
| i18n.js loads before navigation.js | |
| Flash prevention in <head> | |

---

*ecosystem v1.6.1*
