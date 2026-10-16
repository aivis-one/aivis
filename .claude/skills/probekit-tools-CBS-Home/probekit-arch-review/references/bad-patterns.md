---
name: bad-patterns
description: "Bad architecture patterns (BP-XX) for arch-review pattern catalog"
---

# Bad Patterns (BP) — Flag When Found

### BP-01: God Module
- Module with >1000 LOC, >15 public functions, or >10 direct dependents
- Name is vague ("utils", "helpers", "common")
- **Fix:** Split by responsibility, extract focused modules

### BP-02: Circular Dependencies
- Module A imports B, B imports C, C imports A
- Or more subtle: A uses B's type, B uses A's function
- **Fix:** Extract shared interface, dependency inversion, restructure layers

### BP-03: Layer Violation
- Router/controller contains business logic
- Service layer has SQL/HTTP-specific code
- Model/entity has presentation logic
- **Fix:** Push logic to correct layer, use DTOs at boundaries

### BP-04: Shotgun Surgery
- Single logical change requires edits in 5+ files across 3+ modules
- Feature additions follow "touch everywhere" pattern
- **Fix:** Consolidate related logic, better module boundaries

### BP-05: Hidden State Coupling
- Global mutable variables shared across modules
- Singleton with state that persists between operations
- Module-level caches without invalidation
- **Fix:** Make state explicit, pass as parameter, use proper state management

### BP-06: Inconsistent Error Handling
- Some modules use exceptions, others return error codes
- Some endpoints return 4xx with body, others return empty 5xx
- Bare `except` / `catch(e)` without context or re-raise
- **Fix:** Establish error convention, refactor to consistency

### BP-07: Import-Time Side Effects
- Database connections established at import
- HTTP clients initialized at module load
- Configuration read and validated at import time
- **Fix:** Lazy initialization, factory functions, DI

### BP-08: Leaky Abstraction
- Internal implementation details exposed in public API
- Database column names in API responses
- Framework-specific types in domain layer
- **Fix:** DTOs at boundaries, map internal to external representation

### BP-09: Mixed Paradigms Without Coherence
- Functional and OOP mixed without clear convention
- Callbacks, promises, and async/await in same module
- **Fix:** Choose paradigm per module/layer, document convention

### BP-10: Over-Engineering (Gas Factory)
- Abstract factory for single implementation
- Strategy pattern with one strategy
- Plugin system for non-extensible feature
- Multiple layers of indirection without benefit
- **Fix:** YAGNI — remove abstraction until needed, inline single implementations

### BP-11: Unprotected Shared Mutable State
- Global dicts/lists modified in async or threaded code without locks
- Module-level counters incremented without atomics
- Cache reads and writes not synchronized
- **Fix:** Add `asyncio.Lock`, `threading.Lock`, or use immutable data structures

### BP-12: Sync Blocking in Async Context
- `time.sleep()` in async function (blocks entire event loop)
- Sync HTTP client (`requests`) called inside async handler
- CPU-heavy computation in async without `run_in_executor`
- **Fix:** Use `asyncio.sleep()`, async HTTP client (`httpx`, `aiohttp`), offload CPU work

### BP-13: Missing Observability Foundation
- No structured logging (only `print()` or plain-text logger)
- No correlation IDs across request lifecycle
- No health check endpoints on a service with external dependencies
- Secrets or PII visible in log output
- **Fix:** Add structured logging library, correlation middleware, health endpoints, log sanitization

### BP-14: Anemic Domain Model
- Classes with only data fields (getters/setters), no behavior
- All logic in external "service" classes that manipulate dumb data objects
- Domain rules scattered across services instead of encapsulated
- **Fix:** Move behavior into domain objects where it belongs

### BP-15: Distributed Monolith
- Multiple services that must be deployed together to function
- Shared database between services
- Synchronous RPC chains (Service A → B → C → D)
- **Fix:** Establish clear service boundaries, use async messaging, own-your-data

### BP-16: Shared Database Between Services
- Multiple services reading/writing to same tables
- Schema changes require coordinating multiple teams
- No clear data ownership
- **Fix:** Database-per-service, expose data via APIs, eventual consistency

### BP-17: Configuration Sprawl
- Config loaded from env vars, files, CLI args, and hardcoded defaults in scattered locations
- No single source of truth for configuration
- Config values used without validation (raw `os.getenv()` with no type check)
- **Fix:** Centralize config loading, validate at startup, type all settings

### BP-18: Log-and-Throw Anti-pattern
- `except Exception: logger.error(...); raise` — same error logged multiple times as it bubbles up
- Log noise makes incident investigation harder
- **Fix:** Log at the point of handling (catch + resolve), not at every re-raise

### BP-19: Missing Idempotency
- Non-idempotent operations exposed via retry-prone channels (HTTP, message queue)
- Duplicate processing on retry (double charge, double email)
- No deduplication key or idempotency token
- **Fix:** Add idempotency key, check-before-act, atomic upserts

### BP-20: Feature Flag Rot
- Feature flags created but never cleaned up after rollout
- Code paths behind permanently-on flags that nobody dares remove
- Flag combinations creating untested states
- **Fix:** Flag lifecycle policy (create date, review date, cleanup deadline)

### BP-21: Chatty Microservices
- Single logical operation requires 10+ inter-service calls
- No batching or aggregation layer
- Network latency dominates response time
- **Fix:** BFF / aggregation layer, batch APIs, async messaging for non-critical paths

### BP-22: Catch-Rethrow Without Context
- `except Exception as e: raise SomeError(str(e))` — loses original traceback and exception chain
- `except Exception: raise CustomError("something went wrong")` — no context
- **Fix:** Use `raise ... from e` (Python) or wrap with cause chain, preserve original traceback
