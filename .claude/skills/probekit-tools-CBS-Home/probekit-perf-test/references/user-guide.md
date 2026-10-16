# perf-test — User Guide

Performance testing skill for Claude Code.
Generates scripts, runs load tests, and returns a scored report
with p50/p95/p99 metrics and pass/fail gates.

---

## Invocation

### Slash command
/perf-test http://localhost:8000
/perf-test src/api/
/perf-test .

### Auto-trigger keywords
"run a load test"
"stress test this API"
"how many concurrent users can it handle"
"check the performance"
"will it survive the traffic spike"

### Test type override
/perf-test http://localhost:8000 --type=smoke
/perf-test src/api/ --type=stress
/perf-test . --type=soak

### Dry run (generate script, don't execute)
/perf-test http://localhost:8000 --dry-run

### Profiling (CPU flame graph)
/perf-test http://localhost:8000 --profile
/perf-test src/api/ --type=load --profile

### SLO compliance check
/perf-test http://localhost:8000 --slo p95=200,p99=1000,error=0.1%,rps=500

### Focus hint
/perf-test src/api/ -- focus on checkout and auth endpoints

---

## Usage Examples

### Quick smoke check
/perf-test http://localhost:8000
→ 2 VU, 1 min, verifies endpoints respond. PASS/FAIL.

### Load test a directory
/perf-test src/api/
→ Discovers routes, generates load profile, runs 15min load test.

### Stress test to find the limit
/perf-test http://localhost:8000 --type=stress
→ Increments VUs until error rate > 1%. Reports max safe capacity.

### Spike test
/perf-test src/api/ --type=spike -- focus on /api/checkout
→ Simulates flash-sale traffic burst on checkout endpoint.

### Soak test (memory leak check)
/perf-test http://localhost:8000 --type=soak
→ Runs at 70% load for 2 hours. Detects gradual degradation.

### Load test with profiling
/perf-test http://localhost:8000 --type=load --profile
→ Runs load test + CPU profiler in parallel. Produces flame graph bottleneck analysis.

### Load test with SLO check
/perf-test src/api/ --slo p95=200,p99=1000,error=0.1%,rps=500
→ Runs load test, evaluates results against SLO targets, reports compliance + error budget.

### Dry run (review script before executing)
/perf-test src/api/ --dry-run
→ Generates test script, shows it in chat. Does not execute.

---

## What Gets Generated

For each run:
- `tests/perf/<type>-<YYYYMMDD>.<ext>` — runnable test script
- `{{report_dir}}/PERF-REPORT-<target>-<YYYYMMDD>.md` — full report
- `{{report_dir}}/PERF-TRACKER.md` — running history with deltas

---

## Tool Priority

1. k6 (JS) — preferred for API load testing
2. Locust (Python) — preferred for Python projects
3. Artillery (YAML) — if already in project
4. pytest-benchmark — for function-level benchmarks
5. stdlib fallback — when nothing is installed

For Python projects with Locust not installed:
> pip install locust
Then re-run — the skill will use it automatically.

---

## Report Metrics

Every report includes:
- p50, p95, p99 latency per endpoint
- RPS (peak and sustained)
- Error rate
- p99/p50 ratio (tail divergence indicator)
- Pass/fail gate per threshold
- Bottleneck analysis with root cause hypotheses (enhanced with flame graph data when `--profile` used)
- SLO Compliance section (when `--slo` or `.probekit.yml` SLO targets defined)
- Ranked next steps

---

## Threshold Defaults

| Metric | Threshold |
|--------|-----------|
| p95 | < 500ms |
| p99 | < 1500ms |
| Error rate | < 1.0% |
| p99/p50 ratio | < 2.5× |

To override: edit `Configuration` section in `SKILL.md`.

---

## Notes

- Always run smoke before load/stress. If smoke fails, fix it first.
- Soak tests are long (1–4h). Use `--dry-run` to review the script first.
- Test against staging/dev, not production, unless explicitly intended.
- If the target is not running, the skill diagnoses the connection error and suggests a fix.
- Reports are saved automatically. Re-running the same target shows a delta vs previous run.
