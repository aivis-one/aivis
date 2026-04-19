# Output Template — Dependency Audit

## Report Header

```
Dependency Audit Report: [target]
Manifests found: [list of manifest files]
Lock files: [present/missing]
Total dependencies: N
Tested: [date]
```

---

## Version Pinning Summary

| Package | Version Spec | Pinning Level | Severity |
|---------|-------------|---------------|----------|
| requests | ==2.31.0 | Exact | 🟢 |
| flask | >=2.0 | Lower bound | 🔴 |

Lock file status: ✅ Committed / 🔴 Missing / 🔴 In .gitignore

Pinning score: X/10

---

## Suspicious Packages

| Package | Signal | Similarity To | Distance | Severity |
|---------|--------|--------------|----------|----------|
(If none: "No suspicious packages detected.")

---

## Import/Manifest Mismatches

| Import | File | In Manifest? | Status |
|--------|------|-------------|--------|
(If none: "All imports have corresponding manifest entries.")

---

## Abandonment Signals

| Package | Signal | Details | Severity |
|---------|--------|---------|----------|
(If none: "No abandonment signals detected.")

---

## Findings

🔴/🟡/🟢 findings with details per `probekit-core/references/severity-format.md`.

---

## Final Score

Dependency Gate: ✅ PASS / ⚠️ WARN / ❌ FAIL

| Metric | Result |
|--------|--------|
| 🔴 CRITICAL | N |
| 🟡 WARNING | N |
| 🟢 SUGGESTION | N |
| Pinning score | X/10 |
| Suspicious packages | N |

---

## Recommendations

1. [Fix unpinned dependencies]
2. [Commit lock file]
3. [Investigate suspicious packages]
4. [Run `npm audit` / `pip-audit` for CVE check — outside ProbeKit scope]

---

## Audit Tracker Update

Append row: skill=`dependency-audit`, pinning=X/10, suspicious=N, mismatches=N.
