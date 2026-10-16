# Changelog

## v2.2.0 — 2026-03-19

### Added
- **AI Patterns 10.11–10.20** — 10 new patterns covering vibe coding, context window artifacts, confident incorrectness, specification drift, sycophantic code, training data leakage, approximate implementation, stale pattern application, semantic naming mismatch, integration point amnesia
- **Detection Master-Checklist** — 9-step systematic procedure for AI pattern detection per file
- **Severity Calibration** — universal escalation/de-escalation rules for all 20 AI patterns
- **Section 4 expansion** — SSRF, deserialization, mass assignment, IDOR, open redirect detection patterns added
- **AI Pattern escalation rules** in severity-format.md — context-aware severity for all 10 new patterns

### Changed
- ai-patterns.md: 10 patterns → 20 patterns + master-checklist + calibration section
- severity-format.md: references probekit-core + adds AI pattern and Section 12 escalation rules
- analysis-sections.md Section 4: expanded with 5 new concrete detection patterns

---

## v2.1.0 — 2026-03-15

### New Features
- **Section 12: Test Quality Audit** — comprehensive analysis of existing test suites
  - 12.1 Coverage Gaps (critical paths, error branches, boundary conditions)
  - 12.2 Test Effectiveness (assert-free tests, trivial assertions, happy-path-only, tautological tests)
  - 12.3 Test Isolation and Reliability (state pollution, fixture teardown, environment assumptions)
  - 12.4 Flakiness Indicators (sleep-based sync, floating point equality, time-dependent assertions)
  - 12.5 Test Design Quality (god tests, copy-paste tests, anonymous names, excessive setup)
  - 12.6 Test Maintenance Debt (permanent skips, commented-out tests, missing regression tests)
  - 12.7 Test Architecture (inverted pyramid, missing contract tests — for large suites only)
- **--tests flag** and natural language triggers ("audit tests", "проверь тесты")
  for expanded Section 12 treatment
- **Auto-detection of test files** — Section 12 runs automatically when test files found,
  no flag required; supported: pytest, jest/vitest, Go test, GUT (Godot)
- **ENVIRONMENT.md detection** — skill reads project environment file if present,
  adapts shell syntax and tool commands accordingly; never hardcodes platform-specific syntax

### Changes
- Section 12 severity follows dedicated escalation rules in severity-format.md
- User guide updated with Section 12 documentation and --tests flag examples
- SKILL.md Step 1 now includes environment detection step
- Section 12 severity findings flow into existing severity counters (WARNING/SUGGESTION) in the totals table — no table structure change required

---

## v2.0.0 — 2026-03-13

### New Features
- **--fix mode**: auto-apply CRITICAL and WARNING fixes to source files, then re-verify (Sections 2+4)
- **Cross-module analysis (Section 11)**: detect inconsistencies across files when reviewing 2+ files together
- **Audit tracker**: AUDIT-TRACKER.md with history and delta tracking per file set
- **Configurable review_dir**: path variable in SKILL.md Configuration instead of hardcoded path

### Changes
- Trigger words for fix mode: `--fix`, "fix", "починь", "исправь"
- SUGGESTION-level items are never auto-fixed (too subjective)
- Report filename uses `{{review_dir}}` from Configuration section
- Single-file reviews skip Section 11 automatically

---

## v1.0.0 — 2026-03-13

Initial release.

### Sections
- 9 core analysis sections based on senior engineer review methodology
- Section 10: AI-Generated Code Patterns (new layer, 2025-2026 threat data)

### AI Patterns Covered
- Slopsquatting and hallucinated dependencies (CRITICAL by default)
- Hallucinated APIs and functions
- God classes via append behavior
- Prompt residue
- Logic duplication
- Copy-paste inheritance
- Mixed paradigms
- Over-engineering (Gas Factory)
- Leaky abstractions
- Phantom code

### Security Additions vs Standard Review
- Privilege escalation path detection (322% more common in AI code, Apiiro 2025)
- Architectural auth drift detection (silent authentication failures)
- Dependency verification flag for slopsquatting

### Features
- Language-adaptive output (responds in user's language)
- Auto-saves report to file for large inputs
- Slash command: /code-audit
- Auto-trigger on review/audit/find bugs keywords

Toolchain: skill-architect v3.0.0
