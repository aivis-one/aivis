# probekit-core CHANGELOG

## v1.0.0 — 2026-03-19

Initial release of shared core references.

### Created
- `references/severity-format.md` — unified severity markers (🔴/🟡/🟢/💎), output syntax, decision tree, diff format, honesty rules, test result markers, coverage scale
- `references/audit-tracker-format.md` — unified AUDIT-TRACKER.md table format, field definitions, key metrics per skill, delta rules
- `references/environment-detection.md` — standard procedure for detecting project language, framework, shell, test structure, package manager

### Changed in other skills
- All 8 skill `severity-format.md` files slimmed to escalation-rules-only + core reference
- All 8 skill `output-template.md` audit tracker sections replaced with core reference
- No SKILL.md files changed — backward compatible

Toolchain: skill-architect v3.0.0
