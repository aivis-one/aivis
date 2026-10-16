# 05_Clean-Sync
> SPEC v3.0.0 | Project data hygiene — FILE-TREE sync, path/version consistency, backlog health, stale pruning
> Triggered by: after 04_Sprint-Closer (mandatory before 06_Brain-Next)
> Sequence: 04_Sprint-Closer → 05_Clean-Sync → 06_Brain-Next → 02_Sprint-Builder

---

## Purpose

Physical hygiene of project files. Sync FILE-TREE with disk, cross-validate
paths and versions between documents, prune stale content from active files,
rebalance backlogs, archive dead information.

Clean-Sync does NOT do:
- Strategy review (→ 02_Sprint-Builder)
- Knowledge/ADR audit (→ 06_Brain-Next)
- Code quality review (→ 04_Sprint-Closer Part 1)
- VISION/ARCHITECTURE content review (→ 06_Brain-Next / 02_Sprint-Builder)

Clean-Sync runs AFTER Sprint-Closer which may create filesystem drift from code audit fixes, SNAPSHOT creation, RETRO creation. Clean-Sync catches this drift before Brain-Next uses these files for framework review.

---

## Before You Begin

Load in chat:

□ 01_Declaration.md
□ docs/01_refer/ENVIRONMENT.md
□ docs/01_refer/FILE-TREE-{PROJECT}.md
□ docs/01_refer/KNOWLEDGE/BACKLOG-{PROJECT}.md
□ ARCHITECTURE-{PROJECT}.md
□ ROADMAP-{PROJECT}.md
□ S{N}-SNAPSHOT.md (latest closed sprint)
□ S{N}-SPRINT.md (current or just-closed sprint)

Note: ENVIRONMENT.md SPEC Update may show PENDING — expected. 05_Clean-Sync runs regardless (framework-phase protocol).

This is a deterministic protocol — execute immediately after loading documents.
No Session Plan confirmation required (Rule 6).

---

## Operational Limits

| Operation | Per-session limit | Notes |
|-----------|------------------|-------|
| FILE-TREE scan (full project) | 1 prompt | Bash output is compact |
| Cross-document path grep | 1 prompt | All checks in one scout |
| Stale file scan | 1 prompt | find + grep combined |
| Backlog cleanup (transfers) | 1-2 prompts | Depends on volume |
| Version/path fixes | 1-2 prompts | Depends on BREAK count |
| Sprint archive | 1 prompt | If applicable |

Total expected: 4-8 Claude Code prompts per session.

---

## Prompt Discipline

All prompts for Claude Code MUST follow Declaration Rule 15 header schema:
```
# [Prompt Title]
Type: scout | execute
Risk: LOW
Scope: [file paths or module names]
Anti-scope: [explicitly excluded]
```

All commits follow ENVIRONMENT.md commit conventions.
Commit prefix for this protocol: `clean-sync:` (see ENVIRONMENT.md).

---

## Step 1: FILE-TREE Sync

**Executor:** Claude Code (scout prompt)

Create scout prompt. Claude Code:
1. Generates fresh file tree from actual filesystem (tree or find command)
2. Compares with existing FILE-TREE-{PROJECT}.md
3. Reports:

```
[PHANTOM] Listed in FILE-TREE but not on disk: [path]
[MISSING] On disk but not in FILE-TREE: [path]
[RENAMED] Was [old], now [new]
```

Also validate:
□ Tool versions: run `python --version`, `node --version`, etc. from ENVIRONMENT.md Tools table — report any mismatch

**After scout — STOP. Claude Chat reviews findings.**

**Drift resolution:**
If drift count ≤ 10: create execute prompt — Claude Code adds MISSING entries (with placeholder comment `# [describe]`), removes PHANTOM entries, preserves all existing comments. One execute, all fixes.
If drift count > 10: create execute prompt — Claude Code regenerates FILE-TREE-{PROJECT}.md from filesystem. Use ARCHITECTURE-{PROJECT}.md layer descriptions for top-level comments. Preserve per-file comments where entry existed in previous version.

FILE-TREE-{PROJECT}.md is Tier 3 — update date stamp in header.

If tool versions drifted — create execute prompt to update ENVIRONMENT.md.
ENVIRONMENT.md is Tier 3 — update date stamp.

**After fix (if any) — STOP.**

---

## Step 2: Cross-Document Path and Version Consistency

**Executor:** Claude Code (scout prompt)

Create scout prompt. Claude Code runs cross-checks:

### 2a. Path Consistency (project files only)

□ All paths in ENVIRONMENT.md → Information Map → exist on disk?
□ All paths in ENVIRONMENT.md → Project Structure → match FILE-TREE?
□ ROADMAP → Document Structure folder paths → match disk?
□ ARCHITECTURE → Satellite Documents paths → match disk?
□ SPRINT-S{N}.md → References table paths → match disk?
□ BACKLOG → routing path to Project Backlog → matches actual location?

Note: Protocol filename consistency and Before You Begin path validation
belong to 06_Brain-Next (framework layer). Not checked here.

### 2b. Version Alignment

□ Tier 2 docs (ARCHITECTURE, VISION): header version = changelog latest row version?
□ FILE-TREE version pins → match current doc header versions?
□ Cross-references: grep for old version numbers in active docs
  (exclude changelog entries, archives, KB source citations)
□ SYNC lines in footers: referenced doc versions current?

### 2c. Terminology Consistency

□ Stale M-prefix (M4, M5, M6...) in active prose/tables?
  Historical names in changelog/history = OK. Active text = must use S-prefix.

**Output:** Numbered finding list:

```
[BREAK|GAP|NIT] Location: [file:section]
Problem: [what's wrong]
Expected: [correct value]
Actual: [current value]
```

**After scout — STOP. Claude Chat reviews findings and decides:**
- BREAK → must fix before Step 3
- GAP → fix now or create BACKLOG item
- NIT → fix now (low cost) or defer

If fixes needed — create execute prompt. Apply fixes.

Rules for fixes:
- Documents describe what IS, not what was planned
- Remove references to deleted/renamed things
- Never invent — only document what actually exists
- Tier 2 documents: version bump + changelog row
- Tier 3 documents: update date stamp

Validation standard: `docs/02_spec/07_Validation.md`

**After fixes — STOP.**

---

## Step 3: Stale Content Scan

**Executor:** Claude Code (scout prompt)

Create scout prompt. Claude Code checks active project files for dead content:

### 3a. Document Staleness

□ ARCHITECTURE: descriptions of deleted/renamed modules or components?
□ ENVIRONMENT: obsolete tools, outdated Shell/Tool Notes, stale Known Limitations?
□ Any project doc with information older than 2 sprints and no current consumer?

### 3b. Stale Files on Disk

□ Sprint folders older than current-6 — flag as archive candidates (consumed by Step 7)
□ Orphaned phase folders (docs/03_sprint/S{N}-*/P{NN}-*/) with no C{NN}-{name}.md files?
  → Expected if phase hasn't started. Log only if folder looks orphaned (phase skipped/cancelled).
  → Never auto-delete — flag to Human if uncertain.

### 3c. Backlog Staleness (pre-scan for Step 5)

□ BACKLOG-{PROJECT}.md: resolved/DONE/SUPERSEDED items still in active tables?
□ BACKLOG items with Target referencing sprints >2 behind current — flag as stale
□ CODE-AUDIT items >3 sprints old — flag for re-evaluate or archive
□ BACKLOG items with Target = completed sprint (S{N-1} or older DONE sprints) but Status not DONE — flag as "completed but unmarked"

**Output:** List of stale items per file, stale files on disk, backlog stale items.

**After scout — STOP. Claude Chat reviews findings.**

---

## Step 4: Prune and Archive

**Executor:** Claude Code (execute prompt per file group)

Transfer stale items identified in Step 3 to CHANGELOG-{PROJECT}.md.

CHANGELOG-{PROJECT}.md is an immutable history log.
Location: `docs/01_refer/ARCHIVES/CHANGELOG-{PROJECT}.md`.
Created by 05_Clean-Sync if it doesn't exist yet.

**CASCADE:** If CHANGELOG-{PROJECT}.md is created for the first time → update
FILE-TREE-{PROJECT}.md to include it.

Format:

```markdown
## S{N} Cleanup — [date]

### From BACKLOG-{PROJECT}.md
- [DONE/SUPERSEDED item] — removed from active table

### From ARCHITECTURE-{PROJECT}.md
- [stale description] — module renamed/removed

### From ENVIRONMENT.md
- [obsolete tool/note] — no longer installed/relevant

### Stale Files Archived
- [file path] — reason for archive
```

For each file group, Claude Code:
1. Appends items to CHANGELOG-{PROJECT}.md
2. Removes items from the source active file
3. Active files keep ONLY current, actionable content
4. Tier 2 documents modified (ARCHITECTURE, VISION): version bump + changelog row
5. Tier 3 documents modified (ENVIRONMENT, FILE-TREE, ROADMAP): update date stamp

**After transfers — STOP.**

---

## Step 5: Backlog Health

**Executor:** Claude Chat (analysis) + Claude Code (execute prompt)

Claude Chat reviews project backlog:

□ BACKLOG-{PROJECT}.md Backlog Statistics table — counts match actual item counts?
□ Categories still make sense? Any sections with 0 active items → collapse or remove?
□ DONE/SUPERSEDED items all transferred to CHANGELOG (should be clean after Step 4)

If updates needed — create execute prompt.

**After moves (if any) — STOP.**

---

## Step 6: Information Map Boundaries

**Executor:** Claude Chat (analysis)

Claude Chat reads ENVIRONMENT.md → Information Map section.

For each file loaded in this chat (from Before You Begin):

□ "Contains" column — does the actual file stay within these boundaries?
□ "Does NOT Contain" column — has any prohibited content crept in?

For files listed in Information Map but NOT loaded in chat:
□ Create scout prompt — Claude Code reads file headers/TOC and reports if content
  appears outside declared boundaries.

Flag any file whose actual content has drifted outside its declared boundary.

If drift found — create execute prompt to fix:
- Move out-of-bounds content to the correct file
- Or update Information Map if boundaries need adjustment (with Human confirmation)

**After fix (if any) — STOP.**

---

## Step 7: Sprint Archive Maintenance

**Executor:** Claude Chat (decision) + Claude Code (execute prompt if needed)

□ Count sprint folders in docs/03_sprint/
□ Sprints older than current-6 (e.g., S1-S5 when current is S11):
  - Phase folders with cycle docs → candidates for compression
  - Decision: archive to ZIP and remove originals? Or leave as-is?
  - **Human confirmation required** for any deletion or compression

This step is advisory — Human decides whether to compress old sprint folders.
If Human approves — create execute prompt to archive.

**After decision — STOP.**

---

## Step 8: Close — Universal Close Flow

### 8a. Verify Completion

□ Step 1: FILE-TREE-{PROJECT}.md current + validated against filesystem
□ Step 2: Path/version/terminology consistency validated, all BREAKs resolved
□ Step 3: Stale content identified
□ Step 4: Stale items transferred to CHANGELOG-{PROJECT}.md
□ Step 5: Backlog structure healthy — statistics current
□ Step 6: Information Map boundaries verified
□ Step 7: Sprint archive reviewed

### 8b. SPEC-LOG Persist

□ Scan this chat: any unrecorded decisions or framework findings?
□ YES → create execute prompt to append to `docs/01_refer/KNOWLEDGE/BACKLOG-{PROJECT}.md`
         Wait for Claude Code confirmation before proceeding.
□ NO  → record: "SPEC-LOG: nothing to persist"

### 8c. Deferred Items Check

□ Scan chat for any "do later", "next chat", "handle next time" verbal commitments.
□ If found → write each item to Project Backlog immediately
  via execute prompt. Verbal intent without a written record does not exist.

### 8d. SPRINT.md Update

S{N}-SPRINT.md is already CLOSED at this point (sprint close happened before FW Phase).
If accessible: append Clean-Sync row to Protocol Log.
If not loaded or inaccessible: skip — next Sprint-Builder will create S{N+1}-SPRINT.md.

### 8e. Final Commit

```
git add docs/
git commit -m "clean-sync: S{N} project data hygiene"
git push
```

### 8f. Hand Off

Next: Session Code S{N}-Brain-Next — 06_Brain-Next
Load:
  □ 01_Declaration.md
  □ 06_Brain-Next.md
  □ docs/01_refer/ENVIRONMENT.md
  □ docs/01_refer/KNOWLEDGE/BACKLOG-{PROJECT}.md
  □ S{N}-SNAPSHOT.md
  □ S{N}-SPRINT.md (if exists)
Run: 06_Brain-Next

After 06_Brain-Next → 02_Sprint-Builder.

**STOP — close this chat.**

## Chat Boundary — MANDATORY STOP

After final commit — this chat is DONE. Close it.
Do NOT start the next protocol in this chat.
One protocol = one chat. No exceptions.
Next protocol = new chat.

---

## Removed from v2 → v3

| Element | Reason | Now lives in |
|---------|--------|--------------|
| KNOWLEDGE-{PROJECT}.md (L0) checks | Brain-Next v2 Phase 4d does L0 rebuild | 06_Brain-Next |
| ADR index/status checks | Brain-Next v2 Phase 4c does status updates | 06_Brain-Next |
| VISION strategic review ("Problem still relevant?") | Strategy question, not hygiene | 02_Sprint-Builder |
| ARCHITECTURE deep content review ("Module relationships accurate?") | Code/knowledge review | 06_Brain-Next / 04_Sprint-Closer |
| Changelog Centralization (4e-CL per-file changelog management) | Dual bookkeeping with Brain-Next | Removed — CHANGELOG-{PROJECT}.md is archive only |
| MOTHERBOARD.md loading in Before You Begin | Not consumed by any Clean-Sync step | Removed |
| VISION-{PROJECT}.md loading in Before You Begin | Not consumed — deep review removed | Removed |
| Cross-document SYNC absorbed from Sprint-Closer (full 4a) | Scoped down to paths/versions only | Step 2 (lean version) |
| Scope Traceability (4d) | Sprint-Builder validates scope | 02_Sprint-Builder |
| Analytical Input Traceability (4g) | Brain-Next tracks recommendations | 06_Brain-Next |
| Protocol filename consistency check | Framework layer (Rule 13) | 06_Brain-Next |
| Protocol Before You Begin path validation | Framework layer (Rule 13) | 06_Brain-Next |
| Backlog items closed by this session | Framework layer (Rule 13) | 06_Brain-Next |

## Added in v3

| Element | Source | Step |
|---------|--------|------|
| Operational Limits table | Brain-Next v2 pattern | Header |
| Stale file scan (physical files on disk) | Backlog #46 | Step 3b |
| Sprint archive maintenance | Backlog #47 | Step 7 |
| Concrete pruning criteria (>2 sprints, >3 sprints) | Backlog #53 | Step 3c |
| Reference path validation (Before You Begin paths) | Backlog #65 | Moved to 06_Brain-Next |
| CASCADE to FILE-TREE on new file creation | Backlog #45 | Step 4 |
| Backlog Health step (structure, statistics, routing) | BACKLOG TD082 | Step 5 |
| Brain-Next feedback integration | Moved to 02_Sprint-Builder | Removed |
| Chat vs Code executor labels per step | Brain-Next v2 pattern | All steps |
| Tool version check in FILE-TREE step | Moved from Step 2 into Step 1 | Step 1 |

---

[*] 05_Clean-Sync SPEC v3.0.0 * ready
Project data hygiene — FILE-TREE sync, path/version consistency, backlog health, stale pruning
Sequence: 04_Sprint-Closer → 05_Clean-Sync → 06_Brain-Next → 02_Sprint-Builder
Session Code: S{N}-Clean-Sync
Output: clean FILE-TREE, consistent paths/versions, healthy backlogs, lean active files, CHANGELOG-{PROJECT}.md
Next chat: S{N}-Brain-Next — run 06_Brain-Next
