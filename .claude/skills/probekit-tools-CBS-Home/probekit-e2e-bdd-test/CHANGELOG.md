# Changelog

## v1.0.0 — 2026-03-15

Initial release.

### Modes
- **GENERATE mode**: reads source code → generates Gherkin + step definitions → runs + fixes
- **AUDIT mode**: reads existing tests → audits quality, coverage, anti-patterns

### Framework Support
- Python: pytest-bdd (primary), behave (fallback)
- JavaScript/TypeScript: Playwright + Cucumber (primary), Cypress (fallback)
- Universal: adapts to detected environment, reads ENVIRONMENT.md if present

### Analysis Sections
- Section 1: Flow extraction from source code
- Section 2: Step definition generation patterns
- Section 11: Gherkin Quality Audit (11.1–11.10)
- Section 12: Coverage Gap Analysis
- Section 13: Step Definition Code Quality (13.1–13.11)

### Anti-Pattern Detection
- Procedural Gherkin (UI-coupled steps)
- Hardcoded sleep/wait
- Missing Page Object Model (Section 13.10)
- Tautological step implementation — Then with no assertion body (Section 13.11)
- Shared state between scenarios
- Scenarios without assertions
- Ice cream cone pattern (too many E2E, no unit/integration base)
- Tautological Gherkin steps (step name = assertion, no actual check)

### Fix Loop
- Up to 3 iterations per failing test
- Real bugs documented, not hidden by test edits
- Gherkin never modified during fix loop (behavior is the contract)

### Fix Mode (--audit --fix)
- Auto-fixes CRITICAL and WARNING structural findings
- Exceptions: 11.3 (Missing Assertions) and 11.7 (Vague Steps) flagged for manual review only — behavioral intent cannot be safely auto-corrected
- SUGGESTION-level items never auto-fixed
- Re-verifies with Sections 11, 12, 13 after applying fixes
- Reports delta table: before/after counts per severity

Toolchain: skill-architect v3.0.0
