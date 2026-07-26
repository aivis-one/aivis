# Architecture Review Report Template

## Report Format

```markdown
# ARCH-REVIEW — <target> — <date>

## Architecture Snapshot
<Brief paragraph: language, framework, module count, architectural style detected,
key patterns observed, overall impression>

## Findings Summary

| Severity | Count | Sections |
|----------|-------|----------|
| 🔴 CRITICAL | N | S1, S4 |
| 🟡 WARNING | N | S2, S5, S6 |
| 🟢 SUGGESTION | N | S3, S7, S9 |
| 💎 DIAMOND | N | S8, S10 |

## Section 1: Module Boundaries & Cohesion
<findings with severity markers>

## Section 2: Dependency Direction & Acyclicity
<findings with severity markers>

## Section 3: Coupling Assessment
<findings with severity markers>

## Section 4: Layer Separation
<findings with severity markers>

## Section 5: Pattern Consistency
<findings with severity markers>

## Section 6: Error Architecture
<findings with severity markers>

## Section 7: Data Flow & State Management
<findings with severity markers>

## Section 8: Scalability Design
<findings with severity markers>

## Section 9: Testability Assessment
<findings with severity markers>

## Section 10: Evolution Readiness
<findings with severity markers>

## Section 11: Concurrency Architecture
<findings with severity markers>

## Section 12: Observability Design
<findings with severity markers>

## Section 13: Pattern Quality Assessment
<Diamond patterns found, anti-patterns flagged>

## Architecture Balance Scorecard

| Dimension | Score | Notes |
|-----------|-------|-------|
| Modularity | X/10 | |
| Coupling | X/10 | |
| Cohesion | X/10 | |
| Layering | X/10 | |
| Consistency | X/10 | |
| Error Design | X/10 | |
| Data Flow | X/10 | |
| Scalability | X/10 | |
| Testability | X/10 | |
| Evolvability | X/10 | |
| Concurrency | X/10 | |
| Observability | X/10 | |
| **Weighted Average** | **X.X/10** | |

## Quality Gate: PASS / WARN / FAIL

## Top Recommendations
1. <Most impactful improvement>
2. <Second most impactful>
3. <Third most impactful>
```

## Audit Tracker Update

> Format: see `probekit-core/references/audit-tracker-format.md` for table format, delta rules, and field definitions.

Append row with: skill=`arch-review`, key metric=`weighted avg`.
