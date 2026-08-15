---
name: probekit-code-audit
description: "Senior engineer code review with severity markers, diff examples, and scored report. Use when reviewing code files, directories, or pull requests for bugs, security vulnerabilities, performance issues, code quality, and test quality. Triggers on: 'review this code', 'audit', 'find bugs', 'check my code', 'code review', '/probekit-code-audit', or when the user pastes code without explicit instructions. Always use this skill when any file path, directory, or code snippet is provided for review — even if the user just says 'look at this' or shares code without a clear request, 'пробкит аудит', 'пробкит код'."
---

# code-audit v2.3.0

Senior engineer code review skill. Finds bugs, security issues, bad practices, and test quality problems.
Produces a scored report with actionable fixes. Optionally auto-fixes findings.

## Configuration

review_dir: docs/01_refer/ARCHIVES/CODE-AUDIT/PROBKIT-REVIEW

## Execution Steps

**Step 1 — Identify input and environment**
Determine what to review: single file, directory, or inline code.
- File/directory path → read with bash, detect language and framework
- Path with focus hint (e.g. `/code-audit src/auth/ -- focus on security`) →
  path is everything before `--` or `—`; text after is a focus hint,
  apply it as additional attention during all sections (not a filter — still run all sections)
- `--fix` flag (or words "fix", "починь", "исправь" in user message) →
  set fix_mode = true; remove flag from path before proceeding
- `--tests` flag (or words "audit tests", "check tests", "проверь тесты", "what's wrong with my tests") →
  set test_audit_mode = true; Section 12 becomes the primary focus (all other sections still run)
- Inline code in chat → use directly
- No input yet → ask: "What would you like me to review? Provide a file path, directory, or paste the code."

Check for ENVIRONMENT.md in the project (common locations: root, docs/01_refer/).
If found — read it for shell/tool pitfalls before executing any commands.
Do not hardcode shell syntax — adapt to the detected environment.

**Step 2 — Run full analysis**
Read `references/analysis-sections-core.md`.
Execute all 9 sections in order. No skipping.
Apply severity markers from `references/severity-format.md` to every finding.

**Step 3 — Run AI-specific scan**
Read `references/ai-patterns-catalog.md` and `references/ai-patterns-checklist.md`.
Add Section 10: AI-Generated Code Patterns.
Run even if origin is unknown — AI patterns appear in human-written code too.

**Step 3.5 — Cross-module analysis (multi-file only)**
If reviewing 2+ files:
Read `references/analysis-sections-core.md` Section 11.
Run cross-module consistency check across all reviewed files.
Add findings to report as Section 11: Cross-Module Consistency.
Skip this step if reviewing a single file or inline code.

**Step 3.6 — Test audit (always run if test files present)**
Read `references/analysis-sections-test-audit.md`.
Detect test files automatically:
- Python: files matching test_*.py or *_test.py
- JS/TS: *.test.*, *.spec.*
- Go: *_test.go
- GDScript: test_*.gd or res://tests/
- Any other: files inside directories named test, tests, spec, specs
If test files found → run Section 12: Test Quality Audit.
If no test files found → write: "No test files detected." and close section.
If test_audit_mode = true → give Section 12 expanded treatment (check all subsections thoroughly).

**Step 3.7 — Orphan source file detection (directory reviews only)**

**Scope:** Source code files only (.ts, .vue, .py, .go, .gd, .js, .rs, .java).
Non-source orphans (config, docs, data, assets) are owned by `probekit-project-hygiene` (PH-DEAD-FILES probe).

If reviewing a directory:
1. List all **source** files in the target directory (recursively)
2. For each non-test, non-config source file:
   - Grep the rest of the codebase for imports/references to this file's module/class/function
   - Check if the file is referenced in any manifest, config, or entry point
3. A file is "orphan" if:
   - Zero imports from any other source file
   - Not an entry point (main.py, app.py, __init__.py, index.*)
   - Not a config file (.toml, .yaml, .json, .env)
   - Not a migration, test, or documentation file
4. Flag findings (LOC-based severity):
   - Orphan file < 50 LOC: 🟢 SUGGESTION — likely dead code, verify and delete
   - Orphan file 50-200 LOC: 🟡 WARNING — significant unreferenced code
   - Orphan file > 200 LOC: 🔴 CRITICAL — major dead module, wasting maintenance attention

Add findings as Section 13: Orphan Source Files.
Skip if reviewing a single file or inline code — write: "Skipped (single file review)."

**Step 4 — Produce report**
Read `references/output-template.md`.
Build final scored report.
Adapt language to the user's language (respond in the same language the user wrote in).
For small input (<100 LOC or inline code): output report inline in chat.
For large input (file >100 LOC or directory): save report to `{{review_dir}}` (resolved from Configuration above) and inform the user of the exact path.

**Step 4.5 — Update audit tracker**
Read or create `{{review_dir}}/AUDIT-TRACKER.md`.
Append entry with: date, files reviewed, score, CRITICAL/WARNING/SUGGESTION counts.
If previous entries exist for the same files — show delta (resolved/new findings).
See `references/output-template.md` for tracker format.

**Step 5 — Fix mode (optional)**
If fix_mode is true:
Read `probekit-core/references/auto-fix-safety.md` — follow Safety Checklist and Fix-Verify-Revert Protocol.
1. For each CRITICAL finding: check 5-point safety checklist → apply fix → verify → confirm or revert
2. For each WARNING finding: same checklist → apply → verify → confirm or revert
3. Skip SUGGESTION fixes (per core standard: never auto-fix)
4. After applying all fixes, re-run a quick verification scan (Sections 2 + 4 only) on the modified files
5. Report using standard auto-fix table format (see core reference)
If fix_mode is false — skip this step entirely.

## Quick Reference

See `references/user-guide.md` for installation, invocation, and usage examples.

## Anchor

[*] code-audit v2.3.0 * ready
[>] | NEXT: user command
