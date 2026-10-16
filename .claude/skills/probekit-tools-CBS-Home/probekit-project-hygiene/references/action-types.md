# Action Types — probekit-project-hygiene

## Actions

### DELETE
**When:** File has zero references, is not an entry point, and is not in grace period.
**Method:** `git rm {path}`
**Safety check:** Confirm zero grep matches for filename across entire codebase.
**Examples:** Old scaffold files, orphan tests for deleted modules, exact archive duplicates.

### ARCHIVE
**When:** File may have historical value but is no longer active.
**Method:** `git mv {path} archive/{relative_path}`
**Safety check:** File is not imported anywhere; has not been modified in 90+ days.
**Examples:** Old specs, superseded documentation, deprecated configs.

### CONSOLIDATE
**When:** Two or more files have >80% identical content.
**Method:** Keep the more recently modified / more central copy. Delete others.
**Safety check:** Both files are referenced — update references to point to the surviving copy.
**Examples:** Duplicate i18n files, forked-then-forgotten components, copy-pasted utilities.

### REVIEW
**When:** File appears unused but has recent commits (< 30 days) or uncertain reference patterns.
**Method:** Flag for human review. Do NOT auto-delete.
**Safety check:** N/A — human decides.
**Examples:** Files referenced only in comments, files used via dynamic imports, config files referenced by tools.

---

## Decision Matrix

| Zero refs? | Recent commits? | In active dir? | Action |
|-----------|----------------|---------------|--------|
| Yes | No (> 30 days) | No (archive/) | DELETE |
| Yes | No | Yes (src/) | DELETE |
| Yes | Yes (< 30 days) | Any | REVIEW |
| No (has dup) | Any | archive/ | DELETE (archive copy) |
| No (has dup) | Any | Both active | CONSOLIDATE |
| Partial refs | Any | Any | REVIEW |

---

## Justification Requirements

Every finding MUST include:

1. **Proof of non-use:** The grep command and result showing zero matches
2. **Impact statement:** "Removing this file breaks nothing because..."
3. **Alternative:** If the content might be needed, suggest where it lives (e.g., "same content exists in docs/02_spec/")
