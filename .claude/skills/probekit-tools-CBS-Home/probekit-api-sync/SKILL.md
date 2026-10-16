---
name: probekit-api-sync
description: "API alignment audit between backend (FastAPI/Pydantic) and frontend (Vue 3/TypeScript). Detects endpoint existence mismatches, request/response shape divergences, pagination format inconsistencies, error handling gaps, auth requirement discrepancies, and CORS config issues. Triggers on: 'api sync', 'api alignment', 'api audit', 'check api', 'api divergence', '/probekit-api-sync'."
---

# api-sync v1.0.0

API alignment audit for CBS HOME. Compares backend FastAPI routes and
Pydantic schemas against frontend TypeScript API modules and interfaces.
Produces a scored report with divergences categorized by severity and
concrete fix recommendations (which side to fix).

**Scope**: source code comparison only. Does NOT make HTTP requests or
start servers. Reads backend router/schema files and frontend api/*.ts files.

## Configuration

report_dir: docs/01_refer/ARCHIVES/CODE-AUDIT/PROBKIT-REVIEW
backend_dir: backend/app
frontend_api_dir: mockups/frontend/src/api

## Execution Steps

**Step 1 -- Identify input**
Parse the user's request to extract:
- Target: "full" (all modules) or specific module (auth, users, kyc, documents, etc.)
- `--fix` flag: generate correction code for frontend API layer
- `--backend-only`: only scan backend, produce endpoint registry
- `--frontend-only`: only scan frontend, produce call registry

Read `docs/01_refer/ENVIRONMENT.md` for project context.

**Step 2 -- Build Backend API Registry**

Scan `backend/app/main.py` to find all `app.include_router()` calls with their prefixes.
Then for each router file (`backend/app/modules/*/router.py`, `*/staff_router.py`):

1. Extract `APIRouter(prefix="...")` or prefix from include_router
2. Extract all route decorators: `@router.get/post/patch/put/delete("/{path}")`
3. For each route, record:
   - Full path (prefix + route path)
   - HTTP method
   - Request body: type hint on `body:` parameter or `Depends()` schema
   - Response model: `response_model=` parameter
   - Auth: presence of `Depends(get_current_user)` or `Depends(get_current_user_write)`
   - Source: file:line
4. For each referenced Pydantic schema, read `modules/*/schemas.py`:
   - Extract model class name, fields with types
   - Follow inheritance (BaseModel subclasses)

Build structured registry of all backend endpoints.

**Step 3 -- Build Frontend API Call Registry**

Scan all `mockups/frontend/src/api/*.ts` files (except client.ts which is infrastructure):

1. Extract all `api.get/post/patch/put/delete<Type>('/path', ...)` calls
2. Extract `apiUpload<Type>('/path', ...)` calls for FormData uploads
3. For each call, record:
   - Path (the URL string)
   - HTTP method
   - Request type (second argument type or FormData)
   - Response type (generic type parameter)
   - skipAuth: presence of `{ skipAuth: true }` option
   - Source: file:line
4. Read `mockups/frontend/src/api/types.ts`:
   - Extract all TypeScript interfaces with fields and types
   - Map interface names to their field definitions

Build structured registry of all frontend API calls.

**Step 4 -- Execute Probes**

Read `references/probe-definitions.md` for detection methods and thresholds.

Run all 7 probes:

1. **P1-EXIST** (Endpoint Existence): Cross-reference frontend calls against backend routes.
   Flag phantom endpoints (frontend calls with no backend route) as CRITICAL.
   Flag backend-only endpoints as SUGGESTION (informational).

2. **P2-REQSHAPE** (Request Shape): For matched endpoints, compare frontend request interface
   fields against backend Pydantic request schema fields.
   Flag missing required fields as CRITICAL, missing optional as WARNING, type mismatches as WARNING.

3. **P3-RESPSHAPE** (Response Shape): For matched endpoints, compare backend response schema
   fields against frontend response interface fields.
   Flag fields expected by frontend but absent from backend as CRITICAL.
   Flag fields in backend but not typed in frontend as SUGGESTION.

4. **P4-AUTH** (Auth Alignment): Compare frontend skipAuth flag against backend auth dependency.
   Flag skipAuth=true when backend requires auth as CRITICAL.

5. **P5-PAGINATE** (Pagination Format): Compare pagination wrapper field names.
   Flag collection field name mismatch (e.g., `data` vs `items`) as CRITICAL.

6. **P6-ERROR** (Error Format): Compare frontend error parsing logic in client.ts against
   backend error response format from exception handlers.
   Flag field name mismatches in error bodies as WARNING.

7. **P7-CORS** (CORS Config): Read backend CORS middleware config.
   Check that all headers frontend sends are in allow_headers.
   Check credentials alignment.

**Step 5 -- Score and classify**

Read `references/output-template.md` for report format.

Calculate severity points:
```
severity_points = (critical_count * 1.5) + (warning_count * 0.5) + (suggestion_count * 0.1)
score = max(1, min(10, 10 - severity_points))
```

Quality gate:
- PASS: 0 CRITICAL, score >= 7
- WARN: 1-2 CRITICAL, score 4-6
- FAIL: 3+ CRITICAL or score < 4

For each divergence, determine fix side:
- Frontend fix: change API path, update type, add field
- Backend fix: add endpoint, add schema field
- Both: requires coordination (e.g., new feature endpoint)

**Step 6 -- Write report**

Save to `{report_dir}/API-SYNC-{YYYYMMDD}.md` using output-template.md format.

Include:
1. Endpoint registries (backend + frontend)
2. Coverage matrix (which calls map to which routes)
3. Divergences by severity
4. Recommendation table (fix side + effort estimate)
5. Score breakdown by probe

**Step 7 -- Update audit tracker (if exists)**

If `{report_dir}/AUDIT-TRACKER.md` exists, append a row with date, scope, score, finding counts.

## Anchor

[*] api-sync v1.0.0 * ready
[>] | NEXT: user command
