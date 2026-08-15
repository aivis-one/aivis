---
name: probekit-i18n-audit
description: "v1.0.0 | CBS HOME i18n compliance audit. Checks all strings use t(), keys exist in all 4 locales (en/ru/de/ar), RTL support, no hardcoded text. Use when: 'i18n audit', 'check translations', 'locale check', 'проверка переводов'."
---

# i18n-audit v1.0.0

CBS HOME i18n compliance audit for Vue 3 frontend.
Verifies all user-visible strings go through vue-i18n `t()` and keys exist in all 4 locales.

## Configuration

source_dir: mockups/frontend/src
locales_dir: mockups/frontend/src/i18n/locales
supported_locales: [en, ru, de, ar]
base_locale: en

## Probes

Read `references/probe-definitions.md` for full probe specifications (P1–P8):
P1: Hardcoded Strings in Templates (CRITICAL), P2: Hardcoded Strings in Script (HIGH),
P3: Key Parity Across Locales (CRITICAL), P4: Unused i18n Keys (LOW),
P5: Missing i18n Keys in Code (CRITICAL), P6: RTL Locale Setup (HIGH),
P7: Locale File Structure (MEDIUM), P8: Placeholder/Attribute i18n (MEDIUM).

## Execution Steps

1. Read all 4 locale files — build key maps
2. Scan all .vue files for template text and t() calls
3. Run P1-P8 probes
4. Cross-reference keys: used vs defined
5. Classify and report

## Severity Rules

| Finding | Severity |
|---------|----------|
| Hardcoded user-visible string | P1 |
| Missing key in non-base locale | P1 |
| t() call with nonexistent key | P1 |
| Missing RTL support | P2 |
| Empty translation value | P2 |
| Hardcoded placeholder text | P2 |
| Unused i18n key | P3 |
| Structure mismatch between locales | P2 |

## Anchor

[*] i18n-audit v1.0.0 * ready
