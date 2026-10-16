---
name: quality-gate-contract
description: "Unified quality gate thresholds for all pipeline stages"
---

# Unified Quality Gate Contract

Every stage produces a gate result:
```
Gate: PASS / WARN / FAIL
Score: X.X/10
Blocking: true/false
```

| Stage | PASS | WARN | FAIL | Blocking? |
|-------|------|------|------|-----------|
| arch-review | >= 5.0/10, 0 CRITICAL | 3.0-4.9 | < 3.0 or systemic CRITICAL | No |
| type-audit | 0 compiler errors, patterns < 5 | 0 compiler errors, patterns 5-15 | compiler errors > 0 | **Yes** (blocks code-audit) |
| code-audit | >= 7/10, 0 CRITICAL | 4-6 | < 4 | **Yes** (after auto-fix) |
| unit-test | all pass, cov >= 60% | all pass, cov < 60% | any failure | No |
| integration-test | all pass | all pass, error path gaps | any CRITICAL failure | No |
| e2e-bdd-test | all pass | all pass, minor issues | any CRITICAL failure | No |
| perf-test | thresholds met | p99 warn range | p95/p99 exceeded or err > 1% | No |
| security-audit | 0 CRITICAL, score >= 7 | 1-2 CRITICAL, score 4-6 | 3+ CRITICAL or secrets found | No |
| dependency-audit | pinning >= 8/10, 0 suspicious | pinning 5-7, warnings | unpinned deps or typosquat | No |
| health-audit | >= 6.0/10, 0 CRITICAL | 4.0-5.9 | < 4.0 or 3+ CRITICAL | No |
| api-sync | 0 CRITICAL, score >= 7 | 1-2 CRITICAL, score 4-6 | 3+ CRITICAL or 5+ phantom endpoints | No |
| design-audit | 0 CRITICAL, score >= 7 | 1-2 CRITICAL, score 4-6 | 3+ CRITICAL hardcoded values | No |
| responsive-audit | 0 CRITICAL, score >= 7 | 1-2 CRITICAL, score 4-6 | 3+ CRITICAL or no viewport meta | No |
| i18n-audit | 0 CRITICAL, score >= 7 | 1-2 CRITICAL, score 4-6 | 3+ CRITICAL or missing locale keys | No |
| a11y-audit | 0 CRITICAL, score >= 7 | 1-2 CRITICAL, score 5-6 | 3+ CRITICAL or keyboard inaccessible | No |
| project-hygiene | waste < 5%, 0 CRITICAL | waste 5-15% or 1-2 CRITICAL | waste > 15% or 3+ CRITICAL | No |
| comprehension-debt | >= 6.0/10, churn < 5% | 4.0-5.9, churn 5-8% | < 4.0 or churn > 8% | No |

## Blocking Gate + Auto-Fix

**Pipeline stops** only when the **code-audit** stage FAILs **after auto-fix attempt** (score < 4/10 with remaining CRITICALs).

**Sequence:**
1. code-audit runs, produces score
2. If score < 4 AND CRITICALs found → attempt auto-fix (see SKILL.md Auto-Fix Protocol)
3. Recalculate score after auto-fixes
4. If score still < 4 → STOP pipeline
5. If score >= 4 → continue with WARN gate

**Scoring after auto-fix:** Fixed CRITICALs are removed from the deduction formula. Score is recalculated as if they never existed. Report notes original vs post-fix score.

Non-blocking FAIL: continue, flag in AUDIT-REPORT.

## Stage Relevance

Stages marked SKIP due to relevance gate are excluded from scoring entirely. They appear in the report pipeline summary with reason but do not affect the overall quality score.
