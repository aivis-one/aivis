# Performance Test Anti-Patterns

Reference catalog for perf-test. Flag when found during test audit or analysis.

## AP-01: No Thresholds
- Test script has no pass/fail thresholds defined
- Test always passes regardless of latency or error rate
- No `thresholds` block in k6, no assertions in Locust
- **Severity:** 🟡 WARNING
- **Fix:** Define p95, p99, error rate thresholds per endpoint

## AP-02: Hardcoded URLs
- Base URL hardcoded in test script
- Cannot run against different environments (staging, prod)
- **Severity:** 🟢 SUGGESTION
- **Fix:** Use environment variables or CLI parameters for base URL

## AP-03: Single Endpoint Only
- Test hits one endpoint, misses N+1 patterns across endpoints
- No realistic traffic distribution
- **Severity:** 🟡 WARNING
- **Fix:** Test all user-facing endpoints with realistic weight distribution

## AP-04: Too Short Duration
- Load test runs < 30 seconds
- No time for JIT warm-up, connection pool saturation, GC pressure
- **Severity:** 🟡 WARNING
- **Fix:** Minimum 1 minute for smoke, 5 minutes for load, 10 for stress

## AP-05: No Ramp-Up
- All VUs hit simultaneously from second 0
- Creates artificial spike, not realistic load pattern
- **Severity:** 🟡 WARNING
- **Fix:** Ramp from 0 to target over 10-30% of test duration

## AP-06: Ignoring p99
- Report shows only average or p50 latency
- p99 tail ignored — hides worst-case user experience
- Ratio p99/p50 not analyzed
- **Severity:** 🟡 WARNING (🔴 CRITICAL if p99/p50 > 4x)
- **Fix:** Always report p50, p95, p99. Analyze p99/p50 ratio.

## AP-07: Missing Error Rate Gate
- Errors counted but no threshold for pass/fail
- 5% error rate silently passes
- **Severity:** 🟡 WARNING
- **Fix:** Set error rate threshold (typically < 1% for PASS)

## AP-08: Testing Against Localhost Only
- Performance measured on localhost (no network latency, no DNS)
- Results not representative of production
- **Severity:** 🟢 SUGGESTION
- **Fix:** Note in report if localhost-only; recommend staging test

## AP-09: No Baseline
- Performance test run without previous baseline to compare
- Cannot detect regression
- **Severity:** 🟢 SUGGESTION
- **Fix:** Save results to PERF-TRACKER; compare delta on next run

## AP-10: Static Data Only
- All requests use same payload / same user / same resource
- Cache artificially inflates performance
- No realistic data distribution
- **Severity:** 🟡 WARNING
- **Fix:** Use parameterized data, random selection from dataset

## AP-11: No Profiling on FAIL
- Test gate result is ❌ FAIL but no profiling was run
- Root cause unknown — only symptoms (high p99, errors) observed
- Cannot prioritize fix without knowing CPU hotspots
- **Severity:** 🟢 SUGGESTION
- **Fix:** Re-run with `--profile` to identify bottleneck functions via flame graph

## AP-12: No SLO Mapping
- Performance test runs without defined SLO targets
- Results evaluated only against generic thresholds
- No error budget tracking across runs
- Cannot answer "are we meeting our service commitments?"
- **Severity:** 🟢 SUGGESTION
- **Fix:** Define SLO targets via `--slo` flag or `.probekit.yml` → `perf.slo` section
