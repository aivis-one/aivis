# Test Anti-Patterns

Used in audit mode (--audit) and as a quality check on generated tests.
Every finding maps to a severity level. Apply markers from severity-format.md.

---

## AP-01: Happy Path Only

**Symptom:** Test suite covers only successful scenarios. No tests for empty input,
None/null, boundaries, exceptions, or error states.

**Detection:** Scan all test files. If a function has tests but none test
negative inputs, empty collections, None/null, or expected errors — flag it.

**Severity:** 🟡 WARNING

**Why it matters:** Most production bugs happen at boundaries and error paths.
A 100% passing suite that only tests happy paths gives false security.

**Fix direction:** Add parametrized edge cases. For each tested function, add:
- Empty input test
- None/null input test
- Boundary value test (zero, negative, max)
- Expected exception test

---

## AP-02: Assertion-Free Test (Tautology)

**Symptom:** Test function contains no assertions, or asserts only that no exception
was raised (`assert True`, empty function body, only `pass`).

**Detection by language:**
- Python: no `assert` statement and no `pytest.raises` / `assertRaises` context
- GDScript: no `assert_*` call anywhere in the test function
- Go: no `t.Error`, `t.Errorf`, `t.Fatal`, or `t.Fatalf` call
- JS/TS: no `expect(...)` call

**Severity:** 🔴 CRITICAL

**Why it matters:** These tests always pass and catch nothing.
They provide false coverage numbers while protecting against zero regressions.

```python
# Bad — assertion-free
def test_create_user():
    user = create_user("Alice", "alice@example.com")
    # No assertion — always passes, catches nothing

# Good
def test_create_user_sets_correct_name():
    user = create_user("Alice", "alice@example.com")
    assert user.name == "Alice"
    assert user.email == "alice@example.com"
    assert user.is_active is True
```

---

## AP-03: Structural Inspection (Testing Implementation Details)

**Symptom:** Test verifies HOW the code works internally rather than WHAT it returns.
Signs: patching private methods, asserting mock call order, checking internal attribute names.

**Detection:** Tests that:
- Access private attributes (`_internal`, `__private`) directly
- Assert that specific internal methods were called a specific number of times
  when that count is an implementation detail, not a contract
- Would break on any refactor even if observable behavior is unchanged

**Severity:** 🟡 WARNING

**Why it matters:** Couples tests to implementation. Any refactor breaks tests
even when the feature is working correctly.

```python
# Bad — structural inspection
def test_user_service_calls_repo_twice():
    service = UserService(mock_repo)
    service.get_with_fallback(user_id=1)
    assert mock_repo.find.call_count == 2  # implementation detail

# Good — behavior verification
def test_user_service_returns_fallback_when_primary_missing():
    mock_repo.find.side_effect = [None, User(name="fallback")]
    result = service.get_with_fallback(user_id=1)
    assert result.name == "fallback"
```

---

## AP-04: Conjoined Twins (Test Interdependency)

**Symptom:** Tests depend on execution order. Test B uses state left by Test A.
If tests are shuffled or run in isolation, some fail.

**Detection:**
- Module-level mutable variables modified in tests without teardown
- DB or file state shared across tests without fixture cleanup
- Tests that explicitly call other test functions

**Severity:** 🔴 CRITICAL

**Why it matters:** Order-dependent tests are a time bomb. They pass locally,
fail in CI, and produce random failures that waste hours of debugging.

**Fix direction:** Use fixtures with `yield` for teardown. Use in-memory DBs
per-test. Reset all shared state in `before_each` / `setUp`.

---

## AP-05: Giant Test

**Symptom:** One test function tests multiple scenarios, multiple functions, or multiple
expected outcomes sequentially. Usually 30+ lines, multiple Act+Assert blocks.

**Detection:** Test functions > 30 lines OR containing 3+ separate assert blocks
that test different aspects of different operations.

**Severity:** 🟡 WARNING

**Why it matters:** When it fails, it's unclear which scenario failed.

```python
# Bad — giant test
def test_user_lifecycle():
    user = create_user("Alice", "alice@example.com")
    assert user.name == "Alice"
    update_user(user, name="Bob")
    assert user.name == "Bob"
    delete_user(user)
    assert not user_exists(user.id)

# Good — split into focused tests
def test_create_user_returns_correct_name(): ...
def test_update_user_name_changes_stored_name(): ...
def test_delete_user_removes_from_storage(): ...
```

---

## AP-06: Coverage Chasing (Trivial Tests)

**Symptom:** Tests exist only to raise coverage %. They test trivial property access,
auto-generated getters/setters, `__repr__`, or `__str__` with no business logic.

**Detection:** Tests where the entire body sets a field and asserts it was set.
Tests for dunder methods with no logic.

**Severity:** 🟢 SUGGESTION

**Why it matters:** Wastes time. Inflates coverage with zero regression protection.

---

## AP-07: Mocking Own Code (Over-mocking)

**Symptom:** Mocking classes and functions that belong to your own codebase,
not external dependencies. Testing mocks instead of real code.

**Detection:**
- Patching internal application classes (not external libraries or I/O)
- Mock chains deeper than 2 levels: `mock.return_value.method.return_value = ...`

**Severity:** 🟡 WARNING

**Rule:** Mock at the boundary with the outside world. Use real internal objects.

---

## AP-08: Non-Deterministic Test (Flaky)

**Symptom:** Test outcome depends on: current time, random number, network state,
file system contents, process execution order, sleep/delay timing.

**Detection by language:**
- Python: `datetime.now()` / `time.time()` / `random.*` in test or SUT without mock;
  `time.sleep()` in test body; network calls without patching
- GDScript: `Time.get_unix_time_from_system()` without stub; `OS.delay_msec()` in test
- Go: `time.Now()` in tested function without injection; `time.Sleep()` in test

**Severity:** 🔴 CRITICAL

**Why it matters:** Flaky tests destroy trust in the entire suite.

```python
# Bad — time-dependent
def test_token_not_expired():
    token = create_token(expires_in=3600)
    assert not token.is_expired()  # Will fail in exactly 1 hour

# Good — time is controlled
def test_token_not_expired(monkeypatch):
    fixed_time = datetime(2026, 1, 1, 12, 0, 0)
    monkeypatch.setattr("myapp.auth.datetime", lambda: fixed_time)
    token = create_token(expires_in=3600)
    assert not token.is_expired()
```

---

## AP-09: Missing Error Path Tests

**Symptom:** Source code raises or returns errors in documented cases,
but no tests verify these error conditions.

**Detection by language:**
- Python: source has `raise SomeError(...)` with no corresponding `pytest.raises` in tests
- GDScript: source has `push_error(...)` or returns error enum values;
  no test calls the function with bad input and checks `assert_eq` on the error result
- Go: source returns `error` type; no test checks `if err != nil` result with wrong inputs
- JS/TS: source throws or rejects; no test uses `.rejects.toThrow()`

**Severity:** 🟡 WARNING

---

## AP-10: Unnamed / Meaningless Test Name

**Symptom:** Test names that convey no information: `test_1`, `test_login`,
`test_it`, `test_function`, `test_method`.

**Detection:** Test names shorter than 3 underscore-separated words or not following
`test_{function}_{scenario}_{outcome}` or equivalent descriptive pattern.

**Severity:** 🟢 SUGGESTION

**Why it matters:** When a test fails in CI, the name is the first thing you see.
`test_1 FAILED` tells you nothing. `test_login_with_expired_token_returns_401 FAILED`
tells you exactly where to look.

---

## AP-11: Test Without Fixture Cleanup (Resource Leak)

**Symptom:** Test creates files, DB connections, sockets, or temp directories
and does not clean them up.

**Detection:**
- Python: `open()` without `with` block or fixture teardown; DB connection without `yield` and `close()`
- GDScript: `Node.new()` or `Resource.new()` created in test without `free()` in `after_each()`
- Go: `os.Create()` / `os.MkdirTemp()` without `defer os.Remove()`

**Severity:** 🟡 WARNING

---

## AP-12: Example-Only Testing of Pure Functions

**Symptom:** Pure functions with clear mathematical properties (sorting, encoding,
arithmetic, normalization) are tested only with hand-picked examples.
Property-based testing would cover the entire input space.

**Detection:** Function is pure (no side effects, no I/O) + has a testable property
(roundtrip, idempotency, commutativity, invariant preservation) + tests only use
specific hardcoded values.

**Severity:** 🟢 SUGGESTION

**Why it matters:** Example tests miss edge cases that PBT finds automatically.
PBT with shrinking pinpoints minimal failing inputs.

**Fix direction:** Add `@given(st.text())` / `fc.property()` tests alongside
existing example tests. See `references/property-based-testing.md`.

---

## AP-13: Mutation-Immune Tests

**Symptom:** Tests pass even when code is mutated (operators flipped, conditions negated,
return values changed). Tests don't actually verify the logic — they verify
that the function runs without error.

**Detection signals:**
- Tests only check type/shape of return value, not content: `assert isinstance(result, dict)`
- Tests check only `is not None` without verifying actual values
- Tests check only length without checking elements
- Tests on boundary functions (comparisons, thresholds) test only middle-of-range values,
  never the boundary itself (e.g., test `age=25` for `age >= 18` — never test `age=18`)

**Severity:** 🟡 WARNING

**Why it matters:** False confidence. Line coverage is 100% but tests catch zero regressions.

**Fix direction:** Add boundary value assertions. Check exact return values, not just types.
Consider running `mutmut` / Stryker to identify surviving mutants.
See `references/mutation-testing.md`.

---

## Scoring the Test Suite (Audit Mode)

After running all anti-pattern checks, score the suite:

| Score | Meaning |
|-------|---------|
| 9-10 | Production-quality test suite, minor improvements only |
| 7-8 | Good coverage and structure, some anti-patterns present |
| 5-6 | Works but notable quality problems, flaky or shallow tests |
| 3-4 | Serious problems: missing edge cases, flaky tests, no cleanup |
| 1-2 | Test suite provides false confidence; needs significant rework |
