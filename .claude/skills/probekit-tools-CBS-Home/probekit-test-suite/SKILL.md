---
name: probekit-test-suite
description: "Testing pipeline orchestrator for CBS HOME frontend. Runs probekit skills in sequence, gates on quality, auto-fixes safe CRITICALs, produces single consolidated AUDIT-REPORT. Modes: full (15 stages), quick (type-audit + code-audit + unit), quality (type + code + unit + integration), types (type-audit only), arch (arch-review only), deep (arch + type + code + security + health + comprehension + tests), secure (code + security + dependency), health (runtime health), comprehension (comprehension-debt only), design (design-audit + responsive-audit + i18n-audit + a11y-audit). Use when: 'run full test suite', 'test everything', 'quality check', '/probekit-test-suite', 'пробкит всё', 'пробкит полный', 'пробкит запусти'."
---

# test-suite v4.4.0 (CBS HOME)

Testing pipeline orchestrator for CBS HOME Vue 3 frontend.
Runs testing skills in logical sequence, gates on quality, auto-fixes safe CRITICALs, aggregates results into a single consolidated report.

Target: `mockups/frontend/src/` (Vue 3 + TypeScript)

## Configuration

report_dir: docs/01_refer/ARCHIVES/CODE-AUDIT/PROBKIT-REVIEW
source_dir: mockups/frontend/src
test_dir: mockups/frontend/src/__tests__

## Pipeline

relevance-gate → arch-review → **type-audit** → code-audit → auto-fix → api-sync → design-audit → responsive-audit → i18n-audit → **a11y-audit** → security-audit → dependency-audit → health-audit → project-hygiene → comprehension-debt → unit-test → integration-test → e2e-bdd-test → perf-test → consolidated-report

## Modes

| Mode | Stages | When to use |
|------|--------|-------------|
| `full` | All 15 | Pre-release, sprint close, comprehensive check |
| `design` | design-audit + responsive-audit + i18n-audit + a11y-audit | CBS HOME design system compliance |
| `quick` | type-audit + code-audit + unit-test | Fast feedback during development |
| `quality` | type-audit + code-audit + unit-test + integration-test | Thorough without E2E/perf overhead |
| `arch` | arch-review | Architecture-only analysis |
| `deep` | arch + type-audit + code-audit + security + health + comprehension-debt + unit + integration | Full depth without E2E/perf |
| `secure` | code-audit + security-audit + dependency-audit | Security-focused review |
| `health` | health-audit | Runtime health only |
| `comprehension` | comprehension-debt --deep | Comprehension debt analysis with ownership matrix |
| `api` | api-sync | Backend-frontend API alignment check |
| `hygiene` | project-hygiene | Dead files, duplicates, stale deps, git bloat |
| `types` | type-audit | TypeScript type-safety only |

Default: `quality` (if user doesn't specify mode)

## Stage Relevance Gate

**Before executing each stage**, check if it is relevant for the current project state. Skip irrelevant stages with reason logged.

**Relevance rules:**

| Stage | Skip when | Detection method |
|-------|-----------|-----------------|
| `type-audit` | No `.ts`/`.vue` files in target | Check for TypeScript/Vue source files. Skip if target is pure Python/Go/GDScript. |
| `perf-test` | No HTTP endpoints at all | Check for FastAPI/Flask app, HTTP routers, server config. Desktop with local HTTP server: SMOKE profile (10 requests per health endpoint). Production HTTP API: FULL profile. |
| `e2e-bdd-test` | No user-facing web UI | Check if frontend is Godot-only (no browser-based UI, no web routes serving HTML). |
| `dependency-audit` | < 15 direct dependencies | Count entries in requirements.txt / package.json. Below threshold = low risk. |
| `integration-test` (generation) | Service-layer coverage >= 80% | Run `pytest --cov --cov-report=json` on service layer. If coverage >= 80%: skip generation, run existing only. If < 80%: generate tests for uncovered modules. |
| `comprehension-debt` | < 50 source files in target | Count source files (exclude tests, configs, migrations). Below 50 = too small for meaningful churn/ownership analysis. |

**When a stage is skipped:**
- Log: `SKIPPED: {stage} — {reason}` (e.g., "SKIPPED: perf-test — desktop-only project, no production HTTP load")
- Record in report as `SKIP` gate with reason
- Do NOT count skipped stages in scoring

**Override:** User can force any stage with `--force-{stage}` flag (e.g., `--force-perf`).

## Auto-Fix Protocol

After code-audit (Step 4), if CRITICAL findings meet ALL conditions:
1. **Localized** — fix is within a single file, < 20 LOC change
2. **Clear logic** — the correct fix is unambiguous (wrong table name, missing await, missing cleanup)
3. **No architectural conflict** — fix doesn't change public API, service boundaries, or data model
4. **No cross-module side effects** — fix doesn't require changes in other modules
5. **Testable** — existing tests cover the affected code path

**Auto-fix workflow:**
1. Apply the fix
2. Run the full test suite (`python -m pytest tests/ -x --tb=short -q`)
3. If tests pass → mark as `AUTO-FIXED` in report, continue pipeline
4. If tests fail → **revert the fix immediately**, mark as `NEEDS-MANUAL` in report
5. If test patch needed (mock target changed, etc.) → fix test too, re-run

**What is NOT auto-fixable:**
- Anything requiring new files, new services, or new abstractions
- Refactoring (even if "obvious") — e.g., extracting a service, renaming across modules
- Security credential rotation (ops task, not code)
- Anything touching > 3 files

**Report format for auto-fixes:** Table with columns: #, File, Problem, Fix (under heading "Fixed During Audit")

## Language Routing

| Target files | Unit test skill | Other skills |
|-------------|----------------|--------------|
| `.ts/.vue` files | probekit-unit-test (Vitest) | All standard |
| `.js` files | probekit-unit-test (Vitest) | All standard |

## Quality Gates

Read `references/quality-gate-contract.md` for per-stage thresholds.
Read `references/scoring-formula.md` for overall scoring algorithm and gate rules.

## Execution Steps

**Step 1 — Parse input, load config, select mode**

Input formats:
- `/test-suite src/api/` — quality mode on directory
- `/test-suite --full framework/services/` — full mode on directory
- `/test-suite --quick framework/llm/adapter.py` — quick mode on file
- `/test-suite --arch framework/` — architecture review only
- `/test-suite --deep framework/services/` — arch + code + tests
- `/test-suite` (no path) — ask user what to test

**Config loading** (check in order, merge top-down):
1. CLI flags (highest priority)
2. `.probekit.yml` in current directory
3. `.probekit.yml` in git root
4. Defaults in this SKILL.md (lowest priority)

If `.probekit.yml` found, read sections: `paths.review_dir`, `thresholds`, `exclude.paths`, `features.skills`, `scoring.weights`.
If not found — use defaults. Do NOT require it.

Detect target language from file extensions. Select unit test skill accordingly.

**Step 1.5 — Stage relevance check**

Apply Stage Relevance Gate rules. Log skipped stages. Proceed with relevant stages only.

**Step 2 — Stage 1: Architecture Review (general)**

_Skip if mode is `quick` or `quality`._
Invoke `probekit-arch-review` on target. Record: {Gate, Score, Blocking, findings_summary}.
Build structured context (see `references/inter-skill-context.md`).

**Step 2.5 — Stage 1.5: Type Audit**

_Skip if mode is `arch`, `health`, `hygiene`, or `comprehension`._
_Check relevance gate: skip if no `.ts`/`.vue` files in target._
Invoke `probekit-type-audit` on target. Pass `--fix` if pipeline auto-fix is enabled.
Record: {Gate, compiler_errors, pattern_findings, score}.
**Blocking gate:** If compiler_errors > 0 after auto-fix attempt — **STOP pipeline**. Type errors must be resolved before code-audit can produce meaningful results.
If mode is `types` — run this stage only, then skip to Step 9.

**Step 3 — (removed, was BOGame-specific)**

If mode is `arch` — skip to Step 9.

**Step 4 — Stage 3: Code Audit**

Invoke `probekit-code-audit`. Pass hotspot files from arch stages.

**Step 4.1 — Auto-Fix CRITICALs**

If code-audit found CRITICALs, apply Auto-Fix Protocol (see above).
- For each CRITICAL: evaluate auto-fix eligibility → fix → test → confirm or revert.
- Recalculate code-audit score after fixes.
- **Blocking gate:** If Gate = FAIL after auto-fixes — **STOP pipeline**. Report and do NOT proceed.

**Step 4.2 — Stage 3.2: API Sync Audit**

_Skip if mode is `quick`, `arch`, `health`, or `comprehension`._
_Check relevance gate: skip if no `mockups/frontend/src/api/` directory exists._
Invoke `probekit-api-sync`. Pass context from code-audit (API-related findings).
If mode is `api` — run this stage only, then skip to Step 9.

**Step 4.3 — Design Cluster: design-audit + responsive-audit + i18n-audit + a11y-audit**

_Skip if mode is `quick`, `arch`, `health`, `secure`, `types`, or `comprehension`._
Run in sequence: `probekit-design-audit` → `probekit-responsive-audit` → `probekit-i18n-audit` → `probekit-a11y-audit`.
Each passes relevant findings forward (e.g., i18n ARIA labels feed a11y-audit P8 check).
If mode is `design` — run this cluster only, then skip to Step 9.

**Step 4.5 — Stage 3.5: Security Audit**

_Skip if mode is `quick`, `quality`, or `arch`._
Invoke `probekit-security-audit`. Pass security findings from code-audit.
If mode is `secure` — also run Step 4.7, then skip to Step 9.

**Step 4.7 — Stage 3.7: Dependency Audit**

_Skip if mode is `quick`, `quality`, or `arch`._
_Check relevance gate: skip if < 15 direct dependencies._
Invoke `probekit-dependency-audit`. No upstream context needed.

**Step 4.8 — Stage 3.8: Health Audit (universal)**

_Skip if mode is `quick`, `quality`, `arch`, or `secure`._
Invoke `probekit-health-audit`. Scans runtime artifacts: disk bloat, log rotation, DB growth, dead files, config drift, orphan data.
If mode is `health` — also run Step 4.9, then skip to Step 9.

**Step 4.85 — Stage 3.85: Project Hygiene**

_Skip if mode is `quick`, `quality`, `arch`, `secure`, or `api`._
_Check relevance gate: skip if < 20 git-tracked source files._
Invoke `probekit-project-hygiene`. Pass dead file findings from health-audit.
If mode is `hygiene` — run this stage only, then skip to Step 9.

**Step 4.95 — Stage 3.95: Comprehension Debt**

_Skip if mode is `quick`, `quality`, `arch`, or `secure`._
Invoke `probekit-comprehension-debt` on target.
If mode is `deep` or `full` — use `--deep` flag (include ownership matrix).
If mode is `comprehension` — use `--deep --fix`, then skip to Step 9.
Pass context: hotspot files from arch stages, churn files to unit-test for targeted coverage.

**Step 5 — Stage 4: Unit Tests**

Invoke `probekit-unit-test` (or `probekit-godot-unit-test` for .gd).
_Check relevance gate: skip godot-unit-test if no .gd files in target._
Pass findings with file:line:function for targeted test generation.
If mode is `quick` — skip to Step 9.

**Step 6 — Stage 5: Integration Tests**

_Check relevance gate: skip generation if existing coverage > 80%._
Invoke `probekit-integration-test`. Pass uncovered findings + boundary functions.
If mode is `quality` or `deep` — skip to Step 9.

**Step 7 — Stage 6: E2E/BDD Tests**

_Check relevance gate: skip if no user-facing web UI._
Invoke `probekit-e2e-bdd-test`. Skip if no user-facing endpoints.

**Step 8 — Stage 7: Performance Tests**

_Check relevance gate: skip if desktop-only project._
Invoke `probekit-perf-test`. Skip if no HTTP endpoints. Use `smoke` profile.

**Step 9 — Produce AUDIT-REPORT**

Read `references/output-template.md`. Aggregate all stage results.
Apply Finding Deduplication Protocol (see `references/inter-skill-context.md`):
1. Assign canonical IDs to all findings
2. Deduplicate by canonical_id (keep highest severity per ID)
3. Use deduplicated counts for scoring formula
Calculate overall score per `references/scoring-formula.md`.
Include `files_analyzed` count in score calculation (see scoring-formula.md v2.0.0).
**Produce ONE consolidated report:** `{{report_dir}}/AUDIT-REPORT-{YYYYMMDD}.md`
- Section 1: Fixed during audit (auto-fixes with diffs)
- Section 2: Remaining P1 (important)
- Section 3: Remaining P2 (medium)
- Section 4: Remaining P3 (recommended)
- Section 5: Architecture strengths (DIAMOND patterns)
- Section 6: Test health
- Section 7: Runtime health

**Do NOT produce intermediate per-stage reports.** One report, no duplication.

**Step 10 — Update audit tracker**

Update `{{report_dir}}/AUDIT-TRACKER.md`.

**Delta tracking:**
1. Read previous AUDIT-TRACKER entries for the same target
2. If previous report exists: load its findings by canonical_id
3. For each current finding:
   - If canonical_id found in previous report: mark as "RECURRING since {first_seen_date}"
   - If canonical_id is new: mark as "NEW"
4. In the AUDIT-TRACKER row: record count of NEW vs RECURRING findings
5. In the report P1/P2/P3 tables: populate Status column with NEW or RECURRING

## Skills NOT in Pipeline

| Skill | Reason |
|-------|--------|
| livemockup-studio | UI prototyping, not testing |
| project-map | Architecture mapping, not testing |
| simplify | Code quality improvement, not testing |

## Context Passing

Read `references/inter-skill-context.md` for the full protocol on passing structured context between stages.

## Quick Reference

Invoke:
- `/test-suite {path}` — quality mode (default)
- `/test-suite --full {path}` — all 14 stages
- `/test-suite --quick {path}` — code-audit + unit-test
- `/test-suite --arch {path}` — architecture only
- `/test-suite --deep {path}` — arch + code + security + health + unit + integration
- `/test-suite --secure {path}` — code-audit + security-audit + dependency-audit
- `/test-suite --health {path}` — runtime health audit
- `/test-suite --types {path}` — TypeScript type-safety audit only
- `/test-suite --comprehension {path}` — comprehension debt analysis with ownership matrix

## Changelog

### v4.4.0 (2026-04-14)
- **NEW:** Accessibility Audit stage (probekit-a11y-audit v1.0.0) — in design cluster
- **NEW:** Design cluster step (4.3) groups design-audit + responsive-audit + i18n-audit + a11y-audit
- **CHANGED:** Pipeline now 18 stages (added a11y-audit after i18n-audit)
- **CHANGED:** `full` mode now 15 stages, `design` mode includes a11y-audit
- **CHANGED:** Inter-skill context: i18n-audit feeds ARIA label findings to a11y-audit

### v4.3.0 (2026-04-13)
- **NEW:** Type Audit stage (probekit-type-audit v1.0.0) — Step 2.5 in pipeline
- **NEW:** `--types` mode — standalone TypeScript type-safety audit (vue-tsc + ESLint + pattern scan)
- **CHANGED:** Pipeline now 17 stages (added type-audit after arch-review, before code-audit)
- **CHANGED:** `full`, `deep`, `quality`, `quick` modes now include type-audit stage
- **CHANGED:** Type-audit is a blocking gate — compiler errors must be zero before code-audit runs

### v4.2.0 (2026-04-12)
- **NEW:** Project Hygiene stage (probekit-project-hygiene v1.0.0) — Step 4.85 in pipeline
- **NEW:** `--hygiene` mode — standalone dead files, duplicates, stale deps, git bloat check
- **CHANGED:** Pipeline now 16 stages (added project-hygiene after health-audit)
- **CHANGED:** `full`, `deep`, `health` modes now include project-hygiene stage

### v4.1.0 (2026-04-12)
- **NEW:** API Sync Audit stage (probekit-api-sync v1.0.0) — Step 4.2 in pipeline
- **NEW:** `--api` mode — standalone backend-frontend API alignment check
- **CHANGED:** Pipeline now 15 stages (added api-sync after auto-fix, before design-audit)
- **CHANGED:** `full`, `deep`, `quality` modes now include api-sync stage

### v3.3.0 (2026-04-11)
- **MERGED:** `probekit-motherboard-audit` absorbed into `probekit-motherboard-audit-bogame` (standalone, 18 probes)
- **NEW:** Density-normalized scoring formula (scoring-formula.md v2.0.0) — comparable across codebase sizes
- **NEW:** Finding Deduplication Protocol — canonical IDs prevent double-counting across stages
- **NEW:** Delta tracking — findings marked NEW or RECURRING since {date}
- **NEW:** Relevance gate: comprehension-debt skips if < 50 source files
- **CHANGED:** Pipeline reduced from 15 to 14 stages (motherboard-audit merged)
- **CHANGED:** perf-test relevance gate: 3-tier SKIP/SMOKE/FULL (detects server mode)
- **CHANGED:** integration-test relevance gate: checks coverage %, not test count
- **CHANGED:** `--motherboard` mode: now single stage (motherboard-audit-bogame)

### v3.2.0 (2026-04-10)
- **NEW:** Motherboard Audit stages — `probekit-motherboard-audit` + `probekit-motherboard-audit-bogame`
- **NEW:** `--motherboard` mode — standalone MB + TZ-SPEC validation
- **CHANGED:** `deep` and `full` modes now include motherboard validation
- **CHANGED:** `full` mode now has 15 stages (was 13)
- **CHANGED:** AUDIT-REPORT Section 9: Motherboard Health added
- **CHANGED:** Relevance gate: motherboard-audit skipped if no JSON files in motherboards/

### v3.1.0 (2026-04-10)
- **NEW:** Comprehension Debt stage — runs `probekit-comprehension-debt` for churn, duplication, ownership, context window fitness
- **NEW:** `--comprehension` mode — standalone comprehension debt analysis with ownership matrix
- **CHANGED:** `deep` mode now includes comprehension-debt stage
- **CHANGED:** `full` mode now has 13 stages (was 12)
- **CHANGED:** AUDIT-REPORT Section 8: Comprehension Debt added to consolidated output
- **CHANGED:** Inter-skill context: health-audit feeds ADR/rules gaps to comprehension-debt, comprehension-debt feeds churn files to unit-test

### v3.0.0 (2026-04-05)
- **NEW:** Auto-Fix Protocol — automatically fixes safe CRITICALs (localized, < 20 LOC, testable), reverts on test failure
- **NEW:** Stage Relevance Gate — skips irrelevant stages based on project state (desktop-only, no web UI, low deps)
- **NEW:** Consolidated report format — single AUDIT-REPORT with Fixed/P1/P2/P3 sections, no intermediate reports
- **CHANGED:** Output template now produces one document instead of SUITE-REPORT + separate stage reports
- **CHANGED:** Blocking gate now applies AFTER auto-fix attempt (not before)

### v2.5.0
- Initial release with 12-stage pipeline, 7 modes, quality gates

## Anchor

[*] test-suite v4.4.0 * ready
[>] | NEXT: user command
