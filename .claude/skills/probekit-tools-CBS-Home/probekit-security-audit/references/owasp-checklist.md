# OWASP Top 10 — Detection Checklist

Structured checklist for code-level security scanning.
Only includes patterns detectable by reading source code.

---

## A01: Broken Access Control

**What to check:**
- Direct object access by ID without owner filter (IDOR)
- Endpoints missing auth middleware/decorator
- Role checks using string comparison instead of enum
- `os.path.join()` with user input (path traversal)
- Admin functions without role verification

**Detection signals:**
- `Model.objects.get(id=<user_input>)` without `.filter(user=request.user)`
- Route handler without `@login_required` / `authMiddleware`
- `req.params.id` used directly in DB query without owner check
- `os.path.join(base, user_input)` without `os.path.realpath` validation

**Severity:** 🔴 for IDOR, missing auth on write ops, path traversal to system files. 🟡 for missing auth on read-only public-like resources.

---

## A02: Cryptographic Failures

**What to check:**
- Passwords hashed with MD5/SHA1/SHA256 (without bcrypt/argon2)
- Hardcoded encryption keys or secrets
- TLS verification disabled (`verify=False`, `rejectUnauthorized: false`)
- `random` module used for security tokens (should use `secrets`/`crypto`)
- ECB mode in symmetric encryption

**Detection signals:**
- `hashlib.md5(password)`, `hashlib.sha1(password)`
- `SECRET_KEY = "literal_string"`, `ENCRYPTION_KEY = b"..."`
- `requests.get(url, verify=False)`
- `AES.new(key, AES.MODE_ECB)`
- `random.randint()` for token/OTP generation

**Severity:** 🔴 for plaintext/weak password hashing, hardcoded keys, disabled TLS. 🟡 for weak algorithms in non-critical paths.

---

## A03: Injection

**What to check:**
- SQL: string concatenation/f-string in SQL queries
- Command: `os.system()`, `subprocess.call(shell=True)` with user input
- XSS: user input rendered without escaping in templates
- Template injection: user input in template string
- LDAP/XML injection patterns

**Detection signals:**
- `f"SELECT * FROM users WHERE id = {user_input}"`
- `cursor.execute("... WHERE name = '" + name + "'")`
- `os.system(f"convert {filename}")`, `subprocess.call(cmd, shell=True)`
- `|safe` filter on user input in Jinja2/Django templates
- `render_template_string(user_input)`

**Severity:** 🔴 for SQL injection, command injection, template injection. 🟡 for potential XSS with partial escaping.

---

## A04: Insecure Design

**What to check:**
- No rate limiting on auth endpoints
- No input validation framework (Pydantic, Joi, etc.)
- Business logic without abuse prevention
- Missing account lockout after failed attempts

**Detection signals:**
- Login endpoint without rate limit middleware
- `request.body` / `req.body` used directly without schema validation
- Password reset without token expiration

**Severity:** 🟡 for most design issues (they are patterns, not specific vulns).

---

## A05: Security Misconfiguration

**What to check:**
- `DEBUG = True` in production config
- `CORS(app, origins="*")` or `Access-Control-Allow-Origin: *`
- `ALLOWED_HOSTS = ['*']`
- Verbose error messages exposing stack traces
- Default credentials in config files

**Detection signals:**
- `DEBUG = True` outside test/dev files
- `cors({ origin: '*' })` or `CORS_ALLOW_ALL_ORIGINS = True`
- `app.use(errorHandler)` that sends `err.stack` to client

**Severity:** 🔴 for debug in prod, default credentials. 🟡 for overly permissive CORS, verbose errors.

---

## A07: Auth Failures

**What to check:**
- JWT decoded without signature verification
- Session without expiration/timeout
- Password stored in plaintext or reversible encoding
- Missing brute-force protection on login

**Detection signals:**
- `jwt.decode(token, options={"verify_signature": False})`
- `jwt.decode(token, algorithms=["none"])`
- Session config without `expires` or `maxAge`
- `base64.b64encode(password)` as "encryption"

**Severity:** 🔴 for JWT without verification, plaintext passwords. 🟡 for missing session expiration.

---

## A08: Data Integrity

**What to check:**
- Insecure deserialization (`pickle.loads`, `yaml.load` without SafeLoader)
- Missing CSRF protection on state-changing endpoints
- `eval()` / `exec()` on user-controlled input

**Detection signals:**
- `pickle.loads(user_data)`, `pickle.load(open(user_file))`
- `yaml.load(data)` without `Loader=yaml.SafeLoader`
- `eval(request.data)`, `exec(user_input)`
- Forms without CSRF token in non-API web apps

**Severity:** 🔴 for pickle/yaml deserialization of user input, eval/exec. 🟡 for missing CSRF on low-risk forms.

---

## A09: Logging Failures

**What to check:**
- Security events not logged (failed login, auth failures, access denied)
- PII/secrets in log output
- No log for admin actions

**Detection signals:**
- Login handler without `logger.warning("failed_login", ...)`
- `logger.info(f"User data: {user}")` with full user object
- `print(password)`, `logger.debug(f"token={token}")`

**Severity:** 🟡 for missing security logging. 🔴 for secrets/passwords in logs.

---

## A10: SSRF

**What to check:**
- URL from user input passed to HTTP client without validation
- Internal service URLs constructable from user input
- Redirect URL from user input without allowlist

**Detection signals:**
- `requests.get(request.args['url'])`
- `fetch(req.body.webhookUrl)`
- `http.Get(userProvidedURL)` without URL validation
- Redirect: `redirect(request.args.get('next'))` without domain check

**Severity:** 🔴 for unvalidated URL fetch from user input. 🟡 for redirect without allowlist.
