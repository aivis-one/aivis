# User Guide — probekit-type-audit

## What It Does

Runs a comprehensive TypeScript type-safety audit on your Vue 3 + TS codebase:
1. **Compiler check** — `vue-tsc --noEmit` to find all type errors
2. **ESLint type rules** — `@typescript-eslint/*` violations
3. **Pattern scan** — 10 common type-safety anti-patterns (as any, ts-ignore, template leaks, etc.)
4. **Auto-fix** — optional mode to automatically fix safe patterns

## Invocation

### Slash command
```
/type-audit                        # Full project audit
/type-audit src/stores/            # Audit specific directory
/type-audit src/api/client.ts      # Audit single file
/type-audit --fix                  # Audit + auto-fix
/type-audit --fix src/composables/ # Fix specific directory
/type-audit --strict               # Treat warnings as criticals
```

### Natural language triggers
- "check types", "проверь типы"
- "typescript audit", "ts errors"
- "type safety", "пробкит типы"
- "пробкит тайпскрипт"

## Output

- **Small scope** (< 5 files): inline in chat
- **Large scope**: saved to `docs/01_refer/ARCHIVES/CODE-AUDIT/PROBKIT-REVIEW/TYPE-AUDIT-{target}-{date}.md`
- **Audit tracker**: row appended to `AUDIT-TRACKER.md`

## Fix Mode

When invoked with `--fix` or "fix"/"починь"/"исправь":
1. Fixes are applied in severity order (CRITICAL → WARNING)
2. Each fix is verified by re-running vue-tsc
3. Failed fixes are reverted and marked NEEDS-MANUAL
4. SUGGESTION-level items are never auto-fixed

## Integration with test-suite

type-audit runs as a pipeline stage in `probekit-test-suite`:
- **Position**: after arch-review, before code-audit
- **Blocking**: if compiler errors > 0 after auto-fix → pipeline stops
- **Modes**: included in `full`, `deep`, `quality`, `quick`, `types`
- **Standalone mode**: `--types` runs only type-audit

## Examples

### Quick check after refactoring
```
/type-audit src/composables/
```
Output: inline report with compiler errors + pattern findings.

### Fix all type issues before PR
```
/type-audit --fix
```
Output: applies fixes, shows before/after compiler error count, saves report.

### Strict mode for pre-release
```
/type-audit --strict
```
Output: all warnings treated as criticals, lower score threshold.
