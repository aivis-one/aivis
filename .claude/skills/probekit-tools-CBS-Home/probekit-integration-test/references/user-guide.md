# integration-test — User Guide

Generates, runs, and verifies integration tests for API layers, DB layers,
and service boundaries. Produces real passing test files + a scored coverage report.

---

## Installation

### Option A — Project-level

your-repo/
  .claude/
    skills/
      integration-test/
        SKILL.md
        references/

### Option B — Global

~/.claude/skills/integration-test/

### Install from GitHub

cd ~/.claude/skills
git clone https://github.com/YOUR_ORG/integration-test

---

## Invocation

### Slash command

/integration-test src/api/users.py
/integration-test src/services/
/integration-test src/db/repository.py src/api/routes.py

### Auto-trigger phrases

"write integration tests for users.py"
"test my API layer"
"generate tests for the database layer"
"integration tests for services/"
"test the repository"

---

## Usage Examples

### Test a single API file

/integration-test src/api/users.py

Generates: tests/integration/test_users.py + conftest.py if missing
Runs: pytest tests/integration/test_users.py
Reports: pass/fail + coverage + findings

### Test an entire service directory

/integration-test src/services/

Analyses all modules, generates test suite, runs all, reports.

### Test multiple files (cross-module)

/integration-test src/db/repository.py src/api/routes.py

Generates tests for both layers + contract tests verifying they agree.

### Run with focus hint

/integration-test src/api/ -- focus on error paths

Generates extra error-path and edge-case tests beyond the default set.

### Run existing tests only (no generation)

/integration-test --run-only

Runs existing tests in tests/integration/, reports results, no new files.

### Generate and auto-fix failures

/integration-test src/api/users.py --fix

After generation: iterates on failing tests up to 3 times each.
Note: fixes the test code, not the source code.

---

## What Gets Tested

### API Layer
- Every route handler: success response shape, status codes
- Request validation: missing fields, wrong types, bad values
- Not-found cases: 404 responses
- Conflict cases: duplicate data, constraint violations
- Contract compliance: required fields present, internal fields absent

### Database Layer
- CRUD operations against real DB (in-memory SQLite or temp file)
- Constraint enforcement: UNIQUE, NOT NULL, FOREIGN KEY
- Transaction behaviour: rollback on failure
- Query correctness: returns expected rows, filters work

### Service Layer
- Business logic with mocked external dependencies
- DB state after service calls (verify via direct DB query)
- Failure paths: external service down, invalid input, DB error

### Cross-Module Contract
- API response fields match what DB/service layer provides
- No internal DB schema leaked through API
- Error response shape is consistent

---

## Output

Each run produces:
1. Generated test files in `tests/integration/` (or detected test dir)
2. Integration test report in `docs/01_refer/ARCHIVES/CODE-AUDIT/PROBKIT-REVIEW/`
3. Updated `INTEGRATION-TEST-TRACKER.md`

---

## Environment Handling

The skill auto-detects:
- Language and test framework
- DB engine and connection pattern
- Shell type (PowerShell / bash) — affects test command syntax
- Existing test infrastructure (reuses, never duplicates)

If ENVIRONMENT.md is present in the project — reads it for shell/tool pitfalls first.

---

## Notes

- Tests use isolated DB (in-memory or temp file) — never touches production data
- External dependencies (Stripe, email, OAuth) are mocked automatically
- If Docker or external services are required: flagged and user is asked, not auto-started
- SQLite projects: uses SQLite directly, no additional setup needed
- Source bugs found during test runs are reported as bonus findings
- Skill never invents passing tests — if it passes, it actually ran and passed
