---
name: analysis-sections-test-audit
description: "Section 12 — Test Quality Audit: coverage gaps, test effectiveness, isolation, flakiness, design quality, maintenance debt, and test architecture."
---

# Section 12 — Test Quality Audit

Run whenever test files are detected. If test_audit_mode = true, give expanded treatment.
If no test files found: write "No test files detected." and close section.

This section evaluates whether existing tests actually protect the codebase —
not just whether they exist or whether coverage numbers look good.

**12.1 — Coverage Gaps**
- Identify critical paths in production code that have zero test coverage
- Flag: public API methods with no corresponding test
- Flag: error handling branches that are never exercised
- Flag: boundary conditions never tested (empty input, zero, max values, None/null)
- Do not require 100% coverage — flag gaps on high-risk paths only
- Note: coverage percentage alone is meaningless; a test that asserts nothing can cover 100%

**12.2 — Test Effectiveness (Are Tests Actually Testing Anything?)**

The most critical subsection. A passing test suite with bad tests provides false confidence.

- Assert-free tests: test function that runs code but has no assertions
  → WARNING: test passes no matter what the code does, provides false confidence
- Trivial assertions: `assert result is not None`, `assert len(result) > 0`
  with no check of actual values — verifies existence, not correctness
- Testing implementation details instead of behavior:
  tests that break on every refactor even if behavior is unchanged
  (e.g., asserting internal method was called instead of asserting output)
- Tautological tests: `assert x == x`, comparing a value to itself
- Mocking the system under test: mocking the very function being tested
  means the test never exercises real code
- Happy path only: no error path, no edge case, no boundary tested
  → tests document that code works when everything is fine; silent on failure modes
- Secret catchers: test with no assertions relying on implicit exception catch —
  passes even when the function does the wrong thing silently
- **AI Test Tautology:** AI writes function → AI writes test → test verifies
  implementation matches implementation, not business intent. Signals:
  - Test mirrors the function logic step-by-step (same conditions, same branches)
  - Test was generated in the same session as the implementation (check git timestamps)
  - Test has no edge cases from production experience (idempotency, race conditions,
    vendor API quirks, timezone issues, currency rounding)
  - Test asserts internal data shapes rather than business outcomes
  - Bulk test updates: AI changed behavior → AI updated 10+ tests to match new behavior
    (question: were all those test changes intentional or did AI just make tests pass?)
  - Test uses exact same mock data patterns as the implementation's defaults
    → test is a mirror, not a contract

**12.3 — Test Isolation and Reliability**

- Test interdependence: test B fails when test A hasn't run first
  (shared mutable state, database rows, files left on disk)
- Generous leftovers: one test creates data, another test depends on it implicitly
- Global state pollution: tests modify module-level variables or singletons without cleanup
- Missing fixture teardown: files, DB rows, network connections opened but not closed
- Hard-coded environment assumptions: absolute paths, specific ports, env vars only on dev machine
- Time-dependent tests: assertions against `datetime.now()` or similar without pinning
- Non-deterministic data: random inputs or UUIDs used in assertions without seeding

**12.4 — Flakiness Indicators**

Flaky tests erode trust in the entire test suite.

- `time.sleep()` or explicit waits used to synchronize async operations
  → brittle: works on developer machine, fails under load or slow CI
- Assertions on floating point equality without tolerance (`pytest.approx()`)
- Race conditions in tests that share state across concurrent operations
- Tests sensitive to execution order (no `pytest-randomly` guard)
- Tests that retry on failure instead of fixing root cause (masked flakiness)
- Hardcoded dates that will fail after a certain date

**12.5 — Test Design Quality**

- God tests: one test function testing multiple unrelated behaviors
  (name contains "and", or has 20+ assertions across unrelated outcomes)
- Excessive setup (Mother Hen): hundreds of lines of setup for one assertion
  → usually signals the code under test is untestable and needs decomposition
- Copy-paste tests: identical test bodies differing only in one value
  → should be parameterized (`@pytest.mark.parametrize`, `test.each`, table-driven)
- Enumerator naming: tests named test1, test2, test3 or test_thing_1, test_thing_2
  → test names are documentation; anonymous tests are useless after a failure
- Free-ride assertions: unrelated assertions piggybacking in one test
  → when test fails, unclear which behavior broke
- Testing framework code: tests that assert language behavior rather than application behavior
  (`assert [] == []`, `assert True`)

**12.6 — Test Maintenance Debt**

- Skipped/xfail tests with no explanation or tracking issue
  → silent dead weight; skips accumulate and are never revisited
- Commented-out tests: indicate known failures that were silenced instead of fixed
- Tests for deleted code: test file imports a module that no longer exists
- Duplicate test scenarios: same behavior tested multiple times with different names
- Missing regression tests: if a bug was fixed, was a test added to prevent recurrence?

**12.7 — Test Architecture (for larger suites)**

Only flag if the test suite has 20+ test files or 200+ test functions.

- Inverted pyramid: 90%+ unit tests with no integration or acceptance tests
  → mocked behaviors never verified against real dependencies
- Testing only via UI or E2E with no unit/integration layer
  → slow, fragile, impossible to diagnose on failure
- No test categorization: fast unit tests mixed with slow integration tests
  → slow feedback loop, developers skip running tests locally
- Missing contract tests: services calling each other with no verification that
  the caller's assumptions match what the callee actually returns

Severity escalation for Section 12:
- Assert-free test → WARNING (silently passes always)
- Test with only trivial assertions on critical path → WARNING
- Flaky test (sleep-based, time-dependent) → WARNING
- Skipped test with no reason → SUGGESTION
- Copy-paste tests that should be parameterized → SUGGESTION
- God test → SUGGESTION
- Missing regression test for known bug → WARNING
- AI test tautology (test mirrors implementation, no production edge cases) → WARNING
- Bulk AI test update (10+ tests changed to match new behavior in one commit) → CRITICAL
