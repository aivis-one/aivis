# ProbeKit Reference File Naming Convention

Standard file names for `references/` directories across all ProbeKit skills.

## Required Files (all skills)

| File | Purpose |
|------|---------|
| `output-template.md` | Report output format and structure |
| `severity-format.md` | Skill-specific severity escalation rules (extends core) |

## Recommended Files

| File | When to include |
|------|----------------|
| `probe-definitions.md` | Skills with numbered probes (P1-P8+) — audit-type skills |
| `user-guide.md` | Skills invoked directly by users (not sub-components) |

## Naming Rules

1. **kebab-case** — all lowercase, hyphens between words: `probe-definitions.md`, not `ProbeDefinitions.md`
2. **Descriptive nouns** — name describes content, not function: `owasp-checklist.md`, not `step3-data.md`
3. **No version suffixes** — version tracked in frontmatter/heading, not filename: `probe-definitions.md`, not `probe-definitions-v2.md`
4. **Domain-specific files** use domain vocabulary — `gherkin-patterns.md`, `metrics-thresholds.md`, `secret-patterns.md`
5. **Multi-part analysis** uses suffix: `analysis-sections-structure.md`, `analysis-sections-behavior.md`

## Anti-patterns

- `data.md`, `notes.md`, `misc.md` — too vague
- `README.md` inside references/ — use `user-guide.md` instead
- Numbered filenames: `01-setup.md` — order is determined by SKILL.md execution steps
