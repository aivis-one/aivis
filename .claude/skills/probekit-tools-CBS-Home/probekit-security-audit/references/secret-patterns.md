# Secret Detection Patterns

Regex patterns for detecting hardcoded secrets in source code.
Organized by provider. All patterns are prefix-based for low false positive rate.

---

## Cloud Providers

### AWS
- Access Key ID: `AKIA[0-9A-Z]{16}`
- Temporary Key: `ASIA[0-9A-Z]{16}`
- Secret Key (contextual): `(?i)(aws_secret_access_key|secret_access_key)\s*[=:]\s*['"]?([A-Za-z0-9/+=]{40})`

### GCP
- API Key: `AIza[0-9A-Za-z\-_]{35}`
- Service Account: `"private_key"\s*:\s*"-----BEGIN`
- OAuth Secret: `GOCSPX-[0-9A-Za-z\-_]{28}`

### Azure
- Connection String: `DefaultEndpointsProtocol=https;AccountName=[^;]+;AccountKey=[A-Za-z0-9+/=]{88}`
- Client Secret (contextual): `(?i)(client.secret)\s*[=:]\s*['"]([A-Za-z0-9~.\-_]{34,44})`

---

## SaaS API Keys

### Stripe
- Live/Test Secret: `(sk_live_|sk_test_)[0-9a-zA-Z]{24,}`
- Webhook Secret: `whsec_[0-9a-zA-Z]{32,}`

### GitHub
- PAT (classic): `ghp_[A-Za-z0-9]{36}`
- Fine-grained PAT: `github_pat_[A-Za-z0-9_]{82}`
- App tokens: `(gho_|ghs_|ghu_)[A-Za-z0-9]{36}`

### GitLab
- PAT: `glpat-[0-9a-zA-Z\-_]{20}`

### Slack
- Bot/User tokens: `xox[bpas]-[0-9A-Za-z\-]{10,}`

### OpenAI
- API Key: `sk-[A-Za-z0-9]{48}`
- Project Key: `sk-proj-[A-Za-z0-9\-_]{48,}`

### SendGrid
- API Key: `SG\.[A-Za-z0-9\-_]{22}\.[A-Za-z0-9\-_]{43}`

### Twilio
- Account SID: `AC[a-fA-F0-9]{32}`
- API Key: `SK[a-fA-F0-9]{32}`

---

## Generic Patterns

### Private Keys
- RSA/EC/PKCS8: `-----BEGIN (RSA |EC )?PRIVATE KEY-----`

### Database Connection Strings
- PostgreSQL: `(?i)postgres(ql)?://[^:]+:[^@]+@`
- MySQL: `(?i)mysql://[^:]+:[^@]+@`
- MongoDB: `(?i)mongodb(\+srv)?://[^:]+:[^@]+@`

### Generic Secrets (contextual — require assignment context)
- `(?i)(password|passwd|pwd)\s*[=:]\s*['"][^'"]{8,}['"]`
- `(?i)(secret|api_key|apikey|access_token)\s*[=:]\s*['"][^'"]{8,}['"]`
- `(?i)(private_key|encryption_key)\s*[=:]\s*['"][^'"]{8,}['"]`

---

## False Positive Exclusions

Skip these patterns to avoid noise:
- Values that are clearly placeholders: `xxx`, `test`, `example`, `placeholder`, `changeme`, `TODO`
- Environment variable references: `os.environ`, `process.env`, `$ENV`, `${...}`
- Config templates: `.env.example`, `.env.template`, `*.sample`
- Test files with fixture data (if values match placeholder patterns)
- Comments documenting expected format (not actual values)

---

## Severity

All confirmed hardcoded secrets: **🔴 CRITICAL**
Generic pattern matches requiring context: **🟡 WARNING** (may be false positive)
