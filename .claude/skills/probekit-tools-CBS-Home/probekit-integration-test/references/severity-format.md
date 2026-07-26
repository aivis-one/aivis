# Severity Format — Integration Test

> Core format: read `probekit-core/references/severity-format.md` for markers, output syntax, decision tree, honesty rules, test result markers, coverage estimate scale.

## Integration-Test Escalation Rules

- Critical path with zero tests (auth, payment, data write) → always CRITICAL
- Test with no assertions (assertion-free) → always CRITICAL
- Test that always passes regardless of code (trivially true assertion) → always CRITICAL
- DB tests touching production DB path → always CRITICAL
- Missing error path test on public endpoint → WARNING minimum
- Fixture scope too wide (session-scoped with mutable state) → WARNING minimum
- Missing teardown/cleanup in fixture → WARNING minimum
- Dead test (tests a function that no longer exists) → WARNING
- Missing import or broken test that was never run → WARNING
- Parametrize opportunity (3+ near-identical tests) → SUGGESTION
- Style/naming issues → SUGGESTION
- Full contract test suite with schema validation → 💎 DIAMOND

## Source Bug Reporting

If tests reveal actual bugs in production code — report separately:

🔴 SOURCE BUG — [description]
Location: [file:line]
Found by: [test name]
Symptom: [what the test caught]
Recommended fix: [diff or description]
