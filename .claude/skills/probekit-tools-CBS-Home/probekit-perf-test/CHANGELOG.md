# Changelog — perf-test

## v1.2.0 — 2026-03-19
- Added profiling integration: `--profile` flag runs py-spy/clinic.js/pprof in parallel with load test
- Added `references/profiling-guide.md` — 3 profiler tools, 5 flame graph bottleneck patterns, report format
- Added SLO mapping: `--slo` flag defines latency/reliability/capacity targets
- Added `references/slo-mapping.md` — SLI/SLO/SLA definitions, error budget formula, compliance report format
- Added Step 8.5 (optional): Profiling Analysis with flame graph pattern matching
- Enhanced Step 9: Bottleneck Analysis always present (metrics-based or profiler-based), SLO Compliance section
- Added output-template.md: profiling bottleneck + SLO compliance report sections
- Added AP-11: No Profiling on FAIL (SUGGESTION)
- Added AP-12: No SLO Mapping (SUGGESTION)
- Updated user-guide.md: documented `--profile` and `--slo` flags with examples

## v1.1.0 — 2026-03-19
- Added 💎 DIAMOND severity level
- Added perf-antipatterns.md (10 anti-patterns: AP-01 through AP-10)
- Unified report naming: PERF-TEST-<target>-<YYYYMMDD>.md (was PERF-REPORT)
- Unified report_dir: docs/02_milestones/ADR/review (was docs/02_milestones/perf-reports)
- Unified AUDIT-TRACKER.md format (was PERF-TRACKER.md)

## v1.0.0 — 2026-03-15
- Initial release
- 5 test types: smoke, load, stress, spike, soak
- Tool detection priority: k6 → Locust → Artillery → pytest-benchmark → stdlib
- 3-tier gate logic with p95/p99/error rate thresholds
- Dry-run mode for script review before execution
- Bottleneck analysis with root cause hypotheses

Toolchain: skill-architect v3.0.0
