---
name: good-patterns
description: "Good architecture patterns (GP-XX) for arch-review pattern catalog"
---

# Good Patterns (GP) — Reward When Found

### GP-01: Composition Over Inheritance
- Mixin-based composition for shared behavior
- Strategy pattern for variant algorithms
- Delegation instead of deep class hierarchies
- **Why it matters:** Flexible, testable, avoids fragile base class problem

### GP-02: Explicit Session/Transaction Management
- Transaction boundary defined at one layer (router/handler)
- Service layer does `flush()` only, never `commit()`
- Single point of transaction control per request
- **Why it matters:** Prevents partial commits, simplifies error recovery

### GP-03: Lazy Singleton with Reset
- Resource created on first access, not at import time
- Factory function with module-level cache
- Reset mechanism for testing
- **Why it matters:** Solves async lifecycle issues, enables test isolation

### GP-04: Double-Entry / Self-Verifying Data
- Every state change creates balancing records
- Sum invariants (always zero, always positive)
- Immutable audit trail alongside mutable state
- **Why it matters:** Data integrity, auditability, catch bugs early

### GP-05: Snapshot at Decision Point
- Copy mutable data into immutable record at action time
- Decision survives future changes to source data
- Clean separation: current state vs historical state
- **Why it matters:** Audit trail, no retroactive data corruption

### GP-06: Three-Stage Pipeline
- Separate stages for: resolve → execute → aggregate
- Each stage independent (can fail without blocking others)
- Exponential backoff on empty work queues
- **Why it matters:** Resilience, horizontal scaling, debuggability

### GP-07: Guarded Field with Warning
- `__setattr__` hook warns on direct writes to computed/managed fields
- Distinguish creation vs mutation (check persistence state)
- Warning, not exception — catches bugs without blocking valid code
- **Why it matters:** Prevents silent corruption of derived data

### GP-08: Dependency Injection via Function Parameters
- Dependencies passed as parameters, not imported directly
- Factory functions or DI framework for wiring
- Configuration injectable, not hardcoded
- **Why it matters:** Testability, flexibility, explicit dependencies

### GP-09: Domain Exception Hierarchy
- Base error with code + message + HTTP status
- Domain-specific subclasses (NotFound, Conflict, Forbidden)
- Catch specific, log with context, translate at boundary
- **Why it matters:** Consistent error handling, good diagnostics

### GP-10: Trace ID Propagation
- Unique ID per request/operation
- Bound to structured logging context
- Propagated across async boundaries
- Returned in response headers
- **Why it matters:** Distributed tracing, debugging, audit correlation

### GP-11: Structured Logging with Context Binding
- JSON/key-value logs with contextual fields (user_id, operation, duration_ms)
- Logger bound to request context via middleware (structlog, winston, zap)
- Log levels used consistently: ERROR=unexpected, WARNING=degraded, INFO=business events, DEBUG=internal
- **Why it matters:** Machine-parseable logs, fast incident investigation, correlation across services

### GP-12: Bounded Connection Pool with Health Checks
- Pool size explicitly configured (not defaults), with min/max bounds
- `pre_ping` or equivalent health check before returning connection
- `pool_recycle` to prevent stale connections
- Metrics on pool utilization (active, idle, waiting)
- **Why it matters:** Prevents connection leaks, handles database restarts gracefully

### GP-13: Context-Based Timeout Propagation
- Timeout/deadline set at entry point and propagated through all layers
- Python: `asyncio.timeout()` or `httpx.Timeout`; Go: `context.WithTimeout`; JS: `AbortController`
- Each layer respects remaining budget, not a fresh timeout
- **Why it matters:** Prevents cascading timeouts, ensures predictable request lifecycle


### GP-14: Repository Pattern
- Data access encapsulated behind interface (ABC / Protocol)
- Business logic depends on interface, not on concrete DB implementation
- Concrete implementation injected at startup
- **Why it matters:** Swappable persistence (SQLite → PostgreSQL), testable without DB

### GP-15: DTO / Value Object at Layer Boundaries
- Dedicated types for data crossing layer boundaries (API → Service, Service → DB)
- No ORM models in API responses, no request dicts in business logic
- Validation at boundary (Pydantic, dataclass, TypedDict)
- **Why it matters:** Prevents leaky abstractions, clear contracts between layers

### GP-16: Middleware Chain / Pipeline Pattern
- Cross-cutting concerns (auth, logging, rate limiting) composed as ordered pipeline
- Each middleware has single responsibility
- Order configurable, not hardcoded
- **Why it matters:** Clean separation of concerns, easy to add/remove/reorder

### GP-17: Configuration Hierarchy with Startup Validation
- Config loaded from multiple sources with priority (env > file > defaults)
- All config validated at startup, fail-fast on invalid values
- Typed config objects (Pydantic BaseSettings, dataclass), not raw dicts/strings
- **Why it matters:** No runtime config surprises, self-documenting settings

### GP-18: Graceful Shutdown
- Signal handler catches SIGTERM/SIGINT
- In-flight requests complete before exit
- Resources cleaned up in reverse order of initialization
- Timeout for forced shutdown if graceful takes too long
- **Why it matters:** No dropped requests, no leaked connections, clean restarts

### GP-19: Retry with Jitter
- Failed operations retried with exponential backoff + random jitter
- Max retries bounded, not infinite
- Idempotent operations only (or idempotency key used)
- **Why it matters:** Prevents thundering herd on service recovery

### GP-20: Dead Letter Queue with Monitoring
- Failed jobs moved to separate queue after max retries
- DLQ monitored with alerts on growth
- Manual replay mechanism available
- **Why it matters:** No silent data loss, operational visibility into failures
