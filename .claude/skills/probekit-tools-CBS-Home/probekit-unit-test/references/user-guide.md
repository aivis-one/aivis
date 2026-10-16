# unit-test — User Guide

Generates, runs, and verifies unit tests for any module or function.
Produces working tests — not templates — with mocks, fixtures, and coverage report.

---

## Installation

### Option A — Project-level

your-repo/
  .claude/
    skills/
      unit-test/
        SKILL.md
        references/

### Option B — Global

~/.claude/skills/unit-test/

### Install from GitHub

cd ~/.claude/skills
git clone https://github.com/YOUR_ORG/unit-test

---

## Invocation

### Slash command

/unit-test src/services/user_service.py
/unit-test src/services/
/unit-test .

### Auto-trigger keywords

"write tests for this"
"напиши тесты для"
"покрой тестами"
"generate tests"
"add unit tests"

---

## Usage Examples

### Test a single file

/unit-test src/api/users.py

### Test entire directory

/unit-test src/services/

### Test with focus hint

/unit-test src/core/ -- focus on error paths and edge cases

### Audit existing test quality (no generation)

/unit-test tests/ --audit
"проверь тесты"
"проверь качество тестов"
"оцени тесты"
"оцени мои тесты"

### Coverage report only (no generation)

/unit-test src/ --coverage-only

### Test pasted code

Paste code, then write "напиши тесты" — skill activates.

---

## What the Skill Does

**Generate + Run mode (default):**
1. Detects framework from project files
2. Maps public API, dependencies, boundaries
3. Generates test file(s) with AAA structure
4. Runs tests via detected framework command
5. Iterates on failures (max 3 attempts per test)
6. Reports coverage + any unresolved failures

**Audit mode (--audit):**
1. Reads all existing test files
2. Checks for 11 anti-patterns (AP-01 through AP-11)
3. Scores test suite quality 1-10
4. Produces actionable findings with before/after diffs

**Coverage-only mode:**
1. Runs existing tests
2. Reports coverage per file
3. Flags files below 60% with specific uncovered paths

---

## Framework Support

| Language | Framework | Auto-detected via |
|----------|-----------|-------------------|
| Python | pytest | pytest.ini, pyproject.toml |
| GDScript | GUT 9.x | addons/gut/ directory |
| JavaScript | Jest | package.json (jest) |
| TypeScript | Jest/Vitest | package.json |
| Go | testing | go.mod |

---

## Output Format

**Each generated test:**
- AAA structure with comments
- Descriptive name: `test_{function}_{scenario}_{outcome}`
- Mocks for all external boundaries
- Happy path + edge cases + error paths

**Report sections:**
- Generated files list with coverage targets
- Run results: passed / failed / needs review
- Coverage table per file
- Audit findings (audit mode) with severity markers

---

## Test Naming Convention

`test_{function}_{scenario}_{expected_outcome}`

Examples:
- `test_calculate_price_with_zero_quantity_raises_value_error`
- `test_user_login_with_expired_token_returns_401`
- `test_parse_date_with_empty_string_raises_value_error`
- `test_add_item_to_cart_updates_total_correctly`

---

## Coverage Philosophy

Quality over quantity. The skill does NOT chase 100%.

Priority order:
1. Critical business logic paths
2. Error handling paths
3. Boundary conditions
4. Happy paths

The skill flags files below 60% as needing attention.
It does NOT generate tests for: trivial getters/setters, `__repr__`/`__str__`
with no logic, auto-generated boilerplate, private methods.

---

## Notes

- The skill never modifies source code to make tests pass — only test code is fixed.
- If a test cannot be made to pass after 3 attempts, it is flagged as NEEDS REVIEW
  with a detailed explanation of the issue.
- GUT tests cannot be run headlessly unless Godot binary is in PATH.
  If Godot is not available in the shell, tests are generated but not run;
  the report notes this and provides the run command.
- For Pydantic models: special patterns handle `is not None` vs truthiness
  and `extra="forbid"` validation.
- For SQLite: always uses in-memory DB in tests, never touches production files.
