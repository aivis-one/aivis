# Code Anti-Patterns Catalog

Reference catalog for code-audit. Flag when found during analysis.

## AP-01: God Class / God Module
- Class/module with >1000 LOC, >15 public functions, or >10 direct dependents
- Name is vague ("utils", "helpers", "common", "misc")
- **Severity:** 🟡 WARNING (🔴 CRITICAL if in critical path)
- **Fix:** Split by responsibility, extract focused modules

## AP-02: Hallucinated Dependency
- Import in code that doesn't exist in package manifest (requirements.txt, package.json, go.mod)
- Dependency >2 years without update (staleness risk)
- Name similar to popular package but slightly different (slopsquatting)
- **Severity:** 🔴 CRITICAL
- **Fix:** Verify in registry, pin version, remove if phantom

## AP-03: Copy-Paste Inheritance
- Multiple classes/components with near-identical structure
- Same boilerplate repeated with minor variations
- **Severity:** 🟡 WARNING
- **Fix:** Extract base class, use composition, or template pattern

## AP-04: Prompt Residue
- TODOs that are generic AI-generated placeholders ("TODO: implement this")
- Docstrings that describe what the function should do but don't match implementation
- Template code that was never customized
- **Severity:** 🟢 SUGGESTION (🟡 WARNING if in security-sensitive path)
- **Fix:** Remove or replace with real implementation

## AP-05: Phantom Code
- Functions defined but never called from anywhere
- Classes instantiated nowhere in the codebase
- Dead imports, unreachable branches
- **Severity:** 🟢 SUGGESTION (🟡 WARNING if >100 LOC of dead code)
- **Fix:** Delete. If needed later, git has history.

## AP-06: Over-Engineering (Gas Factory)
- Abstract factory for single implementation
- Strategy pattern with one strategy
- Plugin system for non-extensible feature
- Multiple layers of indirection without benefit
- **Severity:** 🟡 WARNING
- **Fix:** YAGNI — inline single implementations, remove premature abstraction

## AP-07: Leaky Abstraction
- Internal implementation details exposed in public API
- Database column names in API responses
- Framework-specific types in domain layer
- ORM models returned directly from endpoints
- **Severity:** 🟡 WARNING (🔴 CRITICAL if security-sensitive internals)
- **Fix:** DTOs at boundaries, map internal to external representation

## AP-08: Mixed Paradigms Without Coherence
- Functional and OOP mixed without clear convention
- Callbacks, promises, and async/await in same module
- Some modules use dataclasses, others use raw dicts
- **Severity:** 🟡 WARNING
- **Fix:** Choose paradigm per module/layer, document convention

## AP-09: Silent Exception Swallowing
- `except Exception: pass` or `catch(e) {}` with no logging
- Error caught, logged, but not re-raised and no fallback
- Generic catch hiding specific failures
- **Severity:** 🟡 WARNING minimum (🔴 CRITICAL in critical path)
- **Fix:** Catch specific, log with context, re-raise or return error

## AP-10: Hardcoded Secrets
- API keys, passwords, tokens in source code
- Credentials in config files committed to git
- Sensitive data in log messages
- **Severity:** 🔴 CRITICAL (always)
- **Fix:** Environment variables, secrets manager, .env with .gitignore

## AP-11: Inconsistent Validation
- Some endpoints validate input, others don't
- Validation at wrong layer (deep inside service instead of at boundary)
- Different validation libraries/approaches across modules
- **Severity:** 🟡 WARNING (🔴 CRITICAL if security-relevant)
- **Fix:** Validate at boundary, consistent approach, schema-first

## AP-12: N+1 Query Pattern
- Loop that makes individual DB/API call per item
- List endpoint that loads related data one-by-one
- **Severity:** 🟡 WARNING (🔴 CRITICAL if in production hot path)
- **Fix:** Batch query, JOIN, eager loading, or preload
