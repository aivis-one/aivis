# Metrics, Thresholds, and Pass/Fail Gates

## Core Metrics

| Metric | What it measures | Why it matters |
|--------|-----------------|----------------|
| p50 (median) | Typical user experience | Baseline; half of users are faster |
| p95 | 95% of users' experience | Primary SLO metric — covers nearly everyone |
| p99 | Worst 1% of requests | Catches tail latency; high-value traffic lives here |
| RPS | Requests per second (throughput) | System capacity ceiling |
| Error rate | % of failed requests (non-2xx + timeouts) | Direct user impact |
| p99 / p50 ratio | Tail divergence | > 2.5× signals architectural bottleneck |

**Never use mean/average as primary latency metric.** Latency distributions are long-tailed.
A handful of 2000ms responses inflate the mean without affecting p50, hiding real problems.
Always report p50 + p95 + p99 together.

---

## Default Thresholds

Apply these when no project-specific SLOs are defined.
Source: industry SRE practice + 2025 SaaS performance benchmarks.

| Metric | PASS | WARN | FAIL |
|--------|------|------|------|
| p95 latency | < 500ms | 500–1000ms | > 1000ms | Google/Akamai: 53% users abandon after 3s; 500ms covers interactive feel |
| p99 latency | < 1500ms | 1500–3000ms | > 3000ms | 3× p95 ceiling; tail users still under abandonment threshold |
| Error rate | < 0.5% | 0.5–1.0% | > 1.0% | SaaS industry SLA standard: 99.9% availability ≈ <0.1% server errors; 1% accounts for client errors too |
| p99/p50 ratio | < 2.5× | 2.5–4× | > 4× | >4× signals architectural bottleneck (GC, lock contention); 2.5× is normal variance |

Adjust for endpoint type:
- Static/cached endpoints: p95 < 100ms, p99 < 300ms
- DB-heavy endpoints: p95 < 800ms, p99 < 2000ms (note in report)
- External API calls (if under test): p95 < 2000ms (network-bound)
- Background jobs / async endpoints: p95 < 5000ms

---

## Pass/Fail Gate Logic — Standard (smoke / load / stress)

Apply after every standard test run:

```
CRITICAL FAIL  → error rate > 1.0% OR p99 > 3000ms
WARNING        → p95 in 500–1000ms OR p99 in 1500–3000ms OR p99/p50 ratio > 2.5×
PASS           → all thresholds met
```

Additional diagnostic flags (do not change gate result, add to Findings):
- p99 > 3× p95: "tail divergence" — likely intermittent blocking (GC, lock contention, cold DB query)
- Error rate spikes before latency degrades: "capacity ceiling hit cleanly"
- Latency climbs linearly with VU count: "no connection pooling or thread exhaustion"
- Latency stable but error rate climbs: "rate limiting or queue overflow"

---

## Pass/Fail Gate Logic — Spike

Spike tests simulate abnormal burst traffic. Standard error rate thresholds do not apply during the spike window.

```
CRITICAL FAIL  → error rate > 5% during spike window
               OR system crashes and requires manual restart
               OR p95 does not recover to pre-spike baseline within 60s post-spike
WARNING        → error rate 1–5% during spike window
               OR p95 recovery takes 30–60s
PASS           → error rate < 5% during spike, p95 recovers within 30s post-spike

Rationale — 5% vs standard 1%: Spikes are abnormal burst traffic (3-10x normal).
Some request rejection is expected and healthy (rate limiters, queue overflow).
A system that rejects 3% during a 10x spike is well-designed, not broken.
The critical signal is recovery speed, not spike-window error rate.
```

---

## Pass/Fail Gate Logic — Soak

Soak tests measure stability over time. The key signal is degradation, not absolute thresholds.
Record p95 at T=start (first 2 minutes of steady load) and T=end (last 2 minutes of test).

```
CRITICAL FAIL  → error rate > 1.0% at any point
               OR error rate shows upward trend (even if < 1%)
WARNING        → p95 at end > 120% of p95 at start (degradation detected)
               OR memory visibly growing (if observable)
PASS           → p95 at end ≤ 120% of p95 at start AND error rate < 1% throughout

Rationale — 120% degradation threshold: Accounts for normal variance (JIT warmup,
GC cycles, cache churn) without masking real leaks. 110% would false-positive on
healthy systems with GC pauses. 150% would miss slow memory leaks that compound
over hours. 120% is the industry-standard soak degradation gate (Netflix Chaos
Engineering, Google SRE handbook recommendations for long-running service tests).
```

---

## Regression Detection (tracker delta)

When comparing to a previous run:
- p95 increased > 20% → REGRESSION (flag even if still under threshold)
- Error rate increased > 0.3 percentage points → REGRESSION
- Max RPS decreased > 15% → CAPACITY REGRESSION
- p95 improved > 20% → IMPROVEMENT (note)

---

## Bottleneck Patterns and Root Causes

| Observed pattern | Likely root cause | Where to look |
|-----------------|-------------------|---------------|
| p99 >> p95, p50 normal | Intermittent slow path | Long tail: GC pause, cold query, connection pool wait |
| Latency climbs linearly with VUs | No connection reuse | DB connection pool, HTTP keep-alive |
| Error rate at VU ceiling, then hard stop | Thread/worker pool exhausted | Server worker count, thread pool config |
| Memory grows linearly during soak | Memory leak | Object accumulation, unclosed connections |
| p95 spikes at regular intervals | Scheduled job interference | Cron jobs, cache revalidation, batch processes |
| Error rate spikes, latency stays low | Rate limiting or circuit breaker | Middleware, API gateway config |
| Latency jumps at specific endpoint only | N+1 query, missing index | DB slow query log, explain plan |

---

## Metric Collection Reference

### k6 automatic metrics
`http_req_duration` — full request cycle (most important)
`http_req_waiting` — TTFB (time to first byte)
`http_req_connecting` — TCP handshake (should be near 0 after warm-up)
`http_req_failed` — rate of non-2xx or failed checks
`vus` — current virtual user count
`vus_max` — peak VUs

### Locust CSV columns (stats file)
`Name` — endpoint name/tag
`Request Count` — total requests
`Failure Count` — failed requests
`Median Response Time` ≈ p50
`95%ile (ms)` — p95
`99%ile (ms)` — p99
`Requests/s` — RPS

### Parsing Locust headless output
Locust prints a summary table to stdout after `--headless` run.
Also check `_stats.csv` for per-endpoint data.
`_failures.csv` lists each failure type and count.
