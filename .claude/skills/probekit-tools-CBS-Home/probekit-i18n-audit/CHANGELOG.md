# Changelog

## v1.0.0 — 2026-04-10

### Features
- **8 i18n probes**: hardcoded strings in templates, hardcoded strings in scripts, key parity across locales, unused keys, missing keys in code, RTL locale setup, locale file structure, placeholder/attribute i18n
- **4-locale support**: en, ru, de, ar — key parity comparison across all four
- **RTL flash prevention**: detects missing dir="rtl" for Arabic locale
- **Deep key comparison**: JSON structure hierarchy consistency check
- **CBS HOME calibration**: targets mockups/frontend/src/ Vue 3 + vue-i18n
- **Scored report**: severity-based scoring with totals table
- **Audit tracker integration**: appends to AUDIT-TRACKER.md

Toolchain: probekit-tools-CBS-Home
