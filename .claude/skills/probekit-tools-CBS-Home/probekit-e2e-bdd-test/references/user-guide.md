# e2e-bdd — User Guide

E2E and BDD test generation for Claude Code.
Two modes: GENERATE (write tests from source) and AUDIT (review existing tests).

---

## Installation

### Option A — Project-level

your-repo/
  .claude/
    skills/
      e2e-bdd/
        SKILL.md
        references/

### Option B — Global

~/.claude/skills/e2e-bdd/

### Install from GitHub

cd ~/.claude/skills
git clone https://github.com/YOUR_ORG/e2e-bdd

---

## Invocation

### Slash command

/e2e-bdd src/api/
/e2e-bdd src/auth/login.py
/e2e-bdd tests/e2e/ --audit
/e2e-bdd .

### Auto-trigger keywords

"write e2e tests for..."
"create bdd scenarios for..."
"generate feature files for..."
"audit my feature files"
"find issues in my tests"

---

## Usage Examples

### Generate E2E tests for a module

/e2e-bdd src/api/users.py

Claude reads the module, identifies user flows, generates:
- tests/e2e/features/users.feature
- tests/e2e/steps/users_steps.py
- tests/e2e/pages/ (if UI)
Runs tests, fixes failures, reports results.

### Generate tests with security focus

/e2e-bdd src/api/ -- focus on authorization and missing auth checks

Runs all sections but applies extra attention to auth flows.

### Audit existing feature files

/e2e-bdd tests/e2e/ --audit

Audits all .feature files and step definitions for:
- Gherkin quality (procedural steps, missing assertions, vague steps)
- Coverage gaps (missing error paths, uncovered flows)
- Step definition quality (hardcoded waits, brittle selectors, shared state)

### Generate for full project

/e2e-bdd .

Scans entire project, identifies all major user flows, generates comprehensive feature files.
Saves report automatically for large inputs.

### Audit + fix

/e2e-bdd tests/e2e/ --audit --fix

Runs audit, then auto-fixes WARNING and CRITICAL structural findings where possible.
SUGGESTION-level issues are reported but not auto-fixed.
Exception: findings 11.3 (Missing Assertions) and 11.7 (Vague Steps) are flagged for manual review — they touch behavioral intent and cannot be safely auto-corrected.

---

## Framework Selection

The skill auto-detects the framework from your project:

| Detected | Framework Used |
|----------|---------------|
| pytest in requirements/pyproject | pytest-bdd + Playwright |
| behave in requirements | behave |
| package.json with playwright | Playwright + Cucumber |
| package.json with cypress | Cypress |
| project.godot present | GUT (GDScript tests) |
| none detected | asks user to confirm |

---

## Output Structure

Generated tests land in `test_output_dir` (default: tests/e2e/):

```
tests/e2e/
  features/
    auth.feature
    user_management.feature
  steps/
    auth_steps.py
    user_management_steps.py
  pages/
    login_page.py
    dashboard_page.py
  conftest.py
```

Reports saved to `report_dir` (default: docs/01_refer/ARCHIVES/CODE-AUDIT/PROBKIT-REVIEW/).

---

## What the Skill Checks (Audit Mode)

### Section 11 — Gherkin Quality
- Procedural vs declarative steps
- Missing assertions (Then with no verifiable outcome)
- Scenario bloat and copy-paste
- Hardcoded test data / credentials
- Missing tags

### Section 12 — Coverage Gaps
- Flows with no happy path scenario
- Auth flows with no unauthorized access test
- Missing error paths on mutation flows
- Ice cream cone pattern (too many E2E, too few unit tests)

### Section 13 — Step Definition Quality
- Hardcoded waits (time.sleep, waitForTimeout) — #1 cause of flaky tests
- Missing teardown / state pollution between scenarios
- Assertions in POM classes (POM = interactions only)
- Brittle locators (XPath, generated CSS classes, positional selectors)
- Global mutable state (breaks parallel runs)
- God step file (100+ functions in one file covering unrelated features)
- Duplicate step definitions (same pattern implemented in multiple files)
- No error context on assertion failure (generic AssertionError messages)
- UI steps for data setup (should use API/DB instead)
- Missing Page Object Model (direct selector calls in step definitions)
- Tautological step implementation (Then-decorated function with no assertion)

---

## Severity Legend

🔴 CRITICAL — blocks reliable testing (missing assertion, exposed secret, auth gap)
🟡 WARNING — causes flakiness or maintenance pain (hardcoded wait, no teardown)
🟢 SUGGESTION — improvement opportunity (missing tags, copy-paste consolidation)

---

## Notes

- The skill never modifies Gherkin files during the fix loop — Gherkin is the contract.
  Only step definitions and POM are modified to make tests pass.
- Real application bugs discovered during test runs are documented, not hidden.
- Godot/GUT projects: GUT test scripts are generated instead of .feature files,
  with Given/When/Then intent expressed as comments and method names.
- For very large projects (50+ routes): provide a subdirectory path for focused generation.
- Always reads ENVIRONMENT.md if present for shell/tool pitfalls before running commands.
