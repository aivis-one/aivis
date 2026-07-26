# Severity Format — Type Audit Escalation Rules

Read `probekit-core/references/severity-format.md` first for universal format and decision tree.

## Type-Audit Specific Escalation Rules

| Condition | Severity | Reason |
|-----------|----------|--------|
| Compiler error in `.d.ts` file | Escalate +1 | Affects all consumers of the type |
| Compiler error in test file only | De-escalate -1 (min 🟢) | No production impact |
| `as any` in test helper | 🟢 SUGGESTION | Acceptable in test infrastructure |
| `as any` in production code | 🟡 WARNING | Type safety bypass |
| `as any` in security-sensitive code (auth, crypto, permissions) | 🔴 CRITICAL | Security-critical path loses type safety |
| `@ts-ignore` in code < 1 week old | 🟡 WARNING | Fresh code should not need suppressions |
| `@ts-ignore` with TODO/FIXME comment | 🟢 SUGGESTION | Acknowledged tech debt |
| Template using browser global directly | 🔴 CRITICAL | Vue compiler cannot type-check, runtime crash risk |
| Missing type on exported public API | 🟡 WARNING | Consumers lose type safety |
| Missing type on internal function | 🟢 SUGGESTION | TypeScript inference usually sufficient |
| > 10 compiler errors in single file | Escalate entire file to 🔴 | Systematic type-safety failure |
| Zero compiler errors project-wide | 💎 DIAMOND | Clean type discipline |

## Score Impact

Type audit scoring uses the standard formula from output-template.md:
`10 - (criticals * 2) - (warnings * 0.5) - (suggestions * 0.1)`

Floor: 0, Cap: 10.

## Interaction with Other Skills

- **code-audit**: type-audit findings in Step 4 (pattern scan) may overlap with code-audit Section 3 (type correctness). Deduplicate by canonical file:line.
- **security-audit**: `as any` in auth/crypto code feeds into security-audit as an additional signal.
- **unit-test**: compiler errors in test files are reported but de-escalated; unit-test skill handles test quality.
