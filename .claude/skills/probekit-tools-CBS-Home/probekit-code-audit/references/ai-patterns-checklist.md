---
name: ai-patterns-checklist
description: "AI pattern Detection Master-Checklist (9-step per-file scan) and Severity Calibration rules for universal escalation/de-escalation."
---

# AI Patterns — Detection Checklist & Severity Calibration

## Detection Master-Checklist

When analyzing each file, run through these 9 steps:

1. **IMPORTS**: Unknown packages? Cross-domain imports? → 10.1, 10.12, 10.20
2. **NAMING vs BEHAVIOR**: Does function name match return value? → 10.11, 10.19
3. **DOCUMENTATION vs CODE**: Professional docs + simple bugs? → 10.13
4. **DEFENSIVE PROGRAMMING**: Missing null checks, validation, error handling? → 10.15
5. **TEXT MARKERS**: `example.com`, `TODO`, `print()`, hardcoded credentials? → 10.16
6. **ERROR HANDLING**: Wrong exception types for domain? No try/except on I/O? → 10.12, 10.15
7. **VALIDATION LOGIC**: Email `@`-only? Date single format? Float for money? → 10.17
8. **STRUCTURE**: God class? File creates own DB connection? → 10.3, 10.20
9. **FRAMEWORK CURRENCY**: Deprecated APIs? Old patterns? → 10.18

Each step maps to specific patterns with severity. Apply escalation rules from severity-format.md.

---

## Severity Calibration — Universal Escalation

Any pattern escalates to 🔴 CRITICAL if it:
- Is in authentication / authorization code
- Is in payment / billing code
- Handles PII (personal data)
- Is a public API endpoint without auth
- Contains raw SQL queries / DB access

Any pattern de-escalates to 🟢 SUGGESTION if it:
- Is in test files (`test_*.py`, `*_test.py`)
- Is in `scripts/` / `tools/` with clear "dev only" purpose
- Has 100% test coverage including the found issue
- Is explicitly marked intentional with explanation comment
