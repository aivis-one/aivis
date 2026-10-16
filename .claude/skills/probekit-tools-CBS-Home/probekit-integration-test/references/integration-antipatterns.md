# Integration Test Anti-Patterns

Reference catalog for integration-test. Flag when found during test audit or generation.

## AP-01: Test Without Assertions
- Test runs code but never asserts anything
- `assert True` or trivially true assertion
- Test catches exceptions silently and passes
- **Severity:** 🔴 CRITICAL
- **Fix:** Add meaningful assertions on response status, body, DB state

## AP-02: Session Scope Leak
- Mutable fixture shared across tests (session or module scope)
- Test A modifies shared state, Test B reads corrupted state
- Database not rolled back between tests
- **Severity:** 🔴 CRITICAL
- **Fix:** Use function-scoped fixtures, transaction rollback per test

## AP-03: Production DB in Test
- Tests hit production or staging database
- No test database isolation
- Missing test environment configuration
- **Severity:** 🔴 CRITICAL
- **Fix:** Separate test database, use TEST_ env vars, docker compose

## AP-04: Missing Teardown
- Test creates records but never cleans up
- File system artifacts left after test
- External service state not restored
- **Severity:** 🟡 WARNING
- **Fix:** Use fixtures with teardown, `yield` in pytest, `afterEach` in Jest

## AP-05: Dead Test
- Test references function/endpoint that no longer exists
- Test never actually runs (wrong naming convention)
- Test file not included in test discovery
- **Severity:** 🟡 WARNING
- **Fix:** Remove dead tests, fix naming to match framework convention

## AP-06: Hardcoded IDs / URLs
- Test uses hardcoded UUIDs, database IDs, or URLs
- Breaks when run against different environment
- **Severity:** 🟡 WARNING
- **Fix:** Generate IDs in fixtures, use relative URLs, config-based base URL

## AP-07: Ignoring Error Paths
- Only happy path tested
- No 4xx/5xx response tests
- No timeout/connection error tests
- **Severity:** 🟡 WARNING (🔴 CRITICAL if auth/payment error paths untested)
- **Fix:** Add error path tests for every endpoint: 400, 401, 403, 404, 409, 500

## AP-08: Over-Mocking
- Everything mocked — database, services, HTTP — test verifies nothing real
- Mock returns exactly what assertion expects (circular test)
- **Severity:** 🟡 WARNING
- **Fix:** Integration tests should use real DB, real services where possible. Mock only external APIs.

## AP-09: Giant Setup
- Test setup is 50+ lines of fixture creation
- Hard to understand what the test actually verifies
- Changes to unrelated models break the test
- **Severity:** 🟢 SUGGESTION
- **Fix:** Use factory functions, builder pattern, minimal fixtures per test

## AP-10: Flaky Timing
- Test depends on `sleep()` or `time.sleep()`
- Assertion on time-dependent values (timestamps, durations)
- Race conditions in async test setup
- **Severity:** 🟡 WARNING (🔴 CRITICAL if flaky in CI)
- **Fix:** Use polling/retry, freeze time with `freezegun`, await specific conditions

## AP-11: Missing Contract Tests
- API has known consumers but no response schema validation
- Endpoint response shape changed without test catching it
- No test for error envelope format consistency
- **Severity:** 🟡 WARNING (when API has consumers)
- **Fix:** Add JSON Schema validation, test required/forbidden fields, test error envelope

## AP-12: No Failure Path Testing
- Only successful responses tested
- No tests for upstream timeout, DB failure, connection drop
- No verification that system degrades gracefully under failure
- **Severity:** 🟡 WARNING
- **Fix:** Add mock-based failure injection tests (Pattern 8): timeout, 500, connection refused
