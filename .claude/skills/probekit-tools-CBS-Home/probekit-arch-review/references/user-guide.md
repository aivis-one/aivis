# arch-review — User Guide

## What It Does

Evaluates the structural quality of any codebase against universal architecture principles.
Checks 10 dimensions: modularity, coupling, cohesion, layering, consistency, error design,
data flow, scalability, testability, and evolvability.

## How to Invoke

```
/arch-review src/                          # Review directory (quality mode)
/arch-review src/ -- focus on coupling     # Review with focus hint
/arch-review src/ --fix                    # Review + auto-fix critical/warning
/arch-review framework/services/llm/       # Review specific module
```

## What You Get

- **Architecture Snapshot:** Brief structural overview
- **10-Section Analysis:** Module boundaries, dependencies, coupling, layers, patterns,
  errors, data flow, scalability, testability, evolution readiness
- **Pattern Quality Scan:** Diamond patterns (good) and anti-patterns (bad)
- **Balance Scorecard:** 10-dimension score with weighted average
- **Quality Gate:** PASS / WARN / FAIL with reasoning
- **Top Recommendations:** 3 most impactful improvements

## Severity Levels

| Marker | Meaning | Action |
|--------|---------|--------|
| CRITICAL | Will cause bugs/data loss | Fix now |
| WARNING | Real consequences | Fix soon |
| SUGGESTION | Improvement opportunity | Backlog |
| DIAMOND | Exceptional quality | Preserve |

## Report Location

Reports saved to: `docs/01_refer/ARCHIVES/CODE-AUDIT/PROBKIT-REVIEW/ARCH-REVIEW-<target>-<date>.md`

## Works With

- Any language (Python, GDScript, JS/TS, Go, Rust, etc.)
- Any framework
- Any project size
- Standalone or as part of `/test-suite` pipeline
