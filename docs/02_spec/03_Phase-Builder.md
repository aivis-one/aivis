# 03_Phase-Builder
> SPEC v3.0.0 | One entry stream = one chat. All cycles execute within.
> OPEN starts the phase, WORK executes cycles, CLOSE finishes the phase.

---

## Routing

Starting a phase?                    → OPEN
Executing cycle work?                → WORK
All cycles done, ready to close?     → CLOSE

Note: all three sections execute in the SAME chat. This file is loaded once
at phase start. CLOSE is used at the end of the same chat.

**Multi-Entry Note:** If a phase has multiple entries (parallel streams),
each entry = separate chat. CLOSE runs only after ALL entries report DONE.
The last entry to finish runs the full CLOSE with phase verification.
Single-entry phases (most common) ignore this — one chat covers everything.

---

## Before You Begin

Load in chat:

□ S{N}-SPRINT.md (current sprint)
□ 01_Declaration.md
□ Current P{NN}-{name}.md
□ ARCHITECTURE-{PROJECT}.md (for Coding Standards reference — Rule 17)
□ KB L2 files and ADR files referenced in current P{NN}-{name}.md tasks (if any)
□ docs/01_refer/ENVIRONMENT.md
□ 03_Phase-Builder.md (this file)

Additional loads if this is the last phase of the sprint:
□ ROADMAP-{PROJECT}.md
□ VISION-{PROJECT}.md

Check S{N}-SPRINT.md → Current State → confirm which cycle number is next.

This is a deterministic protocol — execute immediately after loading documents.
No Session Plan confirmation required (Rule 6).

---

# OPEN: Phase Start

## Purpose
Open the phase. Load context, plan all cycles, scout the full phase scope.
Runs ONCE at the start of the phase chat.

## Step 1: Session Plan

Output full plan for the phase — all cycles, all tasks, estimated sequence.
Show which cycles are HIGH/MEDIUM/LOW risk and which can be batched.

Claude Chat outputs current Session Code.

No Human confirmation required (Rule 6 — deterministic protocol).

## Step 2: Combined Scout

Create ONE scout prompt (.md artifact per Rule 1) covering ALL phase tasks.
Claude Code reads:

□ All files and modules across all cycle scopes
□ Existing tests for all affected areas
□ Current state of any in-progress work
□ TODO/FIXME markers in scope
□ Coding Standards compliance in files to be touched
□ Patterns in existing code (output as Pattern References)
□ KB/ADR references from P{NN}-{name}.md for all tasks
  (per Rule 18 — L2 content enters via scout, not execute prompt)
□ L1 INDEX files for KB/ADR domains referenced in P{NN}-{name}.md:
  - ADR refs → load {PROJECT}-ADR-INDEX.md (resolves ADR-NNN → actual filename)
  - KB refs → load {DOMAIN}-INDEX.md (resolves topic → actual filename)
  Path: docs/01_refer/KNOWLEDGE/ADR-{PROJECT}/{PROJECT}-ADR-INDEX.md
  Path: docs/01_refer/KNOWLEDGE/KB-{DOMAIN}/{DOMAIN}-INDEX.md
□ If any task touches DB tables — Rule 7 checks:
  schema, migration SQL, cross-validation

Scout output per Rule 2 format, with **per-task scope blocks** so each
execute prompt can reference "Scout §R2" instead of re-stating findings:
□ Confirmed scope (per task block — labeled by task ID from P{NN}-{name}.md)
□ Pattern references
□ Relevant ADR/KB refs
□ Resolve ADR-NNN to actual L2 filenames via L1 INDEX ({PROJECT}-ADR-INDEX.md)
  before attempting to read ADR files (ADR files use topic-based names, not ADR-NNN.md)
□ Context / unexpected findings
□ KB/ADR Assessment (per-ref: Applicable / Not applicable / Conflict)

**Practical ceiling:** ~20 files / ~3 related task blocks per combined scout.
Beyond that, scout output becomes too long and findings blur together.

**Exception:** if phase tasks are in completely unrelated codebases with
no shared context, split into 2-3 focused scouts. Default: one scout.

**Stream scope enforcement (Rule 23):** if the phase has multiple entries,
scout ONLY files within this entry's scope.

**After Scout — STOP.** Claude Chat reviews findings, then proceeds to WORK.

---

# WORK: Execute Cycles

## Purpose
Execute all phase cycles. Each cycle produces working code + tests.
No intermediate docs, no intermediate commits, no intermediate sprint updates.

## Per-Cycle Flow

Risk determines ceremony level:

### HIGH / MEDIUM risk cycles
Scout (if not covered by Combined Scout) → Assess → Execute → Validate

- **Scout:** only if Combined Scout didn't cover this cycle's scope.
  Create scout prompt per Rule 1 + Rule 2 format.
- **Assess (mandatory for HIGH, advisory for MEDIUM):**
  **HIGH:** execute prompts include Assess step. Claude Code reads current state,
  confirms plan is feasible against actual code, outputs ASSESS REPORT → STOP →
  Human confirms → Execute. Non-negotiable.
  **MEDIUM:** Claude Chat judgment — if scout was recent and code hasn't changed
  between scout and execute, Assess may be skipped. If gap is large or scope is
  complex, include Assess. Human may override: "skip assess" or "add assess."
- **Execute prompt:** .md artifact per Rule 1, with full header
  (Risk/Scope/Anti-scope/Phase). Pre-Execution Validation per Rule 12.
  MUST NOT include git commit/push steps — deferred to CLOSE.
  Include Completion Signal per Rule 24.
- **Validate:** Claude Code runs tests, Claude Chat checks results.
  If validation fails → fix before next cycle.

### LOW risk cycles
Execute only. Scout findings already available from OPEN Step 2.

- Execute prompt may omit separate scout.
- Assess may be skipped (LOW risk = config, docs, formatting).
- MUST NOT include git commit/push steps.
- Include Completion Signal per Rule 24.
- Verify: one-liner command confirming done.

### Task Batching
Multiple LOW-risk tasks MAY be combined into a single execute prompt
when they share no file conflicts and have no decision gates between them.
Claude Chat judgment — not mandatory, not prohibited.

**Practical ceiling:** 3-4 LOW tasks per prompt. For code tasks (even LOW), 2 is
safer. For pure doc tasks (backlog updates, version bumps), 4-5 is fine.
If any single task might fail → keep it separate so failure doesn't block the batch.

**Scope:** These ceilings apply to batching multiple tasks within ONE cycle.
Cross-cycle merging is governed by Rule 16 (decision-gate test) and Batch
Prompt Delivery above — not by task count limits.

### Batch Prompt Delivery

After Combined Scout (OPEN Step 2), Claude Chat creates ONE combined execute
prompt covering all phase cycles as sequential sections — instead of creating
separate prompts per cycle.

**When to use (default for single-entry phases):**
- Combined Scout covered all cycle scopes
- No decision gate between cycles (Rule 16 test: Claude Chat will NOT review
  output of cycle N before cycle N+1 — all derived from same scout)

**Combined prompt structure:**
One .md artifact with sequential cycle sections:

    # P{NN} Combined Execute — [Phase Name]
    ## §C{NN}: [cycle name]
    [Pre-Execution Validation, intent, tasks, acceptance criteria]
    ## §C{NN+1}: [cycle name]
    [Pre-Execution Validation, intent, tasks, acceptance criteria]
    ...
    ## Completion Signal
    [Aggregate: all cycles DONE/FAILED]

One file = one copy-paste to Claude Code. No multi-message delivery.

**Rules:**
- Claude Code executes sections in order — not in parallel
- Each section's Pre-Execution Validation runs against actual codebase state
  (which includes changes from prior sections)
- Each section's Acceptance Criteria verified before proceeding to next
- If any section FAILS → Claude Code STOPS and reports. Does not continue.
- HIGH risk sections retain Gather → Validate → Apply staging inside Claude Code
- Consolidated report at the end replaces per-cycle reporting to Claude Chat

**What changes vs per-cycle prompts:**
- ONE prompt instead of N separate files
- Claude Chat reviews ONE consolidated report
- Verification Scout (CLOSE Step 2) becomes the primary quality gate
- Faster wall-clock time (no Human round-trips between cycles)

**What does NOT change:**
- Combined Scout still required before the combined execute prompt
- Pre-Execution Validation still in every section
- Acceptance Criteria still in every section
- CLOSE protocol unchanged (verification scout + phase close)
- Risk tiers unchanged (HIGH still gets staged execution within its section)

**When NOT to use:**
- Phase has multiple entries (parallel streams) — each entry is its own chat
- Scout findings were incomplete or uncertain — build sections incrementally
- Cycles have genuine decision gates (output of N determines content of N+1)
- Context overflow risk — combined prompt exceeds Claude Code context window

## Rules During WORK
- No cycle doc creation (deferred to CLOSE)
- No S{N}-SPRINT.md updates (deferred to CLOSE)
- No git commit (deferred to CLOSE)
- Execute prompts MUST NOT include git commit/push steps
- Claude Chat maintains Running SPEC Log inline per Declaration
- If Claude Code reports unexpected issues → Claude Chat decides:
  fix now, defer to backlog, or escalate to Human

## Crash Recovery
For phases with >5 cycles or >1 day duration, Human may request
an intermediate commit checkpoint at any point. At that checkpoint:
- git add + commit + push (all accumulated changes)
- Update S{N}-SPRINT.md Current State (which cycles DONE)
- Resume WORK in same chat after checkpoint

This is a safety valve, not standard flow.

---

# CLOSE: Phase Finish

## Purpose
Close the phase. Verify all work, create all docs, commit everything, close chat.
Runs ONCE after all WORK cycles are done.

## Step 1: Phase Verification

Apply Validation Anti-Bias (Rule 22).

□ All tasks from P{NN}-{name}.md completed
□ All tests passing (full suite or affected subset)
□ No TODO/FIXME left in code touched this phase
□ New code follows Coding Standards from ARCHITECTURE-{PROJECT}.md
□ No logic duplication introduced

If new modules/components were created OR this is the last phase:
□ Architecture compliance check (two-way):
  Direction 1 — Doc reflects Code (ARCHITECTURE describes what exists)
  Direction 2 — Code follows Architecture (module boundaries, patterns)
□ FILE-TREE-{PROJECT}.md verify against filesystem (if drift suspected)

If anything incomplete → fix before proceeding.

## Step 2: Verification Scout

ONE verification scout covering ALL files changed across ALL cycles in this phase.
Create scout prompt (.md artifact per Rule 1).

Claude Code checks:
□ Coding Standards (Rule 17) across all touched files
□ Logic duplication across all new code
□ Linter (if configured in ENVIRONMENT.md)
□ Tests: all passing, new functionality has tests
□ No TODO/FIXME or placeholder code
□ New modules/components list (for ARCHITECTURE update)
□ Version consistency in updated documents

Scope: git diff from phase start. Not the whole codebase.

After Scout — STOP. Claude Chat reviews. Fix issues if found.

## Step 3: Session Review

Claude Chat scans the chat:
□ Framework findings?
□ Deferred items ("do later", "next chat")?
□ Unrecorded decisions?
□ Any protocol step that felt awkward or unclear?

Findings exist → include in Close Prompt (Step 4e).
No findings → record "Session Review: no framework findings."

## Step 4: Close Prompt

ONE execute prompt (.md artifact per Rule 1) that does everything.
Include Completion Signal per Rule 24.

### 4a. Create ALL cycle docs (batch)

One .md file per cycle in:
  Single-entry: docs/03_sprint/S{N}-[name]/P{NN}-[name]/C{NN}-{name}.md
  Multi-entry:  docs/03_sprint/S{N}-[name]/P{NN}-[name]/E{NN}-[name]/C{NN}-{name}.md

Lightweight template (Tier 4):

# Cycle C[NN]: [Name]
> Phase [N]: [Phase Name] | Sprint [N]: [Sprint Name]
> Status: DONE

## Goal
[one sentence]

## Result
[2-3 sentences: what was done, what changed, notable decisions]

Status: DONE
Closed: [date]

Detail (steps, scout findings, KB/ADR decisions) lives in the chat history
and can be reconstructed. Cycle docs capture the outcome, not the process.

### 4b. Update P{NN}-{name}.md
- All Cycles table rows → DONE with dates and one-line results
- Phase status → DONE
- Phase closed date and summary

### 4c. Update ARCHITECTURE-{PROJECT}.md (if needed)
New modules/components → add to relevant section.
Tier 2 doc: version bump + Changelog row as numbered deliverable.

### 4d. Update S{N}-SPRINT.md

Current State:
  | Phase | [N]: [name] — DONE |
  | Entry | E[N] — DONE |
  | Cycle | C[last]: [name] — DONE |
  | Status | Ready for next phase / Sprint complete |
  | Tests | [N pass / N fail / N skip] |

Protocol Log — one row per cycle:
  | S{N}-P{NN}-E{NN}-C{NN} | 03_Phase-Builder | [date] | DONE |

Last Session: 3-5 sentences covering the entire phase.
Next Action: [from Step 5 routing]
For Human: [per Declaration template]

### 4e. Persist findings
If framework findings → append to Project Backlog docs/01_refer/KNOWLEDGE/BACKLOG-{PROJECT}.md
If deferred project items → append to Project Backlog
If no items → skip

### 4f. Commit and push

git add [all modified files — code + docs from entire phase]
git commit -m "phase: Phase {N} {name} — DONE"
git push

ONE commit for the entire phase.

### 4g. For Human

Per Declaration template:
## For Human
> Next chat instruction. Copy-paste.

**Session Code:** [next]
**Load:**
1. Framework: 01_Declaration.md + [next protocol].md
2. Project: ENVIRONMENT.md + [other project docs]
3. Sprint: S{N}-SPRINT.md + P{NN}-{name}.md [if applicable]
**Run:** [next protocol] — [first step]

## Step 5: Routing

Last phase of sprint?
├── YES → Sprint Readiness Check:
│    □ S{N}-SPRINT.md Success Criteria — all met?
│    □ Quality tools from ENVIRONMENT.md ready for 04_Sprint-Closer?
│    □ All known CRITICAL issues resolved?
│    If any NO → log blocker in S{N}-SPRINT.md Last Session.
│    Then: next = 04_Sprint-Closer
│    next Session Code: S{N}-Sprint-Closer
│
└── NO  → next phase
         next Session Code: S{N}-P{NN+1}-E{NN}-C{NN+1}

Output current Session Code. Include next Session Code in For Human.

---

## Chat Boundary — MANDATORY STOP

After Step 5 — this chat is DONE. Close it.

Do NOT start the next protocol in this chat.
Next phase or protocol = new chat.
Load S{N}-SPRINT.md → read Next Action → proceed.

---

[*] 03_Phase-Builder SPEC v3.0.0 * ready
One entry stream = one chat. All cycles execute within.
OPEN: session plan + combined scout (once)
WORK: execute cycles — assess/exec/validate per risk tier, no intermediate overhead
CLOSE: verify + batch docs + one commit + close chat
