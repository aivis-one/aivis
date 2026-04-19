# Health Audit — Output Template

---

## Report Header

```markdown
# HEALTH-AUDIT — <target> — <YYYY-MM-DD>

**Skill:** probekit-health-audit v1.0.0
**Target:** <path> (<N files scanned>, <N directories>)
**Total Runtime Data:** <X> MB
**Environment:** <OS> (<shell>)
```

## Probe Sections

For each probe (1-7), output:

```markdown
## Probe N: <Probe Name>

**Score:** <X>/10

<findings in severity-format order: CRITICAL first, then WARNING, SUGGESTION, DIAMOND>

### Evidence

<file paths, sizes, code references, config entries>
```

If no findings for a probe:

```markdown
## Probe N: <Probe Name>

**Score:** 10/10

No issues found.
```

## Cross-Probe Analysis

```markdown
## Cross-Probe Analysis

<compound issues, root cause chains, escalated findings>
```

If none:

```markdown
## Cross-Probe Analysis

No compound issues detected.
```

## Final Scorecard

```markdown
---

## Scorecard

| # | Probe | Score | Key Evidence |
|---|-------|-------|--------------|
| 1 | Disk Bloat | <X>/10 | <brief> |
| 2 | Log Rotation | <X>/10 | <brief> |
| 3 | Log Duplication | <X>/10 | <brief> |
| 4 | DB Growth | <X>/10 | <brief> |
| 5 | Dead Files | <X>/10 | <brief> |
| 6 | Config Drift | <X>/10 | <brief> |
| 7 | Orphan Data | <X>/10 | <brief> |
|   | **Average** | **<X.X>/10** | |

---

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | N |
| WARNING | N |
| SUGGESTION | N |
| DIAMOND | N |
| **Total** | **N** |

**Quality Gate:** <PASS/WARN/FAIL>

---

## Recommended Actions

1. <most urgent fix>
2. <second priority>
3. ...
```

## Audit Tracker Entry

```markdown
| YYYY-MM-DD | health-audit | <target> | <score>/10 | <N> | <N> | <N> | <N> | <total-runtime-MB> MB | <delta> |
```
