# Pipeline Stage Ordering Rationale

Why stages run in this specific order. Each stage's position is justified by data dependencies and failure propagation.

## Ordering Principle

**"Find structural problems first, verify details later, test last."**

Stages are ordered by:
1. **Dependency** — stage N produces context that stage N+1 consumes
2. **Failure blast radius** — stages that can STOP the pipeline run earliest (fail fast)
3. **Cost** — cheaper/faster stages run before expensive ones

## Stage Order with Rationale

| Order | Stage | Why here |
|-------|-------|----------|
| 1 | **arch-review** | Finds structural issues (god modules, circular deps) that affect everything downstream. Hotspots feed all later stages. |
| 1.5 | **type-audit** | Compiler errors invalidate code-audit results (false positives from wrong types). **Blocking gate** — if types don't compile, code-audit findings are unreliable. |
| 3 | **code-audit** | Needs arch hotspots + clean types. Produces the richest context (security findings, test hints, API patterns) consumed by 5+ downstream stages. |
| 3.1 | **auto-fix** | Immediately after code-audit — fixes CRITICALs before they propagate. Later stages see the fixed code. |
| 3.2 | **api-sync** | Needs code-audit API findings. Runs before security because auth alignment issues feed security-audit. |
| 3.3 | **design cluster** | design-audit → responsive-audit → i18n-audit → a11y-audit. Internal chain: i18n feeds ARIA labels to a11y, responsive feeds touch targets to a11y. Independent of code-audit results — runs in parallel conceptually. |
| 3.5 | **security-audit** | Needs code-audit security findings + api-sync auth findings. Must run before tests so vulnerability regression tests can be generated. |
| 3.7 | **dependency-audit** | Independent (reads manifests only). Placed after security for report grouping. |
| 3.8 | **health-audit** | Independent of source code analysis. Scans runtime artifacts. Feeds dead files to project-hygiene and ADR gaps to comprehension-debt. |
| 3.85 | **project-hygiene** | Needs health-audit dead file findings for cross-reference. |
| 3.95 | **comprehension-debt** | Needs health-audit ADR/rules data + project-hygiene dead code. Feeds churn files to unit-test. |
| 4 | **unit-test** | Needs findings with file:line:function from code-audit + churn data from comprehension-debt. Generates targeted tests. |
| 5 | **integration-test** | Needs unit-test coverage gaps. Tests service boundaries that unit tests can't cover. |
| 6 | **e2e-bdd-test** | Needs integration-test unhappy paths. Tests full user journeys. |
| 7 | **perf-test** | Last — most expensive. Needs critical user journeys from e2e. Only runs if functional tests pass. |

## Why not parallel?

Some stages *could* run in parallel (design cluster vs security-audit), but:
- Sequential execution keeps context window manageable
- Each stage's context enriches the next
- Blocking gates (type-audit, code-audit) must resolve before downstream work
- Serial execution produces a deterministic, reproducible pipeline
