---
name: test
description: "v1.8.0 | L3.5 - Validate mockup quality before delivery"
---

# test

## Purpose

Validate mockup against quality checklist before delivery.

| Creates | Validated mockup |
|---------|------------------|
| Layer | L3.5 (after polish) |
| Output | Ready-to-deliver HTML |

---

## Pre-read

| # | Read | Why |
|---|------|-----|
| 1 | reference/checklist.md | Full quality gates (94 checks) |
| 2 | reference/shell.md | If shell issues found |

---

## Phase 0: Integrity Gate

Check file is not corrupted (see reference/integrity.md):
- Last line must be `</html>`
- No `cdn-cgi` or `__cf_email__` injections
- No truncation

| Result | Action |
|--------|--------|
| All pass | → Phase 1 |
| Any fail | STOP → sanitize protocol |

---

## Phases 1-7: Quality Checks

Run all checks from **reference/checklist.md**:

1. **Visual** — page loads, no console errors
2. **Shell** — toolbar, device frame, no overlap
3. **Resolution** — Phone (390px), Tablet (820px), Desktop (1280px)
4. **Layout** — flex chain, tab bar at bottom, sticky header
5. **Clickability** — all onclick elements respond, nested buttons work
6. **Interaction** — navigation, scroll reset, toasts, popups
7. **Content** — no Lorem ipsum, realistic data, readable text
8. **Navigation Map** — button visible, popup opens, screens clickable
9. **Endpoints** — all non-nav clicks show `📌 ... — финальная точка`

---

## Phase 8: Fix & Retest

### Severity Guide

| Severity | Examples |
|----------|----------|
| BLOCKER | Clicks don't work, tab-bar floats, shell broken |
| MAJOR | Lorem ipsum, missing toast, sticky not working |
| MINOR | Hover inconsistent, spacing off |

### Pass Criteria

| Criteria | |
|----------|-|
| 0 BLOCKER | |
| ≤2 MAJOR | |

After fixes → rerun phases until pass criteria met.

---

## Auto-Validation Script

Run in browser console to check common issues:

```javascript
const results = [];
// INT: File structure
results.push({ check: 'Screens exist', ok: document.querySelectorAll('.screen').length > 0 });
results.push({ check: 'Nav Map exists', ok: !!document.getElementById('navMapOverlay') });
results.push({ check: 'Device frame', ok: !!document.getElementById('deviceFrame') });
// Brand
results.push({ check: 'Font Montserrat', ok: getComputedStyle(document.body).fontFamily.includes('Montserrat') });
// Flex chain
results.push({ check: 'Flex chain', ok: getComputedStyle(document.querySelector('.mockup-content')).display === 'flex' });
// No Lorem
results.push({ check: 'No Lorem', ok: !document.body.innerText.toLowerCase().includes('lorem') });
console.table(results);
```

---

*test v1.8.0*
