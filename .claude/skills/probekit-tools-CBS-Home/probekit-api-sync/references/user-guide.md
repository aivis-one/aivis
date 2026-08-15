# User Guide -- probekit-api-sync

## Invocation

### Full audit (default)
```
api sync
```
or
```
/probekit-api-sync
```

### Module-scoped audit
```
api sync -- focus on auth
api sync -- focus on users
```

### Generate fix patches
```
api sync --fix
```
Generates corrected frontend API code for all CRITICAL divergences.

### Backend-only registry
```
api sync --backend-only
```
Produces endpoint registry without frontend comparison.

### Frontend-only registry
```
api sync --frontend-only
```
Produces call registry without backend comparison.

## Output

Report saved to: `docs/01_refer/ARCHIVES/CODE-AUDIT/PROBKIT-REVIEW/API-SYNC-{YYYYMMDD}.md`

## Scoring

- **PASS** (score >= 7): 0 CRITICAL divergences, all endpoints aligned
- **WARN** (score 4-6): 1-2 CRITICAL divergences, some endpoints misaligned
- **FAIL** (score < 4): 3+ CRITICAL divergences, significant API mismatch

## When to run

- After merging backend changes from main into design
- Before starting a new frontend phase that calls new API endpoints
- After adding new API modules to frontend
- During sprint close as part of quality gate

## Integration with test-suite

Included in `probekit-test-suite` pipeline as Step 4.2 (after code-audit).
Available in modes: `--full`, `--deep`, `--quality`, `--api`.
