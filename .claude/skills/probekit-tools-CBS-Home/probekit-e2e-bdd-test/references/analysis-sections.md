# Analysis Sections

---

## Section 1 — Flow Extraction

Read the source code and extract testable user flows.

**For each flow identify:**
- Flow name (e.g. "User Registration", "Product Checkout", "Player Movement")
- Entry point: HTTP route / function call / UI interaction / game event
- Happy path: the success scenario
- Error paths: what can go wrong (invalid input, missing auth, DB failure, etc.)
- Edge cases: empty state, boundary values, concurrent access
- Pre-conditions: what must be true before the flow starts
- Post-conditions: what the system state should be after

**Priority order (highest risk first):**
1. Authentication and authorization flows
2. Data mutation flows (create, update, delete)
3. Payment / financial flows
4. State machine transitions
5. External integrations
6. Read / display flows

**For Godot/GUT projects:**
- Scene load and transition flows
- Player input → game state change flows
- Save/load game state flows
- UI interaction flows (menus, HUD, dialogs)

Output: a numbered list of flows with their entry points and risk level (HIGH / MEDIUM / LOW).
If no flows found: write "No testable flows identified — provide entry point files." and stop.

---

## Section 2 — Step Definition Patterns

When generating step definitions, follow these rules:

**Structure:**
- One step definition file per feature file (feature_name_steps.py / featureNameSteps.ts)
- Shared cross-feature steps → conftest.py or support/world.ts
- Page Object Model (POM) for all UI interactions

**POM rules:**
- One POM class per page or major component
- POM methods describe user actions, not UI mechanics
  GOOD: `login_page.login(username, password)`
  BAD: `login_page.find_element('#username').send_keys(username)`
- POM methods never contain assertions — assertions belong in step definitions
- POM stored in: tests/e2e/pages/ (Python) or tests/e2e/page-objects/ (JS/TS)

**Fixtures / Hooks:**
- @pytest.fixture or Before/After hooks for setup and teardown
- Always clean up after each scenario — no shared state between scenarios
- Seed test data via API calls or DB helpers, not via UI steps
- Use unique identifiers (timestamps, UUIDs) for test data to avoid conflicts

**Waiting strategy:**
- NEVER use time.sleep() or page.waitForTimeout() for synchronization
- Python/Playwright: use page.wait_for_selector(), expect(locator).to_be_visible()
- pytest-bdd: use retrying assertions with polling
- Godot/GUT: use await get_tree().create_timer(0.1).timeout only when no signal available

**Locator strategy (UI tests, priority order — best to worst):**
1. Test IDs: get_by_test_id('checkout-submit') / data-testid attribute — most stable, survives redesigns
2. ARIA roles: get_by_role('button', name='Submit') — very stable, accessibility-friendly
3. Labels: get_by_label('Email address') — stable for form elements
4. Text: get_by_text('Confirm order') — breaks on copy changes, use sparingly
5. CSS selectors: LAST RESORT — fragile, breaks on styling changes
6. XPath: NEVER — most brittle option

---

## Section 11 — Gherkin Quality Audit

Run in AUDIT mode. Analyze all .feature files found.

**Check for:**

**11.1 Procedural Gherkin (UI-coupled steps)**
Steps that describe implementation mechanics instead of user intent.
BAD: `When I click the green "Submit" button at coordinates (450, 200)`
GOOD: `When I submit the registration form`
BAD: `When I enter "test@email.com" in the input with id "email-field"`
GOOD: `When I provide my email address`
→ WARNING

**11.2 Scenarios as Test Scripts**
Scenario reads like a Selenium script — every click, every field, every assertion is explicit.
Symptoms: 10+ steps in one scenario, And chains longer than 3 items, step names contain CSS selectors or element IDs.
→ WARNING

**11.3 Missing Assertions**
Scenario ends with no Then step, or Then step has no verifiable outcome ("Then the page loads").
A scenario without a meaningful assertion is not a test.
→ CRITICAL

**11.4 Scenario Bloat**
Single feature file with 20+ scenarios covering unrelated behaviors.
Each feature file should cover one user-facing capability.
→ WARNING

**11.5 Copy-Paste Scenarios**
Two or more scenarios with identical Given/When blocks, only Then differs.
Should be merged into a Scenario Outline with an Examples table.
→ SUGGESTION

**11.6 Missing Background**
Multiple scenarios in the same feature repeat identical Given steps.
Extract into a Background block.
→ SUGGESTION

**11.7 Vague Steps**
Steps with no parameters where parameters are needed:
BAD: `Given I am logged in`  (which user? which role?)
GOOD: `Given I am logged in as "admin"`
→ WARNING

**11.8 Hardcoded Test Data in Gherkin**
Real emails, passwords, production IDs, or PII in feature files.
→ CRITICAL (security) if credentials, WARNING otherwise

**11.9 Missing Tags**
No @smoke, @regression, or grouping tags.
Without tags, entire suite must run for any single change.
→ SUGGESTION

**11.10 Inconsistent Language**
Mix of languages in one feature file, or steps written from different perspectives
(sometimes "I", sometimes "the user", sometimes "the system").
→ SUGGESTION

---

## Section 12 — Coverage Gap Analysis

Map existing scenarios to identified application flows.

**For each flow from Section 1, check:**
- Is there at least one happy path scenario? If not → WARNING
- Is there at least one error path scenario for critical flows? If not → WARNING
- Auth flows: is there a scenario for unauthorized access attempt? If not → CRITICAL
- Data mutation flows: is there a rollback/failure scenario? If not → WARNING
- Are edge cases covered (empty input, boundary values)? If not → SUGGESTION

**Test pyramid check:**
- Count E2E scenarios vs unit test files vs integration test files (if visible)
- Flag if E2E count >> unit tests: "Ice cream cone anti-pattern suspected" → WARNING
- E2E tests should cover user journeys, not every edge case (that's unit test territory)

**Output format:**
Flow name | Happy Path | Error Path | Edge Cases | Status
---------|------------|------------|------------|-------
User Login | ✅ | ✅ | ❌ | PARTIAL
Product Search | ✅ | ❌ | ❌ | PARTIAL
Admin Delete | ❌ | ❌ | ❌ | MISSING

---

## Section 13 — Step Definition Code Quality

Analyze step definition files (.py, .ts, .js).

**Check for:**

**13.1 Hardcoded Waits**
time.sleep(N), page.waitForTimeout(N), asyncio.sleep(N) used for synchronization.
These are the #1 cause of flaky E2E tests.
→ WARNING minimum; CRITICAL if N > 5 seconds

**13.2 Missing Teardown**
Scenarios create data (users, records, files) but no cleanup after test.
Causes test pollution — tests pass in isolation, fail in suite.
→ WARNING

**13.3 Assertions in POM**
POM class methods contain assert/expect calls.
POM should only encapsulate interactions; assertions belong in step definitions.
→ WARNING

**13.4 Brittle Locators**
CSS selectors using auto-generated class names (.css-a8f7d3), positional selectors (nth-child),
or XPath with absolute paths.
→ WARNING

**13.5 God Step File**
Single step definition file with 100+ step functions covering multiple unrelated features.
→ WARNING

**13.6 Duplicate Step Definitions**
Same Gherkin step pattern implemented in multiple files, or two slightly different patterns
doing the same thing ("I am logged in" vs "I have logged in").
→ WARNING

**13.7 No Error Context on Failure**
Assertions fail with generic messages ("AssertionError") with no context about what was expected.
→ SUGGESTION

**13.8 Global Mutable State**
Step definitions share state via module-level globals instead of fixtures or World object.
→ WARNING (flakiness risk in parallel runs)

**13.9 UI Steps for Data Setup**
Test data created by navigating the UI (fill forms, click create) instead of API/DB calls.
Slow, fragile, inflates test duration.
→ WARNING

**13.10 Missing Page Object Model**
Step definitions interact with UI elements directly (selectors, clicks, fills) without a POM layer.
All UI interactions must go through POM classes — direct selector use in step definitions is a structural anti-pattern.
Detection: step definition files that import page/browser directly and call `.fill()`, `.click()`, `.locator()` inline rather than through a page object.
→ WARNING

**13.11 Tautological Step Implementation**
Step definition body contains no assertion — the step name implies a check but the implementation does nothing verifiable (empty body, bare `pass`, or only a navigation without assertion).
Distinct from 11.3 (Gherkin level): this is the step definition that implements a Then step but skips the actual check.
Detection: Then-decorated functions with no `assert`, `expect()`, or equivalent assertion call.
→ WARNING minimum; CRITICAL if the step is the only Then in its scenario
