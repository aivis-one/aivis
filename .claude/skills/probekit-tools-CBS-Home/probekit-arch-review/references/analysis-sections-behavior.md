---
name: analysis-sections-behavior
description: "Architecture analysis sections (behavior) for arch-review"
---

# Architecture Analysis Sections — Behavior (7-12)

## Section 7: Data Flow & State Management

**What to check:**
- Is data transformation pipeline clear and traceable?
- Are there hidden state mutations?
- Is mutable shared state minimized?
- Are data boundaries clear (external → internal → storage)?
- Is there unnecessary data copying or transformation?

**Data flow checklist:**
- Input → Validate → Transform → Process → Persist → Respond
- Each step should be identifiable in the code
- Data shapes should be explicit (schemas, types, interfaces)
- Transformations should be pure where possible
- Side effects should be isolated and explicit

**State management red flags:**
- Global mutable state without locks
- Implicit state in module-level variables
- State split across multiple sources of truth
- Cache without invalidation strategy
- Session state without cleanup

**Severity guide:**
- CRITICAL: Mutable shared state causing race conditions
- CRITICAL: Multiple sources of truth for same data
- WARNING: Implicit state mutations (side effects in getters)
- SUGGESTION: Could make transformation more explicit

---

## Section 8: Scalability Design

**What to check:**
- Are there architectural bottlenecks (single point of failure)?
- Can the system scale horizontally (add more instances)?
- Are resources properly pooled (connections, threads)?
- Is work distributable (queue-based, event-driven)?
- Are there N+1 query patterns?

**Scalability patterns:**
- Connection pooling with health checks
- Queue-based async processing
- Batch operations instead of per-item
- Pagination for large datasets
- Caching with clear invalidation
- Stateless request handling (session in external store)

**Scalability anti-patterns:**
- In-process state that prevents horizontal scaling
- Unbounded queries (SELECT * without LIMIT)
- Sequential processing of independent items
- Synchronous calls to slow external services in request path
- No connection pool or pool exhaustion
- N+1 queries (loop of individual SELECTs)

**Severity guide:**
- CRITICAL: Unbounded query in production path
- CRITICAL: N+1 query pattern affecting response time
- WARNING: No connection pooling for database/external services
- WARNING: Synchronous blocking call in async context
- SUGGESTION: Could benefit from caching strategy

---

## Section 9: Testability Assessment

**What to check:**
- Can modules be tested in isolation (unit tests possible)?
- Is dependency injection used to enable test doubles?
- Are there interfaces/protocols/ABCs at module boundaries?
- Are side effects isolated and mockable?
- Is configuration injectable (not hardcoded)?

**Testability enablers:**
- Constructor/parameter injection for dependencies
- Interface-based boundaries (can substitute fakes)
- Pure functions where possible (deterministic, no side effects)
- Configuration as parameters, not global reads
- Lazy initialization (not import-time side effects)
- Clear separation of I/O from logic

**Testability blockers:**
- Hardcoded dependencies (import and use directly)
- Import-time side effects (database connections at module load)
- Global state that persists between tests
- Tight coupling to framework internals
- Hidden dependencies (function reads env vars internally)

**Severity guide:**
- CRITICAL: Import-time side effects preventing test isolation
- WARNING: Hardcoded dependency that blocks unit testing
- WARNING: No injection point for external service dependency
- SUGGESTION: Could extract interface for better testability

---

## Section 10: Evolution Readiness

**What to check:**
- Can new features be added without modifying core?
- Is the codebase open for extension, closed for modification?
- Are there intentional extension points (plugins, hooks, strategies)?
- Is there feature flag infrastructure?
- Can modules be replaced independently?
- Are boundaries aligned with likely change vectors?

**Evolution patterns:**
- Strategy pattern for swappable algorithms
- Plugin architecture for extensions
- Event-driven decoupling for cross-cutting features
- Feature flags for gradual rollout
- Interface-based boundaries at likely split points
- Versioned APIs for backward compatibility

**Evolution blockers:**
- Deep inheritance hierarchies (change at root cascades)
- Switch/if-else chains for type dispatch (add type = modify everywhere)
- Hardcoded integrations without abstraction layer
- No clear boundaries for future extraction
- Mixed concerns that prevent independent deployment

**Severity guide:**
- CRITICAL: Change in one module requires changes in 5+ others (shotgun surgery)
- WARNING: No extension mechanism for likely change area
- WARNING: Deep inheritance blocking modification
- SUGGESTION: Could add strategy pattern for anticipated variation point

---

## Section 11: Concurrency Architecture

**What to check:**
- Is shared mutable state protected (locks, atomics, immutable patterns)?
- Are async/await patterns correct (no missing awaits, no sync calls in async context)?
- Are connection pools configured and bounded (not leaking)?
- Is there a consistent lock ordering to prevent deadlocks?
- Are goroutines/tasks/threads properly lifecycle-managed (no fire-and-forget leaks)?
- Are timeouts propagated through all external calls?

**Race condition signals:**
- Global/module-level mutable dicts, lists, counters modified in async/threaded code without locks
- TOCTOU: `if exists(x): use(x)` — check and use separated by time
- GIL reliance: assuming Python's GIL protects multi-step operations (LOAD+INCR+STORE)
- SQLite without WAL mode in concurrent write scenarios
- Node.js: shared state modified across tick boundaries without guards

**Async correctness signals:**
- `time.sleep()` in async function (blocks event loop)
- Sync HTTP client (requests) called inside async handler
- Missing `await` on coroutine call (coroutine never executes)
- Fire-and-forget tasks with no error handling (`asyncio.create_task` without exception capture)
- `Promise` created but never awaited/caught in JS

**Connection pool signals:**
- No connection pool for database (new connection per request)
- Pool with no max size (unbounded growth)
- Pool with no `pre_ping` / health check (stale connections)
- Pool with no `recycle` setting (long-lived connections go stale)
- Connection obtained but not released in error paths

**Severity guide:**
- CRITICAL: Shared mutable state without synchronization in concurrent code
- CRITICAL: Sync blocking call in async request handler (blocks entire event loop)
- CRITICAL: Connection pool leak (connections not released on error path)
- WARNING: Missing `await` on coroutine (silent no-op)
- WARNING: Fire-and-forget task without error capture
- WARNING: No connection pool configuration (using defaults)
- WARNING: No timeouts on external service calls
- SUGGESTION: Could use immutable data structures to eliminate lock need
- SUGGESTION: Could add `go test -race` / thread sanitizer to CI

---

## Section 12: Observability Design

**What to check:**
- Is logging structured (JSON/key-value) or plain text?
- Are correlation/request IDs generated and propagated through request lifecycle?
- Is log level usage consistent (DEBUG/INFO/WARNING/ERROR used correctly)?
- Are business-critical operations instrumented with metrics?
- Are health check endpoints present and correct (liveness vs readiness)?
- Is sensitive data (PII, secrets) excluded from logs?

**Structured logging signals:**
- `print()`, `console.log()`, `fmt.Println()` in production code → unstructured
- No imports of structured logging libraries (structlog, winston, zap, zerolog)
- Log messages are plain strings with no key-value context
- No correlation ID in any log statement in HTTP handlers
- No middleware generating/propagating request ID

**Metrics signals (RED/USE methods):**
- RED (request-driven): Rate, Errors, Duration per endpoint — missing any of the three
- USE (resource-driven): Utilization, Saturation, Errors for DB pool, memory, CPU — no instrumentation
- No custom business metrics (orders processed, payments completed, queue depth)
- Metric labels have unbounded cardinality (user_id as label → metric explosion)

**Health check signals:**
- No `/health`, `/healthz`, or `/readyz` endpoints
- Single health endpoint that checks everything (should separate liveness from readiness)
- Health check that makes expensive calls (full DB query instead of simple ping)
- Health check returning 200 even when dependencies are down

**Log level consistency signals:**
- ERROR used for non-error conditions (expected 404, validation failure)
- WARNING never used (jump from INFO to ERROR)
- DEBUG left enabled in production (log volume explosion)
- Different modules use different log levels for same event type

**Severity guide:**
- CRITICAL: Secrets or PII in log output (passwords, tokens, credit cards)
- CRITICAL: No structured logging in production service with multiple instances
- WARNING: No correlation ID propagation across request lifecycle
- WARNING: No health check endpoints on service with external dependencies
- WARNING: Metrics with unbounded label cardinality
- WARNING: Inconsistent log level usage across modules
- SUGGESTION: Could add distributed tracing (OpenTelemetry)
- SUGGESTION: Could add readiness probe separate from liveness

