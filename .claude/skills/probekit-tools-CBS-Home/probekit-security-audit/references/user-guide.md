# security-audit — User Guide

Security-focused code review for Claude Code.
Scans for OWASP Top 10 vulnerabilities, hardcoded secrets,
insecure defaults, and auth/authz gaps.

---

## Invocation

### Slash command
/security-audit src/api/
/security-audit .
/security-audit framework/services/auth.py

### Auto-trigger keywords
"security audit"
"find vulnerabilities"
"check for secrets"
"security review this code"
"are there any security issues"

### Fix mode (auto-fix safe patterns)
/security-audit src/ --fix

### Focus hint
/security-audit src/api/ -- focus on auth and IDOR

---

## Usage Examples

### Full project security scan
/security-audit .
→ Scans all source files for OWASP Top 10, secrets, insecure defaults.

### Auth-focused review
/security-audit src/api/ -- focus on auth
→ Prioritizes A01 (Access Control) and A07 (Auth Failures).

### Secret scan only
/security-audit . -- focus on secrets
→ Runs only secret detection patterns across all files.

### Auto-fix safe issues
/security-audit src/ --fix
→ Fixes: verify=False, DEBUG=True, random→secrets. Does NOT fix auth logic.

---

## What Gets Generated

- `{{report_dir}}/SECURITY-AUDIT-<target>-<YYYYMMDD>.md` — full report
- `{{report_dir}}/AUDIT-TRACKER.md` — running history

---

## Report Sections

Every report includes:
- OWASP coverage matrix (which categories checked, findings per category)
- Secret scan results (with file:line for each finding)
- Auth/AuthZ matrix (if auth code detected)
- Findings with OWASP category, CWE, detection signal, fix
- Final score with severity breakdown

---

## Relationship to code-audit

security-audit goes deeper than code-audit Section 4:
- code-audit: ~5 surface-level security checks as part of general review
- security-audit: full OWASP Top 10, 15+ secret regex patterns, auth matrix, insecure defaults catalog
