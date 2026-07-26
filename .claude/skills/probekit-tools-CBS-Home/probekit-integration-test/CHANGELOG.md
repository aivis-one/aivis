# Changelog — integration-test

## v1.2.0 — 2026-03-19

### Added
- **Pattern 8: Chaos/Failure Injection Test** — mock-based failure injection (timeout, 500, connection drop), graceful degradation verification
- **Pattern 9: Contract Compliance Test (Extended)** — JSON Schema validation, pagination contract, error envelope consistency, breaking change detection
- **AP-11: Missing Contract Tests** — WARNING when API has consumers but no schema validation
- **AP-12: No Failure Path Testing** — WARNING when only happy paths tested

### Changed
- SKILL.md Step 3: added failure injection and contract test categories to grouping
- severity-format.md: now references probekit-core
- output-template.md: audit tracker → probekit-core reference

## v1.1.0 — 2026-03-19
- Added 💎 DIAMOND severity level
- Added integration-antipatterns.md (10 anti-patterns: AP-01 through AP-10)
- Unified report naming: INT-TEST-<target>-<YYYYMMDD>.md
- Unified AUDIT-TRACKER.md format (was INTEGRATION-TEST-TRACKER.md)
- Unified report_dir: docs/02_milestones/ADR/review

## v1.0.0 — 2026-03-15
- Initial release
- 6-section analysis: layer ID, endpoint inventory, dependency map, error cases, existing tests, destructive setup flag
- Test generation for API, DB, service, and contract layers
- Iterative fix mode (max 3 per test, 15 total)
- Coverage estimation: HIGH/MEDIUM/LOW/NONE
- Source bug detection during test execution

Toolchain: skill-architect v3.0.0
