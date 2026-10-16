# Tool Detection and Script Patterns

## Detection Priority

Check in this order. Use the first available tool.

### 1. k6
Detection:
  - `k6 version` exits 0
  - OR `package.json` contains `"k6"`
  - OR `.js` files in `tests/perf/` or `k6/`

Install:
  Windows:  `choco install k6`
  macOS:    `brew install k6`
  Linux:    apt/yum per https://grafana.com/docs/k6/latest/set-up/install-k6/
  npm (CI): `npm install -g k6` (unofficial, prefer binary)

Script extension: `.js`
Run command: `k6 run <script>`
Run with output: `k6 run --out json=perf-results.json <script>`

Script template:
```javascript
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

const errorRate = new Rate('errors');

export const options = {
  // Load profile injected here by Step 6
  stages: [],
  thresholds: {
    http_req_duration: ['p(95)<500', 'p(99)<1500'],
    http_req_failed: ['rate<0.01'],
    errors: ['rate<0.01'],
  },
};

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';

export default function () {
  // Endpoint calls injected here
  const res = http.get(`${BASE_URL}/endpoint`);
  const ok = check(res, {
    'status 200': (r) => r.status === 200,
    'p95 < 500ms': (r) => r.timings.duration < 500,
  });
  errorRate.add(!ok);
  sleep(1);
}
```

### 2. Locust
Detection:
  - `locust --version` exits 0
  - OR `locust` in `requirements.txt` / `pyproject.toml`
  - OR `locustfile.py` exists in project root or `tests/`

Install: `pip install locust`

Script extension: `.py`
Run command (headless): `locust -f <script> --headless -u <users> -r <spawn_rate> -t <duration> --host <url> --csv=perf-results`
Run with HTML report: add `--html=perf-report.html`

Key headless flags:
  `-u`  total users
  `-r`  spawn rate (users/sec)
  `-t`  duration e.g. `60s`, `5m`, `1h`
  `--headless` no web UI, exits after test

Script template:
```python
from locust import HttpUser, task, between, events
import json

class APIUser(HttpUser):
    wait_time = between(1, 3)  # think time between requests

    def on_start(self):
        """Called when a user starts. Add auth/login here."""
        pass

    @task(3)  # weight: heavier tasks get higher number
    def get_main_endpoint(self):
        with self.client.get(
            "/endpoint",
            name="/endpoint",  # groups requests in report
            catch_response=True
        ) as response:
            if response.status_code != 200:
                response.failure(f"Got {response.status_code}")

    @task(1)
    def post_endpoint(self):
        payload = {"key": "value"}
        with self.client.post(
            "/endpoint",
            json=payload,
            name="POST /endpoint",
            catch_response=True
        ) as response:
            if response.status_code not in (200, 201):
                response.failure(f"Got {response.status_code}")
```

Parsing Locust CSV output:
  `perf-results_stats.csv` — per-endpoint stats: req count, fail count, median, p95, p99, RPS
  `perf-results_failures.csv` — failure details

### 3. Artillery
Detection:
  - `artillery version` exits 0
  - OR `artillery` in `package.json` devDependencies
  - OR `.yml` files in `tests/perf/` with `artillery` root key

Install: `npm install -g artillery`
Run command: `artillery run <config.yml> --output perf-results.json`
Script extension: `.yml`

Script template:
```yaml
config:
  target: "http://localhost:8000"  # override with BASE_URL env var
  http:
    timeout: 10
  phases:
    # Load profile injected here by Step 6 — example below:
    - duration: 30
      arrivalRate: 5
      name: "Ramp up"
    - duration: 600
      arrivalRate: 50
      name: "Steady load"
    - duration: 30
      arrivalRate: 0
      name: "Ramp down"
  ensure:
    p95: 500        # fail if p95 > 500ms
    p99: 1500       # fail if p99 > 1500ms
    maxErrorRate: 1 # fail if error rate > 1%

scenarios:
  - name: "Main flow"
    flow:
      - get:
          url: "/endpoint"
          expect:
            - statusCode: 200
      - think: 1
      - post:
          url: "/endpoint"
          json:
            key: "value"
          expect:
            - statusCode: 200
```

Parsing Artillery JSON output (`perf-results.json`):
  `.aggregate.latency.p95` — global p95 (ms)
  `.aggregate.latency.p99` — global p99 (ms)
  `.aggregate.latency.median` approx p50
  `.aggregate.rps.mean` — mean RPS
  `.aggregate.errors` — error count map
  Per-scenario stats available under `.intermediate[].latency`

### 4. pytest-benchmark
Detection:
  - `pytest-benchmark` in requirements / `benchmark` in any existing test file
  - Best for: micro-benchmarks, function-level performance (not HTTP load)

Run command: `pytest --benchmark-only --benchmark-json=perf-results.json`
Use when: testing pure Python function performance, not HTTP endpoints.

---

## Endpoint Discovery from Code

When target is a directory or file (not a URL), extract endpoints systematically.

### Framework Detection and Route Extraction

| Framework | Decorator/Pattern | Regex for grep/rg | Example |
|-----------|------------------|-------------------|---------|
| FastAPI | `@app.get/post/put/delete/patch`, `@router.get/post/...` | `@(app\|router)\.(get\|post\|put\|delete\|patch)\(` | `@router.get("/users/{id}")` |
| Flask | `@app.route`, `@bp.route`, `@blueprint.get/post` | `@(app\|bp\|blueprint)\.(route\|get\|post)\(` | `@app.route("/api/users", methods=["GET"])` |
| Django | `path()`, `re_path()` in `urls.py` | `path\(["']` in files named `urls.py` | `path("api/users/", views.UserList.as_view())` |
| Express | `app.get/post`, `router.get/post` | `(app\|router)\.(get\|post\|put\|delete)\(` | `router.get('/api/users', handler)` |
| Hono | `app.get/post`, `app.route` | `app\.(get\|post\|put\|delete\|route)\(` | `app.get('/api/users', (c) => ...)` |
| Godot HTTP | Manual URL matching, no decorators | Look for `_on_request` handlers | Map by URL string comparison in handler code |

### Extraction Procedure

1. Detect framework from imports (`from fastapi`, `from flask`, `require('express')`)
2. Run regex grep for framework-specific decorators
3. For each match, extract: HTTP method, URL path, handler function name
4. Classify endpoint type for threshold adjustment:

| Endpoint Type | Signals | Threshold Adjustment |
|---------------|---------|---------------------|
| Static/cached | Returns hardcoded data, reads config, cache hit | p95 < 100ms |
| DB read | SELECT queries, `.get()`, `.filter()`, repository calls | Default (p95 < 500ms) |
| DB write | INSERT/UPDATE/DELETE, `.create()`, `.save()` | p95 < 800ms |
| External API | `httpx.get`, `requests.post`, SDK client calls | p95 < 2000ms |
| File I/O | `open()`, `Path.read_text()`, file upload | p95 < 1000ms |
| Background/async | task queue, `asyncio.create_task`, job submit | p95 < 5000ms |

5. Build endpoint list for load script generation (Step 6)
6. Assign request weights: heavier traffic to GET endpoints, lighter to POST/DELETE

### When No Framework Detected

If no web framework found:
- Check for raw `http.server` or `socketserver` usage
- Check for CLI entry points (`if __name__ == '__main__'`)
- Ask user: "I couldn't detect a web framework. What's the base URL and which endpoints should I test?"

---

## Shell-Safe Command Construction

Always adapt commands to detected shell:

PowerShell:
  - Use single quotes for file paths: `locust -f 'tests\perf\load.py'`
  - Path separator: backslash `\` in paths
  - ENV variables: `$env:BASE_URL = 'http://localhost:8000'`

Bash/Zsh:
  - Path separator: forward slash `/`
  - ENV variables: `BASE_URL=http://localhost:8000 locust -f ...`

If ENVIRONMENT.md present — check Shell Notes section for project-specific pitfalls.

---

## Tool Not Available

If no tool found and no tool can be installed:
Generate a minimal Python HTTP benchmark script using only stdlib:
```python
import urllib.request, time, statistics, concurrent.futures

def single_request(url):
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            r.read()
            return time.perf_counter() - start, r.status, None
    except Exception as e:
        return time.perf_counter() - start, 0, str(e)

def run_benchmark(url, users=10, requests_per_user=20):
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=users) as ex:
        futures = [ex.submit(single_request, url)
                   for _ in range(users * requests_per_user)]
        for f in concurrent.futures.as_completed(futures):
            results.append(f.result())
    durations = [r[0]*1000 for r in results]
    errors = [r for r in results if r[1] != 200]
    durations.sort()
    p = lambda pct: durations[int(len(durations)*pct/100)]
    print(f"Requests: {len(results)}, Errors: {len(errors)}")
    print(f"p50={p(50):.0f}ms  p95={p(95):.0f}ms  p99={p(99):.0f}ms")
    print(f"Error rate: {len(errors)/len(results)*100:.1f}%")

if __name__ == '__main__':
    run_benchmark('http://localhost:8000/endpoint')
```
Label this as "stdlib fallback — install Locust or k6 for production-grade testing."
