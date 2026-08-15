# Health Audit — Severity Escalation Rules

Extends `probekit-core/references/severity-format.md` with health-audit-specific rules.

---

## Universal Rules (always apply)

Per `probekit-core/references/severity-format.md`:
- Hardcoded secrets → CRITICAL
- Injection vulnerabilities → CRITICAL

## Health-Audit Specific Escalation

### Always CRITICAL
- Any single file > 200 MB in runtime directories
- Log handler writing unbounded with file already > 50 MB
- Database table > 100K rows with no TTL and no cleanup code
- Config declares security-related policy that code ignores
- Dead vendored runtime (interpreters, SDKs) regardless of size

### Always WARNING
- Log handler without rotation (file < 50 MB)
- Database TTL policy exists but cleanup runs only on rare events
- Orphan database files from previous project iterations
- 2x log duplication (undocumented)

### Always SUGGESTION
- Empty directories without .gitkeep
- Small orphan files (< 1 MB)
- Config entries defined but not read (non-security)
- Intentional dual-write that is documented

## Compound Escalation

When multiple probes fire on the same root cause, escalate:

| Combination | Escalate To | Reasoning |
|-------------|-------------|-----------|
| Disk Bloat + No Rotation | CRITICAL | Systemic: will only get worse |
| DB Growth + Config Drift | CRITICAL | Safety policy is dead letter |
| Dead Files + Orphan Data | WARNING | Legacy cleanup incomplete |
| Log Duplication + Disk Bloat | CRITICAL | Duplication is the cause of bloat |
| Config Drift + DB Growth + Disk Bloat | CRITICAL | Trifecta: policy, growth, and bloat |
