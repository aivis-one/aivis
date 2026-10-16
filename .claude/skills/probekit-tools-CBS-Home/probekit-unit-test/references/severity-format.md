# Severity Format — Unit Test

> Core format: read `probekit-core/references/severity-format.md` for markers, output syntax, decision tree, diff format, honesty rules, test result markers.

## Unit-Test Escalation Rules

- Assertion-free test → always CRITICAL
- Non-deterministic (flaky) test → always CRITICAL
- Test interdependency → always CRITICAL
- Happy path only → WARNING
- Giant test → WARNING
- Missing error path tests → WARNING
- Structural inspection → WARNING
- Meaningless test name → SUGGESTION
- Coverage chasing → SUGGESTION
- Exceptionally well-structured test suite with property-based tests, mutation coverage → 💎 DIAMOND
