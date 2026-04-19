# Probe Definitions -- probekit-api-sync

## Probe 1: ENDPOINT-EXISTENCE (P1-EXIST)

**Purpose:** Every frontend API call must map to an existing backend route.

**Detection method:**
1. For each entry in Frontend Call Registry, search Backend API Registry for matching (method + path)
2. Path matching is exact after normalizing trailing slashes
3. Classify results:
   - MATCHED: both sides have the endpoint
   - PHANTOM: frontend calls it, backend has no route (runtime 404/405)
   - BACKEND-ONLY: backend has route, frontend never calls it

**Thresholds:**
| Metric | Severity |
|--------|----------|
| Phantom endpoint | 🔴 CRITICAL (1.5 points each) |
| Backend-only endpoint | 🟢 SUGGESTION (0.1 points each) |

**Scoring:** 0 phantom = 10/10. Each phantom -1.5 points. Floor at 1/10.

---

## Probe 2: REQUEST-SHAPE (P2-REQSHAPE)

**Purpose:** Frontend request body interfaces must match backend Pydantic request schemas.

**Detection method:**
1. For each MATCHED endpoint that has a request body:
   - Extract frontend TS interface fields + types
   - Extract backend Pydantic model fields + types
2. Compare field by field:
   - **Missing required:** backend has required field, frontend interface lacks it
   - **Missing optional:** backend has optional field, frontend interface lacks it
   - **Extra frontend field:** frontend sends field backend does not expect
   - **Type mismatch:** field exists both sides, types differ

**Type mapping (TS → Python):**
| TypeScript | Python |
|-----------|--------|
| string | str, EmailStr |
| number | int, float |
| boolean | bool |
| string \| null | str \| None, Optional[str] |
| string[] | list[str] |
| Record<string, unknown> | dict[str, Any] |

**Thresholds:**
| Metric | Severity |
|--------|----------|
| Missing required field | 🔴 CRITICAL (1.5 points) |
| Extra frontend field (backend ignores) | 🟡 WARNING (0.5 points) |
| Missing optional field | 🟡 WARNING (0.5 points) |
| Type mismatch | 🟡 WARNING (0.5 points) |

---

## Probe 3: RESPONSE-SHAPE (P3-RESPSHAPE)

**Purpose:** Frontend TS response interfaces must match backend Pydantic response schemas.

**Detection method:**
1. For each MATCHED endpoint:
   - Extract backend response model fields + types
   - Extract frontend TS response interface fields + types
2. Compare:
   - **Frontend expects, backend lacks:** field in TS interface but not in Pydantic model → runtime undefined
   - **Backend sends, frontend ignores:** field in Pydantic model but not in TS interface → data loss (acceptable)
   - **Type mismatch:** field exists both sides, types differ

**Thresholds:**
| Metric | Severity |
|--------|----------|
| Frontend expects field backend never sends | 🔴 CRITICAL (1.5 points) |
| Backend sends field frontend ignores | 🟢 SUGGESTION (0.1 points) |
| Type mismatch | 🟡 WARNING (0.5 points) |

---

## Probe 4: AUTH-ALIGNMENT (P4-AUTH)

**Purpose:** Frontend auth expectations must match backend auth requirements.

**Detection method:**
1. For each MATCHED endpoint:
   - Frontend: check for `{ skipAuth: true }` option in API call
   - Backend: check for `Depends(get_current_user)` or `Depends(get_current_user_write)` in route params
2. Classify:
   - **Skip-on-required:** frontend skips auth, backend requires it → 401 at runtime
   - **Auth-on-public:** frontend sends auth, backend does not require it → harmless

**Thresholds:**
| Metric | Severity |
|--------|----------|
| Skip-on-required (401 at runtime) | 🔴 CRITICAL (1.5 points) |
| Auth-on-public (harmless) | 🟢 SUGGESTION (0.1 points) |

---

## Probe 5: PAGINATION-FORMAT (P5-PAGINATE)

**Purpose:** Frontend and backend must agree on pagination response field names.

**Detection method:**
1. Find frontend `PaginatedResponse<T>` interface — extract collection field name
2. Find backend paginated response schemas — extract collection field name
3. Compare field names

**Known pattern:**
- Frontend uses `data: T[]` (from PaginatedResponse in types.ts)
- Backend uses `items: list[T]` (from various ListResponse schemas)

**Thresholds:**
| Metric | Severity |
|--------|----------|
| Collection field name mismatch | 🔴 CRITICAL (1.5 points) |
| Metadata field mismatch (page, per_page, total) | 🟡 WARNING (0.5 points) |

---

## Probe 6: ERROR-FORMAT (P6-ERROR)

**Purpose:** Frontend error handling must correctly parse backend error responses.

**Detection method:**
1. Read frontend `handleResponse()` in client.ts:
   - Which fields does it read from error body? (message, error, errors/detail)
   - How does it map status codes to error classes?
2. Read backend error handler in main.py:
   - What JSON shape does CBSError produce?
   - Does FastAPI's default 422 handler produce `{detail: [...]}` or custom `{errors: {...}}`?
3. Compare field names and structure

**Thresholds:**
| Metric | Severity |
|--------|----------|
| Error body field completely missing | 🔴 CRITICAL (1.5 points) |
| Format mismatch (array vs object) | 🟡 WARNING (0.5 points) |
| Extra fields (harmless) | 🟢 SUGGESTION (0.1 points) |

---

## Probe 7: CORS-CONFIG (P7-CORS)

**Purpose:** CORS configuration must allow frontend requests.

**Detection method:**
1. Read backend CORS middleware in main.py:
   - allow_origins: must include frontend origin or "*"
   - allow_headers: must include all custom headers frontend sends
   - allow_credentials: must be true if frontend uses `credentials: 'include'`
   - allow_methods: must include all HTTP methods frontend uses
2. Read frontend client.ts:
   - Which custom headers are sent? (Authorization, Content-Type, X-Trace-ID, Accept-Language)
   - Does it use `credentials: 'include'`?
3. Check for conflicts:
   - `allow_origins: "*"` + `credentials: true` is invalid per CORS spec

**Thresholds:**
| Metric | Severity |
|--------|----------|
| Missing required header in allow_headers | 🟡 WARNING (0.5 points) |
| Credential mismatch | 🟡 WARNING (0.5 points) |
| Origin not allowed | 🔴 CRITICAL (1.5 points) |
