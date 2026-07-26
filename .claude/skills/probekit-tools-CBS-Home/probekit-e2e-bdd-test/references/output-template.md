# Output Template

Build the final report in this exact structure.

---

## Report Header

E2E/BDD Report: [filename, directory, or "Generated Tests"]
Mode: [GENERATE | AUDIT]
Framework: [detected framework]
Language: [detected language]
Reviewed: [date]

---

## GENERATE Mode Output

### Generated Files

List every file created:
- tests/e2e/features/auth.feature — 4 scenarios
- tests/e2e/features/user_registration.feature — 6 scenarios
- tests/e2e/steps/auth_steps.py
- tests/e2e/pages/login_page.py
- tests/e2e/conftest.py

### Test Run Results

| Status | Count |
|--------|-------|
| ✅ Passed | N |
| ❌ Failed | N |
| 🚫 Blocked | N |
| Total | N |

For each FAILED or BLOCKED test:
- Scenario name
- Error message (trimmed)
- Diagnosis (timing / state pollution / real bug / environment)
- Fix applied (or "BLOCKED: reason")

### Coverage Map

| Flow | Happy Path | Error Path | Edge Cases | Status |
|------|-----------|------------|------------|--------|
| User Login | ✅ | ✅ | ❌ | PARTIAL |
| Product Search | ✅ | ❌ | ❌ | PARTIAL |

---

## AUDIT Mode Output

Present findings by section with severity markers.

🔴 CRITICAL — [description]
Location: [file:line or scenario name]

// BEFORE:
[problematic Gherkin or code]

// AFTER:
[corrected version]

Explanation: [one to two sentences on impact and fix]

Use same format for 🟡 WARNING and 🟢 SUGGESTION.

---

## Final Score Block

---

Final Score: X/10

Scale:
- 9-10: Production-quality test suite
- 7-8: Good coverage, minor issues
- 5-6: Functional but significant gaps or anti-patterns
- 3-4: Major problems — flaky, incomplete, or unmaintainable
- 1-2: Must be rewritten

🔴 CRITICAL — must fix:
- [item]

🟡 WARNING — should fix:
- [item]

🟢 SUGGESTION — nice to have:
- [item]

---

## Totals Table

| Severity | Count |
|----------|-------|
| 🔴 CRITICAL | N |
| 🟡 WARNING | N |
| 🟢 SUGGESTION | N |
| 💎 DIAMOND | N |
| **Total** | **N** |

---

## AUDIT+FIX Mode Output

Use this section when `--audit --fix` was invoked.
After the standard AUDIT Mode Output, append:

### Fixes Applied

| Finding | Location | Action |
|---------|----------|--------|
| 11.5 Copy-Paste Scenarios | auth.feature:34 | Merged into Scenario Outline |
| 13.1 Hardcoded Wait | auth_steps.py:22 | Replaced sleep(3) with wait_for_selector |
| 13.10 Missing POM | login_steps.py | Extracted LoginPage class |

Manually review required (not auto-fixed):
- 11.3 Missing Assertions — [location]: [description of what needs a Then step]
- 11.7 Vague Steps — [location]: [step that needs parameterization]

### Post-Fix Verification

Re-ran Sections 11, 12, 13 on modified files.

| Severity | Before | After | Delta |
|----------|--------|-------|-------|
| 🔴 CRITICAL | N | N | ±N |
| 🟡 WARNING | N | N | ±N |
| 🟢 SUGGESTION | N | N | ±N |

Remaining issues: [list or "None"]

---

Report file name: `E2E-TEST-<target>-<YYYYMMDD>.md`

Save to: {{report_dir}} from SKILL.md Configuration.

---

## Audit Tracker Update

> Format: see `probekit-core/references/audit-tracker-format.md` for table format, delta rules, and field definitions.

Append row with: skill=`e2e-bdd-test`, key metric=`N scenarios pass/total`.
