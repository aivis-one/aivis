# a11y-audit — Severity Escalation Rules

Extends `probekit-core/references/severity-format.md` with accessibility-specific escalation.

## A11y-Specific Escalation

| Finding | Base Severity | Escalation Condition | Escalated To |
|---------|--------------|---------------------|-------------|
| Missing form label | HIGH | Input is for auth/payment | CRITICAL |
| Low contrast | HIGH | Affects primary CTA or error text | CRITICAL |
| No keyboard access | CRITICAL | (always CRITICAL) | — |
| Missing alt text | MEDIUM | Image conveys essential information | HIGH |
| Positive tabindex | MEDIUM | Used on > 3 elements | HIGH |
| No skip link | MEDIUM | Page has > 10 interactive elements before main content | HIGH |
| Missing aria-live | MEDIUM | Dynamic content is error/status message | HIGH |
| Decorative ARIA | LOW | role overrides native semantics | MEDIUM |

## WCAG 2.1 AA Mapping

| Probe | WCAG Criteria |
|-------|--------------|
| P1 Semantic HTML | 1.3.1 Info and Relationships |
| P2 ARIA | 4.1.2 Name, Role, Value |
| P3 Keyboard | 2.1.1 Keyboard, 2.1.2 No Keyboard Trap |
| P4 Focus | 2.4.3 Focus Order, 2.4.7 Focus Visible |
| P5 Contrast | 1.4.3 Contrast (Minimum), 1.4.11 Non-text Contrast |
| P6 Labels | 1.3.1 Info and Relationships, 3.3.2 Labels or Instructions |
| P7 Landmarks | 2.4.1 Bypass Blocks, 1.3.1 Info and Relationships |
| P8 Screen Reader | 1.1.1 Non-text Content, 4.1.3 Status Messages |
