# Changelog

## v1.1.0 — 2026-03-19

### Added
- **Property-Based Testing** — new reference `references/property-based-testing.md`: property catalog (roundtrip, idempotency, commutativity, invariant preservation, monotonicity, oracle), hypothesis (Python) and fast-check (JS/TS) integration, shrinking explanation
- **Mutation Testing** — new reference `references/mutation-testing.md`: 9 mutation operator types, thresholds (>80% PASS, 60-80% WARN, <60% FAIL), surviving mutant decision tree, tools (mutmut, Stryker, go-mutesting)
- **AP-12: Example-Only Testing of Pure Functions** — SUGGESTION: flag pure functions that could benefit from PBT
- **AP-13: Mutation-Immune Tests** — WARNING: tests that only check type/shape, never boundary values
- **PBT section in test-generation.md** — when to generate PBT, property detection, hypothesis/fast-check examples

### Changed
- SKILL.md Step 3 (Generate): added PBT generation for pure functions with mathematical properties
- SKILL.md Step 5.5 (Audit): expanded to AP-01 through AP-13; added mutation testing recommendation for high-coverage shallow suites
- severity-format.md: now references probekit-core
- test-antipatterns.md: 11 → 13 anti-patterns

---

## v1.0.1 — 2026-03-15

### Fixes
- audit_mode flow: routing now decided in Step 1, not Step 5.5 — Steps 3/4/5 correctly skipped
- Added Step 2-AUDIT: reads test files, not source files, in audit mode
- coverage_only mode: Step 4 iteration correctly skipped
- GUT command line: added `res://` prefix to gut_cmdln.gd path
- `source_dir` added to Configuration (was referenced but undefined)
- AP-09 detection: made language-agnostic (Python / GDScript / Go patterns)
- Audit Tracker: Skill column added to tracker header
- CHANGELOG: now lists all 11 anti-patterns
- Trigger phrase alignment between SKILL.md and user-guide.md

---

## v1.0.0 — 2026-03-15

Initial release.

### Sections
- 6-step execution: detect → analyze → generate → run → iterate → report
- Language-adaptive: Python/pytest, GDScript/GUT, JS/Jest, Go test, and others
- Generate + Run + Iterate loop: tests are verified to actually pass before delivery
- Coverage report: lines, branches, missing paths
- Test audit mode: analyze quality of existing tests without generating new ones

### Generation Patterns
- AAA structure enforced on all generated tests
- Parametrized edge cases (boundaries, empty, zero, max, invalid types)
- Fixture-based setup with correct scope selection
- Mock strategy: identify and mock all external boundaries
- Async test support (pytest-asyncio, GUT async patterns)

### Anti-Pattern Detection (Test Audit) — 11 patterns
- AP-01: Happy Path Only — no boundary or exception tests
- AP-02: Assertion-Free tests — always passes, catches nothing
- AP-03: Structural Inspection — tests implementation details not behavior
- AP-04: Conjoined Twins — tests not isolated from each other
- AP-05: Giant tests — one test doing everything
- AP-06: Coverage Chasing — tests of trivial getters/setters with no logic
- AP-07: Mocking own code — testing mocks instead of real code
- AP-08: Non-deterministic tests — time/random/network without control
- AP-09: Missing Error Path Tests — no tests for raise/error cases
- AP-10: Unnamed/Meaningless Test Name — test_1, test_it, test_function
- AP-11: Test Without Fixture Cleanup — resource leaks after test

### Framework Support
- Python: pytest + unittest.mock + pytest-asyncio + pytest-cov
- GDScript: GUT 9.x (Godot 4.x) — command-line and editor modes
- JavaScript/TypeScript: Jest, Vitest
- Go: testing package (stdlib)
- Generic fallback: detect from project files

### Features
- Language-adaptive output (responds in user's language)
- Auto-saves report to file for large inputs
- Slash command: /unit-test
- Auto-trigger on "write tests", "покрой тестами", "напиши тесты" keywords

Toolchain: skill-architect v3.0.0
