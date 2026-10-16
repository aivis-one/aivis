# Changelog — probekit-project-hygiene

## v1.0.0 (2026-04-12)
- Initial release: 10 probes for project waste detection
- Probes: PH-DEAD-FILES, PH-DEAD-CODE, PH-DUPLICATES, PH-STALE-DEPS, PH-UNUSED-CONFIG, PH-ORPHAN-TESTS, PH-ARCHIVE-DUPS, PH-EMPTY-DIRS, PH-STALE-DOCS, PH-GIT-BLOAT
- Actions: DELETE, ARCHIVE, CONSOLIDATE, REVIEW with justification
- Dry-run by default, --fix for apply mode
- Recovery manifest for rollback
- Integrated into probekit-test-suite as Step 4.85
