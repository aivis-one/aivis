# Changelog — security-audit

## v1.0.0 — 2026-03-19
- Initial release
- OWASP Top 10 scan (A01, A02, A03, A04, A05, A07, A08, A09, A10)
- Secret detection: 15+ regex patterns (AWS, GCP, Azure, Stripe, GitHub, GitLab, Slack, OpenAI, SendGrid, Twilio, private keys, DB connection strings)
- Auth/AuthZ matrix generation
- Insecure defaults scan (DEBUG, CORS, TLS, crypto)
- Fix mode (--fix) for safe auto-fixes
- CWE mapping for all findings
- Scoring: 10 - (CRITICAL×1.5) - (WARNING×0.5) - (SUGGESTION×0.1)

Toolchain: skill-architect v3.0.0
