---
name: analysis-sections-core
description: "Core analysis sections 1-9 and 11 for code audit: overview, bugs, error handling, security, performance, code quality, testability, refactoring, polish, and cross-module consistency."
---

# Analysis Sections (Core)

Execute sections 1–9 in order from this file. Section 11 is invoked separately by SKILL.md step 3.5.
For each section with no findings, write exactly: "No issues found." and move on.
Never invent findings to fill a section.

---

## Section 1 — General Overview

- What does the code do
- Architecture and approach
- Technology stack / framework detected
- Overall quality score: X/10

Scale:
- 9-10: Production-ready, cosmetic only
- 7-8: Good, improvements exist, nothing critical
- 5-6: Works but notable problems
- 3-4: Serious problems, needs rework
- 1-2: Must be rewritten

---

## Section 2 — Critical Bugs and Logic Errors

Targets:
- Logic errors that produce wrong results
- Race conditions, shared mutable state, missing locks
- Null/undefined/nil dereferences and missing guards
- Off-by-one errors, boundary failures
- Async/await mistakes: missing await, unhandled rejections, wrong error propagation
- Type coercion bugs
- Edge cases: empty input, zero, negative values, max values, concurrent access

Every finding must include a diff example. No finding without a concrete fix.

---

## Section 3 — Error Handling

Targets:
- Silent catches: exceptions caught but not logged or re-thrown
- Bare except / catch-all without re-throw
- Unhandled promise rejections
- Generic error messages with no debugging context ("Something went wrong", "Error occurred")
  Good messages include: what failed, which input caused it, where in the system
- Logging completeness: minimum = exception type + message + call origin
  Flag: logging only message string without stack trace or request context
- Missing retry logic on transient failures (network, I/O)
- Missing graceful degradation on non-critical paths

---

## Section 4 — Security and Vulnerabilities

For each vulnerability found: attack vector → impact → fix with diff example.
Show example of malicious input where relevant.

Targets:
- Hardcoded secrets, API keys, tokens, passwords in code or config
- Sensitive data in logs (tokens, PII, passwords)
- Unvalidated user input reaching dangerous sinks:
  - DB queries without parameterization (SQL/NoSQL injection)
  - Template rendering without escaping (XSS)
  - File system paths without sanitization (path traversal)
  - Server-side HTTP calls with user-controlled URLs (SSRF)
  - Deserialization of untrusted data without validation
- Broken authentication or authorization logic
- Missing authorization checks on protected endpoints
- Mass assignment: model binding without allowlist
- Insecure defaults: debug mode on, open CORS, weak or deprecated crypto
- Privilege escalation paths: code grants more permissions than required
  (AI-generated code shows 322% more escalation paths than human-written — flag any pattern
  where a component acquires permissions beyond its stated role)
- Architectural auth drift: auth/authz logic changed across multiple files
  without consistent update — silent authentication failures
- Rate limiting absent on public endpoints
- APIs returning full objects instead of DTOs (data over-exposure)
- Dependency verification: flag any package import for cross-check in Section 10

Additional detection patterns (SSRF, deserialization, mass assignment, IDOR):

- **SSRF**: `requests.get(user_url)`, `urllib.urlopen(url)`, `http.Get(url)`, `fetch(url)` where URL comes from user input without allowlist. Flag any HTTP call where the URL or host is derived from request parameters.
- **Deserialization**: `pickle.loads()`, `yaml.load()` (without `Loader=SafeLoader`), `eval()`, `exec()`, `unserialize()` (PHP), `ObjectInputStream` (Java) on untrusted data. Always CRITICAL.
- **Mass assignment**: ORM model created from `**request.data` or `Object.assign(model, req.body)` without explicit field allowlist. Look for: `Model(**data)`, `Model.create(**kwargs)`, `_.merge(obj, userInput)`.
- **IDOR**: DB query with user-supplied ID without ownership check: `Model.objects.get(id=request_id)` without `.filter(user=current_user)`. Look for: `.get(id=...)`, `.findById(params.id)`, `WHERE id = ?` without `AND user_id = ?`.
- **Open redirect**: `redirect(request.params['url'])`, `res.redirect(req.query.next)` without validating that URL is relative or on allowlist.

---

## Section 5 — Performance

Targets:
- O(n²) or worse algorithms where O(n log n) or O(n) is achievable
- N+1 query problems
- Missing indexes on frequently queried fields
- Unnecessary repeated computation inside loops
- Missing caching on expensive or repeated operations
- Excessive memory allocation: large objects created in loops
- Blocking I/O on async paths
- Missing pagination on potentially large result sets

---

## Section 6 — Code Quality and Best Practices

Targets:
- Naming: variables, functions, classes that mislead or obscure intent
- SOLID violations: classes doing multiple things, tight coupling, no interfaces
- DRY violations: duplicated logic that should be extracted
- KISS violations: unnecessary complexity for simple problems
- Dead code: unused functions, unreachable branches, commented-out blocks
- Comments: missing where logic is non-obvious, or present but lying about what code does
- Modern language features unused where they would simplify (optional chaining, destructuring,
  async/await vs callbacks, dataclasses vs raw dicts, etc.)
- Inconsistent conventions: mixed naming styles, mixed patterns within same module

---

## Section 7 — Testability

Targets:
- Hard dependencies on global state or singletons blocking unit tests
- Missing dependency injection preventing mocking
- Functions doing too much to test in isolation
- Absence of test directory or test files for critical paths
- No error path tests (only happy path tested)
- Tests that test implementation details instead of behavior
- Concrete suggestions: what to extract, what to inject, what to mock

---

## Section 8 — Refactoring Recommendations

Only for patterns that meaningfully improve the code.
Each recommendation must include a before/after example.

Targets:
- Extract: functions/classes that should be split
- Abstract: duplicated structures that need a base class or utility
- Simplify: over-engineered solutions
- Alternative architecture: only when current approach has structural problems

---

## Section 9 — Minor Improvements and Polish

- Type annotations missing on public interfaces
- Linter / formatter issues visible in the code
- Stylistic inconsistencies
- Small correctness improvements not covered above

---

## Section 11 — Cross-Module Consistency (multi-file only)

Run only when 2+ files are reviewed together. Skip for single-file reviews.
If a single file is being reviewed, write: "Skipped (single file review)."

Targets:
- Duplicate functionality across files (same CRUD, same validation, same error handling)
- Inconsistent patterns: one file uses pattern A, another uses pattern B for the same concept
- Inconsistent datetime handling (aware vs naive, UTC vs local, different format strings)
- Inconsistent error handling strategies across modules (one logs, another swallows, third re-throws)
- Shared state or dependencies where a change in one file silently breaks another
- API contract mismatches: caller expects X, callee returns Y
- Inconsistent naming for the same concept across files (e.g. `db_path` vs `database_path`)
- Connection/resource management differences (pooling vs per-call, pragma usage vs bare connect)
- Duplicate APIs: multiple files providing CRUD for the same DB table with incompatible interfaces

Every finding must reference BOTH files and explain the inconsistency with a diff example showing the recommended unification.

