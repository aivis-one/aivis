# Test Quality Probes v1.0.0

Five probes that measure test quality beyond coverage percentage.
High coverage with low quality = false confidence.

---

## TQ-1: Assertion Density

**Purpose:** Detect tests with zero or single assertions — "tests that run but verify nothing."

**Detection method:**
1. Parse each test function/method
2. Count assertion calls: `assert`, `assertEqual`, `expect(...)`, `should`, `toBe`, etc.
3. Classify:
   - **Zero assertions:** Test runs code but checks nothing (smoke test at best)
   - **Single assertion:** Minimal verification, likely missing edge cases
   - **2-5 assertions:** Healthy range for unit tests
   - **6+ assertions:** May be testing too much in one test (SUGGESTION to split)

**Thresholds:**

| Zero-Assert Rate | Level | Signal |
|-----------------|-------|--------|
| 0% | DIAMOND | Every test verifies something |
| 1-5% | OK | Rare assertion-free tests |
| 5-15% | WARNING | Significant portion of tests verify nothing |
| > 15% | CRITICAL | Test suite provides false confidence |

**Scoring:**
- 10/10: 0% zero-assertion tests, average 2-4 assertions per test
- 8/10: < 5% zero-assertion tests
- 5/10: 5-15% zero-assertion tests
- 3/10: 15-30% zero-assertion tests
- 0/10: > 30% zero-assertion tests

---

## TQ-2: Mock Fidelity

**Purpose:** Detect mocks that diverge from real interface signatures — when mocks
return different types, accept different arguments, or omit error cases that the real
dependency produces.

**Detection method:**
1. Find all mock/stub/fake definitions in test files
2. For each mock, locate the real dependency it replaces
3. Compare:
   - Method signatures: same parameters and return types?
   - Return values: realistic or always-happy-path?
   - Error cases: does mock ever raise/throw/reject?
   - Missing methods: does mock implement all methods the code calls?
4. Flag divergences

**Severity:**
- Mock matches real signature but always returns success: SUGGESTION
- Mock has different method signature than real: WARNING
- Mock missing methods that code calls: WARNING
- Mock returns different type than real dependency: CRITICAL

**Scoring:**
- 10/10: All mocks match real signatures, include error cases
- 8/10: Signatures match, 1-2 mocks always-happy-path
- 5/10: 3+ signature mismatches or no error-case mocks
- 3/10: Majority of mocks diverge from real interfaces
- 0/10: Mocks are fabricated with no relation to real dependencies

---

## TQ-3: Test Independence

**Purpose:** Detect tests that depend on execution order or shared mutable state.
Order-dependent tests pass in CI but fail when run individually or in different order.

**Detection method:**
1. Scan for shared mutable state patterns:
   - Module-level variables modified in tests
   - Class attributes set in one test, read in another
   - Global state mutations without teardown/cleanup
   - Database records created in one test, queried in another
2. Scan for ordering signals:
   - Test names with sequential numbers suggesting order dependency
   - `setUp`/`tearDown` that assumes state from prior tests
   - Tests that fail when run with `--randomly` or `-k single_test`
3. Check fixture scope: session/module-scoped fixtures that mutate state

**Severity:**
- Shared fixture with no mutation: OK
- Module-level variable read in tests: SUGGESTION (prefer fixtures)
- Shared mutable state between tests: WARNING
- Tests that only pass in specific order: CRITICAL

**Scoring:**
- 10/10: All tests independent, proper fixture isolation
- 8/10: 1-2 shared-state patterns, all with proper cleanup
- 5/10: 3-5 shared-state patterns, some without cleanup
- 3/10: Widespread order dependency signals
- 0/10: Tests fail when run individually

---

## TQ-4: Boundary Coverage

**Purpose:** Measure whether tests exercise boundary conditions — null, empty, zero,
negative, overflow, max-length, Unicode, and type edge cases.

**Detection method:**
1. For each tested function, identify parameter types
2. Check test inputs for boundary values:
   - **Null/None/nil:** Is null passed as input?
   - **Empty:** Empty string, empty list, empty dict?
   - **Zero:** Zero for numeric parameters?
   - **Negative:** Negative numbers where positive expected?
   - **Overflow:** Very large numbers, very long strings?
   - **Unicode:** Non-ASCII input for string parameters?
   - **Type mismatch:** Wrong type passed (if dynamically typed)?
3. Calculate: `boundary_rate = functions_with_boundary_tests / total_tested_functions`

**Thresholds:**

| Boundary Rate | Level | Signal |
|--------------|-------|--------|
| > 60% | DIAMOND | Thorough boundary testing |
| 40-60% | OK | Good boundary awareness |
| 20-40% | WARNING | Many functions lack boundary tests |
| < 20% | CRITICAL | Happy-path-only test suite |

**Scoring:**
- 10/10: > 60% functions have boundary tests, null/empty always tested
- 8/10: 40-60% boundary coverage
- 5/10: 20-40% boundary coverage
- 3/10: < 20% boundary coverage
- 0/10: No boundary tests anywhere

---

## TQ-5: Error Path Coverage

**Purpose:** Measure whether tests exercise error/exception branches — not just the
happy path. Functions that can throw/raise/reject should have tests that verify the
error behavior.

**Detection method:**
1. Identify functions that can produce errors:
   - Functions with `raise`, `throw`, `reject`, `return err`
   - Functions with try/catch blocks
   - Functions calling external services (network, DB, file I/O)
2. For each error-producing function, check test files:
   - Is there a test that expects the error? (`assertRaises`, `expect(...).toThrow`, `should.panic`)
   - Is the error message/type verified (not just "it throws something")?
   - Are different error conditions tested (not just one)?
3. Calculate: `error_path_rate = functions_with_error_tests / functions_with_error_paths`

**Thresholds:**

| Error Path Rate | Level | Signal |
|----------------|-------|--------|
| > 70% | DIAMOND | Error paths well-tested |
| 50-70% | OK | Most error paths covered |
| 30-50% | WARNING | Many error paths untested |
| < 30% | CRITICAL | Errors will surprise in production |

**Scoring:**
- 10/10: > 70% error paths tested, error types/messages verified
- 8/10: 50-70% error paths tested
- 5/10: 30-50% error paths tested
- 3/10: < 30% error paths tested
- 0/10: No error path tests anywhere
