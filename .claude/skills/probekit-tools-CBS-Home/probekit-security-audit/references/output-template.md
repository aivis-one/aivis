# Output Template — Security Audit

## Report Header

```
Security Audit Report: [target]
Scope: [files/directories analyzed]
Language: [detected language/framework]
Tested: [date]
```

---

## OWASP Coverage

| OWASP Category | Findings | Severity | Status |
|---------------|----------|----------|--------|
| A01: Broken Access Control | N | 🔴/🟡 | Checked/N/A |
| A02: Cryptographic Failures | N | 🔴/🟡 | Checked/N/A |
| A03: Injection | N | 🔴/🟡 | Checked/N/A |
| A05: Security Misconfiguration | N | 🔴/🟡 | Checked/N/A |
| A07: Auth Failures | N | 🔴/🟡 | Checked/N/A |
| A08: Data Integrity | N | 🔴/🟡 | Checked/N/A |
| A09: Logging Failures | N | 🟡 | Checked/N/A |
| A10: SSRF | N | 🔴/🟡 | Checked/N/A |

---

## Secret Scan Results

| Type | File | Line | Pattern | Status |
|------|------|------|---------|--------|
| AWS Key | path | N | AKIA... | 🔴 CRITICAL |

If no secrets found: "No hardcoded secrets detected."

---

## Auth/AuthZ Matrix

| Endpoint/Function | Auth? | AuthZ? | Owner? | Issue |
|-------------------|-------|--------|--------|-------|
(Only if auth code detected. Otherwise: "No auth code detected — skipped.")

---

## Findings

Use severity markers from `probekit-core/references/severity-format.md`.

For each finding:
```
🔴 SEC-A03-001 — SQL Injection in user query
Location: src/api/users.py:42 → `get_user_by_email()`
OWASP: A03 Injection | CWE-89
Detection: f-string in SQL query with unsanitized input
Fix: Use parameterized query: `cursor.execute("SELECT ... WHERE email = %s", (email,))`
```

---

## Fixes Applied (if --fix)

| Finding | File | Change | Status |
|---------|------|--------|--------|
| SEC-A05-002 | config.py:3 | `DEBUG = True` → env-based | Applied |

---

## Final Score

Security Gate: ✅ PASS / ⚠️ WARN / ❌ FAIL

| Metric | Result |
|--------|--------|
| 🔴 CRITICAL | N |
| 🟡 WARNING | N |
| 🟢 SUGGESTION | N |
| Secrets found | N |
| OWASP categories checked | N/10 |

Score: X/10 (formula: 10 - CRITICAL×1.5 - WARNING×0.5 - SUGGESTION×0.1)

---

## Audit Tracker Update

> Format: see `probekit-core/references/audit-tracker-format.md`.

Append row with: skill=`security-audit`, OWASP categories=N, secrets=N.
