---
name: project-map
version: 1.0.0
description: "v1.0.0 | Auto-scan Backend <-> API <-> Frontend triple map. Triggers: project map, project-map, карта проекта, api map, bridge map, coverage, покрытие, dead-ends, тупики, prod-readiness, что готово к проду, обнови карту, map update"
---

# Project Map

Auto-scan backend code, frontend mockups, and spec documents. Generate interactive HTML visualization of the **Frontend <-> API Endpoints <-> Backend** triple connection. Detect dead-ends, measure coverage, recommend what's ready for production.

---

## Invariants

| Rule | Detail |
|------|--------|
| **Always** scan first | Never generate from stale data |
| **Always** 3 sources | Backend code + Frontend mockups + Spec docs |
| **Always** single HTML | Output: `mockups/project-map/index.html` |
| **Always** YAML manifest | Output: `mockups/project-map/manifest.yaml` |
| **Always** 4 statuses | `implemented` / `in_progress` / `planned` / `gap` |
| **Always** dead-end detect | Orphan screens + orphan endpoints |
| **Always** version stamp | Timestamp + git commit in manifest |
| **Never** modify source | Read-only scan of backend/frontend files |
| **Never** manual data | Everything extracted programmatically |

---

## Workflow

```
scan (P1) → generate (P2) → validate (P3)
```

| Phase | Protocol | Input | Output |
|-------|----------|-------|--------|
| P1 | protocols/scan.md | Source code + specs | manifest.yaml |
| P2 | protocols/generate.md | manifest.yaml | index.html |
| P3 | protocols/validate.md | manifest.yaml + index.html | Report + recommendations |

### Quick Paths

| Goal | Run |
|------|-----|
| Full rebuild | P1 → P2 → P3 |
| After code changes | P1 → P2 |
| Check gaps only | P3 (if manifest exists) |

---

## Source Locations

| Source | Path | What to extract |
|--------|------|-----------------|
| Backend routers | `backend/app/modules/*/router.py` | Implemented endpoints |
| Backend models | `backend/app/modules/*/models.py` | DB schema |
| Backend services | `backend/app/modules/*/service.py` | Business logic |
| System endpoints | `backend/app/main.py` | Health, root |
| Frontend mockups | `mockups/*/mockup.html` | Screens, data needs, actions |
| Spec document | `CBSHOME-Backend.md` | Planned endpoints, sprints |
| Core models | `backend/app/core/audit.py` | AuditLog model |

---

## Pre-read References

| # | Read | When |
|---|------|------|
| 1 | `reference/scanner-patterns.md` | Before scan — regex patterns for code parsing |
| 2 | `reference/status-model.md` | Before scan — classification rules, scoring formulas |
| 3 | `reference/html-template.md` | Before generate — HTML structure, CSS tokens, JS |

---

## Output Structure

```
mockups/project-map/
├── manifest.yaml    # Structured data: models, endpoints, screens, cross-refs
└── index.html       # Interactive visualization with 5 panels:
                     #   L0 Overview (Mermaid per role)
                     #   L1 Screens-API (expandable cards)
                     #   L2 Fields-Models (table per model)
                     #   Dead-Ends (orphan lists)
                     #   Prod-Readiness (traffic lights + flow bars)
```

---

## HTML Features

- **Dark theme** matching mockup hub (CBS HOME brand)
- **5 tabs**: L0 Overview / L1 Screens-API / L2 Fields-Models / Dead-Ends / Prod-Readiness
- **Filters**: by role (investor/agent/company/staff), by status (4 states), text search
- **Mermaid diagrams**: flow graphs per role, color-coded by status
- **Expandable cards**: click to see endpoint details per screen
- **Traffic lights**: green (100%) / yellow (50-99%) / orange (1-49%) / red (0%)
- **Flow progress bars**: named business journeys with completion %
- **Prod recommendations**: "ready for prod" list with reasons

---

## Communication

| Aspect | Value |
|--------|-------|
| Language | Russian primary |
| Tone | Professional analytical |
| Output | YAML + HTML files |

---

## Recovery

| Issue | Fix |
|-------|-----|
| Manifest outdated | Re-run P1 (scan) |
| HTML broken | Re-run P2 (generate) |
| Wrong status | Check reference/status-model.md |
| Missing screen | Check reference/scanner-patterns.md |
| New backend module | Re-run P1 — auto-discovers new routers |

---

*project-map v1.0.0*
