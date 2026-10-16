---
name: project-map
version: 1.0.0
description: "v1.0.0 | Auto-scan Backend-API-Frontend triple map. Triggers: project map, project-map, api map, bridge map, coverage, dead-ends, prod-readiness, map update"
---

# Project Map

Auto-scan backend code, frontend mockups, and spec documents. Generate interactive HTML visualization of the Frontend-API-Backend triple connection. Detect dead-ends, measure coverage, recommend what is ready for production.

Also triggers on: project map, coverage, dead-ends, prod-readiness, map update

---

## Invariants

| Rule | Detail |
|------|--------|
| **Always** scan first | Never generate from stale data |
| **Always** 3 sources | Backend code + Frontend mockups + Spec docs |
| **Always** single HTML | Output: `mockups/project-map/index.html` |
| **Always** YAML manifest | Output: `mockups/project-map/manifest.yaml` |
| **Always** 4 statuses | See `reference/status-model.md` for definitions |
| **Always** dead-end detect | Orphan screens + orphan endpoints |
| **Always** version stamp | Timestamp + git commit in manifest |
| **Never** modify source | Read-only scan of backend/frontend files |
| **Never** manual data | Everything extracted programmatically |

---

## Workflow

P1 scan -> P2 generate -> P3 validate

| Phase | Protocol | Input | Output |
|-------|----------|-------|--------|
| P1 | protocols/scan.md | Source code + specs | manifest.yaml |
| P2 | protocols/generate.md | manifest.yaml | index.html |
| P3 | protocols/validate.md | manifest + html | Report + recommendations |

| Goal | Run |
|------|-----|
| Full rebuild | P1 -> P2 -> P3 |
| After code changes | P1 -> P2 |
| Check gaps only | P3 (if manifest exists) |

---

## Pre-read

| # | Read | When |
|---|------|------|
| 1 | `reference/scanner-patterns.md` | Before scan |
| 2 | `reference/status-model.md` | Before scan |
| 3 | `reference/html-template.md` | Before generate |

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
| New backend module | Re-run P1 auto-discovers new routers |

---

## Anchor

[*] project-map v1.0.0 * ready
[>] | NEXT: user command

---

1 -> scan (full rebuild)
2 -> validate (check gaps)

---

*project-map v1.0.0*
