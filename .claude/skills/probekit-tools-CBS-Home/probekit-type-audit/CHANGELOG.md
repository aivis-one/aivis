# Changelog

## v1.0.0 — 2026-04-13

### Features
- **3-stage analysis**: vue-tsc compiler check → ESLint type rules → pattern scan (10 patterns)
- **10 detection patterns**: as any, ts-ignore, non-null assertions, missing return types, unknown catches, reactive generic misuse, global type gaps, template scope leaks, untyped API responses, generic constraint gaps
- **Error classification**: TS error codes mapped to severity + auto-fix eligibility
- **Fix mode**: auto-fix CRITICALs and WARNINGs, verify with re-compilation, revert on failure
- **Strict mode**: treat all WARNINGs as CRITICALs for pre-release checks
- **Scored report**: severity-based scoring with totals table
- **Audit tracker integration**: appends to AUDIT-TRACKER.md with delta tracking
- **Vue-specific detection**: template scope leaks, defineEmits types, reactive generics
- **Pipeline integration**: Stage 1.5 in probekit-test-suite (after arch-review, before code-audit)

### References
- error-classification.md — TS error code → severity mapping
- fix-patterns.md — 10 auto-fix recipes with before/after examples
- output-template.md — report structure and scoring formula
- severity-format.md — type-audit escalation rules
- user-guide.md — invocation, examples, integration docs

Toolchain: probekit-tools-CBS-Home
