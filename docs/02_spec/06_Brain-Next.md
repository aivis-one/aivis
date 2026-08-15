# 06_Brain-Next
> SPEC v3.0.0 | Knowledge audit + research + conflict resolution + ROADMAP recommendations
> Triggered by: after 05_Clean-Sync (mandatory)
> Sequence: 05_Clean-Sync → 06_Brain-Next → 02_Sprint-Builder

---

## Purpose

Ensure priority of new over old. Two hemispheres of project knowledge — external (KB) and internal (ADR) — audited, compared against fresh information, conflicts resolved, recommendations produced for Sprint-Builder.

This is the project's brain maintenance — ensures knowledge is current, consistent, and decisions are valid BEFORE sprint planning begins.

| Hemisphere | Content | Path | Tool |
|-----------|---------|------|------|
| **KB (external)** | Facts, patterns, technologies, market, competitors | `docs/01_refer/KNOWLEDGE/KB-*/` | kb-rag-builder |
| **ADR (internal)** | Decisions, debates, architectural choices | `docs/01_refer/KNOWLEDGE/ADR-{PROJECT}/` | kb-rag-builder (ADR mode) + vector-debates |

Both hemispheres use unified L0/L1/L2 format. ADR files have additional metadata fields (Status, Status-date, Superseded-by).

**L0 (KNOWLEDGE-{PROJECT}.md)** = single aggregator index for both hemispheres.

Flow: Intake → Audit → Conflict → Resolve → Output

Orchestrator executes protocol phases as written. Deferral decisions belong to Human only. Do not suggest deferring required work.

---

## Prerequisites

These kb-rag-builder enhancements MUST be completed before first Brain-Next v2 run:

| # | Enhancement | Blocks | Effort |
|---|------------|--------|--------|
| 1 | ADR mode in refactor protocol (detect + ADR metadata template + ADR-specific DHC checks) | Phase 4 — ADR fixes impossible without ADR-aware skill | S |
| 2 | `audit` protocol (validate-only, no rebuild) | Phase 2 — core operation is audit without rebuild | S |
| 3 | `_BATCH-PROGRESS.md` convention in build-steps.md | Phase 2 — batching for large domains | XS |

Additionally: ADR migration (all ADR files → L0/L1/L2 format with metadata) REQUIRED before first run. Without metadata in ADR files, Phase 2 ADR audit and Phase 4 status updates cannot execute.

**First run file rename:** Existing `BRAIN-NEXT/` folder — verify naming is correct. Existing archive files should use S{N}-BRAIN-NEXT.md naming convention.

---

## Before You Begin

Load in chat:

□ 01_Declaration.md
□ docs/01_refer/ENVIRONMENT.md
□ KNOWLEDGE-{PROJECT}.md (L0 — combined KB + ADR index)
□ ARCHITECTURE-{PROJECT}.md
□ docs/01_refer/KNOWLEDGE/BACKLOG-{PROJECT}.md
□ S{N}-SNAPSHOT.md (latest closed sprint)
□ S{N}-RETRO.md (latest — for carry-forward context)
□ Previous S{N}-BRAIN-NEXT.md (if exists — Research Brief + Feedback Loop)

Session Code: S{N}-Brain-Next

This is an **orchestration protocol**. The main chat coordinates sub-chats. Heavy work (KB audit, ADR audit, fixes) happens in Claude Code via prompts. Main chat: reviews results, detects conflicts, makes decisions, produces outputs.

---

## ADR Lifecycle

All ADR files contain metadata with Status field. Brain-Next is the primary protocol that manages ADR lifecycle transitions.

| Status | Meaning | Set by |
|--------|---------|--------|
| PROPOSED | Formulated, no debate yet | Brain-Next (new ADR from debate prep) |
| ACCEPTED | Approved after debate | Brain-Next (after vector-debates) |
| IMPLEMENTED | In codebase — component exists + tests exist (verified by scout) | Brain-Next Phase 2b |
| SUPERSEDED | Replaced by another ADR. Field: `Superseded-by: ADR-NNN` | Brain-Next |
| DEPRECATED | Outdated, no replacement exists | Brain-Next |
| REJECTED | Considered and declined with documented reason | Brain-Next |
| POLICY | Non-code decision — verified as "documented and referenced" | Brain-Next Phase 2b |

**IMPLEMENTED verification criteria:**
1. Component/pattern from ADR exists in codebase (grep/find by key names)
2. Tests for that component exist
3. Both true → IMPLEMENTED. Code without tests → remains ACCEPTED.

**POLICY verification criteria:**
For ADRs that produce policy documents, not code (e.g., ADR-017 Claude API Policy):
1. Policy document exists and is referenced from relevant docs
2. No IMPLEMENTED status — use POLICY instead

**Automatic flags (checked each Brain-Next run):**
- ACCEPTED >3 sprints without IMPLEMENTED → flag "implementation stale"
- IMPLEMENTED + Verified >6 months → flag "re-verification needed"
- SUPERSEDED/DEPRECATED → CASCADE check: all downstream references updated?

---

## Conflict Levels

| Level | Meaning | Action |
|-------|---------|--------|
| NONE | New information confirms existing knowledge | Batch update Verified dates |
| MINOR | KB update needed, ADR unaffected | kb-rag-builder `update` |
| MAJOR-REVIEW | Contradicts KB or needs focused review, no architectural debate | Focused review + kb-rag-builder `update` |
| MAJOR | Contradicts ADR or architecture, requires debate | vector-debates in separate chat |
| CRITICAL | Invalidates production code | P0 recommendation, immediate escalation |

---

## Material Routing Rules

Fresh material arriving in Phase 1 is routed by type:

| Material type | Route to | Tool |
|--------------|----------|------|
| External facts, patterns, benchmarks | KB domain (existing or new) | kb-rag-builder update/create |
| Architectural decisions, trade-offs | ADR (new or updated) | kb-rag-builder ADR mode + vector-debates |
| Framing, positioning, pitch material | VISION-{PROJECT}.md or marketing docs | Direct doc update |
| Competitive intelligence | KB domain with explicit UNVERIFIED markers | kb-rag-builder update |
| Code bugs, tech debt | BACKLOG-{PROJECT}.md | Direct backlog update |
| Already incorporated | Skip — note in inventory | No action |
| Unverifiable | Skip — mark UNVERIFIED | No action |

---

## Operational Limits

| Operation | Per-session limit | Notes |
|-----------|------------------|-------|
| Validation-only (DHC) | 25+ L2 files | Bash outputs are compact |
| Refactor (full rebuild) | 12-15 L2 files | Read all + write new versions |
| Create (from research) | 8-10 L2 files | Web search + content compete for context |
| Update | 3 L2 files per domain | Hard limit in kb-rag-builder protocol |
| ADR migration batch | ~14 files | Simpler than KB refactor — metadata addition |

When Claude Code signals context exhaustion → Human opens new session with continuation prompt referencing `_BATCH-PROGRESS.md` checkpoint file.

---

## Phase 1: INTAKE

Claude Chat in main chat.

**If no fresh material from Human:** Phase 1 produces empty inventory. Protocol continues — Phase 2 audit runs independently of new material. Phase 3 uses only audit findings to drive actions.

### Step 1: Load Previous Research Brief

If previous S{N}-BRAIN-NEXT.md exists → read Research Brief section. These are questions from the last cycle that need checking.

### Step 2: Inventory Fresh Material

List all fresh material files from Human. For each:
- File name, size, topic count
- Date of material

### Step 3: Already-Incorporated Check

Read ARCHITECTURE-{PROJECT}.md changelog (recent versions) and BACKLOG-{PROJECT}.md latest strategic items section. For each fresh material item: is it already in the system?

Output: table with columns [Item | Already incorporated? | Where | Remaining raw?]

### Step 4: Web Search Validation

For claims in fresh material that could be stale or unverified — validate via web search in main chat. Priority:

| Priority | Criterion |
|----------|----------|
| H | Affects architecture or current sprint scope |
| M | Affects future sprint or competitive positioning |
| L | Informational, no immediate impact |

Validate H items first. M if time permits. L = add to Research Brief for next cycle.

Output: validated material table [Claim | Verified? | Source | Notes]

### Step 5: Route Material

Apply Material Routing Rules. Each item gets a target: KB domain, ADR, VISION, BACKLOG, or skip.

Output: routed inventory table [Item | Route | Target file/domain | Conflict check needed?]

**After Phase 1 — STOP. Present inventory to Human.**

---

## Phase 2: AUDIT

Three sub-phases. Each produces a Claude Code prompt (.md file).

All prompts for Claude Code MUST follow Declaration Rule 15 header schema:
```
# [Prompt Title]
Type: scout
Risk: LOW
Scope: [file paths or module names]
Anti-scope: [explicitly excluded]
```

All commits follow ENVIRONMENT.md commit conventions.

### Phase 2a: Domain Health Check

Claude Chat creates prompt for Claude Code. Prompt Before You Begin includes:
```
□ .claude/skills/kb-rag-builder/SKILL.md
□ .claude/skills/kb-rag-builder/reference/validation.md
□ .claude/skills/kb-rag-builder/reference/quality-rules.md
```

Uses kb-rag-builder `audit` protocol (see Prerequisites #2).

**Claude Code executes:**
1. KB Domain Health Check: run validation commands from kb-rag-builder for all KB domains
   - L2 size check (3-12KB range)
   - Self-containment check (prohibited patterns)
   - Metadata check (Context/Scope/Keywords/Questions/Source/Verified present)
   - L1 completeness (every L2 listed in Topic Map)
   - Freshness (Verified dates — flag >6 months)
2. ADR Domain Health Check: same checks with ADR-specific additions
   - Status field present in every ADR file
   - Superseded-by chain valid (no dangling references)
   - No duplicate ADR numbers
3. Filename collision detection: find same filenames across different domains
4. L0 accuracy: KNOWLEDGE-{PROJECT}.md domain count and file count match reality
5. L0→L1 navigation: every domain in KNOWLEDGE-{PROJECT}.md has `Reference:` line with full path to L1 INDEX file. ADR domain included (must reference {PROJECT}-ADR-INDEX.md). Verify each Reference path resolves to existing file.

**Output:** Health Report per domain (PASS / WARN / FAIL), sizing violations, stale list, filename collisions, L0 accuracy.

### Phase 2b: IMPLEMENTED Verification

Claude Chat creates separate prompt for Claude Code.

**Claude Code executes:**
For each ADR with Status: ACCEPTED:
1. Grep codebase for key component names from the ADR
2. Check if tests exist for those components
3. Report: IMPLEMENTED / NOT IMPLEMENTED / PARTIAL (code exists, no tests)

For each ADR with Status: POLICY:
1. Check if policy document exists and is referenced

**Output:** ADR status matrix [ADR | Current status | Verified status | Evidence]

### Phase 2c: ARCHITECTURE Dedup (optional)

Only if Phase 2a found potential KB↔ARCHITECTURE overlaps.

Claude Chat creates prompt for Claude Code. Read ARCHITECTURE-{PROJECT}.md + one KB domain L2 files at a time. Report: sections where ARCHITECTURE reproduces L2 content (>3 sentences on same topic) instead of referencing.

**Output:** Dedup findings [ARCH section | KB file | Overlap type | Recommendation]

### Cross-Check: Deduplication Matrix

| Pair | Detection method | Action |
|------|-----------------|--------|
| KB ↔ KB | Filename collisions (Phase 2a) + H2 heading overlap + key term frequency | Consolidate to one L2 |
| KB ↔ ADR | Manual review in Phase 3 | Verify consistency, not duplication |
| KB/ADR ↔ ARCHITECTURE | Phase 2c focused prompt | ARCHITECTURE references, doesn't reproduce |
| ADR ↔ ADR | ADR index review | Merge or SUPERSEDE |

**After Phase 2 — resolve any dedup findings before proceeding. Dedup resolution is a prerequisite for Phase 3 fix list.**

**STOP. Present audit results to Human.**

---

## Phase 3: CONFLICT

Claude Chat in main chat.

### Step 1: Resolve Dedup

If Phase 2 found duplications → decide ownership (which domain keeps the topic). Record decisions.

### Step 2: Build Conflict Table

For each routed item from Phase 1 Step 5:
- Compare against existing KB content (from Phase 2 health reports)
- Compare against existing ADR status (from Phase 2b matrix)
- Compare against ARCHITECTURE-{PROJECT}.md
- Assign conflict level: NONE / MINOR / MAJOR-REVIEW / MAJOR / CRITICAL

### Step 3: Produce Action Lists

| List | Contents | Consumer |
|------|----------|---------|
| Direct fix list | MINOR + MAJOR-REVIEW items — specific files, specific changes | Phase 4a |
| Debate list | MAJOR items — require vector-debates | Phase 4b |
| P0 escalation | CRITICAL items — immediate Human attention | Human |
| NONE batch | Items confirming existing — Verified date updates | Phase 4a |

### Step 4: Severity-Prioritized Recommendations (draft)

For items entering ROADMAP Recommendations (Phase 5):

| Severity | Criterion |
|----------|----------|
| P0 | New contradicts production code |
| P1 | New improves nearest sprint scope |
| P2 | New is useful, not urgent |
| P3 | Interesting, backlog |

**After conflict table — STOP. Present to Human. Human confirms debate list before proceeding.**

---

## Phase 4: RESOLVE

Four streams. Execute in order: 4a → 4b → 4c → 4d.

All commits follow ENVIRONMENT.md commit conventions.

### Phase 4a: Direct Fixes

Claude Chat creates prompt(s) for Claude Code.

**KB updates** (MINOR + MAJOR-REVIEW items):
- kb-rag-builder `update` per domain (max 3 L2 files per domain per run)
- Uses kb-rag-builder ADR mode for ADR files (see Prerequisites #1)
- If >3 files in one domain need updating → batch across sessions

**Direct doc edits** (BACKLOG enrichment, project-specific docs, other non-KB docs):
- Single prompt for all small direct edits

**NONE batch** (Verified date updates):
- Update Verified dates on KB/ADR files confirmed by new material

**L1 updates:**
- If any L2 content changed → update corresponding L1 INDEX

### Phase 4b: Debates

For each MAJOR item confirmed by Human:

1. Claude Chat creates debate transfer prompt (.md file) with full context: question, options, evidence, constraints
2. Human opens new chat, loads vector-debates skill + debate prompt + relevant KB/ADR files
3. Human runs debate cycle, gets decision markdown
4. Human returns decision to main Brain-Next chat
5. Claude Chat reviews: decision clear? ADR draft included? Consistent with constraints?
6. Claude Chat creates prompt for Claude Code:
   - Create new ADR file (if new decision) or update existing (if revision)
   - If debate changed architectural decision → update ARCHITECTURE-{PROJECT}.md + changelog row + version bump (Tier 2 Changelog Rule)
   - Commit

Repeat for each debate.

### Phase 4c: ADR Status Updates

Claude Chat creates prompt for Claude Code:
- Update Status and Status-date in ADR files based on Phase 2b findings
- Sync L0 table (KNOWLEDGE-{PROJECT}.md ADR section) with file-level Status values
- Commit

### Phase 4d: Cleanup + L0 Rebuild

Claude Chat creates prompt for Claude Code:
- Remove legacy references (phantom folders, stale links)
- **L0 REBUILD (MANDATORY):** Rebuild KNOWLEDGE-{PROJECT}.md from all L1 INDEX files
  - Correct domain count
  - Correct L2 file counts
  - All L0 snippets present for all domains
  - Every domain snippet MUST include: `Reference: docs/01_refer/KNOWLEDGE/{dir}/{DOMAIN}-INDEX.md` (full path, not filename only)
  - ADR domain MUST include: `Reference: docs/01_refer/KNOWLEDGE/ADR-{PROJECT}/{PROJECT}-ADR-INDEX.md`
  - L0→L1 navigation verified: every Reference path resolves to existing file on disk
  - ADR table synced with file-level Status values
  - Updated date
- Final commit

**L0 rebuild is ALWAYS the last Claude Code operation. Never skip.**

**After Phase 4 — STOP.**

---

## Phase 5: OUTPUT

Claude Chat in main chat. All outputs created as part of protocol close.

### Step 1: Create S{N}-BRAIN-NEXT.md

Save to `docs/01_refer/ARCHIVES/BRAIN-NEXT/S{N}-BRAIN-NEXT.md`

Contents:
- KB Changes: domains updated, files added/removed/renamed, health results
- ADR Changes: status updates, new ADRs, superseded/deprecated
- Conflicts Resolved: conflict table with resolutions
- Debates: topics debated, decisions made (or "0 debates this cycle")
- Fresh Material Routing: where each item went
- Research Brief: questions for next cycle (see Step 3)
- Feedback Loop: previous recommendations status (see Step 5)

### Step 2: ROADMAP Recommendations

Produce prioritized recommendation table:

| # | Recommendation | Severity | Rationale | Target Sprint |
|---|---------------|----------|-----------|--------------|

Severity: P0 / P1 / P2 / P3 (criteria from Phase 3 Step 4).

Include in S{N}-BRAIN-NEXT.md.

### Step 3: Research Brief

Generate specific research questions for next Brain-Next cycle:

```
## Research Brief — S{N}
| # | Domain | Question | Why check | Priority |
|---|--------|----------|-----------|----------|
```

Sources for questions:
- Stale domains from Phase 2 (Verified >6 months)
- Fast-moving fields (agentic AI, frontier AI, competitive landscape)
- Technologies mentioned in KB but not recently verified
- Previous Research Brief items not yet checked

Include in S{N}-BRAIN-NEXT.md.

### Step 5: Feedback Loop Check

If previous S{N}-BRAIN-NEXT.md had recommendations:
- Check which were TAKEN / DEFERRED / REJECTED by Sprint-Builder
- Any recommendation DEFERRED 3+ times → flag for Human: remove or reprioritize?

Record in current S{N}-BRAIN-NEXT.md.

**CASCADE dependencies (log as Project Backlog items if not yet implemented):**
- 02_Sprint-Builder: add step to mark Brain-Next recommendations as TAKEN / DEFERRED / REJECTED

---

## Universal Close Flow

1. Verify all phases DONE (Phases 1-5)
2. Verify mandatory outputs exist:
   □ S{N}-BRAIN-NEXT.md created in `docs/01_refer/ARCHIVES/BRAIN-NEXT/`
   □ L0 (KNOWLEDGE-{PROJECT}.md) rebuilt
   If any missing — protocol CANNOT be closed.
3. Scan chat: unrecorded decisions? SPEC-LOG items?
4. If SPEC-LOG items → create prompt to persist to Project Backlog (`docs/01_refer/KNOWLEDGE/BACKLOG-{PROJECT}.md`)
5. Check deferred items → write to Project Backlog immediately
6. Final commit:
   ```
   git add docs/01_refer/
   git commit -m "brain-next: S{N}-BN — [summary]"
   git push
   ```
7. Output: Session Code S{N}-Brain-Next + next Session Code + what to load
8. STOP — close chat

---

## Hand Off

Brain-Next complete. Knowledge state clean. ROADMAP recommendations ready.

Next: Session Code S{N+1}-Sprint-Builder — 02_Sprint-Builder
Load:
  □ 01_Declaration.md
  □ 02_Sprint-Builder.md
  □ VISION-{PROJECT}.md
  □ ARCHITECTURE-{PROJECT}.md
  □ ROADMAP-{PROJECT}.md
  □ docs/01_refer/KNOWLEDGE/BACKLOG-{PROJECT}.md
  □ KNOWLEDGE-{PROJECT}.md (from docs/01_refer/KNOWLEDGE/)
  □ docs/01_refer/ENVIRONMENT.md
  □ S{N}-SNAPSHOT.md
  □ S{N}-CODE-AUDIT.md (if exists)
  □ S{N}-RETRO.md (if exists)
  □ S{N}-BRAIN-NEXT.md (if exists)
Run: 02_Sprint-Builder

## Chat Boundary — MANDATORY STOP

After final commit — this chat is DONE. Close it.
Do NOT start the next protocol in this chat.
One protocol = one chat. No exceptions.
Next protocol = new chat.

---

## Sub-Chat Reference

| Sub-Chat | Runs In | Input | Output |
|----------|---------|-------|--------|
| KB + ADR Audit (Phase 2a) | Claude Code | Audit prompt + kb-rag-builder skill | Health report |
| IMPLEMENTED Verification (Phase 2b) | Claude Code | Verification prompt | ADR status matrix |
| ARCHITECTURE Dedup (Phase 2c) | Claude Code | Dedup prompt + ARCH + KB L2 | Overlap findings |
| Web search validation | Claude Chat main | Fresh material | Validated material |
| Debates (per topic) | Claude Chat + vector-debates | Debate prompt + evidence | Decision + ADR draft |
| KB/ADR fixes (Phase 4a) | Claude Code | Fix prompt + kb-rag-builder | Updated files + commit |
| ARCHITECTURE update (Phase 4b) | Claude Code | Update prompt | ARCH + changelog + commit |
| ADR status updates (Phase 4c) | Claude Code | Status prompt | Updated ADRs + commit |
| Cleanup + L0 rebuild (Phase 4d) | Claude Code | Cleanup prompt | Rebuilt L0 + commit |

---

## Anchor

```
[*] 06_Brain-Next SPEC v3.0.0 * ready
Knowledge audit + research + conflict resolution + ROADMAP recommendations
Sequence: 05_Clean-Sync → 06_Brain-Next → 02_Sprint-Builder
Session Code: S{N}-Brain-Next
Flow: Intake → Audit → Conflict → Resolve → Output
Uses: kb-rag-builder skill (KB + ADR operations), vector-debates skill (debates), web search (validation)
```
