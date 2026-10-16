# Changelog — test-suite

## v2.3.0 — 2026-03-19
- Integrated probekit-security-audit as pipeline stage 3.5 (after code-audit)
- Integrated probekit-dependency-audit as pipeline stage 3.7 (after security-audit)
- Pipeline now 9 stages (was 7)
- Added `--secure` mode (code-audit + security-audit + dependency-audit)
- Updated `--deep` mode to include security-audit
- Added quality gate entries for security-audit and dependency-audit
- Updated pipeline diagram, summary table, context routes for new skills

## v2.2.0 — 2026-03-19
- Added `.probekit.yml` config support in Step 1 (paths, thresholds, excludes, features, scoring weights)
- Added structured inter-skill context passing (replaces text strings with hotspots, findings, recommendations)
- Added algorithmic Overall Quality Score: `10 - (CRITICAL×1.5) - (WARNING×0.5) - (SUGGESTION×0.1) + diamond_bonus`
- Score formula shown in report with full calculation breakdown
- Weights configurable via `.probekit.yml` → `scoring.weights`
- Config not required — all defaults work without `.probekit.yml`
- Added Inter-Skill Context Protocol section documenting what each stage passes forward
- Downstream skills now report coverage of upstream findings

## v2.1.0 — 2026-03-19
- Added arch-review and arch-review-bogame as pipeline stages 1-2
- Added `--arch` mode (architecture only)
- Added `--deep` mode (arch + code + unit + integration)
- Unified quality gate contract: {Gate, Score, Blocking} per stage
- Unified SUITE-REPORT format with emoji severity columns
- Unified AUDIT-TRACKER.md format
- Added 💎 DIAMOND findings section in SUITE-REPORT
- Pipeline now 7 stages (was 5)

## v2.0.0 — 2026-03-19
- Added arch-review and arch-review-bogame stages
- 5 modes: full, quick, quality, arch, deep

## v1.0.0 — 2026-03-15
- Initial release
- 5-stage pipeline: code-audit → unit-test → integration-test → e2e-bdd-test → perf-test
- 3 modes: full, quick, quality
- Language routing for .py, .gd, .js/.ts
- Quality gate: code-audit score ≥ 4/10

Toolchain: skill-architect v3.0.0
