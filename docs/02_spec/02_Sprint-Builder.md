# 02_Sprint-Builder
> SPEC v3.0.0 | Strategic sprint planning + phase setup — receives decisions from 06_Brain-Next
> Triggered by: after 06_Brain-Next (or project start via Spec-Install)
> Sequence: 06_Brain-Next → 02_Sprint-Builder → 03_Phase-Builder

---

## Purpose

Strategic planning for a new sprint AND tactical phase setup in ONE chat.
Review vision and architecture using KB/ADR context from 06_Brain-Next, define sprint
scope, scout codebase, plan all phases with cycles, create all P{NN}-{name}.md files
and S{N}-SPRINT.md.

Architectural debates happen in 06_Brain-Next (before this protocol). This protocol
receives ready decisions and ROADMAP recommendations. If a question arises mid-sprint,
log it in Project Backlog — it will be resolved at the next 06_Brain-Next session.

Output: S{N}-SPRINT.md + all P{NN}-{name}.md files + phase folders.

---

## Before You Begin

Load in chat:

□ 01_Declaration.md
□ VISION-{PROJECT}.md
□ ARCHITECTURE-{PROJECT}.md
□ ROADMAP-{PROJECT}.md (strategic)
□ docs/01_refer/KNOWLEDGE/BACKLOG-{PROJECT}.md
□ Previous sprint SNAPSHOT (if exists)
□ CODE-AUDIT-S[N-1].md (if exists — detailed findings context for Balance Review)
□ KNOWLEDGE-{PROJECT}.md (L0 — combined KB + ADR) from docs/01_refer/KNOWLEDGE/
□ L1 domain indexes — only domains referenced in ROADMAP-{PROJECT}.md for this sprint
  (load from docs/01_refer/KNOWLEDGE/KB-{domain}/{DOMAIN}-INDEX.md)
□ RETRO-S[N-1].md (from docs/01_refer/ARCHIVES/RETRO/ — if exists)
□ BRAINEXT-S[N-1].md (from docs/01_refer/ARCHIVES/BRAINEXT/ — if exists)
□ docs/01_refer/ENVIRONMENT.md


No S{N}-SPRINT.md yet — it will be created during Step 7 of this protocol.

Human confirmation of Session Plan required before proceeding (Rule 6).

---

## Step 1: Review Vision

> **Gate:** VISION-{PROJECT}.md obviously current and no direction change possible?
> → YES: confirm in one sentence, proceed to Step 2.
> → NO or UNSURE: run full review below.

Read VISION-{PROJECT}.md. Answer each question explicitly:

□ The problem we're solving — is it still painful?
□ The target user — unchanged?
□ The solution approach — still the best option?
□ Did the last sprint reveal something that changes the picture?


**HARD GATE:** If any answer is NO or UNSURE — log as open question for next
06_Brain-Next session. Human must confirm direction before S{N}-SPRINT.md is created.

If VISION-{PROJECT}.md needs updating — create execute prompt. Claude Code updates the file.

**Tier 2 versioning:** If VISION-{PROJECT}.md is modified, the execute prompt must include as
a numbered deliverable: version bump (MAJOR.MINOR +0.1) + changelog row.

---

## Step 2: Review Architecture

> **Gate:** ARCHITECTURE-{PROJECT}.md reflects current system, no gaps, no stale sections?
> → YES: confirm in one sentence, proceed to Step 3.
> → NO: run full review below.

Read ARCHITECTURE-{PROJECT}.md. Ask:

□ Does it reflect current system state?
□ What architectural gaps exist?
□ What technical debt is relevant to this sprint?
□ Coding Standards section exists and is current?
□ Standards still match how code is actually written?


Note any architectural questions — log to Project Backlog for next 06_Brain-Next session
if they cannot be resolved here.

**Tier 2 versioning:** If ARCHITECTURE-{PROJECT}.md is modified, the execute prompt must include
as a numbered deliverable: version bump (MAJOR.MINOR +0.1) + changelog row.

---

## Step 3: Define Sprint Scope

Claude Chat proposes sprint scope based on:
- Strategic ROADMAP-{PROJECT}.md goal for this sprint
- Carry-forward items from previous SNAPSHOT
- BACKLOG-{PROJECT}.md carry-forward items
- Architectural decisions from 06_Brain-Next (BRAINEXT-RECS-S[N-1].md)
- L0 index context (KNOWLEDGE-{PROJECT}.md)

Define:

Sprint Goal: [one sentence — what this sprint delivers]
Out of Scope: [what is explicitly NOT in this sprint]
Success Criteria: [how we know it's done]


Present to Human. Human confirms or adjusts.

**Sprint Capacity Check (mandatory):**

Target: 40-60 cycles per sprint. Count planned cycles across all phases.

- Below 40 → sprint is underfilled. Pull additional items from:
  1. BACKLOG-{PROJECT}.md (P1/P2 items first)
  2. ROADMAP S{N+1} scope (next sprint's planned work)
  3. ROADMAP S{N+2} if still underfilled
  Mark each pulled item in source: "→ S{N}" with date.
- 40-60 → healthy range. Proceed.
- Above 60 → sprint is overfilled. Cut lowest-priority phases or
  move Should-Have phases to S{N+1}.

Re-present to Human after capacity adjustment.

**Backlog Assignment Marking:**

Every item pulled from BACKLOG-{PROJECT}.md into this sprint must be marked in-place:

| ID | ... | Status | Notes |
|----|-----|--------|-------|
| F128 | ... | → S{N} P{NN} | Assigned [date] |

This prevents duplicate assignment in future sprints. Items marked "→ S{N}"
are consumed — they appear in P{NN}-{name}.md tasks, not re-pulled.

**Look-Ahead: S{N+1} direction (lightweight):**

Before finalizing scope, Claude Chat sketches the likely direction for the NEXT sprint
(S{N+1}) based on ROADMAP-{PROJECT}.md. One paragraph — not formal planning:

- What S{N+1} will likely focus on
- Which deliverables from S{N} are prerequisites for S{N+1}
- Any scope that should be deferred from S{N} to S{N+1} (or vice versa)

Purpose: prevents over-scoping the current sprint and ensures clean handoff.
This is a vector, not a plan — S{N+1} will be properly planned in its own Sprint-Builder.

**Metrics review (if previous SNAPSHOT has Sprint Metrics table):**

Claude Chat reviews trends across sprints:

□ CRITICAL/HIGH findings: trending up? → flag to Human,
  consider adding a quality-focused phase or cycle
□ Test count vs LOC: tests growing proportionally?
  If not → flag coverage gap risk
□ Any metric with 3+ sprints of continuous degradation? → mandatory discussion


If no previous metrics or first sprint — skip.

**Balance Review (mandatory if previous SNAPSHOT has Balance findings):**

Claude Chat reads S[N]-SNAPSHOT.md → Codebase Balance Summary and Carry-Forward →
Balance HIGH items.

For each Balance HIGH item:

□ INCLUDE in this sprint scope → assign to specific phase area
□ DEFER → with written rationale why acceptable to wait


Present decisions to Human. Human confirms.

Rules:
- HIGH items cannot be silently ignored — explicit decision required
- Deferred HIGH items carry forward automatically — they will reappear at next
  02_Sprint-Builder
- If same HIGH item deferred 2+ consecutive sprints → flag to Human as recurring
  debt (not a blocker, but requires acknowledgment)
- MEDIUM/LOW items: review at Claude Chat's discretion, no mandatory decision required

If no previous SNAPSHOT or no Balance findings — skip this sub-section.

---

## Step 4: Scout Codebase

> Run BEFORE phase definition so scout findings inform planning.
> **Skip conditions (any one is sufficient):**
> - Brand new project (no code to scout)
> - CODE-AUDIT-S{N-1} loaded in Before You Begin (audit replaces scout)
> - Full-project audit loaded (covers codebase state comprehensively)
>
> If none apply — scout first, then proceed to Step 5.

Create scout prompt. Claude Code reads:

□ Current module/file structure relevant to this sprint
□ Existing test files for affected areas
□ Any interfaces or contracts this sprint will touch
□ State of modules targeted by Balance items (if any)


Output: findings that will inform P{NN}-{name}.md content and phase distribution.

**After Scout — STOP. Claude Chat reviews.**

---

## Step 5: Plan All Phases

For each phase, Claude Chat defines:

Phase [N]: [Name]
  Cycles:
    C[NN]: [goal — one sentence]
    C[NN+1]: [goal — one sentence]
    ...
  Tests:
    - [test scenario 1]
    - [test scenario 2]
  Entry condition: [what must be true before this phase starts]
  Exit condition: [what must be true to close this phase]


**Phase verification:** The last working cycle of each phase includes phase
verification and closure as part of its PART 2 (see 03_Phase-Builder PART 2 Step 1).
No dedicated phase-close cycle is needed.

**Sizing guidance:** Aim for 3-7 phases per sprint, 3-9 cycles per phase.
Each phase should be completable in 1-3 weeks. Fewer cycles for focused
deliverables, more for cross-cutting work. Phases with only 1-2 cycles
are likely too granular — merge with adjacent phase or expand scope.

**KB/ADR Reference Assignment (Rule 18):**

For each task, Claude Chat checks L0 indexes (KNOWLEDGE-{PROJECT}.md) and L1 domain
indexes loaded in Before You Begin. Write specific file paths into P{NN}-{name}.md task
descriptions:
- KB ref: path to L2 topic file if task relates to a KB domain
- ADR ref: path to ADR file if task is constrained by an architectural decision
- If no relevant KB/ADR exists for a task → omit the ref fields (no empty placeholders)

**Phase distribution principles:**

- **Dependency-first** — phases that are prerequisites go before the phases that depend
  on them. Never schedule a dependent phase before its dependency is complete.
- **Spike-early** — if any phase carries architectural uncertainty or requires a
  technology decision, move a validation spike into the first phase.
- **Must-have first** — P1 phases go early. If the sprint runs short on time, later
  phases can be cut.
- **One coherent deliverable per phase** — each phase should produce something
  meaningful and testable on its own.
- **Balance items by module affinity** — integrate balance items into the phase that
  works on that module. Balance work lives next to feature work — not in a separate
  "debt phase."
- **No L0 protocol overlap** — phase deliverables must not duplicate L0 protocol
  outputs (CODE-AUDIT-SN, SNAPSHOT-SN). These are handled by their dedicated protocols.
- **Sprint Close is L0** — do NOT allocate cycles for Sprint Close. Do NOT create a
  Sprint Close phase in S{N}-SPRINT.md Phases section. Sprint Close appears ONLY in
  Protocol Log as S{N}-Sprint-Closer.
- **Code audit prohibition** — never plan code-audit, code-review, or security-audit
  as a cycle task inside a phase. Code audit is exclusively handled by 04_Sprint-Closer Part 1.

**Stream Planning (parallel entries within a phase):**

After defining phases, Claude Chat evaluates each phase for parallelism:

Can this phase be split into independent streams with zero file overlap?
├── YES → define entries (E90, E91, ... — global numbering)
│    Before assigning: check previous sprint's phase docs (Streams tables)
│    for last Entry number used. If first sprint with E{NN} — start at E90.
│    Like cycles: E{NN} numbers never reset across the project.
│    **Entry minimum:** Each entry must have ≥3 cycles. If a stream has only 1-2 cycles,
│    merge it into the main entry (E{NN}) or expand its scope. Overhead of parallel
│    coordination is not justified for tiny streams.
│    **Entry fix rule:** If an entry has <3 cycles, add cycles from adjacent
│    scope or expand task granularity. Never merge entries to remove parallelism —
│    that defeats the purpose. Fixing underfilled entries = expand, not collapse.
│    For each entry:
│    - Name: [descriptive stream name]
│    - Scope: [explicit file/module list — no overlap allowed]
│    - Cycles: [which cycles belong to this entry]
│    - Dependencies: [does this entry depend on another entry finishing first?]
│
│    Overlap Check (mandatory):
│    □ List all files in E{NN} scope (first entry)
│    □ List all files in E{NN+1} scope (etc.)
│    □ Intersection must be EMPTY
│    □ If intersection is non-empty → restructure: merge into one entry
│      or move overlapping files to a sequential phase
│
└── NO  → single entry (still gets global E{NN}), no Streams section needed in P{NN}-{name}.md

Rules:
- Entry dependencies (E91 depends on E90) are allowed but must be declared.
  Dependent entries start only after their dependency is DONE.
- If all cycles in a phase are sequential → single entry (default).
- Stream planning produces the Streams section for P{NN}-{name}.md.
- Entry numbers are globally unique and assigned here — used in Session Codes throughout execution.

**When NOT to create parallel entries:**
- All tasks touch the same module/files (overlap inevitable)
- Tasks are sequentially dependent (B waits for A's output)
- Phase is small (≤4 cycles total — splitting doesn't accelerate)
- High-level work: architecture design, ADR drafting, documentation — one stream thinks, not two
- Uncertain scope: if you can't clearly partition files upfront, don't parallelize

**Default:** Single entry. Parallel entries = optimization, not obligation.

**After listing phases — prioritize explicitly:**

| Priority | Meaning | Action if time runs out |
|----------|---------|------------------------|
| **Must have** | Sprint is not complete without this | Cannot cut |
| **Should have** | Important but deliverable without it | Cut to next sprint |
| **Nice to have** | If time allows | Drop without guilt |

Present phases with priorities to Human. Human confirms or adjusts.

---

## Step 6: Create All P{NN}-{name}.md Files

Create ONE execute prompt that creates all phase folders and P{NN}-{name}.md files.

**Claude Code creates files on disk.** Never create phase/sprint docs as
downloadable chat artifacts — always as execute prompts for Claude Code (Rule 1).
Claude Code writes files, validates structure, and commits. Human does not
manually place files into project folders.

**Batch splitting for large sprints:** If total file content exceeds ~400 lines,
split into 2-3 execute prompts (e.g., S12-SPRINT.md + P64-P66 in batch 1,
P67-P69 in batch 2). Claude Code may truncate or degrade on very large single prompts.

**Mandatory validation after file creation:** Execute prompt must end with
a verification step where Claude Code confirms: all files exist, all cycle
numbers are sequential, all entry numbers match, no content truncation
(check line count of each file vs expected).

For each phase:

docs/03_sprint/S{N}-[name]/P{NN}-[name]/              ← create phase folder
docs/03_sprint/S{N}-[name]/P{NN}-[name]/P{NN}-{name}.md   ← create phase doc

# If phase has parallel entries, also create entry subfolders:
docs/03_sprint/S{N}-[name]/P{NN}-[name]/E{NN}-[name]/  ← per-entry subfolder for cycle docs


Phase document template (Tier 4 — NO SPEC version in header):

# Phase [N]: [Name]
> Sprint [N]: [Sprint Name]
> Status: NOT STARTED

## Goal
[one sentence]

## Entry Condition
[what must be true before this phase starts]

## Exit Condition
[what must be true to close this phase]

## Streams
(omit this section if phase has a single entry — E1 implied)

| Entry | Name | Scope (files/modules) | Status |
|-------|------|-----------------------|--------|
| E1 | [name] | [file/module list] | TODO |
| E2 | [name] | [file/module list] | TODO |

## Tasks

Task 1: [name]
Scope: [what to build]
Entry: [E1 / E2 — which stream owns this task]
ADR ref: [path if applicable]
KB ref: [path if applicable]
Test: [what to verify]

## Cycles
| Cycle | Entry | Name | Status | Date | Result |
|-------|-------|------|--------|------|--------|
| C[NN] | E1 | [name] | TODO | | |
| C[NN+1] | E2 | [name] | TODO | | |

## Tests Summary

| # | Test | Command/Check |
|---|------|---------------|
| T1 | [test name] | [how to verify] |

## Exit Criteria

- [ ] [criterion 1]
- [ ] [criterion 2]


**Backlog marking task (mandatory in first phase):** The first phase of every sprint
must include a task: "Mark all consumed BACKLOG items as → S{N} P{NN}."
This task lives in the phase doc — not deferred to a separate step.
Items are marked during the first cycle that touches BACKLOG-{PROJECT}.md.

**After creation — STOP.**

---

## Step 7: Create S{N}-SPRINT.md

Create execute prompt. Claude Code creates:

docs/03_sprint/S{N}-[name]/S{N}-SPRINT.md

### Embedded S{N}-SPRINT.md Template

```markdown
# SPRINT
> [Project Name] | Sprint [N]: [Name]
> Load this file + docs/02_spec/01_Declaration.md + docs/01_refer/ENVIRONMENT.md
> at the start of every working chat.

---

## SPEC
| File | Path |
|------|------|
| Declaration | docs/02_spec/01_Declaration.md |
| Protocols | docs/02_spec/ |

---

## Environment
> See: docs/01_refer/ENVIRONMENT.md
> Override below ONLY if this sprint differs from project defaults.

---

## References
> Stable paths to project documents. Update only if files move.

| Doc | Path |
|-----|------|
| VISION | docs/01_refer/VISION-{PROJECT}.md |
| ARCHITECTURE | docs/01_refer/ARCHITECTURE-{PROJECT}.md |
| ROADMAP | docs/01_refer/ROADMAP-{PROJECT}.md |
| KNOWLEDGE-INDEX | docs/01_refer/KNOWLEDGE/KNOWLEDGE-{PROJECT}.md |
| ENVIRONMENT | docs/01_refer/ENVIRONMENT.md |
| FILE-TREE | docs/01_refer/FILE-TREE-{PROJECT}.md |
| BACKLOG | docs/01_refer/KNOWLEDGE/BACKLOG-{PROJECT}.md |
| RETRO-SN | docs/03_sprint/S{N}-[name]/S[N]-RETRO.md |

---

## Goal
[one sentence — what this sprint delivers]

## Success Criteria
- [criterion 1]
- [criterion 2]

## Out of Scope
- [item]

---

## Phases

### Phase [N]: [Name]
**Goal:** [one sentence]
**Cycles:** approximately [N-M] 

### Phase [N+1]: [Name]
**Goal:** [one sentence]
**Cycles:** approximately [N-M] 

---

## Carry-Forward from S[N-1]
- [item from previous snapshot]

## Balance Items (from S[N-1] audit)

| # | Area | Finding | Decision | Target Phase |
|---|------|---------|----------|-------------|
| 1 | [module/area] | [what is disproportionate] | Include / Defer | P[N] or "deferred — [reason]" |

If no previous balance findings: "First sprint — no prior balance data."

## Key Decisions
- [ADR references from 06_Brain-Next session]

---

## Sprint Context
> Brief history — what came before this sprint.
> Copy sprint table from ROADMAP-{PROJECT}.md. Update status column here as sprints close.

| Sprint | Status |
|--------|--------|
| S1: [Name] | DONE |
| S[N]: [Name] | IN PROGRESS |

---

## Current State
> The most critical section. Must be accurate at the start of every chat.

| Item | Value |
|------|-------|
| Phase | [N]: [Phase Name] — [NOT STARTED / IN PROGRESS / DONE] |
| Entry | E[NN]: [Entry Name] — [NOT STARTED / IN PROGRESS / DONE] |
| Cycle | C[NN]: [short name or "not started"] |
| Status | [One sentence: what is the situation right now] |
| Tests | [N pass / N fail / N skip] |

---

## Protocol Log
> Record of every protocol run in this sprint. Add a row after EVERY session.
> Cycle column uses Session Code (see 01_Declaration → Session Code table).
> 04_Sprint-Closer spanning multiple sessions: keep row IN PROGRESS until fully done.
> Skipped mandatory steps: record as "SKIPPED — [reason]", not omit.

| Cycle      | Protocol              | Date         | Status |
|------------|-----------------------|--------------|--------|
| S[N]-SB     | 02_Sprint-Builder     | [YYYY-MM-DD] | DONE   |
| S[N]-P01-E90-C01 | 03_Phase-Builder P1   | [YYYY-MM-DD] | DONE   |
| S[N]-P01-E90-C01 | 03_Phase-Builder P2   | [YYYY-MM-DD] | DONE   |

---

## Last Session
> 3-5 sentences: what was done, what decisions were made, what's notable.

[What was done. What decisions were made. Any blockers encountered.]

---

## Next Action
> One concrete action. Not "continue work" — exactly what protocol or step to run.

[Exact next step]

---

## For Human
> Copy-paste instruction for opening the next chat. Update at every Phase-Builder PART 2.
> Must be actionable without reading anything else.

**Next chat:**
1. Load: S{N}-SPRINT.md (this file)
2. Load: docs/02_spec/01_Declaration.md
3. Load: docs/01_refer/ENVIRONMENT.md
4. [Load: protocol file + phase file + other docs as specified]
5. First message: [Project] C[NN]: [Cycle Name] (E[NN])

---

## Plan vs Reality
> Filled during 04_Sprint-Closer at sprint close. Empty while sprint is active.

| Aspect | Planned | Actual | Delta |
|--------|---------|--------|-------|
| Phases | — | — | — |
| Cycles | — | — | — |
| Duration | — | — | — |

### What Worked
(filled at close)

### What Didn't
(filled at close)

### Carry Forward
(filled at close)

---
*S{N}-SPRINT.md*
*[Project Name] | Sprint [N]: [Name]*
```

---

*S{N}-SPRINT.md is a reference document — created once, updated live during execution.*

### Plan Validation Gates

Plans iterate before execution. This is intentional, not a deficiency.

```
v1.0 (draft) → validate → issues → v1.1 (fix) → validate → v1.2 → ... → vN.0 (approved)
```

**Minimum:** 1 validation pass (every plan).
**Complex plans:** 2-3 passes. Architecture-impacting plans: mandatory cross-validation
(Claude Chat + Claude Code independently assess — see 06_Brain-Next §Cross-Validation).

**What each pass checks:**
- Completeness: all declared changes present
- Consistency: no contradictions within plan or against existing docs
- Cascade: every change traced to downstream references
- Feasibility: code-level verification where applicable (Assess step)

Plan that doesn't iterate is likely under-validated.
Plan with 3+ iterations is normal for architecture-level changes.

**Human gate:** Human approves final version before ANY execution begins.
No partial execution of unapproved plans.

Validation standard: `docs/02_spec/07_Validation.md`
**Decision framework:** For ambiguous scope decisions, apply `docs/02_spec/Resolution.md`.
Produces structured decisions with Was/Becomes, cascade analysis, and effort estimates.

**After creation — STOP.**

---

## Step 8: Close — Universal Close Flow

### 8a. Verify Completion

□ Step 1 (Vision): confirmed or updated
□ Step 2 (Architecture): confirmed or updated
□ Step 3 (Scope): Human confirmed
□ Step 4 (Scout): DONE or skipped (new project)
□ Step 5 (Plan): all phases defined, Human confirmed
□ Step 6 (P{NN}-{name}.md files): all created
□ Step 7 (S{N}-SPRINT.md): created with Protocol Log entries

**Executable verification (mandatory):** Create execute prompt for Claude Code.
Replace S{N} with actual sprint number in all commands below.

Claude Code runs these checks and reports results:

1. ROADMAP updated: grep "IN PROGRESS" docs/01_refer/ROADMAP-{PROJECT}.md → expect current sprint
2. BACKLOG items marked: grep -c "→ S[actual_number]" docs/01_refer/KNOWLEDGE/BACKLOG-{PROJECT}.md → expect ≥10
3. Source files deleted (if any _-prefixed consumed files existed): ls docs/01_refer/_*.md → expect "no such file"
4. S{N+1} look-ahead: grep "Look-Ahead" in S{N}-SPRINT.md → expect found
5. Protocol Log: grep "S{N}-SB" in S{N}-SPRINT.md → expect found
6. For Human: grep "First message:" in S{N}-SPRINT.md → expect found
7. Source file consumption: For each file listed in Before You Begin that will be
   deleted after planning (audit reports, recommendation docs, task lists):
   - Read the file
   - List every actionable item (recommendations, findings, tasks, deprecation notes)
   - For each item: verify it exists in EITHER a P{NN} phase doc (this sprint)
     OR BACKLOG-{PROJECT}.md (future sprint)
   - Report: [N] items total, [N] in phases, [N] in BACKLOG, [N] MISSING
   - If MISSING > 0 → create execute prompt to add missing items to BACKLOG
   - Only after 0 MISSING → files safe to delete

Output: checklist with PASS/FAIL per item. If ANY FAIL → fix before committing.
This replaces manual verification — Claude Code catches what Human shouldn't have to remind.


### 8b. Retroactive entries

If DEBATEs were run during this session — add their rows to S{N}-SPRINT.md Protocol Log
NOW, before the Sprint-Builder row.

### 8c. Project Backlog Persist

□ Scan this chat: any unrecorded decisions or framework findings?
□ YES → create execute prompt to append to Project Backlog docs/01_refer/KNOWLEDGE/BACKLOG-{PROJECT}.md
         Wait for Claude Code confirmation before proceeding.
□ NO  → record: "Project Backlog: nothing to persist"


### 8d. Update S{N}-SPRINT.md

Create execute prompt. Claude Code updates S{N}-SPRINT.md:

Current State:

| Phase | 1: [Name] — NOT STARTED |
| Entry | E[NN]: [Name] — NOT STARTED |
| Cycle | C[NN]: not started |
| Status | Planning complete, ready for first cycle |


Protocol Log — add row:

| S{N}-SB | 02_Sprint-Builder | [date] | DONE |


Next Action: C[first cycle number] — run 03_Phase-Builder PART 1

For Human:

Next: Session Code S{N}-P01-E{NN}-C{first cycle number}
Load: S{N}-SPRINT.md + 01_Declaration.md + ENVIRONMENT.md
      + P01-{name}.md + ARCHITECTURE-{PROJECT}.md + 03_Phase-Builder.md
Run: 03_Phase-Builder PART 1


### 8e. ROADMAP rebalance (if items pulled from future sprints)

If Step 3 Capacity Check pulled items from S{N+1} or S{N+2}:

Create execute prompt. Claude Code updates ROADMAP-{PROJECT}.md:
- Mark pulled items as "→ S{N}" in their original sprint section
- Update S{N+1}/S{N+2} scope preview to reflect removed items
- Add note in S{N} Work Streams: "Pulled from S{N+1}: [item list]"

This prevents next Sprint-Builder from planning with stale ROADMAP scope.

### 8f. Final Commit

git add docs/03_sprint/S{N}-[name]/
git commit -m "sprint: S[N] [name] — planning complete, ready to start"
git push


### 8g. Sprint Comprehension Check

Create execute prompt. Claude Code reads S{N}-SPRINT.md + all P{NN}-{name}.md
and outputs a structured report:

Sprint Comprehension Report:
  Total phases: [N]
  Total cycles: [N] (C[first]-C[last])
  Entry numbers: [list]
  Parallel entries: [which phases, if any]
  Files per phase doc: [line counts — check for truncation]
  Missing sections: [any required section absent]
  Cycle gaps: [any non-sequential cycle numbers]
  Cross-references: [phase entry/exit conditions chain correctly?]
  Verdict: READY / ISSUES FOUND

If ISSUES FOUND → fix before closing chat.

### 8h. Close Chat

Output current Session Code: S{N}-SB

## Chat Boundary — MANDATORY STOP

After final commit — this chat is DONE. Close it.
Do NOT start the next protocol in this chat.
One protocol = one chat. No exceptions.
Next protocol = new chat.

**STOP — close this chat.**

---


[*] 02_Sprint-Builder SPEC v3.0.0 * ready
Strategic sprint planning + phase setup — receives decisions from 06_Brain-Next
Output: S{N}-SPRINT.md + all P{NN}-{name}.md files + phase folders
Includes: stream planning (Entry allocation, scope partitioning, overlap check)
Includes: S{N+1} look-ahead for strategic continuity
Session Code: S{N}-SB
Next chat: S{N}-P01-E{NN}-C{first cycle} — run 03_Phase-Builder PART 1
