# Test Types and Load Profiles

## Test Type Selection Guide

| User says / context                          | Test type |
|----------------------------------------------|-----------|
| First run, no baseline                        | smoke → load |
| "Does it work under load?" (default)          | load      |
| "How much can it handle?" / "find the limit"  | stress    |
| "Flash sale / burst traffic"                  | spike     |
| "Memory leak?" / "long-running stability"     | soak      |
| Quick CI check / smoke gate                   | smoke     |

---

## Profiles

### Smoke
Purpose: verify system responds correctly under minimal load. Not a performance test — a sanity gate.
Use before: any other test type. If smoke fails, skip everything else.

Parameters:
  VUs (virtual users): 1–2
  Duration: 1–2 minutes
  Ramp: none, flat

k6 stages:
```javascript
stages: [{ duration: '1m', target: 2 }]
```
Locust: `-u 2 -r 1 -t 1m`

Pass criteria: 0% error rate, p95 < 2× normal threshold (system is lightly loaded)

---

### Load
Purpose: validate system behavior under expected normal traffic.
Models the typical peak production load, not the absolute maximum.

Parameters:
  VUs: estimated concurrent users at peak (if unknown: 10–50 for small services)
  Duration: 10–30 minutes
  Ramp-up: 30–60s to full load, hold, 30s ramp-down

k6 stages (example — 50 VU target):
```javascript
stages: [
  { duration: '30s', target: 10 },   // ramp up
  { duration: '10m', target: 50 },   // steady load
  { duration: '30s', target: 0  },   // ramp down
]
```
Locust: `-u 50 -r 5 -t 12m`

Pass criteria: p95 < threshold, error rate < 1%

---

### Stress
Purpose: find the system's breaking point — max VUs before errors exceed 1% or latency exceeds 3× threshold.
Run load incrementally until failure.

Parameters:
  VUs: start at expected load, increase until failure
  Duration: 5–10 min per stage
  Increment: 50–100% of previous stage

k6 stages (example):
```javascript
stages: [
  { duration: '2m', target: 50  },  // baseline
  { duration: '5m', target: 100 },  // 2×
  { duration: '5m', target: 200 },  // 4×
  { duration: '5m', target: 300 },  // 6× — expect failure here
  { duration: '2m', target: 0   },  // recovery check
]
```
Locust: run multiple sessions with increasing `-u`

Pass criteria: system degrades gracefully (errors increase before crash, not crash before errors).
Record: max_safe_vus = VU count where error rate first exceeded 1%.

---

### Spike
Purpose: test sudden, extreme traffic burst — simulates flash sales, viral content, bot attacks.

Parameters:
  VUs: 10× normal load, injected in <10 seconds
  Duration: 1–2 min at spike, then ramp back

k6 stages:
```javascript
stages: [
  { duration: '10s', target: 10  },   // normal baseline
  { duration: '10s', target: 500 },   // spike — inject instantly
  { duration: '2m',  target: 500 },   // hold spike
  { duration: '30s', target: 10  },   // recover
  { duration: '2m',  target: 10  },   // verify recovery
]
```

Pass criteria: see metrics-thresholds.md — Spike gate.
Summary:
  - During spike: error rate < 5% (more lenient — spike is abnormal load)
  - Post-spike: p95 recovers to pre-spike baseline within 30s (WARNING if 30–60s)
  - System does NOT crash and require manual restart

---

### Soak (Endurance)
Purpose: detect memory leaks, connection pool exhaustion, gradual degradation over time.
Run at moderate load for an extended duration.

Parameters:
  VUs: 60–80% of max safe VUs from load test
  Duration: 1–4 hours (minimum 1h to catch slow leaks)
  Ramp: gentle, 2–3 min to full load

k6 stages:
```javascript
stages: [
  { duration: '3m',  target: 30 },  // gentle ramp
  { duration: '2h',  target: 30 },  // sustained load
  { duration: '3m',  target: 0  },  // graceful shutdown
]
```
Locust: `-u 30 -r 2 -t 2h`

Pass criteria: see metrics-thresholds.md — Soak gate.
Summary:
  - Record p95 at T=start (first 2 min of steady load) and T=end (last 2 min)
  - PASS: p95 at end ≤ 120% of p95 at start AND error rate < 1% throughout
  - WARNING: p95 at end > 120% of p95 at start (degradation)
  - CRITICAL FAIL: error rate > 1% at any point or shows upward trend

Special: if running 2h+ test, warn user about resource costs and suggest running in background.

---

## Recommended First-Run Sequence

1. **Smoke** — 2 min, 2 VUs — "does it respond?"
2. **Load** — 15 min, expected users — "does it hold?"
3. **Stress** — until failure — "where's the ceiling?"

Run soak and spike only when load and stress pass.
