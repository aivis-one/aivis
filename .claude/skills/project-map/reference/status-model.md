---
name: status-model
description: "v1.0.0 | Implementation status definitions, scoring formulas, sprint mapping"
---

# Status Model

4-state classification for every endpoint, screen, and data flow.

---

## Status Definitions

| Status | Code | Lucide Icon | Color (dark) | CSS Class | Meaning |
|--------|------|-------------|-------------|-----------|---------|
| Implemented | `implemented` | `check-circle` | `#4ADE80` | `.st-impl` | Code exists in router.py, returns data |
| In-Progress | `in_progress` | `hammer` | `#FBBF24` | `.st-wip` | Model exists, router/service not yet |
| Planned | `planned` | `clock` | `#9CA3AF` | `.st-plan` | In CBSHOME-Backend.md, sprint assigned |
| Gap | `gap` | `x-circle` | `#F87171` | `.st-gap` | Frontend needs it, no code or spec |

---

## Classification Rules

### Endpoint Status
```
IF endpoint path found in backend/app/modules/*/router.py  -> implemented
ELIF model for this domain exists in models.py              -> in_progress
ELIF endpoint listed in CBSHOME-Backend.md                  -> planned
ELSE                                                        -> gap
```

### Screen Status (worst-of)
Screen inherits the worst status of its required endpoints:
```
IF any required endpoint is gap         -> gap
ELIF any required endpoint is planned   -> planned
ELIF any required endpoint is in_progress -> in_progress
ELSE                                    -> implemented
```

### Flow Status
Business flow inherits worst-of from its steps.

---

## Scoring Formulas

### Screen Prod-Readiness Score
```
score = (implemented_endpoints / total_required_endpoints) * 100
```

### Traffic Light
| Score | Light | Label |
|-------|-------|-------|
| 100% | `#4ADE80` (green) | Ready for prod |
| 50-99% | `#FBBF24` (yellow) | Partially ready |
| 1-49% | `#FB923C` (orange) | Early stage |
| 0% | `#F87171` (red) | Blocked |

### Flow Score
```
flow_score = (completed_steps / total_steps) * 100
```
Step is "completed" if its endpoint status = `implemented`.

### Role Coverage
```
role_coverage = SUM(screen_scores) / COUNT(screens) for given role
```

---

## Sprint-to-Phase Mapping

| Phase | Sprints | Domain |
|-------|---------|--------|
| 0 | 0.1-0.3 | Infrastructure, Docker, CI |
| 1 | 1.1-1.3 | Auth (email, telegram, profile) |
| 2 | 2.1-2.2 | KYC (SumSub integration) |
| 3 | 3.1-3.3 | Staff panel, avatar mode |
| 4 | 4.1-4.3 | Companies, products, pricing |
| 5 | 5.1-5.3 | Payments (crypto, bank) |
| 6 | 6.1-6.4 | Purchases, installments, ledger |
| 7 | 7.1-7.3 | Agents, referrals, commissions |
| 8 | 8.1-8.3 | Notifications, posts, events |
| 9 | 9.1-9.3 | Portfolio, analytics, leaderboard |
| 10 | 10.1-10.2 | Documents, export, finalization |

---

## System Endpoints (Excluded from Orphan Detection)

These serve infrastructure, not UI:
- `GET /` -- API info
- `GET /health` -- health check
- `GET /ready` -- readiness probe

---

## Mermaid Node CSS Classes

```css
.st-impl > rect  { fill: #065F46; stroke: #4ADE80; }
.st-wip > rect   { fill: #78350F; stroke: #FBBF24; }
.st-plan > rect  { fill: #374151; stroke: #9CA3AF; }
.st-gap > rect   { fill: #7F1D1D; stroke: #F87171; }
```

---

*status-model v1.0.0*
