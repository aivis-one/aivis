# CHANGELOG

All notable changes to livemockup-studio.

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

*CHANGELOG v1.3.0*
