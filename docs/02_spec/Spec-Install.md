# Spec-Install
> SPEC v3.0.0 | Entry protocol — onboard existing project or set up new project
> Use ONLY for first SPEC setup. For continuing work — load S{N}-SPRINT.md → Next Action.

---

## Where Are You?


Reading this file?
│
├── Existing project with code/docs, no SPEC
│   └── → Part 1: Collect Reference Docs (Step 1–5)
│       └── then → Part 2: Create SPEC Structure (Step 6–10)
│
├── Existing SPEC v2.x project migrating to v3.0
│   └── → Part 1: Collect Reference Docs (Step 1–5)
│       └── then → Step 5.1: SPEC v2.x Migration
│           └── then → Part 2: Create SPEC Structure (Step 6–10)
│
├── New project, no code yet
│   └── → Part 1: Step 4 (Collect from Scratch)
│       └── then → Part 2: Create SPEC Structure (Step 6–10)
│
└── SPEC project, continuing work
    └── STOP — wrong protocol.
        Load S{N}-SPRINT.md from current sprint folder.
        Read section: Next Action — that is your next step.


---

## Purpose

Audit an existing project (or collect information for a new one), create reference documents,
set up SPEC folder structure, ADR library, quality tools, and launch first sprint.

After this protocol — the project is ready for development cycles.

Output:
- `docs/01_refer/` populated with VISION-{PROJECT}.md, ARCHITECTURE-{PROJECT}.md, ROADMAP-{PROJECT}.md, ENVIRONMENT.md, BACKLOG-{PROJECT}.md
- `docs/02_spec/` populated with protocol files
- `docs/03_sprint/` with first sprint folder
- `docs/01_refer/KNOWLEDGE/ADR-{PROJECT}/` with ADR structure
- First sprint launched via 02_Sprint-Builder

---

## Before You Begin

Load in chat:

□ 01_Declaration.md
□ This file (Spec-Install.md)


No other SPEC documents exist yet — this protocol creates them.
For SPEC v2.x migration: existing S{N}-SPRINT.md and project docs remain on disk.
Do not load them into this chat — Step 5.1 handles migration in place.

---

# ═══════════════════════════════════════
# PART 1 — Collect Reference Documents
# ═══════════════════════════════════════

## Step 1: Scout the Project

> **New project with no code:** skip to Step 4.

Create scout prompt. Claude Code maps the project:


□ List all files under docs/ (if exists)
□ List top-level source directories and key entry points
□ List existing config files (.env, package.json, requirements.txt, etc.)
□ List existing test directories and test files
□ Check for .git — is the project under version control?
□ Check for existing decisions/ folders in sprint directories (v2.x migration scope)


Output the full file tree.

**After Scout — STOP. Claude Chat reviews.**

---

## Step 2: Assess What Exists

For each document found, answer:
- Does it reflect current reality?
- Is it referenced anywhere?
- Is it a duplicate of something else?

Create a quick audit table in chat:


| File | Status | Action |
|------|--------|--------|
| VISION-{PROJECT}.md | outdated | update |
| old-notes.md | unused | delete |
| README.md | partial overlap with ARCHITECTURE | merge |


---

## Step 3: Identify Current State

Determine:
- What sprint are you on? (or: is there a sprint concept at all?)
- What phase? What cycle?
- What was the last completed work?
- What is the immediate next step?

If the project has no sprint structure — that is fine. Record the current state as-is.
Part 2 will create the structure.

---

## Step 4: Create Reference Documents

Ensure these exist and are current. If existing docs cover the topic — rename/move.
If outdated — rewrite based on current reality.

**For new projects with no code:** collect information from Human to create these documents.

### VISION-{PROJECT}.md

Answer these questions in the file:
- What is this project?
- What problem does it solve?
- Who uses it?
- What does success look like at the end?

Keep it under 1 page.

### ARCHITECTURE-{PROJECT}.md

Document:
- Main components / modules
- How they interact
- Key technology choices
- What is intentionally out of scope
- Coding Standards: naming conventions, error handling pattern, logging format,
  import order, test structure (Rule 17)

### ROADMAP-{PROJECT}.md

List sprints: `S1: [name] — [one line goal]`
Keep total under ~100 lines. This is a reference document, not a task list.

No Backlog section in ROADMAP-{PROJECT}.md — project backlog lives in a separate file.
See Step 4b below.

If the project had an existing backlog (any format) — migrate items into BACKLOG-{PROJECT}.md (Step 4b).

### ENVIRONMENT.md

Location: `docs/01_refer/ENVIRONMENT.md`

Document:
- System: OS, shell, project path, Prompt Detail Level
- Tools: language, runtime, package manager versions
- Quality Tools table:

| Tool | Command | Purpose |
|------|---------|---------|
| Linter | [command or "not configured"] | Code style enforcement |
| Formatter | [command or "not configured"] | Auto-formatting |
| Type checker | [command or "not configured"] | Static type verification |
| Pre-commit | [command or "not configured"] | Automated checks |
| Mutation testing | [command or "not configured"] | Test quality measurement |
| SCA scanner | [command or "not configured"] | Vulnerability scanning |

- Git Workflow: branch strategy, commit convention, rules
- Known Limitations section:

markdown
## Known Limitations

Things Claude Code CANNOT do in this project environment:

| Limitation | Workaround |
|------------|------------|
| [limitation] | [workaround] |


- Project Structure (compact) with reference to FILE-TREE-{PROJECT}.md for full detail
- Information Map section:

```markdown
## Information Map
> File boundary definitions. What each file contains and does NOT contain.
> Producer/Consumer tracking: define in this table as needed.

| File | Contains | Does NOT Contain |
|------|----------|-----------------|
| VISION-{PROJECT}.md | Problem, user, solution approach, success metrics | Implementation details, technical specs |
| ARCHITECTURE-{PROJECT}.md | Current system state, components, standards, key decisions | Plans, future state, task lists |
| ROADMAP-{PROJECT}.md | Strategic sprint sequence | Phase details, cycle tasks |
| ENVIRONMENT.md | System, tools, shell notes, Information Map | Protocol rules, project decisions |
| FILE-TREE-{PROJECT}.md | Complete file/folder structure | File contents, code |
| BACKLOG-{PROJECT}.md | Code issues, tech debt, features, protocol improvements, carry-forward | — |
| S{N}-SPRINT.md | Current state, protocol log, next action | Success criteria (→ S{N}-SPRINT), carry-forward (→ SNAPSHOT) |
| S{N}-SPRINT.md | Sprint scope, phases, success criteria, carry-forward | Cycle-level details (→ P{NN}) |
| P{NN}-{name}.md | Phase tasks with KB/ADR refs, cycles, tests, exit criteria | Other phase details, architectural decisions |
| C{NN}.md | Cycle goal, steps, scout findings, result | Phase-level planning |
| S[N]-SNAPSHOT.md | Immutable sprint record, stats, carry-forward, balance | Mutable data, plans |
| CODE-AUDIT-SN.md | Audit findings, severity, balance assessment | Fixes (→ BACKLOG-{PROJECT}) |
| S[N]-RETRO.md | Process observations, what worked/didn't | Carry-forward items (→ SNAPSHOT) |
| KNOWLEDGE-{PROJECT}.md | L0 compact KB domain list | Domain details (→ L1), topic content (→ L2) |
| KNOWLEDGE-{PROJECT}.md | L0 compact ADR decision list | Decision details (→ ADR files), research (→ research/) |

> Project adds specific files below this line during setup.
```

- Shell Notes (project-specific pitfalls)
- Tool Notes (project-specific pitfalls)

If tools are already configured — verify they run correctly.
If project is too early for tooling — note: "Configure quality tools when codebase stabilizes"
and add to BACKLOG-{PROJECT}.md.

### Step 4b: BACKLOG-{PROJECT}.md

Location: `docs/01_refer/KNOWLEDGE/BACKLOG-{PROJECT}.md`

Create project backlog as a standalone file (not inside ROADMAP-{PROJECT}.md):

markdown
# PROJECT BACKLOG
> [Project Name]
> Updated: [date]
> Location: docs/01_refer/KNOWLEDGE/BACKLOG-{PROJECT}.md
> Project-level issues, tech debt, carry-forward items.
> Consumed by: 02_Sprint-Builder (scope planning), 02_Sprint-Builder PART 1 (cycle assignment).

| # | Item | Source | Priority | Status |
|---|------|--------|----------|--------|


If the project had an existing backlog (any format) — migrate items into this table.

**After creating/updating all documents — STOP.**


SPEC v2.x migration?
├── YES → proceed to Step 5.1
└── NO  → proceed to Step 5.2 (Security Check)


---

## Step 5.1: SPEC v2.x Migration (existing SPEC projects only)

> Skip this step entirely if the project has never used SPEC.

### Session Code Migration

Update any active S{N}-SPRINT.md Protocol Log entries:

| Old Code | New Code | Note |
|---|---|---|
| S{N}CA | S{N}-Code-Review | Code Audit → Code Review |

All other Session Codes are unchanged.

### ADR Migration

Migrate ADR and debate artifacts from per-sprint folders to centralized location:


Source: docs/03_sprint/S{N}-[name]/decisions/
Target:
  ADR-NNN-*.md        → docs/01_refer/KNOWLEDGE/ADR-{PROJECT}/
  research-*.md        → docs/01_refer/KNOWLEDGE/ADR-{PROJECT}/research/
  prompt-debate-*.md   → docs/01_refer/KNOWLEDGE/ADR-{PROJECT}/debates/


For each sprint folder that has a `decisions/` subfolder:
1. Move ADR files to `docs/01_refer/KNOWLEDGE/ADR-{PROJECT}/`
2. Move research files to `docs/01_refer/KNOWLEDGE/ADR-{PROJECT}/research/`
3. Move debate prompts to `docs/01_refer/KNOWLEDGE/ADR-{PROJECT}/debates/`
4. Remove empty `decisions/` folders

After migration — create `docs/01_refer/KNOWLEDGE/ADR-{PROJECT}/KNOWLEDGE-{PROJECT}.md` with all moved ADRs.

### Phase Document Rename

Rename `PHASE.md` to `P{NN}-{name}.md` in all existing sprint phase folders:


docs/03_sprint/S{N}-[name]/P{NN}-[name]/PHASE.md
  → docs/03_sprint/S{N}-[name]/P{NN}-[name]/P{NN}-{name}.md


Extract the phase number from the folder name (`P{NN}-*`) and use it in the filename.

### ENVIRONMENT.md Relocation


Source: docs/03_sprint/ENVIRONMENT.md
Target: docs/01_refer/ENVIRONMENT.md


Update S{N}-SPRINT.md reference if pointing to old path.

### Project BACKLOG.md Migration


Source: docs/03_sprint/BACKLOG.md
Target: docs/01_refer/KNOWLEDGE/BACKLOG-{PROJECT}.md (append items)


After migration — delete `docs/03_sprint/BACKLOG.md`.

### Protocol File Reference Update

Update S{N}-SPRINT.md → SPEC section:

| Old | New |
|-----|-----|
| `Rules \| docs/02_spec/01_RULES.md` | `Declaration \| docs/02_spec/01_Declaration.md` |

Update S{N}-SPRINT.md → References section:

| Old | New |
|-----|-----|
| `ENVIRONMENT \| docs/03_sprint/ENVIRONMENT.md` | `ENVIRONMENT \| docs/01_refer/ENVIRONMENT.md` |
| (add row) | `ADR-INDEX \| docs/01_refer/KNOWLEDGE/ADR-{PROJECT}/KNOWLEDGE-{PROJECT}.md` |

### Inline ADR Path References

Scan project documents for old ADR paths and update:


Search pattern: docs/03_sprint/S{N}-[name]/decisions/ADR-
Replace with:   docs/01_refer/KNOWLEDGE/ADR-{PROJECT}/ADR-

Files to check:
□ ARCHITECTURE-{PROJECT}.md → Key Decisions table
□ S{N}-SPRINT.md → Key Decisions section
□ C{NN}-*.md → any ADR references in Scout Findings or Steps


**After all migration steps — STOP. Claude Chat verifies.**

---

## Step 5.2: Security Check


□ No hardcoded secrets, API keys, tokens in codebase?
□ No credentials in config files or .env examples?
□ No secrets in git history (recent commits)?


If found → fix before proceeding. Do not commit secrets.

---

## Step 5.3: Verify Reference Documents


□ docs/01_refer/ has VISION-{PROJECT}.md, ARCHITECTURE-{PROJECT}.md, ROADMAP-{PROJECT}.md, ENVIRONMENT.md
□ VISION-{PROJECT}.md answers: what, problem, user, success
□ ARCHITECTURE-{PROJECT}.md has: components, interactions, tech choices, out of scope, coding standards
□ ROADMAP-{PROJECT}.md has: sprint list (no backlog — separate file)
□ BACKLOG-{PROJECT}.md created (docs/01_refer/KNOWLEDGE/)
□ ENVIRONMENT.md has: System (OS, shell, path, Prompt Detail Level), Tools,
  Quality Tools, Git Workflow, Known Limitations, Project Structure,
  Information Map section populated
□ Security check passed (no secrets in code)
□ If SPEC v2.x migration: ADR migrated, PHASE.md renamed, ENVIRONMENT.md moved,
  BACKLOG.md merged, inline ADR paths updated


**After verification — STOP. Proceed to Part 2.**

---

# ═══════════════════════════════════════
# PART 2 — Create SPEC Structure
# ═══════════════════════════════════════

## Naming Conventions

All projects MUST use these naming conventions:

| Item | Convention | Example |
|------|-----------|---------|
| Sprint folder | `S{N}-short-name/` | `S12-four-streams/` |
| Phase folder | `P{NN}-short-name/` | `P01-foundation/` |
| Phase doc | `P{NN}-{name}.md` | `P01-{name}.md` |
| Sprint doc | `S{N}-SPRINT.md` | `S8-SPRINT.md` |
| Cycle doc | `C{NN}-{name}.md` | `C01-setup.md` |
| ADR | `ADR-NNN-short-name.md` | `ADR-001-auth-strategy.md` |
| ADR index | `KNOWLEDGE-{PROJECT}.md` | — |
| Research artifact | `research-[topic].md` | `research-auth-libs.md` |
| Debate prompt | `prompt-debate-[topic].md` | `prompt-debate-auth.md` |
| Snapshot | `S[N]-SNAPSHOT.md` | `SNAPSHOT-S3.md` |
| Code audit | `CODE-AUDIT-SN.md` | `CODE-AUDIT-S3.md` |
| Retrospective | `S[N]-RETRO.md` | `RETRO-S3.md` |

Rationale: `P{NN}-{name}.md` and `C{NN}-{name}.md` are self-identifying — when opened outside folder context, the file name tells you which phase or cycle it is.

---

## Step 6: Create Folder Structure

Create execute prompt. Claude Code creates the target structure:


docs/
├── 01_refer/
│   ├── VISION-{PROJECT}.md               ← exists (from Part 1)
│   ├── ARCHITECTURE-{PROJECT}.md         ← exists (from Part 1)
│   ├── ROADMAP-{PROJECT}.md              ← exists (from Part 1)
│   ├── ENVIRONMENT.md                    ← exists (from Part 1)
│   ├── FILE-TREE-{PROJECT}.md            ← create (initial project file tree)
│   └── KNOWLEDGE/                        ← unified knowledge hierarchy
│       ├── BACKLOG-{PROJECT}.md           ← create (project backlog)
│       ├── KNOWLEDGE-{PROJECT}.md         ← combined KB + ADR index (L0)
│       ├── ARCHIVES/
│       ├── CODE-AUDIT/                    ← consolidated audit reports
│       │   └── PROBKIT-REVIEW/            ← raw ProbeKit reports (temp)
│       ├── SNAPSHOT/                      ← sprint snapshots
│       ├── RETRO/                         ← sprint retrospectives
│       ├── BRAIN-NEXT/                    ← brain-next session outputs
│       ├── ADR-{PROJECT}/                 ← architecture decision records
│       └── KB-*/                          ← knowledge base domains
│
├── 02_spec/
│   ├── 01_Declaration.md
│   ├── 02_Sprint-Builder.md
│   ├── 03_Phase-Builder.md
│   ├── 04_Sprint-Closer.md
│   ├── 05_Clean-Sync.md
│   ├── 06_Brain-Next.md
│   ├── 07_Validation.md
│   ├── Resolution.md
│   ├── Deploy.md
│   └── Spec-Install.md
│
└── 03_sprint/
    ├── s01-[name]/             ← first sprint folder


Root `docs/02_spec/` = protocol files only.

**After creation — STOP.**

---

## Step 7: Configure Quality Tools

Set up baseline code quality tools for the project.


□ Linter configured?
□ Formatter configured?
□ Type checker configured (if applicable)?
□ Pre-commit hook or equivalent?


Document chosen tools in ENVIRONMENT.md → Quality Tools section.

If tools are already configured — verify they run correctly.
If project is too early for tooling — skip, but create execute prompt for Claude Code
to add to BACKLOG-{PROJECT}.md: "Configure quality tools when codebase stabilizes."

**After setup — STOP.**

---

## Step 8: Create ADR Structure

Create execute prompt. Claude Code creates:


docs/01_refer/KNOWLEDGE/ADR-{PROJECT}/                  ← folder
docs/01_refer/KNOWLEDGE/ADR-{PROJECT}/KNOWLEDGE-{PROJECT}.md      ← index file
docs/01_refer/KNOWLEDGE/ADR-{PROJECT}/research/         ← empty
docs/01_refer/KNOWLEDGE/ADR-{PROJECT}/debates/          ← empty
docs/01_refer/KNOWLEDGE/KNOWLEDGE-{PROJECT}.md      ← KB master index


KNOWLEDGE-{PROJECT}.md content:

markdown
# ADR Index
> All architectural decisions for the project.
> Updated: each time an ADR is created, superseded, or deprecated.

| # | ADR | Title | Date | Status | Sprint | Summary |
|---|-----|-------|------|--------|-----------|---------|


Status values: ACCEPTED, SUPERSEDED (by ADR-NNN), DEPRECATED.

**After creation — STOP.**

---

## Step 9: Initial Commit

Create execute prompt. Claude Code commits the initial SPEC structure:


git add docs/
git commit -m "init: SPEC v3.0.0 project structure"
git push


**After commit — STOP.**

---

## Step 10: Launch First Sprint

Open a new chat — Session Code: **S1-Sprint-Builder**

Load:

□ 01_Declaration.md
□ 02_Sprint-Builder.md
□ VISION-{PROJECT}.md
□ ARCHITECTURE-{PROJECT}.md
□ ROADMAP-{PROJECT}.md
□ docs/01_refer/ENVIRONMENT.md
□ KNOWLEDGE-{PROJECT}.md (from docs/01_refer/KNOWLEDGE/ADR-{PROJECT}/)


Run 02_Sprint-Builder.

After 02_Sprint-Builder closes → new chat Session Code **S1PB** → run 02_Sprint-Builder PART 1.
02_Sprint-Builder PART 1 creates all P{NN}-{name}.md files and S1-SPRINT.md.

**S{N}-SPRINT.md template:** use embedded template from 02_Sprint-Builder PART 1 Step 4.
That is the single source of truth (SSOT). This protocol does NOT maintain a separate copy.

After 02_Sprint-Builder PART 1 closes → next chat Session Code **S1P01C01** → run 03_Phase-Builder.

## Chat Boundary — MANDATORY STOP

After completing Spec-Install — this chat is DONE. Close it.
Do NOT start 02_Sprint-Builder in this chat.
One protocol = one chat. No exceptions.
Next protocol = new chat.

---

## Tier Registry

Canonical reference for document versioning tiers (from ADR-XXX).

| Document | Path | Tier | Format |
|----------|------|------|--------|
| 01_Declaration.md | docs/02_spec/ | 1 | SPEC MAJOR.MINOR.PATCH |
| 02_Sprint-Builder.md | docs/02_spec/ | 1 | SPEC MAJOR.MINOR.PATCH |
| 03_Phase-Builder.md | docs/02_spec/ | 1 | SPEC MAJOR.MINOR.PATCH |
| 04_Sprint-Closer.md | docs/02_spec/ | 1 | SPEC MAJOR.MINOR.PATCH |
| 05_Clean-Sync.md | docs/02_spec/ | 1 | SPEC MAJOR.MINOR.PATCH |
| 06_Brain-Next.md | docs/02_spec/ | 1 | SPEC MAJOR.MINOR.PATCH |
| 07_Validation.md | docs/02_spec/ | 1 | SPEC MAJOR.MINOR.PATCH |
| Resolution.md | docs/02_spec/ | 1 | SPEC MAJOR.MINOR.PATCH |
| Deploy.md | docs/02_spec/ | 1 | SPEC MAJOR.MINOR.PATCH |
| Spec-Install.md | docs/02_spec/ | 1 | SPEC MAJOR.MINOR.PATCH |
| ARCHITECTURE-{PROJECT}.md | docs/01_refer/ | 2 | MAJOR.MINOR + changelog |
| VISION-{PROJECT}.md | docs/01_refer/ | 2 | MAJOR.MINOR + changelog |
| ENVIRONMENT.md | docs/01_refer/ | 3 | Date stamp only |
| ROADMAP-{PROJECT}.md | docs/01_refer/ | 3 | Date stamp only |
| FILE-TREE-{PROJECT}.md | docs/01_refer/ | 3 | Date stamp only |
| BACKLOG-{PROJECT}.md | docs/01_refer/KNOWLEDGE/ | 3 | Date stamp only |
| S{N}-SPRINT.md | docs/03_sprint/ | 4 | None |
| P{NN}-{name}.md | docs/03_sprint/ | 4 | None |
| C{NN}-{name}.md | docs/03_sprint/ | 4 | None |
| S[N]-SNAPSHOT.md | docs/03_sprint/ | 4 | None |
| CODE-AUDIT-SN.md | docs/03_sprint/ | 4 | None |
| S[N]-RETRO.md | docs/03_sprint/ | 4 | None |
| ADR files | docs/01_refer/KNOWLEDGE/ADR-{PROJECT}/ | 4 | None (status field) |
| KB L0/L1/L2 artifacts | docs/01_refer/KNOWLEDGE/ | 4 | None |

**Tier definitions:**
- **Tier 1 — SPEC versioned (shared):** Single MAJOR.MINOR.PATCH version across all. Header = canonical source; anchor = display copy (must match).
- **Tier 2 — Individually versioned:** MAJOR.MINOR + inline changelog. Bumped by any protocol that modifies the document.
- **Tier 3 — Date-stamped:** `Updated: YYYY-MM-DD` in header. No version number.
- **Tier 4 — No versioning:** Lifecycle-bound or immutable after close.

**Disambiguation:** `06_Brain-Next.md` at `docs/02_spec/` is a protocol file (Tier 1) that orchestrates KB/ADR audits.
The `KNOWLEDGE/` folder at `docs/01_refer/KNOWLEDGE/` contains generated
KB (KB-*/) and ADR (ADR-{PROJECT}/) L0/L1/L2 artifacts (Tier 4). These are distinct.

---

## Checklist


□ Part 1: Reference docs exist and are verified
  (VISION, ARCHITECTURE, ROADMAP, ENVIRONMENT in docs/01_refer/)
□ Part 1: Security check passed
□ Part 1: migration complete (if applicable)
□ Part 2: Folder structure created (docs/01_refer/, 02_spec/, 03_sprint/)
□ Part 2: Information Map section added to ENVIRONMENT.md
□ Part 2: Quality tools configured (or deferred to Project Backlog)
□ Part 2: ADR structure created (KNOWLEDGE-{PROJECT}.md, research/, debates/)
□ Part 2: FILE-TREE-{PROJECT}.md created
□ Part 2: Initial commit pushed
□ Part 2: First sprint launched (02_Sprint-Builder → 02_Sprint-Builder PART 1)


---


[*] Spec-Install SPEC v3.0.0 * ready
Entry protocol — onboard existing project or set up new project
Output: docs/01_refer/ populated + SPEC structure created + first sprint launched
S{N}-SPRINT.md template SSOT: 02_Sprint-Builder PART 1 Step 4
Next: 02_Sprint-Builder (Session Code S1-Sprint-Builder)
