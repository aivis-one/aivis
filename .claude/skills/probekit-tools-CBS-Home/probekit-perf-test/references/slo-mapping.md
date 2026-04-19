# SLO Mapping

Maps perf-test results to SLO compliance. Use in Step 9 report when SLO targets
are defined (user-provided, `.probekit.yml`, or codebase hints).

---

## Definitions

**SLI** (Service Level Indicator) — measurable quality metric.
Examples: `successful_requests / total_requests`, `requests faster than 200ms / total`.

**SLO** (Service Level Objective) — target value for an SLI over a period (typically 30 days).
Examples: 99.9% availability, 95% of requests < 200ms.

**SLA** (Service Level Agreement) — contractual commitment with consequences. SLA ≥ SLO.

**Error Budget** — allowable failure amount before SLO is breached.
Formula: `Error Budget = 1 - SLO target`
Example: SLO 99.9% over 30 days → budget = 0.1% × 43200 min = **43.2 min downtime**.

---

## Mapping Perf-Test Results → SLO

### Latency SLO
```
Input:  p95, p99 from test results
Target: slo_latency_p95_ms, slo_latency_p99_ms (from config or user)
Result: COMPLIANT if actual ≤ target, VIOLATION if actual > target
Margin: target - actual (positive = headroom, negative = over)
```

### Reliability SLO
```
Input:  error_rate from test results
Target: slo_max_error_rate (from config or user; default 0.1%)
Result: COMPLIANT if actual ≤ target
Budget: (actual / target) × 100 = % of error budget consumed in this test
```

### Capacity SLO
```
Input:  sustained RPS from test, p99 under load
Target: slo_min_rps (from config or user)
Result: COMPLIANT if actual_rps ≥ target AND latency SLO still met
```

---

## SLO Source Detection

Check in order:
1. `--slo` CLI flag (e.g. `--slo p95=200,p99=1000,error=0.1%,rps=500`)
2. `.probekit.yml` → `perf.slo` section
3. Codebase hints: SLO comments in config, README mentions of latency targets
4. If none found → skip SLO Compliance section, note "No SLO targets defined"

---

## SLO Compliance Report Format

```
## SLO Compliance
Test duration: Xs | VUs: N | Total requests: N

### Latency SLO
  p95: Xms  [TARGET: ≤Yms]  ✅ PASS / ❌ FAIL  (margin: ±Zms)
  p99: Xms  [TARGET: ≤Yms]  ✅ PASS / ❌ FAIL  (margin: ±Zms)

### Reliability SLO
  Error rate: X%  [TARGET: ≤Y%]  ✅ PASS / ❌ FAIL
  Error budget consumed this run: Z%

### Capacity SLO
  Actual RPS: X  [TARGET: ≥Y]  ✅ PASS / ❌ FAIL
  Latency under load: p99=Xms (cross-ref Latency SLO)

### Overall: ✅ SLO MET / ❌ SLO VIOLATION
  Failing: <list of failing SLOs>
  Action: <recommended next step>
```

If no SLO targets defined:
```
## SLO Compliance
No SLO targets defined. To enable: use `--slo` flag or add `perf.slo` to `.probekit.yml`.
Results evaluated against default thresholds only (see Final Score).
```
