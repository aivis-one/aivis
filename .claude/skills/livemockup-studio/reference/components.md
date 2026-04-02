---
name: components
description: "v1.3.0 | UI component patterns for mockups"
---

# Components

Reusable UI patterns for mockup content.

---

## ❌/✅ Examples

| ❌ Wrong | ✅ Correct |
|----------|-----------|
| Hardcoded colors | Use CSS variables |
| No border-radius | `border-radius: var(--radius-md)` |
| Flat buttons | Add shadow + hover lift |
| No focus states | Always style :focus |
| Generic shadows | Use shadow scale (sm/md/lg) |
| Children block parent onclick | Add `pointer-events: none` on children |
| Tab bar `position: fixed` | Tab bar `position: sticky` |
| `display: block` on screen | `display: flex` on screen |

---

## Design Tokens

```css
:root {
  /* Colors */
  --primary: #2563eb;
  --primary-dark: #1d4ed8;
  --primary-light: #3b82f6;
  --accent: #f59e0b;
  --accent-dark: #d97706;
  
  /* Neutrals */
  --bg: #ffffff;
  --bg-subtle: #f8fafc;
  --bg-elevated: #f1f5f9;
  --text: #1e293b;
  --text-secondary: #64748b;
  --text-tertiary: #94a3b8;
  --border: #e2e8f0;
  
  /* Semantic */
  --success: #22c55e;
  --success-dim: rgba(34, 197, 94, 0.15);
  --warning: #f59e0b;
  --warning-dim: rgba(245, 158, 11, 0.15);
  --danger: #ef4444;
  --danger-dim: rgba(239, 68, 68, 0.1);
  
  /* Shadows */
  --shadow-sm: 0 1px 2px rgba(0,0,0,0.05);
  --shadow-md: 0 4px 6px rgba(0,0,0,0.07);
  --shadow-lg: 0 10px 15px rgba(0,0,0,0.1);
  --shadow-xl: 0 20px 25px rgba(0,0,0,0.15);
  
  /* Radius */
  --radius-sm: 6px;
  --radius-md: 10px;
  --radius-lg: 16px;
  --radius-xl: 24px;
}
```

---

## Clickable Container Fix ⚠️ REQUIRED

When a container (card, row, etc.) has `onclick`, its children will block the click by default.

### The Problem

```html
<!-- Click on "Название" text won't trigger onclick! -->
<div class="card" onclick="doSomething()">
  <div class="card-title">Название</div>  <!-- blocks click -->
  <div class="card-text">Описание</div>   <!-- blocks click -->
</div>
```

### The Solution

```css
/* Disable pointer-events on children of clickable containers */
.card[onclick] *,
.stat-card[onclick] *,
.list-item[onclick] *,
.metric-row[onclick] *,
table tr[onclick] * {
  pointer-events: none;
}

/* Re-enable for nested interactive elements */
button,
input,
select,
textarea,
a {
  pointer-events: auto;
}
```

Now clicks anywhere in the card trigger the onclick, but nested buttons still work.

---

## Buttons

### Primary

```html
<button class="btn btn-primary">Оформить заказ</button>
```

```css
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px 24px;
  border-radius: var(--radius-md);
  font-weight: 600;
  font-size: 14px;
  cursor: pointer;
  border: none;
  transition: all 0.2s;
}

.btn-primary {
  background: var(--primary);
  color: white;
}

.btn-primary:hover {
  background: var(--primary-dark);
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3);
}

.btn-primary:active {
  transform: scale(0.98);
}
```

### Secondary

```css
.btn-secondary {
  background: white;
  color: var(--primary);
  border: 2px solid var(--primary);
}

.btn-secondary:hover {
  background: var(--primary);
  color: white;
}
```

### Sizes

```css
.btn-sm { padding: 8px 16px; font-size: 13px; }
.btn-lg { padding: 16px 32px; font-size: 16px; }
```

---

## Cards

### Basic Card

```html
<div class="card" onclick="showDetail(1)">
  <div class="card-image">
    <img src="product.jpg" alt="">
    <span class="card-badge">Хит</span>
  </div>
  <div class="card-body">
    <h3 class="card-title">Название товара</h3>
    <p class="card-text">Описание товара</p>
    <div class="card-price">
      <span class="price-current">45 990 ₽</span>
      <span class="price-old">52 990 ₽</span>
    </div>
  </div>
</div>
```

```css
.card {
  background: white;
  border-radius: var(--radius-lg);
  overflow: hidden;
  box-shadow: var(--shadow-sm);
  border: 1px solid var(--border);
  transition: transform 0.2s, box-shadow 0.2s;
  cursor: pointer;
}

.card:hover {
  transform: translateY(-4px);
  box-shadow: var(--shadow-lg);
}

/* ⚠️ If card has onclick, add this! */
.card[onclick] * {
  pointer-events: none;
}
.card[onclick] button {
  pointer-events: auto;
}

.card-image {
  position: relative;
  aspect-ratio: 4/3;
  overflow: hidden;
}

.card-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.card-badge {
  position: absolute;
  top: 12px;
  left: 12px;
  background: var(--accent);
  color: white;
  padding: 4px 10px;
  border-radius: var(--radius-sm);
  font-size: 12px;
  font-weight: 600;
}

.card-body {
  padding: 16px;
}

.card-title {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 8px;
}

.card-text {
  font-size: 14px;
  color: var(--text-secondary);
  margin-bottom: 12px;
}

.card-price {
  display: flex;
  align-items: center;
  gap: 8px;
}

.price-current {
  font-size: 18px;
  font-weight: 700;
  color: var(--primary);
}

.price-old {
  font-size: 14px;
  color: var(--text-tertiary);
  text-decoration: line-through;
}
```

---

## Metric Rows

For dashboards with clickable stat rows:

```html
<div class="metric-row" onclick="showDetails('check-in')">
  <span class="metric-label">Check-in rate</span>
  <div class="metric-bar"><div class="metric-fill" style="width: 78%"></div></div>
  <span class="metric-value">78%</span>
</div>
```

```css
.metric-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  cursor: pointer;
  transition: background 0.2s;
  border-radius: var(--radius-md);
}

.metric-row:hover {
  background: var(--bg-elevated);
}

.metric-row:active {
  background: var(--border);
}

/* ⚠️ CRITICAL: Children must not block clicks */
.metric-row[onclick] * {
  pointer-events: none;
}

.metric-label {
  min-width: 120px;
  flex-shrink: 0;
  font-size: 13px;
  color: var(--text-secondary);
}

.metric-bar {
  flex: 1;
  height: 8px;
  background: var(--border);
  border-radius: 4px;
  overflow: hidden;
}

.metric-fill {
  height: 100%;
  background: var(--primary);
}

.metric-value {
  width: 50px;
  font-size: 13px;
  font-weight: 600;
  color: var(--primary);
  text-align: right;
}
```

---

## Form Elements

### Input

```html
<div class="form-group">
  <label class="form-label">Email</label>
  <input type="email" class="form-input" placeholder="example@mail.ru">
</div>
```

```css
.form-group {
  margin-bottom: 16px;
}

.form-label {
  display: block;
  font-size: 14px;
  font-weight: 500;
  margin-bottom: 6px;
  color: var(--text);
}

.form-input {
  width: 100%;
  padding: 12px 16px;
  border: 2px solid var(--border);
  border-radius: var(--radius-md);
  font-size: 14px;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.form-input:focus {
  outline: none;
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1);
}

.form-input::placeholder {
  color: var(--text-tertiary);
}
```

### Select

```css
.form-select {
  appearance: none;
  background-image: url("data:image/svg+xml,...");
  background-repeat: no-repeat;
  background-position: right 12px center;
  padding-right: 40px;
}
```

### Textarea

```css
.form-textarea {
  min-height: 120px;
  resize: vertical;
}
```

---

## Navigation

### Header

```html
<header class="header">
  <div class="container">
    <a href="#" class="logo">
      <span class="logo-icon">A</span>
      <span class="logo-text">Brand</span>
    </a>
    <nav class="nav-links">
      <a href="#">Каталог</a>
      <a href="#">О нас</a>
      <a href="#">Контакты</a>
    </nav>
    <div class="header-actions">
      <button class="icon-btn">🔍</button>
      <button class="icon-btn">
        🛒
        <span class="badge">3</span>
      </button>
    </div>
  </div>
</header>
```

```css
.header {
  background: white;
  border-bottom: 1px solid var(--border);
  padding: 12px 0;
  position: sticky;  /* NOT fixed! */
  top: 0;
  z-index: 100;
}

.header .container {
  display: flex;
  align-items: center;
  gap: 24px;
}

.logo {
  display: flex;
  align-items: center;
  gap: 8px;
  text-decoration: none;
  font-weight: 700;
  font-size: 20px;
  color: var(--text);
}

.logo-icon {
  width: 36px;
  height: 36px;
  background: var(--primary);
  color: white;
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
}

.nav-links {
  display: flex;
  gap: 24px;
  flex: 1;
}

.nav-links a {
  color: var(--text);
  text-decoration: none;
  font-weight: 500;
  font-size: 14px;
  transition: color 0.2s;
}

.nav-links a:hover {
  color: var(--primary);
}

.icon-btn {
  width: 40px;
  height: 40px;
  border: none;
  background: var(--bg-elevated);
  border-radius: var(--radius-sm);
  cursor: pointer;
  position: relative;
  font-size: 18px;
  transition: background 0.2s;
}

.icon-btn:hover {
  background: var(--border);
}

.icon-btn .badge {
  position: absolute;
  top: -4px;
  right: -4px;
  width: 18px;
  height: 18px;
  background: var(--accent);
  color: white;
  font-size: 10px;
  font-weight: 700;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
}
```

---

## Stats

### Stat Card

```html
<div class="stat-card" onclick="showStatDetails('orders')">
  <div class="stat-icon">📊</div>
  <div class="stat-value">1,250</div>
  <div class="stat-label">Заказов</div>
  <div class="stat-change positive">+12%</div>
</div>
```

```css
.stat-card {
  background: white;
  border-radius: var(--radius-lg);
  padding: 20px;
  border: 1px solid var(--border);
  cursor: pointer;
  transition: transform 0.2s, box-shadow 0.2s;
}

.stat-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
}

/* ⚠️ If clickable */
.stat-card[onclick] * {
  pointer-events: none;
}

.stat-icon {
  font-size: 24px;
  margin-bottom: 12px;
}

.stat-value {
  font-size: 32px;
  font-weight: 700;
  margin-bottom: 4px;
}

.stat-label {
  font-size: 14px;
  color: var(--text-secondary);
  margin-bottom: 8px;
}

.stat-change {
  font-size: 13px;
  font-weight: 600;
}

.stat-change.positive { color: var(--success); }
.stat-change.negative { color: var(--danger); }
```

---

## Lists

### List Item

```html
<div class="list-item" onclick="showUser(1)">
  <img class="list-avatar" src="avatar.jpg" alt="">
  <div class="list-content">
    <div class="list-title">Название</div>
    <div class="list-subtitle">Описание</div>
  </div>
  <div class="list-meta">14:30</div>
</div>
```

```css
.list-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  border-radius: var(--radius-md);
  transition: background 0.2s;
  cursor: pointer;
}

.list-item:hover {
  background: var(--bg-elevated);
}

/* ⚠️ If clickable */
.list-item[onclick] * {
  pointer-events: none;
}
.list-item[onclick] button {
  pointer-events: auto;
}

.list-avatar {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  object-fit: cover;
}

.list-content {
  flex: 1;
  min-width: 0;
}

.list-title {
  font-weight: 600;
  font-size: 14px;
}

.list-subtitle {
  font-size: 13px;
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.list-meta {
  font-size: 12px;
  color: var(--text-tertiary);
}
```

---

## Tables

### Clickable Table Rows

```html
<table class="table">
  <thead>
    <tr>
      <th>Имя</th>
      <th>Email</th>
      <th>Роль</th>
    </tr>
  </thead>
  <tbody>
    <tr onclick="showUser(1)">
      <td>Анна Петрова</td>
      <td>anna@company.ru</td>
      <td>Менеджер</td>
    </tr>
  </tbody>
</table>
```

```css
.table {
  width: 100%;
  border-collapse: collapse;
}

.table th {
  text-align: left;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  padding: 12px;
  border-bottom: 1px solid var(--border);
}

.table td {
  padding: 12px;
  border-bottom: 1px solid var(--border);
}

.table tr {
  cursor: pointer;
  transition: background 0.2s;
}

.table tr:hover {
  background: var(--bg-elevated);
}

/* ⚠️ CRITICAL: Cells must not block row onclick */
.table tr[onclick] * {
  pointer-events: none;
}
.table tr[onclick] button,
.table tr[onclick] a {
  pointer-events: auto;
}
```

---

## Container

```css
.container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 20px;
}
```

---

## Responsive Prefixes

Inside `.mockup-content`, use device frame classes:

```css
/* Desktop default */
.mockup-content .grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
}

/* Tablet */
.device-frame.tablet .mockup-content .grid {
  grid-template-columns: repeat(2, 1fr);
}

/* Phone */
.device-frame.phone .mockup-content .grid {
  grid-template-columns: 1fr;
}
```

---

## Tab Bar (Mobile)

Bottom navigation for mobile screens.

### HTML

```html
<nav class="tab-bar">
  <button class="tab-item active" onclick="switchTab(this, 'screen-home')">
    <span class="tab-icon">🏠</span>
    <span>Главная</span>
  </button>
  <button class="tab-item" onclick="switchTab(this, 'screen-catalog')">
    <span class="tab-icon">📋</span>
    <span>Каталог</span>
  </button>
  <button class="tab-item" onclick="switchTab(this, 'screen-cart')">
    <span class="tab-icon">🛒</span>
    <span>Корзина</span>
  </button>
  <button class="tab-item" onclick="switchTab(this, 'screen-profile')">
    <span class="tab-icon">👤</span>
    <span>Профиль</span>
  </button>
</nav>
```

### CSS

```css
.tab-bar {
  position: sticky;  /* NOT fixed! */
  bottom: 0;
  left: 0;
  right: 0;
  display: flex;
  justify-content: space-around;
  background: white;
  border-top: 1px solid var(--border);
  padding: 8px 0 env(safe-area-inset-bottom, 20px);
  z-index: 100;
}

.tab-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 8px 16px;
  min-width: 64px;
  min-height: 44px;  /* Touch target */
  color: var(--text-tertiary);
  font-size: 11px;
  font-weight: 500;
  cursor: pointer;
  transition: color 0.2s;
  border: none;
  background: none;
}

.tab-item:hover {
  color: var(--primary-light);
}

.tab-item.active {
  color: var(--primary);
}

.tab-item .tab-icon {
  font-size: 22px;
}

.tab-item .badge {
  position: absolute;
  top: 4px;
  right: 4px;
  min-width: 18px;
  height: 18px;
  background: var(--danger);
  color: white;
  font-size: 10px;
  font-weight: 700;
  border-radius: 9px;
  display: flex;
  align-items: center;
  justify-content: center;
}
```

### JS ⚠️ UPDATED

```javascript
function switchTab(btn, screenId) {
  // Update active tab
  document.querySelectorAll('.tab-item').forEach(t => t.classList.remove('active'));
  btn.classList.add('active');
  
  // Show screen
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  document.getElementById(screenId).classList.add('active');
  
  // ⚠️ Aggressive scroll reset
  const screen = document.getElementById('deviceScreen');
  screen.scrollTop = 0;
  screen.scrollTo({ top: 0, behavior: 'instant' });
  requestAnimationFrame(() => screen.scrollTop = 0);
}
```

### ⚠️ Important

1. Tab bar MUST use `position: sticky`, NOT `position: fixed`.
2. `fixed` positions relative to viewport, causing tab bar to escape device frame.
3. Parent containers MUST have `flex: 1` for sticky bottom to work.

---

## Screen Structure ⚠️ CRITICAL

For tab bar to stay at bottom, use this structure:

```css
.screen {
  display: none;
  flex-direction: column;
  min-height: 100%;
}

.screen.active {
  display: flex;
  flex: 1;  /* MUST have flex:1 */
}

.main {
  flex: 1;  /* MUST have flex:1 to push tab-bar down */
}
```

```html
<div class="screen active" id="screen-home">
  <header class="header">...</header>
  <main class="main">...</main>     <!-- flex:1 pushes tab-bar down -->
  <nav class="tab-bar">...</nav>    <!-- sticky bottom works -->
</div>
```

---

*components v1.3.0*
