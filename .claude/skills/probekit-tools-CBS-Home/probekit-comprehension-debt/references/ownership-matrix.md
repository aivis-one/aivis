# Ownership Matrix — Deep Mode Reference

Per-file ownership classification based on Addy Osmani's Comprehension Debt framework (2026).

## Classification Levels

### Green — Understood
- Single primary author (>60% of commits) OR pair with clear ownership
- Recent activity (commits within analysis_window)
- Commit messages are explainable (subject + why)
- File < 200 LOC (fits in AI context window)

### Yellow — Reviewed
- Multiple authors, all with meaningful commits (>20% each)
- AI-generated code that was deeply reviewed (non-trivial commit messages, follow-up modifications)
- File may be 200-500 LOC but well-structured (clear functions, good naming)
- At least one author could explain the code if asked

### Orange — Needs Re-read
- AI-heavy commits (auto-generated messages, large diffs, no follow-up modifications)
- Superficial review signals (merged quickly, no inline comments, single-approval)
- File > 200 LOC with complex logic
- Nobody has modified this file after initial creation
- High churn (rewritten within 14 days) suggests initial version wasn't understood

### Red — Nobody Knows
- No commits in 3x analysis_window (orphaned)
- No clear owner (diffuse authorship, all with < 20%)
- Opaque commit messages (generic subjects, no body)
- File > 500 LOC (exceeds AI reasoning boundary)
- High churn + diffuse ownership compound signal

## Output Format

```markdown
## Ownership Matrix — {target}

| # | File | LOC | Class | Owner | Last Touch | Signal |
|---|------|-----|-------|-------|------------|--------|
| 1 | path/file.py | 847 | RED | none | 94d ago | orphaned, god module, opaque commits |
| 2 | path/other.py | 312 | ORANGE | dev-a (40%) | 18d ago | AI-heavy, no follow-up review |
| 3 | path/svc.py | 124 | GREEN | dev-b (78%) | 3d ago | clear owner, recent activity |
```

Sort: RED first (highest risk), then ORANGE, YELLOW, GREEN.

## Risk Calculation

For each file: `risk = class_weight * (1 + churn_flag + size_flag)`
- class_weight: RED=4, ORANGE=3, YELLOW=2, GREEN=1
- churn_flag: 1 if file was rewritten within 14 days, else 0
- size_flag: 1 if file > 500 LOC, else 0

Report top 20 files by risk score.

## Goal Targets (from Osmani)

- **Zero Red in Tier 1** (payment logic, auth, external integrations, user data)
- **Minimum Orange everywhere** — every file should have at least one person who can explain it
- Sprint-over-sprint trend: Red count should decrease or stay flat, never increase
