# Fix Recommendations Template

Generated when `--fix` flag is set. Produces actionable file with concrete next steps.

```markdown
# Comprehension Debt — Action Plan — {date}

## 1. Files Needing Comprehension Review (Red/Orange)

Priority files where nobody can confidently explain the code.
Schedule comprehension reviews for these in the next sprint.

| # | File | Class | LOC | Action |
|---|------|-------|-----|--------|
| 1 | path/file.py | RED | 847 | Assign owner, schedule pair review |

## 2. Modules to Split (Context Window Fitness)

Modules exceeding 200 LOC that should be decomposed for AI-assisted development.

| # | File | LOC | Suggested Split |
|---|------|-----|----------------|
| 1 | path/large.py | 634 | Extract X into path/x.py, Y into path/y.py |

## 3. Duplication Clusters to Consolidate

Groups of files with duplicated code that should be extracted into shared modules.

| # | Pattern | Files | Lines | Action |
|---|---------|-------|-------|--------|
| 1 | Similar validation logic | file1.py, file2.py, file3.py | ~40 | Extract to shared/validation.py |

## 4. Domain Rules to Create

Bounded contexts or directories with no `.claude/rules/` coverage.
Each rule captures domain knowledge that prevents AI from making "unknown bugs."

| # | Domain/Path | Suggested Rule | Why |
|---|------------|---------------|-----|
| 1 | framework/payments/ | payments.md | Webhook idempotency, status mapping, Money value objects |

## 5. Three-File Protocol — Read These Now

The 3 files with the largest diffs in the analysis window.
Full read (not skim) — as if you wrote the code yourself.

1. **{file1}** — {N} lines changed
   - Key changes: {summary}
   - Comprehension risk: {why this needs attention}

2. **{file2}** — {N} lines changed
   - Key changes: {summary}
   - Comprehension risk: {why this needs attention}

3. **{file3}** — {N} lines changed
   - Key changes: {summary}
   - Comprehension risk: {why this needs attention}
```

Save to: `{{review_dir}}/COMPREHENSION-DEBT-FIXES-{YYYYMMDD}.md`
