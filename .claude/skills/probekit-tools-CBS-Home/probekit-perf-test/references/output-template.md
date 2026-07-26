# Output Template

Build the final report in this exact structure.

---

## Report Header

Performance Test Report: [target name or URL]
Test Type: [smoke | load | stress | spike | soak]
Tool: [k6 | Locust | Artillery | pytest-benchmark | stdlib-fallback]
Script: [path to generated test script]
Thresholds: p95 < Xms | p99 < Xms | error rate < X%
Tested: [date]

---

## Environment

[Detected: OS, shell, project language/framework, tool version]
[Base URL used]
[VU count, duration, ramp profile — brief summary]

---

## Endpoints Tested

List each endpoint:
- `GET /api/users` — weight 3 (read-heavy)
- `POST /api/auth/login` — weight 1 (auth flow)
- `GET /api/items` — weight 2 (DB-heavy)

---

## Results

### Metrics Summary

| Endpoint | p50 | p95 | p99 | RPS | Error% | Gate |
|----------|-----|-----|-----|-----|--------|------|
| GET /api/users | 45ms | 210ms | 890ms | 142 | 0.1% | ✅ PASS |
| POST /auth/login | 120ms | 480ms | 1200ms | 38 | 0.3% | ✅ PASS |
| GET /api/items | 88ms | 620ms | 3100ms | 95 | 0.0% | ❌ FAIL |

Global: p95 = Xms | p99 = Xms | RPS = X | Error rate = X%

### Gate Result

✅ PASS / ⚠️ WARN / ❌ FAIL

State clearly which thresholds passed and which failed.

---

## Findings

Use severity markers from `references/severity-format.md`.

🔴 CRITICAL — Short description
Location: endpoint or code location if identifiable

Observation: [what the data shows]
Pattern: [bottleneck pattern from metrics-thresholds.md]
Likely cause: [root cause hypothesis]
Fix: [concrete recommendation]

Use 🟡 WARNING or 🟢 SUGGESTION for lower-severity findings.

---

## Bottleneck Analysis

Identify the top 1–3 limiting factors.

**If profiling was run** (`--profile`):
For each slow endpoint, list top CPU consumers from flame graph with pattern match and fix:
```
### <METHOD> <PATH> (p99=Xms, p95=Xms)

**Top CPU consumers** (flame graph, N-sec sample under load):
  1. `<function>` — X% CPU time
     → Pattern: <Serialization | N+1 | GC Pressure | Lock Contention | Regex>
     → Recommendation: <concrete fix>
  2. `<function>` — X% CPU time
     → Recommendation: <concrete fix>

**Estimated improvement**: <projected metrics after fixing top items>
```

**If profiling was NOT run** (default):
Use metrics-only analysis:
```
### Bottleneck Analysis (metrics-based)
For deeper CPU-level analysis, re-run with `--profile`.

Based on observed patterns:
- <endpoint> — <pattern from metrics-thresholds.md> → <recommendation>
```

For each: observed metric → pattern → root cause → fix priority.
See `references/profiling-guide.md` for pattern catalog.

---

## SLO Compliance

Include this section ONLY when SLO targets are defined (via `--slo`, `.probekit.yml`, or Configuration).
See `references/slo-mapping.md` for format and evaluation logic.

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

### Overall: ✅ SLO MET / ❌ SLO VIOLATION
  Failing: <list>
  Action: <recommendation>
```

If no SLO targets defined → omit this section or note:
"No SLO targets defined. Use `--slo` flag or `.probekit.yml` to enable."

---

## Generated Script

Path: `tests/perf/<type>-<YYYYMMDD>.<ext>`
[If --dry-run: show script inline. If executed: confirm path only.]

---

## Next Steps

Ordered by priority:
1. [Fix or investigate item 1]
2. [Fix or investigate item 2]
3. [Recommended next test type, e.g. "Run stress test after fixing p99 on /api/items"]

---

## Final Score

Performance Gate: ✅ PASS / ⚠️ WARN / ❌ FAIL

| Metric | Result | Threshold | Status |
|--------|--------|-----------|--------|
| p95 global | Xms | <500ms | ✅/❌ |
| p99 global | Xms | <1500ms | ✅/❌ |
| Error rate | X% | <1.0% | ✅/❌ |
| p99/p50 ratio | X× | <2.5× | ✅/❌ |

🔴 CRITICAL findings: N
🟡 WARNING findings: N
🟢 SUGGESTION findings: N
💎 DIAMOND findings: N

---

## Audit Tracker Update

> Format: see `probekit-core/references/audit-tracker-format.md` for table format, delta rules, and field definitions.

Append row with: skill=`perf-test`, key metric=`p95=Xms RPS=Y err=Z%`.
