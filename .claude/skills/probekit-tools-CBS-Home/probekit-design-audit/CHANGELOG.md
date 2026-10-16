# Changelog

## v1.0.0 — 2026-04-10

### Features
- **8 design probes**: hardcoded colors, font compliance, spacing tokens, radius tokens, shadow tokens, dark mode completeness, logo icon color, token sync
- **CBS HOME design system**: calibrated for project tokens (--o-primary, --space-*, --radius-*, --shadow-*)
- **Severity classification**: P1 (CRITICAL), P2 (HIGH), P3 (MEDIUM) per probe
- **Token map building**: scans CSS variables.css for token definitions
- **Scored report**: severity-based scoring with totals table
- **Audit tracker integration**: appends to AUDIT-TRACKER.md

Toolchain: probekit-tools-CBS-Home
