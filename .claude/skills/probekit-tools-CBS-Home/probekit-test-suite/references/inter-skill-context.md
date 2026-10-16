---
name: inter-skill-context
description: "Protocol for passing structured context between pipeline stages"
---

# Inter-Skill Context Protocol

After each stage, build a structured context object to pass to the next stage.
This replaces generic text strings with actionable data.

**Context structure** (mental model — not JSON, just organized passing):
```
source_skill: {skill that just ran}
result: { score: X/10, gate: PASS/WARN/FAIL }
severity_counts: { critical: N, warning: N, suggestion: N, diamond: N }
hotspots: [ { file, reason, finding_count, priority: HIGH/MEDIUM } ]
findings_for_next: [
  { severity, file, line, function, title, test_hint }
]
recommendations: [ "free-text guidance for next skill" ]
```

**What each stage passes forward:**

| From -> To | Key context passed |
|-----------|-------------------|
| type-audit -> code-audit | Files with type errors, unsafe `any` casts, `ts-ignore` locations |
| arch-review -> code-audit | Files with arch violations to check at code level |
| code-audit -> unit-test | Findings with file:line:function + specific test scenarios to generate |
| code-audit -> integration-test | Uncovered findings needing real DB/API, boundary functions |
| unit-test -> integration-test | Functions with low coverage at service boundaries |
| integration-test -> e2e-bdd-test | User flows with failures, unhappy paths not covered |
| design-audit -> responsive-audit | Design token compliance findings for layout cross-reference |
| i18n-audit -> a11y-audit | ARIA label translation findings, RTL locale setup for a11y P8 check |
| responsive-audit -> a11y-audit | Touch target findings for keyboard/focus cross-reference |
| code-audit -> security-audit | Security findings (Section 4) for deeper validation, auth-related files |
| security-audit -> unit-test | Vulnerability findings needing regression tests (SQL injection inputs, etc.) |
| dependency-audit -> (independent) | Reads manifests independently, no upstream context needed |
| code-audit -> api-sync | API-related findings, error handling patterns in client code |
| api-sync -> security-audit | Auth alignment findings, CORS issues, phantom endpoints |
| api-sync -> unit-test | Divergences needing regression tests (e.g., pagination field name) |
| health-audit -> project-hygiene | Dead file findings, orphan data findings for cross-reference |
| project-hygiene -> comprehension-debt | Dead code findings feed duplication analysis |
| health-audit -> comprehension-debt | ADR currency findings, domain rules coverage gaps |
| comprehension-debt -> unit-test | High-churn files needing targeted test coverage, Red ownership files |
| e2e-bdd-test -> perf-test | Critical user journeys, endpoints with N+1 findings |

**Rules:**
- Only pass CRITICAL + WARNING findings forward (not SUGGESTION)
- Each recommendation must be actionable: include file path, function name, what to check/test
- Downstream skill reports coverage: "Covered N of M findings from code-audit context"

## Context Receipt Verification

Every receiving skill MUST log context receipt at the start of its execution:

```
CONTEXT RECEIVED from {source_skill}: {N} hotspots, {M} findings (🔴{C} 🟡{W})
```

If context is empty or missing when expected:
```
WARNING: empty context from {source_skill} — running without upstream data
```

**Receipt verification table:**

| Receiving Skill | Expected Context From | Action on Empty |
|----------------|----------------------|-----------------|
| code-audit | arch-review | WARN + run full scan (no hotspot prioritization) |
| security-audit | code-audit | WARN + run full scan (no pre-filtered security findings) |
| unit-test | code-audit, comprehension-debt | WARN + generate tests without targeted hints |
| integration-test | unit-test, code-audit | WARN + scan service boundaries independently |
| e2e-bdd-test | integration-test | WARN + derive user flows from route definitions |
| perf-test | e2e-bdd-test | WARN + test all endpoints (no priority from journeys) |
| project-hygiene | health-audit | WARN + run dead file scan independently |
| comprehension-debt | health-audit, project-hygiene | WARN + skip ADR cross-reference |
| a11y-audit | i18n-audit, responsive-audit | WARN + run full scan without ARIA/touch pre-filtering |
| api-sync | code-audit | WARN + scan API layer without pre-filtered findings |
| type-audit | (none — first analytic stage) | N/A — no upstream context expected |

**In the consolidated report**, include a Context Health section:
```
## Context Health
| Stage | Received From | Hotspots | Findings | Status |
|-------|--------------|----------|----------|--------|
| code-audit | arch-review | 5 | 12 | OK |
| security-audit | code-audit | 3 | 8 | OK |
| unit-test | code-audit | — | 0 | ⚠️ EMPTY |
```

## Finding Deduplication Protocol

Each finding across all stages receives a canonical ID:
```
canonical_id = "{file_path}:{line_number}:{category}"
```

**Categories:** SQL_INJECTION, N_PLUS_ONE, RACE_CONDITION, MISSING_AUTH, SSRF, IMPLICIT_CONTRACT, GOD_MODULE, DEAD_CODE, CONFIG_DRIFT, MISSING_TEST, SYNC_IO_IN_ASYNC, UNBOUNDED_GROWTH, MISSING_VALIDATION, SCHEMA_VIOLATION, FIELD_INCONSISTENCY

Line number: first line of affected code block.
If finding is directory-level (not line-specific): `"{dir_path}:0:{category}"`

**Before final scoring:**
1. Collect all findings from all stages
2. Group by canonical_id
3. For each group: keep highest severity, note all source stages
4. Score uses deduplicated count (not raw count)

**In the report, each finding shows:**
- `Found by: arch-review, code-audit` (comma-separated list of stages that detected this issue)
- First-seen stage determines the primary description; later stages add context
