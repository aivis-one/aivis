---
name: diamond-patterns
description: "Diamond architecture patterns (DP-XX) for arch-review pattern catalog"
---

# Diamond Patterns (DP) — Exceptional Quality, Highlight When Found

### DP-01: JSONB/Flexible Schema with Mutation Safety
- Schema-flexible storage (JSONB, document) with explicit mutation tracking
- `set_jsonb()` or equivalent that forces change detection
- Deep-copy before mutation to prevent reference bugs
- **Why it's diamond:** Solves framework limitation elegantly, prevents silent data loss

### DP-02: Two-Session Fusion for Read-Write Operations
- Read session provides user/context, write session provides transaction
- Framework reuses same connection for both
- Eliminates `merge()` / reattach overhead
- **Why it's diamond:** Zero-cost pattern that prevents subtle ORM bugs

### DP-03: Atomic Update with WHERE Guard
- `UPDATE ... SET counter = counter + 1 WHERE counter < max`
- Prevents race conditions without locks
- Returns affected rows count for conflict detection
- **Why it's diamond:** Lock-free concurrency that's both safe and performant

### DP-04: Savepoint Pattern for Duplicate Detection
- `begin_nested()` + `flush()` to catch IntegrityError
- Rolls back only inner savepoint, outer transaction survives
- **Why it's diamond:** Clean duplicate handling without killing the transaction

### DP-05: Progressive Trust Architecture
- Actions classified by risk level (low → auto, high → approval)
- Risk level determines execution path, not just logging level
- Human-in-the-loop at trust boundaries
- **Why it's diamond:** Safety without operational friction

### DP-06: Lock-Free Concurrency via Immutable Data
- Shared state represented as immutable snapshots
- Updates create new versions (copy-on-write, persistent data structures)
- No locks needed — readers always see consistent state
- **Why it's diamond:** Eliminates entire class of race conditions by design, not by discipline

### DP-07: Circuit Breaker with Observability
- External dependency calls wrapped in circuit breaker (closed → open → half-open)
- Breaker state exposed as metric (Prometheus gauge, structured log event)
- Fallback behavior defined per dependency (cached response, default, error)
- **Why it's diamond:** Graceful degradation + automatic recovery + full visibility

### DP-08: Correlation-Aware Structured Logging
- Request ID generated at entry, propagated via context (ContextVar, AsyncLocalStorage, Go context)
- All log statements automatically include request_id, user_id, operation
- Response headers include request ID for client-side correlation
- Logs are JSON with consistent field naming across all services
- **Why it's diamond:** Any production issue traceable end-to-end in seconds

### DP-09: Transactional Outbox Pattern
- State change + outgoing event written in same DB transaction
- Background poller reads outbox table, publishes events, marks as sent
- Guarantees at-least-once delivery without 2PC
- **Why it's diamond:** Solves distributed consistency without distributed transactions

### DP-10: Event Sourcing with Projection Rebuild
- State derived from ordered event log, not mutable rows
- Projections (read models) can be rebuilt from scratch by replaying events
- Event log is append-only, immutable audit trail for free
- **Why it's diamond:** Complete audit history + time-travel debugging + zero data loss

### DP-11: CQRS with Physical Separation
- Write model (normalized, transactional) and read model (denormalized, fast) in separate stores
- Write events trigger async projection updates to read store
- Each side optimized independently (write for consistency, read for throughput)
- **Why it's diamond:** Scales reads and writes independently, eliminates query/write trade-offs

### DP-12: Saga with Compensations & Idempotency
- Multi-step workflow with explicit compensation for each step (undo on failure)
- Each step idempotent (safe to retry)
- Saga state persisted, recoverable after crash
- **Why it's diamond:** Reliable distributed transactions without 2PC, self-healing on partial failure

### DP-13: Hexagonal Architecture (Ports & Adapters)
- Domain core has zero framework dependencies
- All I/O through ports (interfaces) with injectable adapters
- Tests use in-memory adapters, production uses real adapters
- **Why it's diamond:** Framework-independent domain, trivially testable, swappable infrastructure

### DP-14: Strangler Fig with Routing Facade
- New system built alongside legacy, routing facade directs traffic
- Features migrated one-by-one, not big-bang rewrite
- Legacy and new coexist safely during transition
- **Why it's diamond:** Zero-downtime migration, reversible at any point

### DP-15: Bulkhead Isolation
- Critical resources partitioned into isolated pools (separate thread pools, connection pools, rate limits per tenant)
- Failure in one partition cannot exhaust resources for others
- Monitoring per partition for anomaly detection
- **Why it's diamond:** Prevents cascading failures, guarantees fairness under load

### DP-16: Contract Testing Between Services
- Producer and consumer both test against shared contract (Pact, OpenAPI schema)
- Contract changes caught before deployment (CI gate)
- No integration environment needed for contract validation
- **Why it's diamond:** Catches breaking changes at build time, not runtime

### DP-17: Graceful Degradation Cascade
- Structured degradation levels (full → reduced → minimal → offline)
- Each level has defined behavior (not ad-hoc error handling)
- Degradation triggered by metrics (circuit breaker, budget, latency), not just exceptions
- **Why it's diamond:** System stays useful under partial failure, not just "up or down"

### DP-18: Idempotency Key Pattern
- Client sends unique key per operation, server deduplicates
- Key stored with result; duplicate request returns cached result
- TTL on idempotency records prevents unbounded storage
- **Why it's diamond:** Safe retries at every layer, no double-processing

### DP-19: Typed Configuration with Startup Validation
- All config fields typed (Pydantic BaseSettings, Go struct tags, TS zod schema)
- Validation runs at startup, fail-fast on invalid config
- Secrets loaded from vault/env, never from config files
- Default values explicit, documented, and tested
- **Why it's diamond:** Zero runtime config surprises, self-documenting, testable settings
