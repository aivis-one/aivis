# CHANGELOG

All notable changes to livemockup-studio.

## [1.6.1] - 2026-04-04

### Fixed — Documentation Sync

All skill protocols and references now match actual implementation:

- **build.md** — Full rewrite: ecosystem mode template with flash prevention, favicon, shared CSS/JS, Lucide CDN, theme toggle + lang switcher steps, data-i18n step
- **shell.md** — Toolbar HTML updated with theme-toggle + lang-switcher buttons, JS controller updated with T/L/Escape handlers + ThemeManager/I18N init, theme-toggle + lang-switcher CSS sections added, mobile overrides added
- **checklist.md** — Added 11 Theme & Language checks (T1-T6, I1-I5), total 83 gates
- **ecosystem.md** — Added theme.js + i18n.js extraction steps, flash prevention, Lucide CDN, script load order checks
- **components.md** — Added monitor/sun/moon theme icons, selective lucide.createIcons({ nodes }) pattern
- **brand-cbs.md** — Expanded ThemeManager API table, I18N API table, localStorage keys, dictionary examples

A builder following any protocol now produces mockups identical to actual implementation.

---

## [1.6.0] - 2026-04-04

### Added

- **Theme Toggle** — Dark/Light/Auto mode switching
  - `js/theme.js` — ThemeManager with cycle(), set(), getEffective()
  - Three states: auto (system), light, dark
  - Persist via localStorage('cbs-theme')
  - Flash prevention inline script in `<head>`
  - Keyboard shortcut: T
  - Toolbar button with sun/moon/monitor icons
- **i18n System** — RU/EN language switching
  - `js/i18n.js` — I18N dictionary with ~150 keys, t() interpolation, applyI18n()
  - `data-i18n` attributes on HTML elements
  - Persist via localStorage('cbs-lang')
  - Keyboard shortcut: L
  - Compact RU|EN switcher in toolbar
- **Nav Map Standardization** — Consistent Lucide map-pin icon, all labels via data-i18n

### Changed

- **variables.css** — Dark mode via `[data-theme="dark"]` selector (was `@media prefers-color-scheme`)
  - System preference still works as fallback: `html:not([data-theme])`
  - Added tint/dim overrides for dark mode
- **shell.css** — `.device-screen` background: var(--bg) (was #fff)
  - Added .theme-toggle, .lang-switcher, .lang-btn styles
- **shell.js** — T/L keyboard shortcuts, init calls ThemeManager.init() + I18N.init()
- **navigation.js** — navMapEndpoint/navMapTab use I18N.t() for localized toasts
- **All 5 mockups** — Theme toggle + lang switcher in toolbar, data-i18n attributes on nav map items, tab bars, screen headings

---

## [1.5.1] - 2026-04-03

### Added

- **`reference/cbs-patterns.md`** — CBS HOME-specific UI patterns (role cards, balance card, installment table, commission items, referral cards, KYC status, product cards, leaderboard, filter tabs)
- **Lucide Icons documentation** in `reference/components.md` — CDN setup, usage syntax, icon map for CBS HOME (30+ icons), dynamic icons, tab bar sizing
- **Icon System section** in `reference/brand-cbs.md` — Lucide as official icon library
- **Favicon specification** in `reference/brand-cbs.md` — inline SVG U-icon favicon
- **Nav Map Stats Calculation** in `reference/shell.md` — how to populate screen/endpoint counts

### Fixed

- **design.md** — radius values corrected: 6/10/16 → 4/8/12 (rectangular aesthetic)
- **design.md** — font "Inter" → "Montserrat" in output template
- **test.md** — checklist count 66 → 72
- **deliver.md** — broken path template `{name}-final.html` → clean `mockup.html`
- **brand-cbs.md** — focus states clarified: teal for inputs, orange for buttons (was contradictory)
- **variables.css** — removed duplicate `--shadow-focus` (kept `--shadow-focus-teal` + `--shadow-accent-focus`)
- **integrity.md** — version bumped from v1.3.0 to v1.5.1
- **ecosystem.md** — added dark mode note to Step 2, cbs-patterns.md to pre-read
- Cascade fix: all `--shadow-focus` references → `--shadow-focus-teal` across components.css, mockups, skill docs

---

## [1.5.0] - 2026-04-03

### Added

- **Ecosystem Mode** — Multi-mockup architecture with shared CSS/JS
  - `reference/ecosystem.md` — File structure, templates, migration guide
  - `protocols/ecosystem.md` — Step-by-step protocol for creating ecosystem
  - Shared CSS: variables.css, components.css, shell.css, nav-map.css
  - Shared JS: shell.js, navigation.js
  - Index hub: entry point with role cards linking to mockups
- **Two operation modes:** Standalone (single file) and Ecosystem (shared files)

### Changed

- **SKILL.md** — Added ecosystem mode to flow and quick reference
- **Version** — v1.5.0

---

## [1.4.0] - 2026-04-03

### Added

- **CBS HOME Brand System** — Native brand tokens in `reference/brand-cbs.md`
  - Teal (#1A6B6A) + Orange (#E8651A) palette
  - Montserrat font with exact scale (12-48px)
  - Rectangular aesthetic (radius: 4/8/12px)
  - 8px spacing system (xs→4xl)
  - Dark mode tokens
  - U-icon component specification
  - Gradient CSS classes (no more inline gradients)
  - EUR data conventions
- **Auto-validation script** in `protocols/test.md` — browser console JS checks
- **Endpoint identification workflow** in `protocols/polish.md`
- **CSS variable validation step** in `protocols/polish.md`
- **Focus states specification** in `protocols/design.md`
- **Nav Map auto-stats** JS in `reference/shell.md`

### Changed

- **components.md** — All tokens replaced with CBS HOME values
  - Colors: teal/orange (was blue/amber)
  - Radius: 4/8/12 rectangular (was 6/10/16 rounded)
  - Shadows: brand-correct values
  - SVG select arrow: complete data-URI (was truncated)
  - switchTab(): safer event handling with `el.closest()`
  - Focus ring: orange (was blue)
- **interactions.md** — Toast reads CSS variables via getComputedStyle (was hardcoded hex)
- **data.md** — Added CBS HOME products, roles, EUR formatting, commission levels
- **shell.md** — Added initNavMapStats(), M keyboard shortcut
- **design.md** — Montserrat (was Inter), brand-cbs.md pre-read, focus states
- **build.md** — Montserrat font import, brand-cbs.md pre-read, form pattern explanation
- **polish.md** — Output filename mockup.html (was final.html), endpoint workflow
- **checklist.md** — Added 6 brand compliance checks (B1-B6), total: 72 checks

### Fixed

- Removed "1?" template artifacts from brief.md, design.md, sanitize.md
- Fixed incomplete SVG in form-select component
- Fixed deliver.md hardcoded path
- Fixed switchTab() `this` binding bug

---

## [1.3.0] - 2026-01-24

### Added

- **Traffic Light System** — 3-color status indication in Navigation Map
  - 🟢 Green = Full screen (navigates)
  - 🟡 Yellow = Tab (switches content)
  - 🔴 Red = Dead end (endpoint)
- **Collapsible Sections** — Sections in nav map can collapse/expand
  - Click section header to toggle
  - Arrow indicator (▼/▶)
  - Default state: all collapsed
- **Section Counters** — Each section shows item count `(N)`
- **navMapTab()** — New function for yellow tab items
- **toggleSection()** — New function for section collapse

### Changed

- **Legend** — Now shows 3 colors instead of 2
- **Status dot position** — Moved to end (after badge)
- **Section structure** — Wrapped in `.nav-map-section-content`
- **checklist.md** — Updated N5, N6, E3; added N9-N13 (5 new checks)
  - Total: 66 checks (was 61)

### Reference Files

- shell.md — Traffic light CSS, collapsible sections CSS/JS, updated HTML templates
- checklist.md — Traffic light validation, section collapse checks

---

## [1.2.0] - 2026-01-23

### Added

- **Navigation Map** — 📍 Map button in toolbar with popup showing screen tree
  - Statistics (screens / paths / endpoints)
  - Color legend (● Screen / 📌 Endpoint)
  - Clickable tree with depth levels (L0-L3)
  - Endpoint items navigate to parent screen + show toast
- **Adaptive Toolbar** — Mobile-friendly toolbar (<480px)
  - Device buttons: emoji only (no labels, no sizes)
  - Zoom: +/− only (no percentage)
  - Map: 📍 only (no label)
- **Endpoint Toast Pattern** — `📌 [Name] — финальная точка`
  - All non-navigating clicks show clear endpoint message
  - Users understand it's end of path, not a bug

### Changed

- **Invariants** — Added 3 new rules:
  - Always navigation map
  - Always adaptive toolbar
  - Always endpoint marking
- **checklist.md** — Added 18 new checks:
  - Navigation Map (8 checks: N1-N8)
  - Endpoint (5 checks: E1-E5)
  - Mobile Toolbar (5 checks: M1-M5)
  - Total: 61 checks (was 43)
- **Drift Indicator** — Added 3 new signs

### Reference Files

- shell.md — Added Navigation Map HTML/CSS/JS + Mobile Toolbar CSS
- checklist.md — Added nav map, endpoint, mobile toolbar validation
- interactions.md — Added Endpoint Pattern section

---

## [1.1.0] - 2026-01-22

### Fixed

- **Toolbar overlap** — Changed from floating center to full-width bar
- **Fixed elements escaping frame** — Added sticky rules for mockup content
- **Resolution switching** — Corrected CSS classes for device sizes

### Added

- **test protocol** — Quality validation before delivery (L3.5)
- **checklist.md** — 25 quality gates in 5 categories
- **Tab Bar component** — Mobile bottom navigation with sticky positioning
- **Sticky rules section** — In shell.md for proper element containment

### Changed

- **Flow** — Now includes test step: brief → design → build → polish → test → deliver
- **polish.md** — Now routes to test instead of direct delivery
- **build.md** — Added sticky rule warning and tab bar reference
- **Invariants** — Added "Always sticky inside" and "Never skip test"
- **Drift Indicator** — Added checks for fixed position and skipped test

### Reference Files

- shell.md — Rewritten with new toolbar + sticky rules
- checklist.md — New quality gates file
- components.md — Added Tab Bar component

---

## [1.0.0] - 2026-01-22

### Added

- Initial release
- 4 protocols: brief, design, build, polish
- Device Preview shell (phone/tablet/desktop)
- Microinteraction patterns
- Toast notification system
- Realistic data templates
- UI component library
- Keyboard shortcuts for device switching
- CCC architecture (L0-L3)
- Quick Reference table in SKILL.md
- Quick Checklist in brief.md
- Explicit Never/Always invariants

### Reference Files

- shell.md — Device Preview structure
- interactions.md — Animations + feedback
- data.md — Realistic data patterns
- components.md — UI components

---

*CHANGELOG v1.5.0*
