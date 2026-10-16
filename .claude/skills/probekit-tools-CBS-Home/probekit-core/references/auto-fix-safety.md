# ProbeKit Auto-Fix Safety Standard — Core Reference

Canonical safety rules for all ProbeKit skills with `--fix` mode.
Every skill that modifies source files MUST follow these rules.

## Safety Checklist (ALL conditions must be true)

Before applying any auto-fix, verify:

| # | Condition | Description |
|---|-----------|-------------|
| 1 | **Localized** | Fix is within a single file, < 20 LOC change |
| 2 | **Unambiguous** | The correct fix is clear — wrong name, missing keyword, incorrect type, known-safe pattern swap |
| 3 | **No API conflict** | Fix does not change public API signatures, exported interfaces, or service contracts |
| 4 | **No cross-module effects** | Fix does not require changes in other modules or files |
| 5 | **Testable** | Existing tests cover the affected code path, OR the fix itself is in test infrastructure |

If ANY condition fails → mark as `NEEDS-MANUAL` in report, do NOT apply.

## Fix Priority Order

1. 🔴 CRITICAL findings first
2. 🟡 WARNING findings second
3. 🟢 SUGGESTION — **NEVER auto-fix** (too subjective, context-dependent)

## Fix-Verify-Revert Protocol

For each fix:
```
1. SAVE: record original file content
2. APPLY: make the change using Edit tool
3. VERIFY: run the relevant test/check command:
   - TypeScript: npx vue-tsc --noEmit
   - Python: python -m pytest tests/ -x --tb=short -q
   - ESLint: npx eslint {file}
   - Build: npm run build / python -m build
4. PASS → mark as AUTO-FIXED in report, continue
5. FAIL → REVERT immediately, mark as NEEDS-MANUAL in report
```

**Maximum fix attempts per file:** 3. After 3 failed attempts on same file → stop and report.

## What is NEVER Auto-Fixable

| Category | Reason |
|----------|--------|
| New files, services, or abstractions | Architectural decision |
| Refactoring (even "obvious") | Requires intent confirmation |
| Security credential rotation | Ops task, not code change |
| Changes touching > 3 files | Cross-module side effects |
| Auth/authz logic changes | Security-critical, needs review |
| SQL query modifications | Data integrity risk |
| Complex pattern replacements | Ambiguous correct form |
| Removing functionality | User intent unclear |

## Skill-Specific Allowlists

Each skill MAY define additional auto-fixable patterns beyond the safety checklist,
but only for patterns that are **provably safe**:

| Skill | Allowed auto-fix patterns |
|-------|--------------------------|
| code-audit | Missing `await`, wrong table/column name, missing cleanup in `finally` |
| security-audit | `verify=False` → `verify=True`, removing hardcoded test secrets |
| type-audit | Type narrowing (`as Error`), missing global type props, template scope wrappers, generic constraint simplification |
| e2e-bdd-test | Merge copy-paste outlines, extract Background, remove hardcoded credentials, add tags, replace sleeps with waits |
| project-hygiene | DELETE empty directories, ARCHIVE files with user confirmation |
| arch-review | Module-level `__all__` exports, missing `__init__.py` |
| comprehension-debt | Generate recommendations file (non-destructive) |
| api-sync | Generate correction code (does not modify existing files) |

## Report Format for Auto-Fixes

All skills use the same table format:

```markdown
## Fixed During Audit

| # | File | Problem | Fix | Verified |
|---|------|---------|-----|----------|
| 1 | src/api/client.ts:95 | TS18046: unknown error | Added `as Error` cast | ✅ vue-tsc pass |
| 2 | src/stores/auth.ts:66 | Missing initData type | Added to global declaration | ✅ vue-tsc pass |
| 3 | src/utils/calc.ts:42 | Missing await | Added await | ❌ REVERTED — test fail |

## Needs Manual Fix

| # | File | Problem | Why manual |
|---|------|---------|-----------|
| 1 | src/stores/auth.ts:72 | Auth logic change | Security-critical path |
```

## Standalone vs Pipeline Behavior

- **Standalone** (`/code-audit --fix`): follow this safety standard directly
- **Pipeline** (`/test-suite --full`): test-suite orchestrator decides which stages get `--fix` flag; individual skills still follow this safety standard

The safety standard applies EQUALLY in both contexts. No exceptions.
