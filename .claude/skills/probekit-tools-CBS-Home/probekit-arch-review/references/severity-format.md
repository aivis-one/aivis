# Severity Format — Architecture Review

> Core format: read `probekit-core/references/severity-format.md` for markers, output syntax, decision tree, honesty rules.

## Arch-Review Escalation Rules

- God module (>1000 LOC, >15 public functions, >10 importers) → 🔴 CRITICAL
- Circular dependency between core modules → 🔴 CRITICAL
- Lower layer importing upper layer → 🔴 CRITICAL
- Global mutable state shared across modules → 🔴 CRITICAL
- Shotgun surgery (change in 1 → edit 5+ files) → 🔴 CRITICAL
- Inconsistent error handling across modules → 🟡 WARNING
- Missing dependency injection → 🟡 WARNING
- Import-time side effects → 🟡 WARNING
- Pattern drift (newer code uses different pattern) → 🟡 WARNING
- Minor naming inconsistency → 🟢 SUGGESTION
- Composition over inheritance, strategy pattern, lazy singleton → 💎 DIAMOND (if well-executed)

### Concurrency Escalation
- Shared mutable state without synchronization in concurrent code → 🔴 CRITICAL
- Sync blocking call in async request handler → 🔴 CRITICAL
- Connection pool leak (not released on error) → 🔴 CRITICAL
- Missing `await` on coroutine → 🟡 WARNING
- Fire-and-forget task without error capture → 🟡 WARNING
- No timeouts on external service calls → 🟡 WARNING

### Observability Escalation
- Secrets or PII in log output → 🔴 CRITICAL
- No structured logging in production multi-instance service → 🔴 CRITICAL
- No correlation ID propagation → 🟡 WARNING
- No health check endpoints → 🟡 WARNING
- Metrics with unbounded label cardinality → 🟡 WARNING
- Structured logging with full correlation, proper health checks → 💎 DIAMOND
