# a11y-audit — Output Template

## Report File

Save to: `{{review_dir}}/A11Y-AUDIT-{{target}}-{{YYYYMMDD}}.md`

## Template

```markdown
# Accessibility Audit Report — CBS HOME Frontend
Date: {{date}}
Target: {{source_dir}}
WCAG Level: 2.1 AA

## Summary
| Probe | Status | Score | Findings |
|-------|--------|-------|----------|
| P1 Semantic HTML | PASS/FAIL | X/10 | N issues |
| P2 ARIA Roles | PASS/FAIL | X/10 | N issues |
| P3 Keyboard Nav | PASS/FAIL | X/10 | N issues |
| P4 Focus Mgmt | PASS/FAIL | X/10 | N issues |
| P5 Color Contrast | PASS/FAIL | X/10 | N issues |
| P6 Form Labels | PASS/FAIL | X/10 | N issues |
| P7 Skip/Landmarks | PASS/FAIL | X/10 | N issues |
| P8 Screen Reader | PASS/FAIL | X/10 | N issues |

**Overall Score: X.X/10** | Gate: PASS/WARN/FAIL
Findings: 🔴 N | 🟡 N | 🟢 N | 💎 N

## Findings

### P1: Semantic HTML
| # | Severity | File:Line | WCAG | Issue | Fix |
|---|----------|-----------|------|-------|-----|

### P2: ARIA Roles & Attributes
(same table format)

... (P3-P8)

## WCAG Coverage Matrix
| Criterion | Status | Notes |
|-----------|--------|-------|
| 1.1.1 Non-text Content | PASS/FAIL | |
| 1.3.1 Info and Relationships | PASS/FAIL | |
| 1.4.3 Contrast (Minimum) | PASS/FAIL | |
| 2.1.1 Keyboard | PASS/FAIL | |
| 2.1.2 No Keyboard Trap | PASS/FAIL | |
| 2.4.1 Bypass Blocks | PASS/FAIL | |
| 2.4.3 Focus Order | PASS/FAIL | |
| 2.4.7 Focus Visible | PASS/FAIL | |
| 3.3.2 Labels or Instructions | PASS/FAIL | |
| 4.1.2 Name, Role, Value | PASS/FAIL | |
| 4.1.3 Status Messages | PASS/FAIL | |
```
