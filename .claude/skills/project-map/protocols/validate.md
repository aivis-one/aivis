---
name: validate
description: "v1.0.0 | P3: Validate generated map, detect dead-ends, produce recommendations"
---

# P3: Validate

Verify map accuracy, catalog dead-ends, produce actionable recommendations.

| Creates | Validation report (chat) + manifest.validation section |
|---------|--------------------------------------------------------|
| Phase | P3 — Quality & recommendations |

---

## Requirements

| Input | Check |
|-------|-------|
| `mockups/project-map/manifest.yaml` | Must exist (run P1) |
| `mockups/project-map/index.html` | Must exist (run P2) |

If missing → Run P1 (scan) then P2 (generate) first.

---

## Pre-read

| # | Read | Why |
|---|------|-----|
| 1 | reference/status-model.md | Scoring thresholds, traffic light rules |
| 2 | mockups/project-map/manifest.yaml | Data to validate |

---

## Steps

### Step 1: Integrity Check

Verify manifest has all required sections:
- [ ] `version`, `generated_at`, `git_commit`
- [ ] `backend.models` — non-empty array
- [ ] `backend.endpoints.implemented` — array (may be empty)
- [ ] `backend.endpoints.planned` — non-empty array
- [ ] `frontend.mockups` — non-empty array with screens
- [ ] `cross_reference.dead_ends` — present
- [ ] `cross_reference.coverage` — present
- [ ] `cross_reference.prod_readiness` — present
- [ ] `flows` — non-empty array

Spot-check: verify 3 random screen IDs from manifest actually exist in corresponding mockup HTML files.

### Step 2: Dead-End Analysis

Output table (Russian):

```
╔═══════════════════════════════════════════════════════╗
║                   DEAD-END REPORT                     ║
╠═══════════════════════════════════════════════════════╣
║ Тип                    │ Кол-во │ Детали              ║
╠════════════════════════╪════════╪═════════════════════╣
║ Frontend orphans (0%)  │ XX     │ screen-dashboard,   ║
║                        │        │ screen-portfolio,    ║
║                        │        │ ...                  ║
╠════════════════════════╪════════╪═════════════════════╣
║ Backend orphans        │ XX     │ (endpoint paths)     ║
╠════════════════════════╪════════╪═════════════════════╣
║ Model orphans          │ XX     │ (model names)        ║
╠════════════════════════╪════════╪═════════════════════╣
║ Gap endpoints          │ XX     │ (needed but not in   ║
║                        │        │  spec or code)       ║
╚═══════════════════════════════════════════════════════╝
```

Model orphans = models not used by any implemented endpoint's service.

### Step 3: Coverage Statistics

Output table:

```
╔═══════════════════════════════════════════════════════╗
║                  COVERAGE REPORT                      ║
╠═══════════════════════════════════════════════════════╣
║ Overall Endpoints                                     ║
║   Implemented: XX / XXX (XX%)                         ║
║   In Progress: XX                                     ║
║   Planned: XX                                         ║
║   Gap: XX                                             ║
╠═══════════════════════════════════════════════════════╣
║ By Role            │ Screens │ Avg Score │ Status      ║
╠════════════════════╪═════════╪══════════╪════════════╣
║ Auth               │ 7       │ XX%      │ partial     ║
║ Investor           │ 9       │ XX%      │ blocked     ║
║ Agent              │ 7       │ XX%      │ blocked     ║
║ Company            │ 5       │ XX%      │ blocked     ║
║ Staff              │ 7       │ XX%      │ blocked     ║
╠═══════════════════════════════════════════════════════╣
║ By Sprint Completion                                  ║
║   Sprint 1.1: XX% done                                ║
║   Sprint 1.2: XX% done                                ║
║   ...                                                 ║
╚═══════════════════════════════════════════════════════╝
```

### Step 4: Prod-Readiness Report

Output grouped list:

**Ready for Prod** (score = 100%):
```
🟢 screen-login ─────── 100%  Auth endpoints fully implemented
🟢 screen-register ──── 100%  Auth endpoints fully implemented
```

**Nearest to Ready** (score 50-99%):
```
🟡 screen-X ─────── XX%  Missing: POST /api/v1/...
```

**Blocked** (score < 50%):
```
🔴 screen-dashboard ─── 0%   Blocked by: Sprint 2.1 (investor dashboard)
🔴 screen-portfolio ─── 0%   Blocked by: Sprint 9.2 (portfolio)
...
```

### Step 5: Recommendations

Generate 3 recommendation categories:

**1. Quick Wins** — screens closest to 100% that need the fewest additional endpoints:
```
Рекомендация: Реализуйте Sprint 1.3 (GET/PATCH /users/me)
Результат: screen-profile и screen-settings получат +50% покрытие
```

**2. Maximum Unblock** — which sprint unblocks the most screens:
```
Рекомендация: Sprint X.Y разблокирует N экранов
Детали: [list screens]
```

**3. Prod-Ready Flows** — which business flows can ship first:
```
Ближайший полный flow: "Investor Onboarding" — нужен Sprint 1.3 + 2.1
Текущий прогресс: XX%
```

### Step 6: Output

1. Print full report in Russian in chat (Steps 2-5)
2. Update manifest.yaml with `validation` section:

```yaml
validation:
  performed_at: "<ISO timestamp>"
  integrity: pass
  dead_ends:
    frontend_orphans: XX
    backend_orphans: XX
    model_orphans: XX
    gap_endpoints: XX
  coverage:
    overall_percent: XX
    by_role: {...}
  prod_readiness:
    ready_count: XX
    partial_count: XX
    blocked_count: XX
  recommendations:
    quick_wins: [...]
    max_unblock_sprint: "X.Y"
    nearest_complete_flow: "flow-id"
```

---

## Checklist

- [ ] Manifest integrity verified (all sections present)
- [ ] Spot-check: 3 screen IDs confirmed in HTML
- [ ] Dead-end table output in chat
- [ ] Coverage table output in chat
- [ ] Prod-readiness grouped list output in chat
- [ ] 3 recommendation categories provided
- [ ] manifest.yaml updated with validation section

---

## Anchor

project-map v1.0.0 | validate | complete

Full cycle: scan → generate → validate ✓

---

1 → Re-scan (if code changed): run scan.md
2 → Re-generate (if manifest updated): run generate.md

---

*validate v1.0.0*
