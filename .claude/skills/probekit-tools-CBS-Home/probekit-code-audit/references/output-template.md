# Output Template

Build the final report in this exact structure after completing all sections.

---

## Report Header

Code Review: [filename or directory name]
Language/Framework: [detected stack]
Reviewed: [date if available, else omit]

---

## Section Results

Present each section with its heading and findings inline.
Sections flow naturally — no need to repeat section numbers in the output,
just use the section name as a heading.

Findings format within each section:

🔴 CRITICAL — Short description of the problem
Location: [file:line if available, else function/class name]

// BEFORE:
[code]

// AFTER:
[code]

Explanation: [one or two sentences on why this matters and what the fix achieves]

Use 🟡 WARNING or 🟢 SUGGESTION prefix for lower-severity findings. Same structure.

---

## Final Score Block

Place this at the end of the report.

---

Final Score: X/10

🔴 CRITICAL — must fix before shipping:
- [item 1]
- [item 2]

🟡 WARNING — recommended to fix:
- [item 1]
- [item 2]

🟢 SUGGESTION — nice to have:
- [item 1]
- [item 2]

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

Always save report to: `{{review_dir}}/CODE-AUDIT-<target>-<YYYYMMDD>.md`
- Single file: CODE-AUDIT-[basename-without-extension]-[YYYYMMDD].md
  Example: login.py → CODE-AUDIT-login-20260313.md
- Directory: CODE-AUDIT-[dirname]-[YYYYMMDD].md
  Example: src/auth/ → CODE-AUDIT-auth-20260313.md
- Current directory (.): CODE-AUDIT-[project-root-dirname]-[YYYYMMDD].md
Save to: {{review_dir}} (create directory if needed)
After saving, output brief summary in chat: score, finding counts, path to report.
Never truncate findings — if there are 20 CRITICALs, list all 20.

---

## Audit Tracker Update

> Format: see `probekit-core/references/audit-tracker-format.md` for table format, delta rules, and field definitions.

Append row with: skill=`code-audit`, key metric=`score`.
