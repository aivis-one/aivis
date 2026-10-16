# Output Template

Build the final report in this exact structure.

---

## Report Header

Unit Test Report: [filename or module name]
Language/Framework: [detected stack]
Mode: [Generate + Run | Audit | Coverage Only]
Date: [YYYYMMDD]

---

## Environment Summary

Framework: [pytest 9.x / GUT 9.6.0 / Jest / Go testing]
Shell: [detected from ENVIRONMENT.md or auto-detected]
Test output dir: [path where test files were written]

---

## Generated Tests (Generate mode only)

List each test file created:

📄 tests/unit/test_{module}.py
  - [N] tests generated
  - Functions covered: [list]
  - Patterns used: parametrize, fixtures, mocks (list what was used)

---

## Run Results (Generate + Run mode)

✅ PASSED: N
❌ FAILED: N
⚠️ NEEDS REVIEW: N (failed after 3 attempts)

For each FAILED or NEEDS REVIEW:

❌ test_function_name_scenario
   Error: [exception or assertion message]
   Fix applied: [what was changed in iteration N]
   Status: [resolved | needs review]

---

## Coverage Report

Overall coverage: N%

| File | Coverage | Status |
|------|----------|--------|
| src/module.py | 87% | ✅ |
| src/service.py | 45% | ⚠️ LOW |

Uncovered critical paths (candidates for additional tests):
- [file:line — function name — reason it matters]

---

## Audit Findings (Audit mode only)

Present findings using severity markers. Same format as code-audit:

🔴 CRITICAL — [anti-pattern name]
Location: [test_file.py:line or test function name]

// BEFORE:
[bad test code]

// AFTER:
[corrected test code]

Explanation: [why this anti-pattern is dangerous and what the fix achieves]

---

## Test Suite Score (Audit mode only)

Score: X/10

🔴 CRITICAL issues:
- [list]

🟡 WARNING issues:
- [list]

🟢 SUGGESTIONS:
- [list]

---

## Totals Table — Generate + Run mode

| Metric | Value |
|--------|-------|
| Tests generated | N |
| Tests passing | N |
| Tests failing | N |
| Coverage | N% |
| Files with low coverage (<60%) | N |

---

## Totals Table — Audit mode

| Severity | Count |
|----------|-------|
| 🔴 CRITICAL | N |
| 🟡 WARNING | N |
| 🟢 SUGGESTION | N |
| 💎 DIAMOND | N |
| **Total** | **N** |

---

## Report Destination

Always save report to: `{{report_dir}}/UNIT-TEST-<target>-<YYYYMMDD>.md`
- target = module name or directory name
After saving, output brief summary in chat: tests count, pass/fail, coverage %, path to report.

---

## Audit Tracker Update

> Format: see `probekit-core/references/audit-tracker-format.md` for table format, delta rules, and field definitions.

Append row with: skill=`unit-test`, key metric=`N tests, X% coverage`.
