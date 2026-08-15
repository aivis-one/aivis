---
name: probekit-design-audit
description: "v1.0.0 | CBS HOME design token compliance. Checks colors, fonts, spacing, radius, shadows, dark mode against variables.css + brand-cbs.md. Use when: 'design audit', 'check design tokens', 'brand compliance', 'color check', 'дизайн аудит'."
---

# design-audit v1.0.0

CBS HOME design token compliance audit for Vue 3 frontend.
Verifies all components and views use design tokens from `variables.css` — no hardcoded values.

## Configuration

source_dir: mockups/frontend/src
token_file: mockups/frontend/src/styles/variables.css
brand_ref: .claude/skills/livemockup-studio/reference/brand-cbs.md

## Probes

Read `references/probe-definitions.md` for full probe specifications (P1–P8):
P1: Hardcoded Colors (CRITICAL), P2: Font Compliance (HIGH), P3: Spacing Tokens (MEDIUM),
P4: Radius Tokens (MEDIUM), P5: Shadow Tokens (MEDIUM), P6: Dark Mode (HIGH),
P7: Logo Icon Color (CRITICAL), P8: Token Sync (HIGH).

## Execution Steps

1. Read variables.css — build token map
2. Run P1-P8 probes
3. Classify findings by severity (P1/P2/P3)
4. Output report per `references/output-template.md`

## Output Format

```markdown
# Design Audit Report — CBS HOME Frontend
Date: {date}
Target: {source_dir}

## Summary
| Probe | Status | Findings |
|-------|--------|----------|
| P1 Hardcoded Colors | PASS/FAIL | N issues |
| ... | ... | ... |

## Findings
### P1: {description}
| # | Severity | File:Line | Issue | Fix |
```

## Anchor

[*] design-audit v1.0.0 * ready
