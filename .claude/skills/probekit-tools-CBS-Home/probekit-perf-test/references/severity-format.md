# Severity Format — Performance Test

> Core format: read `probekit-core/references/severity-format.md` for markers, output syntax, decision tree, honesty rules.

## Perf-Test Escalation Rules

- Error rate > 1% under load → 🔴 CRITICAL
- p95 > threshold → 🔴 CRITICAL
- p99 > threshold → 🔴 CRITICAL
- p99/p50 ratio > 4× → 🔴 CRITICAL (architectural bottleneck)
- p99/p50 ratio 2.5–4× → 🟡 WARNING (tail divergence, investigate)
- p95 within threshold but p99 > 2× p95 → 🟡 WARNING
- Missing thresholds in test script → 🟡 WARNING (tests pass vacuously)
- Load test never run (no test files, no baseline) → 🟡 WARNING
- Soak test never run on long-running service → 🟢 SUGGESTION
- No CI performance gate → 🟢 SUGGESTION
- Test uses hardcoded URLs → 🟢 SUGGESTION
- p99/p50 ratio < 1.5× with sustained high RPS → 💎 DIAMOND

## Tool Reliability Note

Stdlib fallback results are less reliable than k6/Locust results — note this in report.
If test could not run (tool missing, connection refused), report honestly. Do not invent synthetic results.
