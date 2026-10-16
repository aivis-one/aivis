---
name: ai-patterns-catalog
description: "AI-Generated Code Patterns catalog (Section 10): patterns 10.1 through 10.20 covering slopsquatting, hallucinated APIs, god classes, prompt residue, and more."
---

# AI-Generated Code Patterns (Section 10)

Always run this section. AI patterns appear in both AI-generated and human-written code.
When code origin is unknown, assume AI involvement and check all patterns.

If none found: write "No issues found." and close section.

---

## 10.1 Slopsquatting / Hallucinated Dependencies

The most critical AI-specific security risk (2025 data: ~20% of AI-suggested packages
do not exist in any public registry; commercial LLMs hallucinate at ~5%, open-source at ~22%).

Check every import, require, and dependency declaration:
- Does the package name exist in the official registry?
  Python: flag any import that looks invented (unusual compound names, unfamiliar prefixes)
  Node: flag any package not recognizable from npm ecosystem
  Go: flag any module path that seems constructed rather than real
- Common hallucination patterns:
  - Context-gap filling: semantically relevant but invented names (e.g. "secure-json-validator")
  - Surface-form mimicry: follows naming conventions but package doesn't exist
    (e.g. "opentelemetry-instrumentation-fastapi-custom")
  - Cross-ecosystem borrowing: Python package name used in Node context
- Any flagged import → CRITICAL, verify before running

Attack vector: attacker registers the hallucinated name with malicious payload.
Zero-click risk: post-install scripts execute on npm install without confirmation.

---

## 10.2 Hallucinated APIs and Functions

- Calls to methods that do not exist on the library being used
- References to function signatures that don't match actual library API
- Invented configuration options on real libraries
- Non-existent CLI flags or environment variables
- How to detect: read the actual call site; if method name feels assembled rather than recalled,
  flag for verification against official docs

---

## 10.3 God Classes via Append Behavior

AI appends to existing classes rather than decomposing. Symptom: one class with
disproportionate method count and LOC absorbing multiple responsibilities.

Detection:
- Flag any class exceeding ~15 methods or ~300 LOC as a size outlier
- Check if methods belong to distinct domains (data access + business logic + formatting = split)
- Note: flag size outlier here; architectural compliance is a separate concern

---

## 10.4 Prompt Residue

Code left over from generation sessions:
- TODO/FIXME/PLACEHOLDER comments in production paths
- Generic docstrings with no real content ("This function handles the process")
- Template code that was never filled in
- Repeated boilerplate that should have been abstracted
- Variable names like "data", "result", "temp", "obj" with no context

---

## 10.5 Logic Duplication

Same functionality implemented differently in multiple modules:
- Similar function names doing the same thing
- Duplicate utility functions (date formatting, string sanitization, error wrapping)
- Same API call patterns copy-pasted across files
- Each AI generation session may re-implement what already exists

---

## 10.6 Copy-Paste Inheritance

Entire component skeletons cloned with minor variations instead of proper abstraction:
- Two or more classes with identical structure, differing only in one field or method
- Duplicated error handling blocks across similar handlers
- Repeated validation logic instead of a shared validator

Differs from logic duplication: here entire structural patterns are cloned.

---

## 10.7 Mixed Paradigms

Functional and OOP patterns coexist within the same module without coherent rationale.
Each AI generation session may pick whichever pattern matched the immediate prompt.

Symptoms:
- Classes that are actually just namespaced functions (no state, no polymorphism)
- Functional pipelines mixed with stateful class mutations in the same flow
- Inconsistent error handling: some paths throw, some return error objects, some use callbacks

---

## 10.8 Over-Engineering (Gas Factory)

Unnecessarily complex solutions using multiple design patterns for simple problems.
AI applies patterns from training data regardless of problem complexity.

Detection: count pattern layers vs actual requirements.
- Factory + Strategy + Observer for a single config loader = over-engineered
- Abstract base class with one concrete subclass and no planned extension = premature abstraction
- Dependency injection container for a 200-line script = unnecessary

---

## 10.9 Leaky Abstractions

Internal implementation details exposed through public interfaces.
AI generates interfaces from implementation rather than from contracts.

Symptoms:
- Public API surface reveals internal DB schemas or ORM models
- Response objects include internal type names or implementation-specific fields
- Interface parameters named after internal variables ("db_row", "raw_entity")
- Caller must know internal state to use the API correctly

---

## 10.10 Phantom Code

Functions, classes, or modules that are defined but never called from anywhere:
- Defined "for future use" and never wired up
- Generated as part of a pattern but the usage was never added
- Event handlers registered to events that are never emitted

Phantom code is not just dead code — it was intended to be used but the connection was never made.
This is distinct from commented-out code (Section 6) and TODO residue (10.4).

---

## 10.11 Vibe Coding Residue

Code that looks structurally correct but contains fundamentally wrong logic.
AI reproduces patterns from training data: correct names, correct docstring, wrong operations.

Detection:
- Function performs the semantic opposite of its name: `is_valid()` returns `not condition`
- Math functions (`average`, `median`) contain only one operation where multiple needed
- Pagination: `page * size` instead of `(page - 1) * size`
- Docstring describes behavior that contradicts the return statement
- Tests only cover happy path with trivial values (page=0, count=0)

Severity: CRITICAL in business logic (pricing, auth, permissions); WARNING in data processing; SUGGESTION in tested utilities.

---

## 10.12 Context Window Artifacts

AI copies patterns from another file in the same context into a module where they don't belong.

Detection:
- Imports from unrelated domain (`payments`, `stripe` in `auth` or `users` module)
- Exception classes don't match file's domain (`PaymentException` in `NotificationService`)
- Retry/backoff logic for operations with no network calls
- Identical `try/except` blocks in two files with different purposes
- Variables named from another domain: `card_token` in user management code

Severity: CRITICAL if wrong security checks; WARNING if wrong error handling; SUGGESTION if unused imports.

---

## 10.13 Confident Incorrectness

AI wraps a bug in professional-quality documentation: detailed docstring, full type hints, explaining comments — on code with a fundamental flaw.

Detection:
- High documentation density (docstring > 5 lines) + f-string in SQL query
- Detailed `Args:/Returns:/Raises:` + `HARDCODED_VALUE = "..."` in body
- Full type hints on a function doing raw string concatenation into queries
- Verbose error handling (`from e`) + no parameterized queries

Severity: CRITICAL if SQL injection or hardcoded credentials; WARNING if incorrect validation; SUGGESTION if doc/behavior mismatch only.

---

## 10.14 Specification Drift

Code implements the "statistically closest" interpretation, not the exact spec.
Main flow works, edge cases are approximate.

Detection:
- Time functions: `created_at` where logic needs `published_at` or `activated_at`
- Status fields: not all enum values handled explicitly (draft, published, archived)
- Discounts/pricing: `*=` without checking `is_already_discounted`
- Permissions: `if user.role == "admin"` without handling moderator, editor, etc.

Severity: CRITICAL in financial calculations and permissions; WARNING in API business rules; SUGGESTION in UI-only logic.

---

## 10.15 Sycophantic Code

Code does exactly what the prompt asked — nothing more. No input validation, no error handling, no null checks, no edge cases.

Detection:
- Functions accepting `list`/`dict` without `if not x` / `if x is None` checks
- API endpoints without `if not user` after DB query
- `sorted()`, `max()`, `min()` on potentially empty sequences without guard
- No `try/except` on network/DB operations
- Endpoint functions without auth decorator or `request.user` check

Severity: CRITICAL on public endpoints and payment/auth; WARNING on internal APIs; SUGGESTION on internal utilities.

---

## 10.16 Training Data Leakage

Tutorial/StackOverflow code inserted as-is without adaptation.

Detection (high-precision text markers):
- `example.com`, `test.com`, `localhost`, `127.0.0.1` in non-test files
- `your-api-key`, `INSERT_KEY_HERE`, `REPLACE_ME`
- `admin:password`, `root:root` in connection strings
- `John Doe`, `test@test.com` outside test fixtures
- `print(f"Response: ...")` in production functions (not CLI tools)

Severity: CRITICAL if hardcoded credentials/API keys; WARNING if hardcoded URLs in non-test; SUGGESTION if print debugging or TODOs.

---

## 10.17 Approximate Implementation

Implementation works for 90% of inputs but fails on edge cases.
AI found a "close enough" algorithm from training data.

Detection:
- `strptime` with single hardcoded format, no `ValueError` handling
- Email validation: `"@" in email` only
- `text[:n]` on string without Unicode/grapheme awareness
- Phone validation: only `len()` check
- Currency arithmetic with `float` instead of `Decimal`

Severity: CRITICAL in financial calculations and auth validation; WARNING in API input validation; SUGGESTION in internal single-format tools.

---

## 10.18 Stale Pattern Application

AI applies patterns from an outdated framework version popular in training data.

Detection:
- Python/Pydantic: `from pydantic import validator` (→ `field_validator`), `class Config:` (→ `model_config`), `orm_mode` (→ `from_attributes`)
- FastAPI: `@app.on_event("startup")` (→ `lifespan`)
- React: `class X extends React.Component` (→ functional + hooks)
- Django: `from django.conf.urls import url` (→ `path`)

Check framework version in `requirements.txt`/`pyproject.toml` before flagging.

Severity: CRITICAL if removed and causes runtime error; WARNING if deprecated with warnings; SUGGESTION if style-only.

---

## 10.19 Semantic Naming Mismatch

Functions named for the prompt context, not for what they actually do.

Detection (high-precision):
- `validate_*` contains only `return bool(x)` or `return x is not None`
- `sanitize_*` / `clean_*` contains only `.strip()` / `.lower()`
- `parse_*` contains only one library call without try/except
- `encrypt_*` contains `md5`, `sha1`, `sha256` (hash, not encryption)
- `secure_*` / `safe_*` without explicit security check

Severity: CRITICAL if `encrypt` = hash or `sanitize` = strip in security context; WARNING if `validate` = presence check in API; SUGGESTION otherwise.

---

## 10.20 Integration Point Amnesia

AI generates a module that works in isolation but ignores existing project infrastructure.

Detection:
- File contains `get_db_connection()` — check if project already has one
- `redis.Redis(host=...)`, `psycopg2.connect(...)` in non-infrastructure files
- `logging.getLogger(__name__)` everywhere instead of importing project logger
- No imports from `app.*`/`src.*` despite existing project modules
- Functions duplicating existing utilities: `send_email()`, `hash_password()`

Severity: CRITICAL if duplicating auth/secrets management; WARNING if bypassing connection pool or project logging; SUGGESTION if minor utility duplication.

