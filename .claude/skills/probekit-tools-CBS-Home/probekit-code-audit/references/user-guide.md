# code-audit — User Guide

Senior engineer code review for Claude Code.
Finds bugs, security issues, AI-specific defects, bad practices, and test quality problems.
Returns a scored report with diffs and actionable fixes.
Optionally auto-fixes CRITICAL and WARNING findings.

---

## Installation

### Option A — Project-level (applies to one repo)

Place the skill folder inside your repository:

your-repo/
  .claude/
    skills/
      code-audit/
        SKILL.md
        references/

Claude Code will auto-discover it when you open the repo.

### Option B — Global (available in all projects)

Place the skill folder in your home directory:

~/.claude/skills/code-audit/

Available in every Claude Code session on your machine.

### Install from GitHub

If the skill is published on GitHub:

cd ~/.claude/skills
git clone https://github.com/YOUR_ORG/code-audit

Or clone into a project:

cd your-repo/.claude/skills
git clone https://github.com/YOUR_ORG/code-audit

---

## Invocation

### Slash command (explicit)

/code-audit src/auth/login.py
/code-audit src/
/code-audit .

### Auto-trigger (implicit)

Claude Code loads the skill automatically when you write:

"review this code"
"audit src/payment.js"
"find bugs in this file"
"check my code"
"what's wrong with services/"

Or paste code directly in chat — the skill triggers without an explicit command.

---

## Usage Examples

### Review a single file

/code-audit src/api/users.py

### Review an entire directory

/code-audit src/

### Review current directory (full repo scan)

/code-audit .

### Review with focus

/code-audit src/auth/ — focus on security

### Review and auto-fix

/code-audit src/api/users.py --fix

Applies all CRITICAL and WARNING fixes automatically, then re-verifies.

### Review multiple files with cross-module analysis

/code-audit src/db/database.py src/services/persistence.py

When 2+ files are reviewed together, Section 11 (Cross-Module Consistency)
detects inconsistencies between them: duplicate APIs, inconsistent patterns,
contract mismatches, etc.

### Audit test quality specifically

/code-audit tests/ --tests

Triggers expanded treatment of Section 12 (Test Quality Audit).
All other sections still run, but test analysis is the primary focus.

Also triggers automatically when you write:
"audit tests"
"check tests"
"проверь тесты"
"what's wrong with my tests"

### Review pasted code

Paste code directly, then write:
"review this" — skill activates automatically

### Save report to file

For large files or directories, the skill saves the report automatically.
Filename pattern:
- Single file: CODE-REVIEW-[basename]-[YYYYMMDD].md
- Directory: CODE-REVIEW-[dirname]-[YYYYMMDD].md
- Current dir (.): CODE-REVIEW-[project-root-name]-[YYYYMMDD].md

---

## What the Skill Checks

12 sections per review:

1. General overview + score (1-10)
2. Critical bugs and logic errors
3. Error handling quality
4. Security vulnerabilities (injection, secrets, privilege escalation, auth drift)
5. Performance bottlenecks
6. Code quality and best practices
7. Testability
8. Refactoring recommendations
9. Minor improvements and polish
10. AI-generated code patterns (slopsquatting, god classes, phantom code, prompt residue, etc.)
11. Cross-module consistency (multi-file reviews only)
12. Test quality audit (when test files are present)

---

## Section 12 — Test Quality Audit

Runs automatically whenever test files are detected in the review scope.
With `--tests` flag or "проверь тесты" — expanded treatment.

What it checks:

**12.1 Coverage Gaps**
Critical paths with no tests, untested error branches, missing boundary tests.
Does not chase 100% coverage — flags gaps on high-risk paths only.

**12.2 Test Effectiveness**
The most important subsection. Detects tests that exist but don't actually test anything:
- Assert-free tests (pass no matter what)
- Trivial assertions that verify existence, not correctness
- Mocking the system under test itself
- Happy path only — no error paths, no edge cases
- Tautological tests

**12.3 Test Isolation and Reliability**
Tests that depend on each other, leave state behind, or assume specific environments.

**12.4 Flakiness Indicators**
`time.sleep()` synchronization, floating point equality, order-dependent tests,
time-dependent assertions, random data in assertions.

**12.5 Test Design Quality**
God tests, excessive setup, copy-paste tests that need parameterization,
anonymous test names, free-ride assertions.

**12.6 Test Maintenance Debt**
Permanently skipped tests, commented-out tests, tests for deleted code,
missing regression tests for known bugs.

**12.7 Test Architecture (suites with 20+ files)**
Inverted pyramid, no integration layer, missing contract tests, slow/fast test mix.

---

## Fix Mode (--fix)

When invoked with `--fix`, the skill:
1. Runs the full audit as usual (all 12 sections)
2. Automatically applies CRITICAL and WARNING fixes to source files
3. Skips SUGGESTION-level items (too subjective for auto-fix)
4. Re-runs verification on Sections 2 (bugs) and 4 (security) on modified files
5. Reports how many fixes were applied and any remaining issues

Trigger words: `--fix`, "fix", "починь", "исправь"

Example:
/code-audit src/db/database.py --fix

---

## Environment Detection

The skill automatically checks for ENVIRONMENT.md in your project
(typically at root or docs/01_refer/).

If found, it reads shell/tool pitfalls and adapts command syntax accordingly.
This means the skill works correctly on Windows/PowerShell, macOS/zsh,
Linux/bash, and other environments without manual configuration.

---

## Audit Tracker

The skill maintains an `AUDIT-TRACKER.md` in the review directory.
Each audit appends a row with date, files, score, and severity counts.

Re-auditing the same files shows a delta column:
- What improved (fewer findings)
- What regressed (new findings)
- First audit marked as "new"

This enables tracking code quality progress across milestones.

---

## Output Format

Each finding is marked:

🔴 CRITICAL — bug, security issue, data loss risk, crash
🟡 WARNING — bad practice, real consequences
🟢 SUGGESTION — improvement, polish

Every finding includes:
- Location (file:line or function name)
- Before/after diff
- Explanation of impact

Final report ends with:
- Score X/10
- Prioritized action lists by severity
- Totals table

---

## Configuration

The `review_dir` variable in SKILL.md controls where reports are saved.
Default: `docs/01_refer/ARCHIVES/CODE-AUDIT/PROBKIT-REVIEW`

To change for your project, edit the Configuration section in SKILL.md.

---

## Language Support

The skill adapts to the language of your request.
Write in English → report in English.
Write in Russian → report in Russian.
Write in any other language → report in that language.

Code language detection is automatic (Python, JavaScript, TypeScript, Go, Rust,
Java, C#, GDScript, PHP, Ruby, and others).

---

## Notes

- The skill never invents findings. If a section has no issues, it says so explicitly.
- For AI-generated codebases: Section 10 (AI patterns) is especially important.
  Slopsquatting (hallucinated package names) is flagged as CRITICAL and must be
  verified before running npm install / pip install.
- Section 12 runs automatically when test files are present — no flag needed.
  The `--tests` flag only triggers expanded treatment of the section.
- Large directories: the skill reads entry points and main modules first,
  then digs into dependencies. For very large repos (1000+ files), provide
  a subdirectory path for focused review.
