---
name: polish
description: "v1.3.0 | L3 - Add animations, feedback, and realistic data"
---

# polish

## Purpose

Polish mockup with animations, feedback, and realistic data.

| Creates | final.html |
|---------|------------|
| Layer | L3 (Roof) |
| Output | Production-ready mockup |

---

## Pre-read

| # | Read | Why |
|---|------|-----|
| 1 | reference/interactions.md | Animation patterns + Toast |
| 2 | reference/data.md | Realistic data |

---

## Step 1: Verify Build Quality

Before polishing, verify critical build elements:

| Check | |
|-------|-|
| Flex chain complete | |
| Tab bar at bottom | |
| Clickability fix present | |
| All onclick elements work | |

If any fail → fix in build before continuing.

---

## Step 2: Enhance Animations

Apply timing curves and enhanced hover effects from **reference/interactions.md**:
- Card Lift (enhanced with shadow)
- Button Press (with ::after overlay)
- Input Focus (border + shadow)

---

## Step 3: Add Feedback

### Toast System

Use unified Toast from **reference/interactions.md** → Toast Notifications section.

### Connect to Actions

| Action | Toast |
|--------|-------|
| Add to cart | `showToast('Добавлено в корзину')` |
| Form submit | `showToast('Отправлено!')` |
| Error | `showToast('Ошибка', 'error')` |
| Endpoint | `showToast('📌 {Name} — финальная точка')` |

---

## Step 4: Fill Realistic Data

Replace all placeholders using patterns from **reference/data.md**:

| Placeholder | Replace With |
|-------------|--------------|
| "Товар 1" | Realistic product name |
| placeholder.jpg | placehold.co or pravatar.cc URL |
| "Lorem ipsum" | Meaningful Russian text |

---

## Step 5: Loading States

Apply from **reference/interactions.md** → Loading States:
- Skeleton screens for content areas
- Button loading state with spinner
- simulateAction() pattern for async feedback

---

## Step 6: Scroll Animations

Apply from **reference/interactions.md** → Scroll Effects:
- IntersectionObserver for fade-in elements
- `.fade-in` → `.fade-in.visible` transition

---

## Step 7: Validate

Run **reference/checklist.md** checks before moving to test protocol.
