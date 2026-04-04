---
name: cbs-patterns
description: "v1.6.1 | CBS HOME-specific UI patterns for investment platform"
---

# CBS HOME Patterns

UI patterns specific to the CBS HOME investment platform.

---

## Role Selection Cards

Used in auth-flow for choosing Investor/Agent/Company role.

```html
<div class="role-cards">
  <div class="role-card" onclick="selectRole(this, 'Инвестор')">
    <div class="role-card-check"></div>
    <div class="role-card-header">
      <span class="role-card-icon">
        <span class="icon-box teal"><i data-lucide="trending-up"></i></span>
      </span>
      <span class="role-card-title">Инвестор</span>
    </div>
    <div class="role-card-desc">Покупайте продукты, управляйте портфелем</div>
    <div class="role-card-features">
      <span class="role-feature">Портфель</span>
      <span class="role-feature">Рассрочки</span>
    </div>
  </div>
</div>
```

### Roles

| Role | Icon | Lucide | Color |
|------|------|--------|-------|
| Инвестор | trending-up | .icon-box.teal | var(--primary) |
| Агент | users | .icon-box.orange | var(--accent) |
| Компания | building-2 | .icon-box.blue | #3b82f6 |

---

## Balance Card

Gradient card for displaying balance (active or passive).

```html
<div class="balance-card" style="background:linear-gradient(135deg, var(--primary), var(--primary-light))">
  <div class="balance-label">Активный баланс</div>
  <div class="balance-value">€5 200</div>
  <div class="balance-row">
    <div class="balance-sub">
      <div class="balance-sub-label">Подтверждён</div>
      <div class="balance-sub-value">€5 200</div>
    </div>
    <div class="balance-sub">
      <div class="balance-sub-label">Заморожен</div>
      <div class="balance-sub-value">€1 000</div>
    </div>
  </div>
</div>
```

### Balance Types

| Type | Gradient | Usage |
|------|----------|-------|
| Active (investor) | primary → primary-light | Deposits, purchases |
| Passive (agent) | accent → accent-dark | Commissions, withdrawals |
| Revenue (company) | primary → primary-dark | Company income |

---

## Installment Schedule Table

Used in investor purchase flow for 6/12 month plans.

```html
<div class="plan-card selected" onclick="selectPlan(this, '6m')">
  <div class="plan-title">6 месяцев</div>
  <div class="plan-desc">10% × 5 платежей + 50% финальный</div>
  <table class="schedule-table">
    <thead><tr><th>Месяц</th><th>Сумма</th><th>Юнитов</th></tr></thead>
    <tbody>
      <tr><td>1 (сейчас)</td><td>€500</td><td>500</td></tr>
      <tr><td>2-5</td><td>€500 × 4</td><td>500 × 4</td></tr>
      <tr><td>6</td><td>€2 500</td><td>2 500</td></tr>
    </tbody>
  </table>
</div>
```

### Plans

| Duration | Schedule | Bonus |
|----------|----------|-------|
| 6 мес | 10% × 5 + 50% final | Investor bonus on completion |
| 12 мес | 5% × 11 + 45% final | Larger bonus on completion |

---

## Commission Item

Agent commission display with L1/L2/L3 levels.

```html
<div class="comm-item" onclick="showToast('📌 Детали комиссии — финальная точка')">
  <div class="comm-level l1">L1</div>
  <div class="comm-info">
    <div class="comm-source">Анна Петрова</div>
    <div class="comm-product">IPI AG · 5 000 юнитов</div>
  </div>
  <div class="comm-amount">
    <div class="comm-sum">+€500</div>
    <div class="comm-date">01.04.2026</div>
  </div>
</div>
```

### Commission Levels

| Level | Rate | Color Class | Background |
|-------|------|-------------|-----------|
| L1 | 10% | .comm-level.l1 | accent tint |
| L2 | 3% | .comm-level.l2 | primary tint |
| L3 | 1% | .comm-level.l3 | neutral tint |

---

## Referral Link Card

Agent referral management.

```html
<div class="ref-card">
  <div class="ref-header">
    <span class="ref-code">REF-SS-001</span>
    <span class="ref-status active">Активна</span>
  </div>
  <div class="ref-url">https://cbshome.org/r/REF-SS-001</div>
  <div class="ref-stats">
    <div class="ref-stat"><div class="ref-stat-value">234</div><div class="ref-stat-label">Клики</div></div>
    <div class="ref-stat"><div class="ref-stat-value">28</div><div class="ref-stat-label">Регистрации</div></div>
    <div class="ref-stat"><div class="ref-stat-value">12</div><div class="ref-stat-label">Покупки</div></div>
  </div>
  <button class="copy-btn" onclick="showToast('Ссылка скопирована','success')">Копировать ссылку</button>
</div>
```

---

## KYC Status Card

Verification status indicator with 3 states.

```html
<div class="kyc-status-card approved">
  <div class="kyc-icon"><i data-lucide="shield-check" style="width:48px;height:48px;color:var(--success)"></i></div>
  <div class="kyc-title" style="color:var(--success)">Верификация пройдена</div>
  <div class="kyc-text">Ваша личность подтверждена.</div>
</div>
```

### States

| State | Class | Color | Icon |
|-------|-------|-------|------|
| Pending | .pending | var(--warning) | shield-alert |
| Approved | .approved | var(--success) | shield-check |
| Rejected | .rejected | var(--danger) | shield-x |

---

## Product Card (Marketplace)

Investment product display.

```html
<div class="product-card" onclick="showProduct('ipi')">
  <div class="product-img gradient-primary">
    <i data-lucide="building" style="width:48px;height:48px;stroke:white"></i>
    <span class="product-company">IPI AG</span>
  </div>
  <div class="product-body">
    <div class="product-name">IPI AG Shares</div>
    <div class="product-desc">Инвестиции в строительные проекты</div>
    <div class="product-meta">
      <span class="product-price">€1.00 / юнит</span>
      <span class="product-units">500 000 доступно</span>
    </div>
  </div>
</div>
```

### Products

| Product | Company | Price | Gradient |
|---------|---------|-------|----------|
| IPI AG Shares | IPI AG | €1.00 | gradient-primary |
| Immo-Pro-Invest | Immo-Pro-Invest GmbH | €1.00 | gradient-deep |
| CBS Home Franchise | CBS Home AG | €1.00 | gradient-accent |

---

## Transaction Item

Balance/history transaction display.

```html
<div class="tx-item" onclick="showToast('📌 Детали транзакции — финальная точка')">
  <div class="icon-box green"><i data-lucide="arrow-down-circle"></i></div>
  <div class="tx-info">
    <div class="tx-title">Пополнение USDT (TRC20)</div>
    <div class="tx-date">01.04.2026, 14:23</div>
  </div>
  <div class="tx-amount">
    <div class="tx-sum positive">+€1 000</div>
    <div class="tx-status frozen">Заморожен</div>
  </div>
</div>
```

### Transaction Types

| Type | Icon | Icon Color | Amount Color |
|------|------|-----------|-------------|
| Deposit | arrow-down-circle | .icon-box.green | .positive (success) |
| Purchase | shopping-cart | .icon-box.teal | .negative (text) |
| Commission | gem | .icon-box.orange | .positive (success) |
| Withdrawal | arrow-up-circle | .icon-box.red | .negative (text) |

---

## Leaderboard Item

Agent ranking display.

```html
<div class="rank-item" onclick="showToast('📌 Профиль агента — финальная точка')">
  <div class="rank-pos top3">1</div>
  <img class="rank-avatar" src="https://i.pravatar.cc/150?img=33" alt="">
  <div class="rank-info">
    <div class="rank-name">Максим Иванов</div>
    <div class="rank-volume">€48 200 объём</div>
  </div>
  <div class="rank-change" style="color:var(--success)">—</div>
</div>
```

Current user highlighted: `class="rank-item me"`

---

## Filter Tabs

Horizontal filter for lists (commissions, users).

```html
<div class="filter-tabs">
  <button class="filter-tab active" onclick="filter(this,'all')">Все</button>
  <button class="filter-tab" onclick="filter(this,'l1')">L1 (10%)</button>
  <button class="filter-tab" onclick="filter(this,'l2')">L2 (3%)</button>
</div>
```

---

*cbs-patterns v1.6.1*
