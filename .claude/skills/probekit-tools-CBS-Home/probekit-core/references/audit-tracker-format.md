# ProbeKit Audit Tracker Format — Core Reference

Canonical format for AUDIT-TRACKER.md used by all ProbeKit skills.

## Tracker Location

Each skill writes to: `{{report_dir}}/AUDIT-TRACKER.md`
All skills share ONE tracker file per project.

## Table Format

If tracker file doesn't exist, create with this header:

```markdown
# Audit Tracker

| Date | Skill | Target | Score | 🔴 | 🟡 | 🟢 | 💎 | Key Metric | Delta |
|------|-------|--------|-------|-----|-----|-----|-----|------------|-------|
```

## Row Format

Append one row per skill run:

```
| YYYY-MM-DD | <skill-name> | <target> | <score> | N | N | N | N | <key-metric> | <delta> |
```

### Field definitions

| Field | Format | Examples |
|-------|--------|---------|
| Date | YYYY-MM-DD | 2026-03-19 |
| Skill | skill short name | arch-review, code-audit, type-audit, a11y-audit, unit-test, integration-test, e2e-bdd-test, perf-test, test-suite |
| Target | file/dir name | login.py, src/api/, framework/ |
| Score | X/10 or X.X/10 | 7/10, 6.8/10 |
| 🔴 🟡 🟢 💎 | integer counts | 2, 5, 3, 1 |
| Key Metric | skill-specific | see below |
| Delta | vs previous run | see below |

### Key Metric per skill

| Skill | Key Metric format |
|-------|------------------|
| arch-review | weighted avg |

| code-audit | score |
| unit-test | N tests, X% coverage |
| integration-test | N pass / N total |
| e2e-bdd-test | N scenarios pass/total |
| perf-test | p95=Xms RPS=Y err=Z% |
| godot-unit-test | N pass / N total, X% cov |
| type-audit | N errors, M patterns |
| a11y-audit | WCAG AA: N/11 criteria |
| test-suite | mode: X stages |

### Delta rules

| Delta value | When to use |
|-------------|-------------|
| `new` | First audit for this target |
| `+2🔴 -1🟡` | Severity counts changed vs previous entry for same target+skill |
| `all clear` | Previous had findings, now 0 |
| `no change` | Identical to previous |
| `p95+120ms p99-80ms` | Perf metrics changed (perf-test only) |
| `regression: p95+45%` | Perf regression > 20% (perf-test only) |
| `+3✅ -1❌` | Test results changed (test skills only) |
| `all green` | Previous had failures, now all pass (test skills only) |
