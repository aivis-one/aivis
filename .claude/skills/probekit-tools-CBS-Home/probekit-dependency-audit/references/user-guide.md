# dependency-audit — User Guide

Dependency analysis for Claude Code.
Audits version pinning, detects typosquatting, checks for abandonment.

---

## Invocation

### Slash command
/dependency-audit .
/dependency-audit src/

### Auto-trigger keywords
"check my dependencies"
"audit packages"
"dependency review"
"are my packages safe"
"typosquatting check"

---

## Usage Examples

### Full dependency audit
/dependency-audit .
→ Finds all manifests, checks pinning, scans for suspicious packages.

### Check specific manifest
/dependency-audit requirements.txt
→ Audits only the specified manifest file.

---

## What Gets Generated

- `{{report_dir}}/DEPENDENCY-AUDIT-<target>-<YYYYMMDD>.md` — full report
- `{{report_dir}}/AUDIT-TRACKER.md` — running history

---

## What It Checks

1. **Version pinning** — are dependencies pinned to exact versions?
2. **Lock files** — is lock file committed to git?
3. **Typosquatting** — do package names look like misspellings of popular packages?
4. **Install scripts** — suspicious postinstall/preinstall in package.json?
5. **Import mismatches** — imports in code without corresponding manifest entry?
6. **Abandonment** — deprecated packages or old versions?

---

## Limitations

Cannot check CVE databases, download packages, or query registries.
For CVE scanning, run `npm audit` or `pip-audit` separately.
