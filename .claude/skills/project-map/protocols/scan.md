---
name: scan
description: "v1.0.0 | P1: Auto-scan backend code, frontend mockups, and spec documents"
---

# P1: Scan

Extract all data from three sources into a unified YAML manifest.

| Creates | `mockups/project-map/manifest.yaml` |
|---------|--------------------------------------|
| Phase | P1 -- Data extraction |

---

## Pre-read

| # | Read | Why |
|---|------|-----|
| 1 | reference/scanner-patterns.md | Regex patterns for parsing each source |
| 2 | reference/status-model.md | Classification rules (implemented/in_progress/planned/gap) |

---

## Steps

### Step 1: Scan Backend Routers

Read all files matching `backend/app/modules/*/router.py` and `backend/app/main.py`.

For each router file:
1. Extract `APIRouter(prefix="...")` to get the base path
2. For each `@router.(get|post|patch|put|delete)("...")` decorator:
   - Capture HTTP method and route path
   - Full path = prefix + route
   - Capture `response_model`, `status_code` from kwargs
   - Capture `Depends(...)` dependencies
   - Note the function name
3. For `main.py`:
   - Extract `@app.get/post(...)` system endpoints
   - Extract `app.include_router(...)` to verify router registration

**Output**: List of implemented endpoints with method, full_path, module, function, dependencies.

### Step 2: Scan Backend Models

Read all files matching `backend/app/modules/*/models.py` plus `backend/app/core/audit.py`.

For each file:
1. Find classes inheriting from `Base`
2. Extract `__tablename__`
3. For each `Mapped[]` column: name, python type, nullable, default
4. Find `ForeignKey(...)` relationships
5. Find `Index(...)` definitions
6. Find enum classes

**Output**: List of models with table name, columns, relationships, file path.

### Step 3: Scan Backend Services

Read all files matching `backend/app/modules/*/service.py`.

For each file:
1. Extract all `async def` function signatures
2. Extract model imports (`from app.modules.X.models import Y`)
3. Extract cross-service imports

**Output**: List of services with functions, model dependencies.

### Step 4: Scan Frontend Screens

Read all `mockups/*/mockup.html` files (exclude `!site/`, `project-map/`, directories without mockup.html).

For each mockup file:
1. Determine role from directory name (see scanner-patterns.md mapping table)
2. Extract all `id="screen-*"` screen IDs
3. For each screen block:
   - Extract `navigateTo('...')` and `switchTab('...')` -> navigation targets
   - Extract `showToast('...финальная точка...')` -> features needing API
   - Count data entity CSS classes (`.tx-item`, `.stat-card`, etc.)
   - Detect forms (`.form-group` with submit buttons) -> write endpoints

**Output**: List of mockups with role, screens, navigation, data entities, endpoint markers.

### Step 5: Scan Spec Document

Read `CBSHOME-Backend.md` from project root.

Parse:
1. Sprint headers: `### (checkmark?) Sprint X.Y: Name`
2. Endpoint declarations: `METHOD /api/v1/path` (may be in backticks)
3. Task checkboxes: `[x]` = done, `[ ]` = pending
4. Link each endpoint to its sprint

**Output**: List of planned endpoints with method, path, sprint, completion status.

### Step 6: Cross-Reference & Classify

For every endpoint found in spec (Step 5):
- If found in router scan (Step 1) -> `implemented`
- Elif its domain model exists (Step 2) but no router -> `in_progress`
- Else -> `planned`

For every screen (Step 4), use the semantic mapping table (scanner-patterns.md §6):
- Look up required endpoints per screen
- For each required endpoint, determine its status from above
- If endpoint not in spec AND not in code -> `gap`

Detect dead-ends:
- **Frontend orphans**: screens where ALL required endpoints have status != `implemented`
  - Sub-category: screens with 0% = "fully orphaned"
- **Backend orphans**: implemented endpoints that no screen requires
  - Exclude system endpoints (`/`, `/health`, `/ready`)

Calculate scores:
- Per screen: `implemented_count / required_count * 100`
- Per flow: `completed_steps / total_steps * 100` (flows defined in scanner-patterns.md §7)
- Per role: average of screen scores

### Step 7: Write manifest.yaml

Create `mockups/project-map/` directory if not exists.

Write `manifest.yaml` with this structure:

```yaml
version: "1.0.0"
generated_at: "<ISO timestamp>"
git_commit: "<current HEAD short hash>"

backend:
  models: [...]          # from Step 2
  endpoints:
    implemented: [...]   # from Step 1
    planned: [...]       # from Step 5
  services: [...]        # from Step 3

frontend:
  mockups:
    - id: <dir-name>
      file: <path>
      role: <role>
      screens:
        - id: <screen-id>
          data_entities: [<css-classes>]
          navigation_targets: [<screen-ids>]
          endpoint_markers: [<toast-texts>]
          required_endpoints:
            - method: <GET/POST/...>
              path: <full-api-path>
              status: <implemented/in_progress/planned/gap>
              sprint: <X.Y or null>

cross_reference:
  dead_ends:
    frontend_orphans: [<screen-ids with 0% score>]
    backend_orphans: [<endpoint paths with no consumer>]
  coverage:
    total_endpoints:
      implemented: <N>
      in_progress: <N>
      planned: <N>
      gap: <N>
    by_role:
      investor: { screens: <N>, avg_score: <N> }
      agent: { ... }
      company: { ... }
      staff: { ... }
  prod_readiness:
    - screen: <screen-id>
      role: <role>
      score: <0-100>
      status: <ready/partial/blocked>
      blocked_by: <sprint or null>

flows:
  - id: <flow-id>
    name: <human-readable name>
    steps:
      - screen: <screen-id>
        endpoint: <METHOD /path>
        status: <status>
    score: <0-100>
```

---

## Checklist

- [ ] All router files scanned (check `backend/app/modules/*/router.py`)
- [ ] All model files scanned (check `backend/app/modules/*/models.py` + core/audit.py)
- [ ] All service files scanned
- [ ] All mockup HTML files scanned (5 files)
- [ ] CBSHOME-Backend.md parsed for planned endpoints
- [ ] Cross-reference completed with status classification
- [ ] Dead-ends identified
- [ ] Scores calculated
- [ ] manifest.yaml written to `mockups/project-map/manifest.yaml`

---

## Anchor

project-map v1.0.0 | scan | complete

NEXT: generate (P2)

---

*scan v1.0.0*
