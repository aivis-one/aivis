# Changelog — arch-review

## v1.1.0 — 2026-03-19

### Added
- Section 11: Concurrency Architecture — race conditions, async/await correctness, connection pools, deadlock detection, timeout propagation
- Section 12: Observability Design — structured logging, correlation IDs, metrics (RED/USE), health checks, log level consistency, PII safety
- Patterns catalog: GP-11 (Structured Logging), GP-12 (Bounded Connection Pool), GP-13 (Context Timeout Propagation)
- Patterns catalog: BP-11 (Unprotected Shared State), BP-12 (Sync Blocking in Async), BP-13 (Missing Observability)
- Patterns catalog: DP-06 (Lock-Free Concurrency), DP-07 (Circuit Breaker), DP-08 (Correlation-Aware Logging)
- 2 new scorecard dimensions: Concurrency (1.0x weight), Observability (1.0x weight) — total 12 dimensions
- Concurrency and Observability escalation rules in severity-format.md
- Pattern Quality Assessment renumbered to Section 13

### Changed
- SKILL.md: 10 sections → 12 sections, 10 dimensions → 12 dimensions
- severity-format.md: now references probekit-core + adds concurrency/observability escalation rules
- output-template.md: added Section 11, 12 to report structure; scorecard expanded with 2 rows

## v1.0.0 — 2026-03-19
- Initial release
- 10-section architecture analysis (modularity, coupling, cohesion, layering, consistency, error design, data flow, scalability, testability, evolvability)
- Weighted 10-dimension scorecard
- Patterns catalog: 10 Good, 10 Bad, 5 Diamond
- 4-level severity: 🔴 CRITICAL, 🟡 WARNING, 🟢 SUGGESTION, 💎 DIAMOND
- Quality gate: PASS/WARN/FAIL
- --fix mode for auto-refactoring
- Unified AUDIT-TRACKER.md format

Toolchain: skill-architect v3.0.0
