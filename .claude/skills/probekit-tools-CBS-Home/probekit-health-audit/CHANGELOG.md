# Changelog

## v1.2.0 — 2026-04-10

### Added
- **Probes 9-12**: domain rules coverage, SQLite table sizes, memory entry age, WAL/log freshness
- **Cross-probe analysis**: compound escalation rules (e.g., Disk Bloat + No Log Rotation → CRITICAL)

### Changed
- Quality gate thresholds refined (PASS ≥6.0/10, FAIL <4.0/10 or 3+ CRITICAL)

## v1.1.0 — 2026-04-05

### Added
- **Auto-fix mode** (`--fix`): rotation config, cleanup scripts
- **Environment detection**: OS/shell/package manager adaptation

## v1.0.0 — 2026-03-29

### Features
- **7 core probes**: disk bloat, log rotation, log duplication, DB growth, dead files, config drift, orphan data
- **Runtime artifact scanning**: checks logs, databases, config files — not source code
- **ADR currency probe**: checks architectural decision records for staleness
- **Scored report**: severity-based scoring with totals table
- **Audit tracker integration**: appends to AUDIT-TRACKER.md

Toolchain: probekit-tools-CBS-Home
