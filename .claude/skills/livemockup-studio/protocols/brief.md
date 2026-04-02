---
name: brief
description: "v1.3.0 | L0 - Collect requirements and data plan"
---

# brief

## Purpose

Collect requirements for mockup — what to build and what data to use.

| Creates | brief.md |
|---------|----------|
| Layer | L0 (Piles) |
| Output | Requirements + data strategy |

---

## Requirements

| Input | Check |
|-------|-------|
| User description | In chat |

No formal input required. User describes what they need.

---

## Pre-read

| # | Read | Why |
|---|------|-----|
| 1 | reference/data.md | Data patterns |

---

1?

---

## Step 1: Clarify Scope

### Questions to Ask

| Aspect | Question |
|--------|----------|
| Type | Dashboard / E-commerce / Landing / Admin / Other? |
| Devices | Phone / Tablet / Desktop? Which primary? |
| Screens | How many views/screens? |
| Interactions | What should be clickable? |
| Data | Real data provided or generate realistic? |

### Extract from User

| Field | Value |
|-------|-------|
| Project name | {name} |
| Type | {type} |
| Primary device | {device} |
| Secondary devices | {devices} |
| Key screens | {list} |

---

## Step 2: Define Interactions

| Element | Behavior |
|---------|----------|
| Buttons | Hover effect? Click action? |
| Cards | Clickable? Link to? |
| Forms | Validation? Submit toast? |
| Navigation | Screen switching? |
| Modals | Which popups needed? |

---

## Step 3: Data Strategy

### Data Sources

| Type | Source |
|------|--------|
| Products | User provides / generate |
| Users | Avatars from pravatar.cc |
| Stats | Generate realistic numbers |
| Text | Write meaningful content |

### Data to Prepare

| Entity | Fields | Count |
|--------|--------|-------|
| {entity} | {fields} | {n} |

---

## Step 4: Output

Create brief.md:

```markdown
# Brief: {project}

## Overview

| Field | Value |
|-------|-------|
| Type | {type} |
| Primary | {device} |
| Devices | {list} |

## Screens

| # | Screen | Description |
|---|--------|-------------|
| 1 | {name} | {what it shows} |

## Interactions

| Element | Behavior |
|---------|----------|
| {element} | {behavior} |

## Data Plan

| Entity | Fields | Count |
|--------|--------|-------|
| {entity} | {fields} | {n} |

## Notes

{any special requirements}
```

---

## Quick Checklist ⭐

| Check | Status |
|-------|--------|
| Project type defined | ☐ |
| Primary device chosen | ☐ |
| Screens listed | ☐ |
| Interactions mapped | ☐ |
| Data entities identified | ☐ |
| brief.md created | ☐ |

---

## Anchor

🎨 livemockup-studio v1.3.0 · brief · complete
🟢 | NEXT: user command

---

1 → design (continue to L1)
2 → revise brief

---

1?
