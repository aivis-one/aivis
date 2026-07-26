# ProbeKit Severity Format — Core Reference

Canonical severity definitions for all ProbeKit skills.
Each skill reads this file for core format, then applies its own escalation rules.

## Severity Markers

| Marker | Icon | Label | Definition |
|--------|------|-------|------------|
| CRITICAL | 🔴 | Blocks release | Bug, security vulnerability, data loss, crash, architectural defect causing system failure |
| WARNING | 🟡 | Should fix | Bad practice with real consequences for maintainability, performance, or reliability |
| SUGGESTION | 🟢 | Nice to have | Improvement opportunity, modernization, clean code, future readiness |
| DIAMOND | 💎 | Highlight | Exceptional pattern worth preserving and replicating |

No other severity levels exist. Do not invent intermediate levels.

## Output Syntax

### Standard format (all skills)

```
🔴 CRITICAL — [short description]
Location: [file:line or module]
Issue: [what's wrong]
Impact: [what will happen if not fixed]
Fix: [specific fix steps]

🟡 WARNING — [short description]
Location: [file:line or module]
Issue: [what's wrong]
Impact: [what could happen]
Fix: [suggested approach]

🟢 SUGGESTION — [short description]
Location: [file:line or module]
Observation: [what could be better]
Suggestion: [improvement idea]

💎 DIAMOND — [short description]
Location: [file:line or module]
Pattern: [what was done well]
Why: [why this is exceptional]
```

### Compact format (when context is obvious)

```
🔴 CRITICAL — [short description]
🟡 WARNING — [short description]
🟢 SUGGESTION — [short description]
💎 DIAMOND — [short description]
```

Use standard format for report files. Compact format is acceptable for inline chat output on small inputs.

## Diff Format

Every finding that recommends a change SHOULD include a before/after diff:

```
// BEFORE:
[original code]

// AFTER:
[corrected code]
```

Rules:
- Show only the relevant snippet, not the entire file
- Keep diffs minimal — changed lines plus enough context to locate them
- If the fix requires significant restructuring, show the key section and note "full refactor needed"
- Architecture-level findings (module moves, dependency inversions) may omit diffs and describe the refactoring instead

## Severity Decision Tree

```
Is it causing or will cause bugs/data loss/security issues?
  YES → 🔴 CRITICAL
  NO  ↓
Will it cause real problems for maintainability/performance/reliability?
  YES → 🟡 WARNING
  NO  ↓
Could the code/architecture/tests be notably improved?
  YES → 🟢 SUGGESTION
  NO  ↓
Is this an exceptionally elegant solution?
  YES → 💎 DIAMOND
  NO  → No finding needed
```

## Universal Escalation Rules

These apply across ALL skills regardless of domain:

- Hardcoded secret or credential → always 🔴 CRITICAL
- SQL/NoSQL injection, XSS, path traversal, SSRF → always 🔴 CRITICAL
- Missing auth check on protected endpoint → always 🔴 CRITICAL
- Test/scenario with zero assertions → always 🔴 CRITICAL
- Assertion-free code that silently passes → always 🔴 CRITICAL

## No-Finding Rule

If a section has no problems: write exactly "No issues found." and proceed.
Never write vague filler. Never invent findings to pad sections.
Write "No diamond patterns found." only if explicitly looking for diamonds.

## Honesty Rules

- Be maximally honest. If quality is bad, say so clearly.
- Do not soften findings to be polite.
- Do not add compliments before criticism.
- If overall quality is 2/10, score it 2/10 and explain why.
- If there is genuinely nothing wrong, say so — do not pad.
- Never invent passing results. Report actual output from actual commands.

## Test Result Markers (test skills only)

| Marker | Meaning |
|--------|---------|
| ✅ PASS | Test generated and passing |
| ❌ FAIL | Test failing after fix iterations — blocked |
| ⚠️ BLOCKED / NEEDS REVIEW | Cannot generate or fix — requires manual intervention |
| 🔵 SKIPPED | Skipped intentionally (missing dependency, external service) |

Additional markers for Godot/GUT:
| 🚫 UNTESTABLE | Method cannot be tested without refactor |
| ⏭️ PENDING | Test generated but marked pending |

## Coverage Estimate Scale (test skills only)

| Level | Meaning |
|-------|---------|
| HIGH | All paths + error paths covered |
| MEDIUM | Happy paths covered, some error/edge paths missing |
| LOW | Partial coverage, critical paths untested |
| NONE | No tests before this run |
