# Severity Format — Dependency Audit

> See `probekit-core/references/severity-format.md` for canonical definition.

## Dependency-Specific Guidance

| Severity | Dependency Context |
|----------|-------------------|
| 🔴 CRITICAL | Unpinned deps in production, lock file in .gitignore, typosquat distance=1 from top-100, suspicious install scripts with network/exec |
| 🟡 WARNING | Range pins without lock, typosquat distance=2, import/manifest mismatch, abandoned package signals |
| 🟢 SUGGESTION | Lock file missing but all exact pins, recommend `pip-audit`/`npm audit` for CVE check |
| 💎 DIAMOND | Exemplary: all exact pins + committed lock + integrity hashes + automated update policy |
