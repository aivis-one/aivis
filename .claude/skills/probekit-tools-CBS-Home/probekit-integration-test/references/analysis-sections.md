# Analysis Sections

Execute all 10 sections in order before generating any tests.
Purpose: understand the code well enough to generate tests that actually verify real behaviour.
For each section with no findings, write "No issues found." and move on.

---

## Section 1 — Layer Identification

Identify what type of code is being tested:

**API Layer** — route handlers, controllers, request/response handling
Signals: Flask/FastAPI/Express/Django routes, HTTP verb decorators, request parsing, status codes

**Repository / DB Layer** — data access objects, query functions, ORM models
Signals: SQLAlchemy sessions, raw SQL, sqlite3 connections, ORM model methods, CRUD functions

**Service Layer** — business logic orchestrating multiple repos or APIs
Signals: functions that call multiple other modules, transaction coordination, domain operations

**Mixed** — multiple layers in same file (common in small projects)

Output: named list of layers found, entry points, and DB schema if detectable.

---

## Section 2 — Endpoint and Function Inventory

List every testable unit:

For API layer:
- Route path, HTTP method, handler function name
- Request parameters: path params, query params, request body schema
- Response shape: status codes, response body fields
- Auth requirements (if any)

For DB / Repository layer:
- Function name and signature
- What it reads/writes to DB
- Tables and columns involved
- Constraints that could be violated (UNIQUE, NOT NULL, FK)

For Service layer:
- Function name and signature
- External dependencies it calls
- What can fail and how

This inventory becomes the test plan skeleton in Step 3.

---

## Section 3 — Dependency Map

Identify what each function depends on:

**Managed dependencies** (use real in tests):
- SQLite / PostgreSQL / MySQL database
- File system (within project)
- In-process caches

**Unmanaged dependencies** (mock in tests):
- External HTTP APIs (payment gateways, email services, OAuth providers)
- System clock (use monkeypatch or freezegun for time-sensitive logic)
- Random number generation
- Environment variables with secrets

For each unmanaged dependency: note what to mock and what the mock should return.

---

## Section 4 — Error and Edge Case Inventory

For each endpoint or function, identify non-happy paths:

- Input validation failures (missing fields, wrong types, out-of-range values)
- DB constraint violations (duplicate keys, FK violations, NULL on required field)
- Not-found cases (query returns empty, record doesn't exist)
- Auth failures (if auth is present)
- Concurrent access (if relevant)
- Connection/transient failures (network down, DB timeout) — flag if no retry/graceful handling

These become the error-path test cases.
Rule: every endpoint needs at least 1 happy path + 1 error path test.

---

## Section 5 — Contract Surface

Identify the contracts between layers or between this service and its callers:

- What fields does the API response include? Are any internal DB fields leaked?
- Does the response schema match what calling code (frontend, other service) expects?
- Are there hardcoded field names that would break callers if renamed?
- Is pagination present where it should be (large result sets)?
- Are error responses structured consistently (same error envelope shape)?

Flag any contract risks as findings. These become contract compliance tests.

---

## Section 6 — Test Infrastructure Assessment

Assess what test infrastructure already exists and what needs to be created:

Existing (reuse):
- conftest.py with fixtures
- Test DB setup helpers
- Factory functions for test data
- Existing integration test files

Missing (generate):
- DB fixture (in-memory or temp file, schema creation, teardown)
- API test client fixture
- Seed data helpers
- Mock factories for unmanaged deps

Note: if the project uses SQLite as primary DB — use it directly with a temp file or :memory:.
Never spin up Docker or external services automatically — flag if needed and ask the user.

---

## Section 7 — API Route Extraction

Systematically discover all testable endpoints from the codebase.

**By framework — decorator/pattern detection:**

| Framework | Decorator/Pattern | Regex | Example |
|-----------|------------------|-------|---------|
| FastAPI | `@app.get/post/put/delete`, `@router.get/post` | `@(app\|router)\.(get\|post\|put\|delete\|patch)\(` | `@router.get("/users/{id}")` |
| Flask | `@app.route`, `@blueprint.route` | `@(app\|bp\|blueprint)\.(route\|get\|post)\(` | `@app.route("/api/users", methods=["GET"])` |
| Django | `path()`, `re_path()` in urls.py | `path\(["']` | `path("api/users/", views.UserList.as_view())` |
| Express | `app.get/post`, `router.get/post` | `(app\|router)\.(get\|post\|put\|delete)\(` | `router.get('/api/users', handler)` |
| Godot HTTP | Manual URL matching in `_on_request` | — | No decorators; map by URL string comparison |

**Extraction procedure:**
1. Grep for framework-specific patterns above
2. For each hit: extract HTTP method, path, handler function name
3. Map handler → dependencies (what services/repos does it call?)
4. Flag endpoints without auth middleware (if auth exists elsewhere)
5. Flag endpoints that accept user input but have no validation

Output: table of (method, path, handler, dependencies, auth, validation).

---

## Section 8 — Dependency Graph Mapping

Trace how modules connect to determine integration boundaries.

**How to extract:**
1. Read `import` statements in each target file
2. For each imported module — classify:
   - **Internal service** (same project) → real dependency, test with real implementation
   - **External API** (HTTP calls, SDK clients) → mock boundary
   - **Database** (ORM, raw SQL, aiosqlite) → test with in-memory/temp DB
   - **Config/env** (settings, secrets) → inject test config
3. Draw dependency direction: A → B means "A calls B"
4. Identify circular dependencies (A → B → A) — flag as WARNING

**Output:** list of integration pairs to test:
```
router_users.py → user_service.py → user_repository.py → SQLite
               → auth_service.py → external_oauth (MOCK)
```

Each arrow = one integration test boundary.

---

## Section 9 — Service Boundary Detection

Identify where one service ends and another begins — these are the critical integration test targets.

**Boundary indicators:**
- Module A calls module B's public method but they live in different directories
- A function receives data from an external source and transforms it before passing downstream
- A service wraps another service and adds error handling, retry, or caching
- A repository is called by multiple services (shared boundary)

**For each boundary found, determine:**
1. What data crosses the boundary? (types, shapes, nullable fields)
2. What errors can cross the boundary? (exceptions, error codes, None returns)
3. Is the boundary contractual? (does changing B's return type break A?)
4. Is there an existing test that covers this boundary?

Output: boundary map with test coverage status (covered / not covered / partially covered).

---

## Section 10 — Database Schema Analysis

For DB-layer integration tests — understand the schema to write correct test data.

**Extract from codebase:**
1. Find migration files, schema definitions, or CREATE TABLE statements
2. List all tables with columns, types, constraints (PK, FK, UNIQUE, NOT NULL, DEFAULT)
3. Identify FK relationships — tests must respect insert order
4. Identify UNIQUE constraints — tests must use unique values or handle conflicts
5. Identify indexes — no action needed but note for perf context

**If SQLite with `PRAGMA foreign_keys`:**
- Check if FK enforcement is ON in production code
- Test fixture MUST also enable FKs: `PRAGMA foreign_keys = ON`
- Otherwise FK violations pass in tests but fail in production

**Common test data pitfalls:**
- Inserting child record before parent (FK violation)
- Reusing the same PK across tests (UNIQUE violation in non-isolated tests)
- Missing NOT NULL fields in test inserts
- Date/time format mismatch between test data and production code
