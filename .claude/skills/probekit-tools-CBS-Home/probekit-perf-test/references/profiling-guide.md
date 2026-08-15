# Profiling Guide

Optional profiling integration for perf-test. Use when `--profile` flag is set
or user explicitly requests profiling alongside load testing.

**Rule: Never auto-launch profiler.** Only run when user opts in.

---

## Tool Selection by Language

| Language | Tool | Install | Profile Command |
|----------|------|---------|-----------------|
| Python | py-spy | `pip install py-spy` | `py-spy record -o profile.svg --pid <PID> --duration <SEC>` |
| Node.js | clinic.js | `npm install -g clinic` | `clinic flame -- node server.js` |
| Go | pprof | built-in (`net/http/pprof`) | `go tool pprof http://localhost:6060/debug/pprof/profile?seconds=30` |

If tool not installed → note in report as SUGGESTION, skip profiling step.

---

## Parallel Profiling with Load Test

General pattern:
1. Start the application under test
2. Find its PID or profiling port
3. Start profiler in background with same duration as load test
4. Start load test
5. Wait for both to finish
6. Analyze profiler output

### Python (py-spy)
```bash
# Attach to running server, profile for 60s while k6 runs
py-spy record -o profile.svg --pid $(pgrep -f "uvicorn") --duration 60 &
k6 run --duration 60s --vus 50 load_test.js
```

### Node.js (clinic.js)
```bash
# clinic wraps the server process — start server via clinic, then load test separately
clinic flame -- node server.js &
sleep 3
k6 run --duration 30s --vus 20 load_test.js
kill -SIGINT $!  # generates HTML report on exit
```

### Go (pprof)
```bash
# Requires `import _ "net/http/pprof"` in server code
# Collect CPU profile during load test
k6 run --duration 60s --vus 100 load_test.js &
sleep 10  # let load ramp up
curl -o cpu.pprof "http://localhost:6060/debug/pprof/profile?seconds=30"
go tool pprof -http=:8080 cpu.pprof
```

---

## Flame Graph Interpretation — 5 Bottleneck Patterns

### Pattern 1: Serialization Bottleneck
**Signal:** `json.dumps` / `JSON.stringify` / `json.Marshal` occupies 30%+ of flame width.
**Fix:** Use faster serializer (orjson for Python, jsoniter for Go). Reduce payload size. Cache serialized responses.

### Pattern 2: N+1 Query
**Signal:** DB driver functions (`execute`, `query`, `fetchone`) repeat N times as narrow identical frames side by side.
**Fix:** Use eager loading (`joinedload`, `include`, `Preload`). Batch queries.

### Pattern 3: GC Pressure
**Signal:** `gc.collect` / `runtime.GC` / GC-related frames occupy >10% of time.
**Fix:** Reduce short-lived allocations in hot path. Use object pooling (`sync.Pool` in Go). Pre-allocate buffers.

### Pattern 4: Lock Contention
**Signal:** `mutex.Lock` / `futex` / waiting frames are wide. Visible in Go mutex pprof profile.
**Fix:** Use `RWMutex` for read-heavy access. Reduce critical section size. Consider lock-free structures.

### Pattern 5: Regex Catastrophic Backtracking
**Signal:** Regex engine frame dominates, time not proportional to input size.
**Fix:** Compile regex once. Avoid nested quantifiers `(a+)+`. Use atomic groups or possessive quantifiers.

---

## Bottleneck Analysis Report Format

For each slow endpoint (p99 > threshold or p95 in WARN range):

```
### <METHOD> <PATH> (p99=Xms, p95=Xms)

**Top CPU consumers** (flame graph, N-sec sample under load):
  1. `<function>` — X% CPU time
     → Pattern: <pattern name>
     → Recommendation: <concrete fix>
  2. `<function>` — X% CPU time
     → Recommendation: <concrete fix>

**Estimated improvement**: <what fixing top items would achieve>
```

If profiling was NOT run, replace with:
```
### Bottleneck Analysis
Profiling not performed. To identify CPU hotspots, re-run with `--profile`.
Based on metrics alone:
- <pattern from metrics-thresholds.md bottleneck table>
- <recommendation>
```
