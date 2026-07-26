# User Guide — probekit-project-hygiene

## Invocation

### Full audit (dry-run, default)
```
project hygiene
```
or
```
/probekit-project-hygiene
```

### Fix mode (apply changes)
```
project hygiene --fix
```
Shows action plan, waits for confirmation, then applies DELETE/ARCHIVE actions.

### Focused scans
```
project hygiene --focus dead-files
project hygiene --focus deps
project hygiene --focus duplicates
```

## Output

Report saved to: `docs/01_refer/ARCHIVES/CODE-AUDIT/PROBKIT-REVIEW/HYGIENE-{YYYYMMDD}.md`

## Scoring

- **PASS** (score >= 7): < 5% waste, no critical bloat
- **WARN** (score 4-6): 5-15% waste or 1-2 critical findings
- **FAIL** (score < 4): > 15% waste or 3+ critical findings

## When to run

- After merging branches (dead code from resolved conflicts)
- Before sprint close (clean up temporary files)
- After major refactoring (orphan files from moved modules)
- Periodically (monthly hygiene check)
- After removing features (stale tests, dead imports)

## What this skill does NOT do

- Does NOT scan node_modules, .venv, or gitignored directories (use health-audit for runtime bloat)
- Does NOT analyze code quality or architecture (use code-audit, arch-review)
- Does NOT check security (use security-audit)
- Does NOT run tests (use unit-test, integration-test)

## Integration with test-suite

Included in `probekit-test-suite` pipeline as Step 4.85 (after health-audit, before comprehension-debt).
Available in modes: `--full`, `--deep`, `--health`, `--hygiene`.
