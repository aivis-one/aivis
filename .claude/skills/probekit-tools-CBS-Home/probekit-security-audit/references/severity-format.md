# Severity Format — Security Audit

> This file references the shared severity format from probekit-core.
> See `probekit-core/references/severity-format.md` for the canonical definition.

## Security-Specific Severity Guidance

| Severity | Security Context |
|----------|-----------------|
| 🔴 CRITICAL | Exploitable vulnerability: SQL injection, RCE, hardcoded secrets, IDOR, disabled TLS, JWT without verification, insecure deserialization |
| 🟡 WARNING | Potential vulnerability requiring context: weak crypto in non-critical path, missing CSRF on low-risk form, overly permissive CORS, missing security logging |
| 🟢 SUGGESTION | Best practice improvement: add rate limiting, use enum for roles, add security headers |
| 💎 DIAMOND | Exemplary security pattern: proper input validation framework, well-implemented RBAC, secure session management |
