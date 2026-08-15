# Comprehension Debt — Probe Definitions v1.1.0

Detailed specification for each of the 7 comprehension debt probes.

---

## Probe 1: Code Churn

**Purpose:** Measure percentage of lines rewritten within 14 days of creation — the strongest signal of "write without understanding" pattern.

**Baseline:** GitClear (211M lines, 2020-2024) shows churn grew from 3.1% to 5.7% (+84%).
7.9% of all new code in 2024 was rewritten within two weeks.

**Detection method:**
1. `git log --since="{analysis_window} days ago" --numstat` — collect all additions
2. For files with additions, check `git log --follow --diff-filter=M` within 14 days of each addition
3. Calculate: `churn_rate = lines_rewritten_within_14d / total_lines_added`
4. Break down by directory to identify hotspot areas

**Simplified method (when full analysis too slow):**
1. `git log --since="{analysis_window} days ago" --format="%H %ai" --name-only` — get commits with dates and files
2. For each file that appears in 2+ commits within 14-day windows: flag as churn
3. Calculate: `churn_file_rate = files_with_rapid_rewrites / total_files_touched`

**Thresholds:**

| Churn Rate | Level | Signal |
|-----------|-------|--------|
| < 3% | DIAMOND | Healthy — code sticks on first write |
| 3-5% | OK | Normal range (2020 baseline was 3.1%) |
| 5-8% | WARNING | Elevated — review comprehension practices |
| > 8% | CRITICAL | Systemic — code written without understanding |

**Scoring:**
- 10/10: Churn < 3%
- 8/10: Churn 3-5%
- 5/10: Churn 5-8%
- 3/10: Churn 8-12%
- 0/10: Churn > 12%

---

## Probe 2: Code Age Distribution

**Purpose:** Measure what percentage of recent changes touch code older than 30 days.
Healthy codebases modify existing code (refactoring, improvement). Comprehension-debt codebases
only add new code and never revisit old.

**Baseline:** GitClear shows "modified lines older than a month" dropped from 30% (2020) to 20% (2024).

**Detection method:**
1. `git log --since="{analysis_window} days ago" --numstat --diff-filter=M` — modified files only
2. For each modified file, check `git log --format="%ai" -1 -- {file}` before the analysis window
3. Calculate: `mature_change_rate = files_where_original_code_older_than_30d / total_files_modified`
4. Also calculate: `new_only_rate = files_only_created_never_modified / total_files`

**Thresholds:**

| Mature Change Rate | Level | Signal |
|-------------------|-------|--------|
| > 35% | DIAMOND | Team actively maintains and improves old code |
| 25-35% | OK | Healthy balance |
| 15-25% | WARNING | Bias toward new code, old code accumulating |
| < 15% | CRITICAL | "Write-only" codebase — nobody revisits |

**Scoring:**
- 10/10: > 35% mature changes
- 8/10: 25-35%
- 5/10: 15-25%
- 3/10: 10-15%
- 0/10: < 10%

---

## Probe 3: Duplication Ratio

**Purpose:** Measure copy/paste volume vs refactoring (moved code) volume.
AI generates duplicates instead of finding existing functions (limited context window).

**Baseline:** GitClear: "moved code" dropped from 24.1% (2020) to 9.5% (2024). 
2024: first year copy/paste exceeded refactoring. Duplicated blocks grew 8x.

**Detection method:**
1. Scan target directory for duplicated code blocks:
   - Functions with >80% similarity across different files
   - Identical blocks of 5+ lines in different files
   - Import patterns that suggest copy-paste (same imports in many files)
2. Estimate refactoring volume:
   - `git log --since="{analysis_window} days ago" --diff-filter=R` — renamed files
   - `git log --diff-filter=D` paired with `--diff-filter=A` — moved code
3. Calculate: `duplication_ratio = duplicate_blocks / (moved_blocks + 1)`
   - Ratio < 1: refactoring exceeds duplication (healthy)
   - Ratio > 1: duplication exceeds refactoring (unhealthy)

**Thresholds:**

| Duplication Ratio | Level | Signal |
|------------------|-------|--------|
| < 0.5 | DIAMOND | Active deduplication culture |
| 0.5-1.0 | OK | Balanced |
| 1.0-2.0 | WARNING | Duplication outpacing refactoring |
| > 2.0 | CRITICAL | Systemic duplication — each bug fix needs N updates |

**Per-duplicate severity:**
- Duplicate block < 10 lines: SUGGESTION
- Duplicate block 10-30 lines: WARNING
- Duplicate block > 30 lines or 3+ copies: CRITICAL

**Scoring:**
- 10/10: Ratio < 0.5, no duplicates > 10 lines
- 8/10: Ratio 0.5-1.0
- 5/10: Ratio 1.0-2.0
- 3/10: Ratio 2.0-3.0
- 0/10: Ratio > 3.0 or systemic 30+ line duplicates

---

## Probe 4: Context Window Fitness

**Purpose:** Measure how many modules exceed the effective AI reasoning boundary (~200 LOC).
AI sees large files but reasons poorly about them. Modules should fit in context completely.

**Reference:**
| Architecture | Typical module size | Context window fit |
|---|---|---|
| Monolithic / God class | 2,000-10,000 lines | Poor |
| Traditional layered | 200-500 per layer | Partial |
| Hexagonal / bounded context | 50-200 per unit | Complete |
| Pure functions | 5-50 lines | Perfect |

**Detection method:**
1. Count LOC for every source file in target (exclude tests, configs, migrations, generated)
2. Classify:
   - **Fit:** < 200 LOC — AI can reason completely
   - **Partial:** 200-500 LOC — AI sees it but misses cross-references
   - **Poor:** 500-1000 LOC — significant AI reasoning degradation
   - **Unfit:** > 1000 LOC — god module, AI cannot hold full context
3. Calculate: `fitness_rate = fit_files / total_source_files`

**Thresholds:**

| Fitness Rate | Level | Signal |
|-------------|-------|--------|
| > 80% | DIAMOND | Architecture designed for AI-assisted development |
| 60-80% | OK | Most modules manageable |
| 40-60% | WARNING | Significant portion exceeds AI reasoning boundary |
| < 40% | CRITICAL | Architecture hostile to AI comprehension |

**Per-file severity:**
- File < 200 LOC: OK
- File 200-500 LOC: SUGGESTION (consider splitting)
- File 500-1000 LOC: WARNING (split recommended)
- File > 1000 LOC: CRITICAL (god module)

**Scoring:**
- 10/10: > 80% files fit, no file > 500 LOC
- 8/10: 60-80% fit, max 2 files 500-1000 LOC
- 5/10: 40-60% fit
- 3/10: < 40% fit, multiple god modules
- 0/10: < 20% fit

---

## Probe 5: Ownership Clarity

**Purpose:** Identify files where nobody has clear ownership — the "Red zone" in the ownership matrix.
When code has no owner, bugs live longer and fixes are riskier.

**Detection method:**
1. `git shortlog -s -n --since="{analysis_window * 3} days ago" -- {file}` for each file
2. Classify each file:
   - **Strong owner:** 1 author with > 60% of commits
   - **Shared ownership:** 2-3 authors each with > 20%
   - **Diffuse:** > 3 authors, none with > 30%
   - **Orphaned:** No commits in 3x analysis window
3. Cross-reference with churn: high-churn + diffuse ownership = highest risk
4. Calculate: `orphan_rate = orphaned_files / total_source_files`

**Bus factor analysis:**
- `git shortlog -s -n` per directory
- Bus factor = number of authors with > 10% of commits
- Bus factor 1 = single point of failure (WARNING for critical paths)

**Thresholds:**

| Orphan Rate | Level | Signal |
|------------|-------|--------|
| < 5% | DIAMOND | Strong ownership culture |
| 5-15% | OK | Some gaps, manageable |
| 15-30% | WARNING | Significant ownership gaps |
| > 30% | CRITICAL | Nobody owns most of the code |

**Scoring:**
- 10/10: < 5% orphaned, bus factor >= 2 for all critical paths
- 8/10: 5-15% orphaned
- 5/10: 15-30% orphaned
- 3/10: 30-50% orphaned
- 0/10: > 50% orphaned or bus factor 1 across entire project

---

## Probe 6: Commit Explainability

**Purpose:** Measure whether commit messages explain what and why — without needing to read the diff.
Proxy for whether the author understood what they committed.

**Detection method:**
1. `git log --since="{analysis_window} days ago" --format="%H|%s|%b"` — hash, subject, body
2. Classify each commit:
   - **Explainable:** Subject describes change type + scope, body explains why
     (e.g., "fix: payment webhook ignores duplicate events — add idempotency check")
   - **Partial:** Subject describes what but no why
     (e.g., "fix payment webhook")
   - **Opaque:** Generic subject, no body
     (e.g., "fix bug", "update", "WIP", "changes", "asdf")
   - **AI-default:** Suspiciously detailed auto-generated message that describes
     every line changed but no motivation
3. Calculate: `explainability_rate = explainable_commits / total_commits`

**Thresholds:**

| Explainability Rate | Level | Signal |
|--------------------|-------|--------|
| > 70% | DIAMOND | Team writes for future readers |
| 50-70% | OK | Acceptable |
| 30-50% | WARNING | Most commits don't explain motivation |
| < 30% | CRITICAL | Commit history is opaque |

**Scoring:**
- 10/10: > 70% explainable
- 8/10: 50-70%
- 5/10: 30-50%
- 3/10: 15-30%
- 0/10: < 15%

---

## Probe 7: Risk Tiering

**Purpose:** Classify code by criticality (Tier 1/2/3) and verify that governance — review gates, test coverage, documentation — is proportional to risk. Critical paths with no extra governance accumulate comprehension debt fastest because failures are costliest and context is hardest to reconstruct.

**Tier definitions:**

| Tier | Criteria | Expected Governance |
|------|----------|-------------------|
| Tier 1 — Critical | Payment, auth, data deletion, security, migration | Mandatory review, >80% coverage, ADR, rules file |
| Tier 2 — Important | Core business logic, API contracts, state machines | Review recommended, >60% coverage, inline docs |
| Tier 3 — Standard | UI helpers, utilities, config, boilerplate | Standard process, basic coverage |

**Detection method:**
1. Identify Tier 1 code paths:
   - Search for payment/billing keywords, auth/session/JWT handlers, DELETE endpoints, migration scripts
   - Files in `security/`, `auth/`, `payments/`, `migrations/` directories
   - Functions with `@critical`, `# CRITICAL`, or similar markers
2. Identify Tier 2 code paths:
   - Core domain models, service layer, API route handlers
   - State machine implementations, workflow engines
   - Files with high fan-in (imported by 5+ other files)
3. For each Tier 1 path, verify governance:
   - Has dedicated test file with >80% coverage?
   - Has ADR or design doc explaining decisions?
   - Has rules file (`.claude/rules/`) covering domain invariants?
   - Has been reviewed (check git log for co-authors or review markers)?
4. For each Tier 2 path, verify proportional governance:
   - Has test coverage >60%?
   - Has inline documentation explaining business logic?
5. Calculate: `governance_gap = tier1_paths_without_full_governance / total_tier1_paths`

**Thresholds:**

| Governance Gap | Level | Signal |
|---------------|-------|--------|
| < 10% | DIAMOND | Governance proportional to risk |
| 10-25% | OK | Minor gaps in critical path governance |
| 25-50% | WARNING | Significant critical paths ungoverned |
| > 50% | CRITICAL | Most critical code has no extra governance |

**Per-path severity:**
- Tier 1 path with no tests: CRITICAL
- Tier 1 path with no ADR/docs: WARNING
- Tier 1 path with no rules file: SUGGESTION
- Tier 2 path with no tests: WARNING
- Tier 2 path with no docs: SUGGESTION

**Scoring:**
- 10/10: All Tier 1 paths fully governed, Tier 2 >80% governed
- 8/10: Governance gap < 15%, no Tier 1 paths without tests
- 5/10: Governance gap 25-50%
- 3/10: Governance gap > 50%, Tier 1 paths without tests
- 0/10: No tiering awareness, critical paths treated same as utilities
