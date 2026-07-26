---
name: analysis-sections-structure
description: "Architecture analysis sections (structure) for arch-review"
---

# Architecture Analysis Sections — Structure (1-6)

## Section 1: Module Boundaries & Cohesion

**What to check:**
- Does each module/package/directory have a single, clear responsibility?
- Are related functions, classes, and data grouped together?
- Is there code that belongs in a different module?
- Do module names accurately describe their contents?
- Are there "god modules" that do too many things (LOC outliers, disproportionate imports)?

**Signals of good cohesion:**
- Module can be described in one sentence without "and"
- Internal classes/functions reference each other frequently
- External modules import a small, stable public API
- Changes to one feature affect one module

**Signals of bad cohesion:**
- Module has unrelated responsibilities joined by coincidence
- Functions in same module never call each other
- Module name is vague ("utils", "helpers", "common", "misc")
- Changes to one feature require editing 5+ modules

**Severity guide:**
- CRITICAL: God module (>1000 LOC, >15 public functions, >10 external importers)
- WARNING: Module with 2+ unrelated responsibilities
- SUGGESTION: Vague naming, minor grouping improvements

---

## Section 2: Dependency Direction & Acyclicity

**What to check:**
- Do dependencies flow in one direction (high-level → low-level)?
- Are there circular imports or mutual dependencies?
- Does the dependency graph form a DAG (directed acyclic graph)?
- Do lower layers import from upper layers (layer violation)?
- Is there a clear dependency hierarchy?

**Analysis approach:**
1. Trace import statements in 10-15 key files
2. Identify dependency direction: UI → Service → Repository → Model
3. Check for inversions: Model importing from Service, Repository importing from Router
4. Check for circular: A imports B imports C imports A

**Severity guide:**
- CRITICAL: Circular dependency between core modules
- CRITICAL: Lower layer importing from upper layer in core architecture
- WARNING: Circular dependency in utility/helper modules
- WARNING: Dependency direction unclear (no layering visible)
- SUGGESTION: Could benefit from dependency inversion (interface extraction)

---

## Section 3: Coupling Assessment

**What to check:**
- How many other modules does each module depend on? (fan-out)
- How many modules depend on each module? (fan-in)
- Are dependencies on concrete implementations or abstractions?
- Is dependency injection used where appropriate?
- Are there hidden coupling through global state, singletons, or shared mutable data?

**Coupling metrics (heuristics):**
- Fan-out > 7: high coupling, module knows too much
- Fan-in > 10: high centrality, changes here break many things
- Concrete dependency on implementation detail: tight coupling
- Dependency on interface/protocol/ABC: loose coupling

**Hidden coupling sources:**
- Global variables / module-level mutable state
- Singletons without injection point
- Shared database tables accessed by multiple modules directly
- Event buses without clear contracts
- Environment variables read deep inside modules (not at boundaries)

**Severity guide:**
- CRITICAL: Global mutable state shared across modules without synchronization
- WARNING: Fan-out > 10 in a single module
- WARNING: Direct implementation dependency where interface would be cleaner
- SUGGESTION: Could use DI to reduce coupling

---

## Section 4: Layer Separation

**What to check:**
- Are layers clearly defined (presentation, business logic, data access)?
- Does each layer only communicate with adjacent layers?
- Is business logic free of presentation/transport concerns?
- Is data access isolated from business rules?
- Are cross-cutting concerns (logging, auth, metrics) handled without polluting layers?

**Common layer violations:**
- HTTP request/response objects in service layer
- SQL queries in router/controller
- Business rules in database triggers or stored procedures
- UI formatting logic in data models
- Framework-specific types leaking across layer boundaries

**Clean layer patterns:**
- Router: deserialize → call service → serialize (zero logic)
- Service: pure business logic, receives typed inputs, returns typed outputs
- Repository/DAL: data access only, returns domain objects
- Cross-cutting: middleware, decorators, aspect-oriented patterns

**Severity guide:**
- CRITICAL: Business logic in router/controller (> 10 LOC of logic)
- WARNING: Data access in service layer (queries outside repository)
- WARNING: Transport types (Request, Response) in domain layer
- SUGGESTION: Could extract cross-cutting concern into middleware

---

## Section 5: Pattern Consistency

**What to check:**
- Is the same pattern used for the same type of problem across the codebase?
- Error handling: same approach in all modules?
- Logging: same library, same format, same levels?
- Validation: same approach (schema-first, decorator, manual)?
- Configuration: same access pattern (env vars, config object, DI)?
- Naming: consistent conventions across modules?

**Consistency dimensions:**
1. **Error handling:** exception types, catch patterns, error response format
2. **Logging:** logger instantiation, structured vs unstructured, levels usage
3. **Validation:** where it happens (boundary vs deep), how it reports
4. **Configuration:** access method, defaults handling, secrets separation
5. **Testing:** file naming, fixture patterns, assertion styles
6. **Async patterns:** callbacks vs promises vs async/await, mixed styles

**Severity guide:**
- CRITICAL: Security-relevant inconsistency (some endpoints validate, others don't)
- WARNING: 2+ different patterns for the same problem in same codebase
- WARNING: Newer code uses different pattern than older code (pattern drift)
- SUGGESTION: Minor naming inconsistencies

---

## Section 6: Error Architecture

**What to check:**
- Is there a coherent error hierarchy (base error → domain errors)?
- Are errors classified by severity/type?
- Is error information preserved through the stack (no swallowing)?
- Are errors translated at boundaries (internal → user-facing)?
- Are retry strategies consistent?
- Is there dead-letter / fallback handling for async operations?

**Good error architecture:**
- Base error class with code, message, HTTP status
- Domain-specific subclasses (NotFoundError, ValidationError, ConflictError)
- Catch specific exceptions, not bare except/catch
- Log with context (IDs, operation, input summary) before re-raise
- Translate at API boundary: internal error → user-safe response
- Retry with exponential backoff for transient failures

**Bad error architecture:**
- Bare `except Exception` without context or re-raise
- Error strings instead of typed errors
- Silent catch (catch and ignore)
- Leaking internal details to user (stack traces, SQL, paths)
- No retry strategy for network/IO operations
- Inconsistent HTTP status codes for same error type

**Severity guide:**
- CRITICAL: Silent error swallowing in critical path
- CRITICAL: Internal details leaked in error responses
- WARNING: Bare except without documented reason
- WARNING: No retry on transient failure for external calls
- SUGGESTION: Could add error codes for machine-readable errors
