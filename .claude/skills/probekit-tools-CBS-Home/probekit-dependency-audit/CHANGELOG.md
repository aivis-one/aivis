# Changelog — dependency-audit

## v1.0.0 — 2026-03-19
- Initial release
- Version pinning audit: 6 ecosystems (Python, npm, Go, Rust, Java, Ruby)
- Lock file verification (committed vs missing vs gitignored)
- Typosquatting detection: Levenshtein distance from top-500 packages
- Suspicious install scripts scan (npm postinstall/preinstall)
- Import/manifest mismatch detection (Python + Node)
- Abandonment signals from local files
- Pinning score formula

Toolchain: skill-architect v3.0.0
