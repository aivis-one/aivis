# Data Flow Tracing v1.0.0

Traces sensitive data from entry to storage/exit to identify unprotected flows.
Complements OWASP scanning (Step 3) by following data movement, not just pattern matching.

---

## Sensitive Data Categories

| Category | Examples | Required Protection |
|----------|----------|-------------------|
| PII | Name, email, phone, address, DOB | Encrypt at rest, mask in logs |
| Credentials | Passwords, API keys, tokens, secrets | Hash (never store plaintext), never log |
| Financial | Card numbers, bank accounts, transactions | Encrypt, audit trail, PCI compliance |
| Health | Medical records, diagnoses | Encrypt, access control, HIPAA compliance |
| Session | Session IDs, JWT tokens, cookies | HttpOnly, Secure, SameSite flags |

---

## Tracing Procedure

### Phase 1: Identify Entry Points

Scan for data entry points where sensitive data arrives:

1. **HTTP endpoints** — request body, query params, headers, cookies
   - Look for: `request.body`, `req.params`, `request.form`, `request.json`
2. **File uploads** — multipart form data, file readers
   - Look for: `request.files`, `multer`, `FileField`, `UploadFile`
3. **Webhook receivers** — external service callbacks
   - Look for: routes named `webhook`, `callback`, `notify`, `hook`
4. **CLI input** — command line arguments, stdin
   - Look for: `sys.argv`, `argparse`, `input()`, `readline`
5. **Database reads** — data retrieved that contains PII
   - Look for: SELECT queries on user/customer/account tables

### Phase 2: Trace Through Code

For each entry point, follow the data:

1. **Validation layer** — is input validated before use?
   - Check: type validation, length limits, format checks, sanitization
   - Flag: raw user input used directly without validation
2. **Transform layer** — is data transformed or enriched?
   - Check: serialization, encoding, formatting
   - Flag: sensitive data concatenated into strings without masking
3. **Storage layer** — where is data persisted?
   - Check: encryption at rest, parameterized queries
   - Flag: plaintext PII in database, credentials in config files
4. **Exit layer** — where does data leave the system?
   - Check: TLS for external calls, data minimization in API responses
   - Flag: full PII sent where partial would suffice
5. **Logging layer** — does data appear in logs?
   - Check: PII masking in log statements
   - Flag: email, phone, names, IPs logged in plaintext

### Phase 3: Build Flow Map

For each sensitive data type, produce a flow:

```
Entry: POST /api/users (email, password, name)
  -> Validation: email format check [OK]
  -> Transform: password -> bcrypt hash [OK]
  -> Storage: INSERT users (email plaintext, password hashed) [OK]
  -> Log: "New user created: {email}" [WARNING: PII in log]
  -> Exit: 201 response with full user object [WARNING: password hash in response]
```

---

## Severity Assignment

| Finding | Severity | Rationale |
|---------|----------|-----------|
| Credentials logged in plaintext | CRITICAL | Immediate secret exposure |
| PII stored without encryption in DB | WARNING | Data breach amplification |
| Sensitive data in URL parameters | WARNING | Server logs, browser history exposure |
| PII in log files without masking | WARNING | Log aggregator becomes PII store |
| Full object returned where partial needed | SUGGESTION | Data minimization principle |
| Sensitive data over non-TLS connection | CRITICAL | Network interception risk |
| User input used without validation | WARNING | Injection and corruption risk |
| Session token without HttpOnly flag | WARNING | XSS session theft |
| Sensitive data in error messages | WARNING | Information disclosure |
| Credentials in environment variables (documented) | OK | Accepted pattern |

---

## Common Anti-Patterns

1. **Log-and-forget** — `logger.info(f"Processing payment for {user.email}: ${amount}")` 
   PII + financial data in one log line.

2. **Over-sharing API responses** — returning full database objects instead of DTOs.
   Internal fields (password_hash, internal_id, admin_notes) leak to clients.

3. **URL parameter secrets** — `redirect_to=https://api.example.com?token=sk_live_...`
   Tokens in URLs appear in server logs, referrer headers, browser history.

4. **Error message data leak** — `raise ValueError(f"Invalid card: {card_number}")`
   Exception messages often end up in logs and error tracking systems.

5. **Clipboard/temp file persistence** — sensitive data written to temp files without cleanup.
   Files survive process crashes and become discoverable.

---

## Output Format

For each unprotected flow, report:

```
DATA FLOW: [data_type] via [entry_point]
  Path: [entry] -> [transform] -> [store/exit]
  Issue: [description of unprotected segment]
  File: [file:line]
  Severity: [CRITICAL/WARNING/SUGGESTION]
  Fix: [concrete recommendation]
```
