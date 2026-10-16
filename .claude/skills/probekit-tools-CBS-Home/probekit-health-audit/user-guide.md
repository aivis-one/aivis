# probekit-health-audit — User Guide

## What It Does

Audits **runtime artifacts** that code-level audit skills miss:
- Log files growing without rotation
- Database tables filling up without cleanup
- Dead files and directories wasting disk space
- Config policies that exist on paper but not in practice
- Legacy artifacts from previous project iterations
- Write multiplication (same event → multiple files)

## When to Use

- After noticing unexpected disk usage
- Before major releases (alongside code-audit)
- Monthly as hygiene check
- After migrations or renames (catch orphaned artifacts)
- When onboarding to a new codebase

## Invocation

```
/probekit-health-audit <target>
```

**Examples:**
- `/probekit-health-audit .` — full project audit
- `/probekit-health-audit framework/` — framework runtime health
- `/probekit-health-audit data/` — database health only
- `/probekit-health-audit --fix framework/logs/` — auto-fix log rotation

## 7 Probes

| # | Probe | Catches |
|---|-------|---------|
| 1 | Disk Bloat | Files > threshold in runtime dirs |
| 2 | Log Rotation | Missing RotatingFileHandler |
| 3 | Log Duplication | Event → multiple files |
| 4 | DB Growth | Tables without working TTL |
| 5 | Dead Files | Files with zero code references |
| 6 | Config Drift | Config says X, code does Y |
| 7 | Orphan Data | Legacy-named artifacts |

## Output

- **Small (< 5 findings):** Inline in chat
- **Large (5+ findings):** Saved to `HEALTH-AUDIT-<target>-<YYYYMMDD>.md`
- **Always:** Audit Tracker row appended

## Quality Gate

| Result | Condition |
|--------|-----------|
| PASS | Score >= 6.0, zero CRITICALs |
| WARN | Score >= 4.0, or 1-2 CRITICALs with fix path |
| FAIL | Score < 4.0, or 3+ CRITICALs |

## Flags

| Flag | Effect |
|------|--------|
| `--fix` | Auto-apply: add rotation, delete dead files (with confirmation), update configs |
| (none) | Audit-only, no changes |

## Integration with test-suite

`probekit-test-suite` includes health-audit as a pipeline stage.
Runs between `dependency-audit` and `unit-test` in `full` and `deep` modes.

## Version History

- v1.0.0 (2026-03-29): Initial release. 7 probes covering runtime health blind spot.
