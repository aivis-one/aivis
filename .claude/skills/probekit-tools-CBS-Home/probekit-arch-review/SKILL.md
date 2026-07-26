---
name: probekit-arch-review
description: "Architecture review skill — project-independent. Evaluates module boundaries, dependency direction, coupling/cohesion, layer separation, pattern consistency, error architecture, data flow, scalability, testability, evolution readiness. Produces scored report with severity markers. Triggers on: 'architecture review', 'arch review', 'review architecture', 'проверь архитектуру', 'архитектурный ревью', '/probekit-arch-review', or when structural/design issues are the focus, 'пробкит архитектура', 'пробкит арх'."
---

# arch-review v1.4.0

Project-independent architecture review skill for Claude Code.
Evaluates structural quality of any codebase against universal architecture principles.
Produces a scored report with actionable findings and severity markers.

## Configuration

review_dir: docs/01_refer/ARCHIVES/CODE-AUDIT/PROBKIT-REVIEW

## Execution Steps

**Step 1 — Identify input and environment**

Determine what to review: file, directory, or entire project.
- File/directory path → read, detect language and framework
- Path with focus hint (e.g., `/arch-review src/ -- focus on coupling`) →
  path is everything before `--` or `—`; text after is a focus hint,
  apply it as additional attention during all sections (not a filter — still run all sections)
- `--fix` flag (or words "fix", "починь", "исправь") →
  set fix_mode = true; remove flag from path
- No input → ask: "What would you like me to review architecturally? Provide a path or describe the scope."

Check for ENVIRONMENT.md, ARCHITECTURE.md, or similar docs in the project.
If found — read for architecture context before proceeding.

**Step 2 — Structural reconnaissance**

Before diving into sections, build a mental model:
1. Read directory tree (2 levels deep) to understand module layout
2. Identify entry points (main, app, index, router files)
3. Map import graph: which modules import which (sample 10-15 key files)
4. Identify configuration and dependency injection patterns
5. Note language, framework, package manager, test framework

Output: brief "Architecture Snapshot" paragraph (included in report header).

**Step 3 — Run architecture analysis**

Read `references/analysis-sections-structure.md` and `references/analysis-sections-behavior.md`.
Execute all 12 sections in order. No skipping.
Apply severity markers from `references/severity-format.md` to every finding.

**Step 4 — Pattern quality scan**

Read `references/good-patterns.md`, `references/bad-patterns.md`, and `references/diamond-patterns.md`.
Check codebase against known good, bad, and diamond architecture patterns.
Add findings as Section 13: Pattern Quality Assessment.

**Step 5 — Architecture balance scorecard**

Score 13 dimensions (0–10 each):

| Dimension | What it measures |
|-----------|-----------------|
| Modularity | Clear boundaries, single responsibility per module |
| Coupling | Low inter-module coupling, dependency injection |
| Cohesion | High intra-module cohesion, related code together |
| Layering | Clear layer separation, no layer violations |
| Consistency | Same patterns across entire codebase |
| Error Design | Coherent error hierarchy, consistent handling |
| Data Flow | Clear transformation pipeline, no hidden state |
| Scalability | Horizontal scaling readiness, no bottlenecks |
| Testability | DI, interfaces, seams for testing |
| Evolvability | Can grow without rewriting core |
| Concurrency | Thread safety, async correctness, connection pooling |
| Observability | Structured logging, metrics, health checks, correlation IDs |
| Operational Health | Data growth policies, log rotation, cleanup mechanisms, runtime hygiene |

Calculate weighted average:
- Modularity, Coupling, Cohesion: weight 1.5x (structural foundation)
- Layering, Consistency: weight 1.2x (maintainability)
- Error Design, Data Flow, Scalability, Testability, Evolvability, Concurrency, Observability, Operational Health: weight 1.0x

Final score = weighted average, rounded to 1 decimal.

**Step 6 — Produce report**

Read `references/output-template.md`.
Build final scored report.
Adapt language to the user's language.
For small input (<5 files): output report inline in chat.
For large input (directory or 5+ files): save report to `{{review_dir}}/ARCH-REVIEW-<target>-<YYYYMMDD>.md` and inform the user.

**Step 7 — Update audit tracker**

Read or create `{{review_dir}}/AUDIT-TRACKER.md`.
Append entry with: date, scope reviewed, score, CRITICAL/WARNING/SUGGESTION counts.
If previous entries exist for the same scope — show delta.

**Step 8 — Fix mode (optional)**

If fix_mode is true:
Read `probekit-core/references/auto-fix-safety.md` — follow Safety Checklist and Fix-Verify-Revert Protocol.
1. For each CRITICAL finding: check 5-point safety checklist → propose concrete refactoring, apply if safe (file moves, interface extractions, dependency inversions)
2. For each WARNING finding: same checklist → propose fix, apply if non-breaking
3. Skip SUGGESTION fixes (per core standard: never auto-fix)
4. After fixes: re-run Step 3 on modified areas, verify score improvement
5. Report using standard auto-fix table format (see core reference)

If fix_mode is false — skip this step.

## Quality Gate

The architecture review **PASSES** when:
- Score ≥ 5.0/10
- Zero CRITICAL findings

**WARN** when:
- Score 3.0–4.9/10
- CRITICAL findings exist but are isolated

**FAIL** when:
- Score < 3.0/10
- Systemic CRITICAL findings (same issue across 3+ modules)

## Quick Reference

Invoke: `/arch-review <path>` or `/arch-review src/ -- focus on coupling`

## Changelog

- **v1.4.0** — Moved comprehension debt dimensions (Contract Explicitness, Risk Governance, AI Fitness) to probekit-comprehension-debt where they belong. Removed Step 3.5 comprehension debt architecture scan. Scorecard reduced from 16 to 13 dimensions.

## Anchor

[*] arch-review v1.4.0 * ready
[>] | NEXT: user command
