---
name: design
description: "v1.3.0 | L1 - Design tokens and interaction map"
---

# design

## Purpose

Define visual style and interaction map before building.

| Creates | design.md |
|---------|-----------|
| Layer | L1 (Foundation) |
| Output | Tokens + interaction map |

---

## Requirements

| Input | Check |
|-------|-------|
| brief.md | In context |

If missing → "brief отсутствует. Сначала brief."

---

## Pre-read

| # | Read | Why |
|---|------|-----|
| 1 | reference/components.md | Token structure |
| 2 | reference/interactions.md | Animation patterns |

---

1?

---

## Step 1: Color Palette

### Primary Colors

| Token | Value | Usage |
|-------|-------|-------|
| --primary | {hex} | Main actions, links |
| --primary-dark | {hex} | Hover states |
| --primary-light | {hex} | Backgrounds |
| --accent | {hex} | CTAs, badges |

### Neutrals

| Token | Value | Usage |
|-------|-------|-------|
| --bg | #ffffff | Main background |
| --bg-subtle | #f8fafc | Subtle sections |
| --bg-elevated | #f1f5f9 | Cards, inputs |
| --text | {hex} | Main text |
| --text-secondary | {hex} | Secondary text |
| --border | {hex} | Borders |

### Semantic

| Token | Value |
|-------|-------|
| --success | #22c55e |
| --warning | #f59e0b |
| --danger | #ef4444 |

---

## Step 2: Typography

| Element | Size | Weight |
|---------|------|--------|
| H1 | 32-44px | 800 |
| H2 | 24-28px | 700 |
| H3 | 18-20px | 600 |
| Body | 14-16px | 400 |
| Small | 12-13px | 500 |

**Font:** Inter, -apple-system, sans-serif

---

## Step 3: Spacing & Radius

| Token | Value |
|-------|-------|
| --radius-sm | 6px |
| --radius-md | 10px |
| --radius-lg | 16px |
| --radius-xl | 24px |

---

## Step 4: Interaction Map

For each screen from brief:

| Element | Trigger | Action | Feedback |
|---------|---------|--------|----------|
| {element} | {click/hover} | {what happens} | {toast/animation} |

### Example

| Element | Trigger | Action | Feedback |
|---------|---------|--------|----------|
| Add to cart | Click | Add item | Toast "Добавлено" |
| Product card | Hover | Lift + shadow | - |
| Submit form | Click | Validate + send | Toast success/error |
| Nav item | Click | Show screen | Screen transition |

---

## Step 5: Component Variants

List which components from reference/components.md will be used:

| Component | Variants |
|-----------|----------|
| Button | primary, secondary |
| Card | product, stat |
| Form | input, select, textarea |
| {other} | {variants} |

---

## Step 6: Output

Create design.md:

```markdown
# Design: {project}

## Color Palette

| Token | Value |
|-------|-------|
| --primary | {hex} |
| --primary-dark | {hex} |
| --accent | {hex} |
| --bg | #ffffff |
| --text | {hex} |
| --border | {hex} |

## Typography

Font: Inter
Scale: 14px base

## Interaction Map

| Element | Trigger | Action | Feedback |
|---------|---------|--------|----------|
| {element} | {trigger} | {action} | {feedback} |

## Components

| Component | Use |
|-----------|-----|
| {component} | {where} |
```

---

## Quick Checklist ⭐

```
□ Primary color defined
□ Accent color defined
□ Text colors defined (primary, secondary, tertiary)
□ Border color defined
□ Font family selected
□ All interactions mapped
□ Feedback type for each action defined
```

---

## Anchor

🎨 livemockup-studio v1.3.0 · design · complete
🟢 | NEXT: user command

---

1 → build (continue to L2)
2 → revise design

---

1?
