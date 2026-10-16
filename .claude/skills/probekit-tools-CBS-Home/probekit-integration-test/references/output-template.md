# Output Template — Integration Test Report

Build the final report in this exact structure.

---

## Report Header

Integration Test Report: [filename or module name]
Language/Framework: [detected stack]
Test Framework: [pytest / jest / go test / etc.]
DB Engine: [SQLite / PostgreSQL / etc.]
Date: [date if available]

---

## Test Plan Summary

List test cases generated:
- [test name] — [what it tests] — [layer: API/DB/Service/Contract]

Total planned: N tests across X files

---

## Generated Files

List every file created or modified:
- `tests/integration/test_users.py` — N tests (created)
- `tests/integration/conftest.py` — shared fixtures (created)

---

## Execution Results

| Test | Status | Notes |
|------|--------|-------|
| test_create_user_success | ✅ PASS | |
| test_create_user_duplicate | ✅ PASS | |
| test_get_user_not_found | ❌ FAIL | Source bug: returns 500 instead of 404 |
| test_db_fk_constraint | ✅ PASS | |

Pass: N / Total: N

---

## Findings

Present findings by severity using format from severity-format.md.

### Coverage Gaps
🔴 / 🟡 / 🟢 findings about untested paths.

### Source Bugs Discovered
If tests revealed actual bugs in production code — list here separately.
These are bonus findings: the tests did their job.

Format:
🔴 SOURCE BUG — [description]
Location: [file:line]
Found by: [test name]
Symptom: [what the test caught]
Recommended fix: [diff or description]

### Test Infrastructure Issues
Issues with fixtures, setup, missing dependencies.

---

## Coverage Summary

| Layer | Endpoints/Functions | Tested | Coverage |
|-------|--------------------|---------|----|
| API | N | N | HIGH/MEDIUM/LOW |
| DB | N | N | HIGH/MEDIUM/LOW |
| Service | N | N | HIGH/MEDIUM/LOW |
| Error paths | N | N | HIGH/MEDIUM/LOW |
| Contract | N | N | HIGH/MEDIUM/LOW |

Overall: HIGH / MEDIUM / LOW / NONE

---

## Final Score Block

---

Integration Test Score: X/10

Scoring guide:
- 9-10: All layers covered, all error paths, contracts verified, all tests passing
- 7-8: Good coverage, minor gaps in error paths or edge cases
- 5-6: Happy paths only, error paths missing, some layers untested
- 3-4: Partial coverage, critical paths untested
- 1-2: Minimal coverage, most of the system untested

🔴 CRITICAL gaps — must address:
- [item]

🟡 WARNING gaps — recommended:
- [item]

🟢 SUGGESTIONS — nice to have:
- [item]

---

## Totals Table

| Category | Count |
|----------|-------|
| Tests generated | N |
| ✅ Passing | N |
| ❌ Failing (blocked) | N |
| 🔴 CRITICAL findings | N |
| 🟡 WARNING findings | N |
| 🟢 SUGGESTION findings | N |
| 💎 DIAMOND findings | N |
| Source bugs discovered | N |

---

## Audit Tracker Update

> Format: see `probekit-core/references/audit-tracker-format.md` for table format, delta rules, and field definitions.

Append row with: skill=`integration-test`, key metric=`N pass / N total`.
