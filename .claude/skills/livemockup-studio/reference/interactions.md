---
name: interactions
description: "v1.6.1 | Microanimations + feedback + endpoints"
---

# Interactions

Microanimations, feedback patterns, and endpoint handling for live mockups.

---

## ❌/✅ Examples

| ❌ Wrong | ✅ Correct |
|----------|-----------|
| No transition | `transition: all 0.2s ease` |
| Animate width/height | Animate transform/opacity |
| 1s+ duration | 150-400ms for UI |
| Linear easing | Use ease-out or cubic-bezier |
| No hover feedback | Always show state change |
| Silent actions | Toast on every action |
| Unclear dead ends | Toast `📌 ... — финальная точка` ⭐ |

---

## Endpoint Pattern ⭐

**Problem:** Users click elements expecting navigation, but mockup doesn't have that screen implemented. They think it's a bug.

**Solution:** Show clear Toast message indicating this is a planned feature endpoint.

### Toast Format

```
📌 {Element Name} — финальная точка
```

### Examples

```javascript
// Wrong - unclear
onclick="showToast('Профиль Maria Flow')"

// Correct - clear endpoint
onclick="showToast('📌 Maria Flow — финальная точка')"
```

### When to Use

| Situation | Toast Format |
|-----------|--------------|
| Card without detail screen | `📌 {Card Title} — финальная точка` |
| Tab without content | `📌 {Tab Name} — финальная точка` |
| Button without action screen | `📌 {Button Label} — финальная точка` |
| Metric without drill-down | `📌 {Metric Name} — финальная точка` |
| Feature placeholder | `📌 {Feature Name} — финальная точка` |

### Endpoint Counting

Track endpoints in Navigation Map stats:
- **Экранов** — full screens with content
- **Полных путей** — L0→L3 complete navigation chains
- **Финальных точек** — all endpoint toasts

---

## Timing Guidelines

| Type | Duration | Easing |
|------|----------|--------|
| Micro (hover) | 150-250ms | ease |
| Standard | 250-400ms | ease-out |
| Complex | 400-600ms | cubic-bezier |

**Cubic-bezier presets:**

```css
--ease-standard: cubic-bezier(0.4, 0, 0.2, 1);  /* Material */
--ease-decelerate: cubic-bezier(0, 0, 0.2, 1);  /* Enter */
--ease-accelerate: cubic-bezier(0.4, 0, 1, 1);  /* Exit */
```

**CBS HOME:** Industrial aesthetic — use linear and ease-out only. Never use bounce or spring curves.

---

## Hover Effects

### Card Lift

```css
.card {
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.card:hover {
  transform: translateY(-4px);
  box-shadow: 0 12px 24px rgba(0,0,0,0.12);
}
```

### Button Press

```css
.btn {
  transition: all 0.15s ease;
}

.btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0,0,0,0.15);
}

.btn:active {
  transform: scale(0.98) translateY(0);
}
```

### Link Underline

```css
.link {
  position: relative;
}

.link::after {
  content: '';
  position: absolute;
  bottom: -2px;
  left: 0;
  width: 0;
  height: 2px;
  background: var(--primary);
  transition: width 0.2s ease;
}

.link:hover::after {
  width: 100%;
}
```

### Icon Rotate

```css
.icon-btn:hover svg {
  transform: rotate(15deg);
  transition: transform 0.2s ease;
}
```

---

## State Transitions

### Input Focus

```css
.input {
  border: 2px solid var(--border);
  transition: border-color 0.2s, box-shadow 0.2s;
}

.input:focus {
  border-color: var(--primary);
  box-shadow: var(--shadow-focus-teal);
  outline: none;
}
```

### Input Validation

```css
.input.error {
  border-color: var(--danger);
  animation: shake 0.3s ease;
}

.input.success {
  border-color: var(--success);
}

@keyframes shake {
  0%, 100% { transform: translateX(0); }
  25% { transform: translateX(-4px); }
  75% { transform: translateX(4px); }
}
```

### Toggle Switch

```css
.toggle {
  width: 44px;
  height: 24px;
  background: var(--border);
  border-radius: 12px;
  position: relative;
  cursor: pointer;
  transition: background 0.2s;
}

.toggle::after {
  content: '';
  position: absolute;
  width: 20px;
  height: 20px;
  background: white;
  border-radius: 50%;
  top: 2px;
  left: 2px;
  transition: transform 0.2s;
  box-shadow: 0 2px 4px rgba(0,0,0,0.2);
}

.toggle.active {
  background: var(--primary);
}

.toggle.active::after {
  transform: translateX(20px);
}
```

---

## Toast Notifications (Unified)

### Toast CSS

```css
.toast {
  position: fixed;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%) translateY(100px);
  color: white;
  padding: 12px 24px;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  opacity: 0;
  transition: all 0.3s ease;
  z-index: 2000;
  box-shadow: 0 4px 12px rgba(0,0,0,0.3);
  display: flex;
  align-items: center;
  gap: 8px;
}

.toast.show {
  transform: translateX(-50%) translateY(0);
  opacity: 1;
}
```

### Toast JS (single canonical version)

```javascript
function showToast(message, type = 'info') {
  const icons = { success: '✓', error: '✕', warning: '⚠', info: 'ℹ' };
  const root = getComputedStyle(document.documentElement);
  const getVar = (v, fb) => root.getPropertyValue(v).trim() || fb;
  const colors = {
    success: getVar('--success', '#22c55e'),
    error: getVar('--danger', '#ef4444'),
    warning: getVar('--warning', '#f59e0b'),
    info: getVar('--primary', '#1A6B6A')
  };

  const existing = document.querySelector('.toast');
  if (existing) existing.remove();

  const toast = document.createElement('div');
  toast.className = 'toast';
  toast.innerHTML = `<span>${icons[type]}</span>${message}`;
  toast.style.background = colors[type];
  document.body.appendChild(toast);

  requestAnimationFrame(() => toast.classList.add('show'));
  setTimeout(() => {
    toast.classList.remove('show');
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}
```

### Usage

```javascript
showToast('Добавлено в корзину', 'success');
showToast('Ошибка сервера', 'error');
showToast('📌 Maria Flow — финальная точка');  // default 'info'
```

---

## Loading States

### Spinner

```css
.spinner {
  width: 24px;
  height: 24px;
  border: 3px solid var(--border);
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
```

### Skeleton

```css
.skeleton {
  background: linear-gradient(
    90deg,
    #f0f0f0 25%,
    #e0e0e0 50%,
    #f0f0f0 75%
  );
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
  border-radius: 4px;
}

@keyframes shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
```

### Button Loading

```css
.btn.loading {
  position: relative;
  color: transparent;
  pointer-events: none;
}

.btn.loading::after {
  content: '';
  position: absolute;
  width: 16px;
  height: 16px;
  top: 50%;
  left: 50%;
  margin: -8px 0 0 -8px;
  border: 2px solid rgba(255,255,255,0.3);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}
```

---

## Popup/Modal

### Overlay + Content

```css
.popup-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  visibility: hidden;
  transition: all 0.3s ease;
  z-index: 1000;
}

.popup-overlay.active {
  opacity: 1;
  visibility: visible;
}

.popup {
  background: white;
  border-radius: 16px;
  padding: 24px;
  max-width: 480px;
  width: 90%;
  transform: scale(0.9) translateY(20px);
  transition: transform 0.3s ease;
}

.popup-overlay.active .popup {
  transform: scale(1) translateY(0);
}
```

### Popup JS

```javascript
function showPopup(id) {
  document.getElementById(id).classList.add('active');
  document.body.style.overflow = 'hidden';
}

function hidePopup(id, event) {
  if (!event || event.target.classList.contains('popup-overlay')) {
    document.getElementById(id).classList.remove('active');
    document.body.style.overflow = '';
  }
}
```

---

## Screen Transitions

### Fade In

```css
.screen {
  display: none;
  opacity: 0;
  animation: fadeIn 0.25s ease forwards;
}

.screen.active {
  display: block;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
```

### Slide

```css
@keyframes slideInRight {
  from { transform: translateX(100%); }
  to { transform: translateX(0); }
}

@keyframes slideOutLeft {
  from { transform: translateX(0); }
  to { transform: translateX(-100%); }
}
```

---

## Scroll Effects

### Fade on Scroll

```javascript
const observer = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      entry.target.classList.add('visible');
    }
  });
}, { threshold: 0.1 });

document.querySelectorAll('.fade-in').forEach(el => observer.observe(el));
```

```css
.fade-in {
  opacity: 0;
  transform: translateY(20px);
  transition: all 0.5s ease;
}

.fade-in.visible {
  opacity: 1;
  transform: translateY(0);
}
```

---

## Performance Tips

| Property | GPU | Recommendation |
|----------|-----|----------------|
| transform | ✅ | Use always |
| opacity | ✅ | Use always |
| box-shadow | ⚠️ | OK for hover |
| background | ⚠️ | OK for states |
| width/height | ❌ | Avoid animating |
| margin/padding | ❌ | Avoid animating |

---

*interactions v1.6.1*
