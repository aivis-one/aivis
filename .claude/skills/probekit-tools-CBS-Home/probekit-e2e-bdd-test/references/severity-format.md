# Severity Format — E2E/BDD Test

> Core format: read `probekit-core/references/severity-format.md` for markers, output syntax, decision tree, diff format, honesty rules.

## E2E/BDD Escalation Rules

- Scenario with no Then assertion → always CRITICAL
- Auth flow with no unauthorized access scenario → always CRITICAL
- Hardcoded credential/secret in feature file → always CRITICAL
- Shared mutable state between scenarios → CRITICAL if parallel, WARNING if sequential
- Hardcoded sleep/wait → WARNING minimum; CRITICAL if > 5 seconds
- Procedural Gherkin → WARNING
- Missing teardown → WARNING
- Brittle CSS/XPath selector → WARNING
- Missing tags → SUGGESTION
- Copy-paste scenarios → SUGGESTION
- Clean declarative Gherkin with full POM and reusable step library → 💎 DIAMOND
