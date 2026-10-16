# Output Template — Type Audit

Build the final report in this exact structure after completing all steps.

---

## Report Header

```
Type Audit: [target path or "full project"]
Stack: Vue 3 + TypeScript [detected versions]
tsconfig: [path to tsconfig used]
Date: [YYYY-MM-DD]
```

---

## Section 1: Compiler Check (vue-tsc)

Group errors by file. For each file:

```
### [relative/path/to/file.ts]

🔴 CRITICAL — TS2339: Property 'initData' does not exist on type '...'
Location: file.ts:66
Error code: TS2339

// BEFORE:
[code snippet showing the error context]

// AFTER:
[code snippet showing the fix]

Explanation: [why this error occurs and what the fix does]
```

If zero compiler errors:
```
💎 DIAMOND — Clean compiler check
All files pass vue-tsc with zero errors.
```

---

## Section 2: ESLint Type Rules

Same format as Section 1. Only include `@typescript-eslint/*` and Vue type-related rules.
Deduplicate: if same file:line already reported in Section 1, skip here.

---

## Section 3: Pattern Scan

Report findings from each pattern (4.1–4.10) that matched.
Group by severity, then by file.

```
### as any casts (Pattern 4.1)

🟡 WARNING — `as any` cast in production code
Location: src/stores/auth.ts:42
Observation: Type assertion bypasses type checking
Suggestion: Replace with specific type or add type guard

[List all occurrences in a table if > 3:]
| # | File | Line | Context |
|---|------|------|---------|
| 1 | src/stores/auth.ts | 42 | `response as any` |
| 2 | src/api/client.ts | 88 | `body as any` |
```

---

## Section 4: Summary

```
### Compiler Health
- vue-tsc errors: N (before fix: M)
- ESLint type violations: N

### Pattern Findings
| Pattern | Count | Severity |
|---------|-------|----------|
| as any casts | N | 🟡 |
| @ts-ignore without reason | N | 🟡 |
| ... | ... | ... |

### Auto-Fixes Applied (if fix_mode)
| # | File | Error | Fix |
|---|------|-------|-----|
| 1 | file.ts:42 | TS18046 | Added instanceof guard |
| 2 | types.ts:10 | TS2339 | Added missing property |
```

---

## Final Score Block

Score formula: `10 - (criticals * 2) - (warnings * 0.5) - (suggestions * 0.1)` (floor 0, cap 10)

```
Final Score: X/10

🔴 CRITICAL — must fix:
- [item 1]

🟡 WARNING — should fix:
- [item 1]

🟢 SUGGESTION — nice to have:
- [item 1]
```

---

## Totals Table

| Severity | Count |
|----------|-------|
| 🔴 CRITICAL | N |
| 🟡 WARNING | N |
| 🟢 SUGGESTION | N |
| 💎 DIAMOND | N |
| **Total** | **N** |

---

## Report Destination

Save report to: `{{review_dir}}/TYPE-AUDIT-{target}-{YYYYMMDD}.md`
- Full project: TYPE-AUDIT-frontend-YYYYMMDD.md
- Directory: TYPE-AUDIT-[dirname]-YYYYMMDD.md
- Single file: TYPE-AUDIT-[basename]-YYYYMMDD.md

After saving, output brief summary in chat: score, compiler errors count, pattern findings count, path to report.

---

## Audit Tracker Update

Append row to `{{review_dir}}/AUDIT-TRACKER.md`.
Format per `probekit-core/references/audit-tracker-format.md`.
Skill: `type-audit`, key metric: `compiler_errors`.
