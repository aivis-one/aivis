# Error Classification — TypeScript Compiler Errors

Maps TS error codes to severity levels and auto-fix eligibility.

## Classification Table

| TS Code | Category | Severity | Auto-fixable? | Description |
|---------|----------|----------|---------------|-------------|
| TS2339 | Missing property | 🔴 CRITICAL | Depends | Property does not exist on type — often missing type declaration |
| TS2345 | Type incompatibility | 🟡 WARNING | Sometimes | Argument not assignable — generics, overloads, library mismatches |
| TS2536 | Index type error | 🟡 WARNING | ✅ Yes | Type cannot be used to index type — generic constraint issue |
| TS2322 | Assignment error | 🟡 WARNING | Sometimes | Type not assignable — narrowing needed |
| TS18046 | Unknown type usage | 🔴 CRITICAL | ✅ Yes | Variable is of type 'unknown' — needs narrowing |
| TS7006 | Implicit any (param) | 🟡 WARNING | ✅ Yes | Parameter implicitly has 'any' type |
| TS7031 | Implicit any (binding) | 🟡 WARNING | ✅ Yes | Binding element implicitly has 'any' type |
| TS2304 | Cannot find name | 🔴 CRITICAL | Depends | Name not found — missing import or declaration |
| TS2307 | Module not found | 🔴 CRITICAL | ❌ No | Cannot find module — missing dependency or path |
| TS2551 | Spelling suggestion | 🟡 WARNING | ✅ Yes | Property does not exist, did you mean...? |
| TS6133 | Unused declaration | 🟢 SUGGESTION | ✅ Yes | Declared but never read |
| TS6196 | Unused import | 🟢 SUGGESTION | ✅ Yes | Import is declared but never used |
| TS2365 | Operator mismatch | 🔴 CRITICAL | ❌ No | Operator cannot be applied to types |
| TS2769 | Overload mismatch | 🟡 WARNING | Sometimes | No overload matches this call |
| TS2352 | Conversion error | 🟡 WARNING | Sometimes | Conversion may be a mistake — insufficient overlap |

## Severity Escalation Rules

Read `probekit-core/references/severity-format.md` for universal rules.

Additional type-audit escalation rules:

| Condition | Escalation |
|-----------|-----------|
| TS2339 on global type (window.*, Telegram.*) | Always 🔴 CRITICAL — runtime crash |
| TS2345 in test helper used by 5+ test files | Escalate to 🔴 CRITICAL — cascade failure |
| TS18046 in catch block with `.message` access | Always 🔴 CRITICAL — runtime TypeError |
| TS2322 in component props | Escalate to 🟡 WARNING — Vue runtime warning |
| Any error in `*.d.ts` file | Escalate one level — affects all consumers |
| Error only in test files | De-escalate one level (min 🟢) — does not affect production |

## Vue-Specific Errors

| Pattern | Severity | Explanation |
|---------|----------|-------------|
| `Property 'X' does not exist on type 'CreateComponentPublicInstance...'` | 🔴 CRITICAL | Template references global not exposed from setup |
| `Type 'X' is not assignable to type 'ComponentMountingOptions...'` | 🟡 WARNING | vue-test-utils generic incompatibility — safe to cast |
| `defineProps type argument must be a type literal or interface` | 🔴 CRITICAL | Vue compiler macro constraint violation |
