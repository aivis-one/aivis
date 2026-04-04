---
name: data
description: "v1.6.1 | Realistic data patterns for mockups"
---

# Data

Realistic data patterns — no Lorem Ipsum.

---

## ❌/✅ Examples

| ❌ Wrong | ✅ Correct |
|----------|-----------|
| "Lorem ipsum dolor" | "Ортопедическая кровать с подъёмным механизмом" |
| "John Doe" | "Анна Петрова" |
| "12345" (price) | "45 990 ₽" |
| placeholder.jpg | Real image or branded placeholder |
| "user@example.com" | "anna.petrova@company.ru" |
| "5 min ago" | "5 мин назад" |

---

## Data Hierarchy

```
Live data > Real data > Realistic-looking > Dummy
```

| Type | When |
|------|------|
| Live | Testing with real users |
| Real | Demo with production data |
| Realistic | Default for mockups |
| Dummy | Layout only |

---

## Believability Rules

| Rule | Description |
|------|-------------|
| Believable values | Names look like names |
| Believable spread | Realistic distribution |
| Believable entities | Record makes sense |
| Believable relations | Connections are logical |

**Example:** Dr. with birthdate 15 years ago = ❌

---

## User Profiles

### Russian Names

```javascript
const names = {
  male: ['Александр', 'Дмитрий', 'Максим', 'Сергей', 'Андрей', 'Алексей', 'Артём', 'Илья', 'Кирилл', 'Михаил'],
  female: ['Анна', 'Мария', 'Елена', 'Ольга', 'Наталья', 'Екатерина', 'Татьяна', 'Ирина', 'Светлана', 'Юлия'],
  surnames: ['Иванов', 'Петров', 'Сидоров', 'Козлов', 'Новиков', 'Морозов', 'Волков', 'Соколов', 'Лебедев', 'Попов']
};
```

### User Object

```javascript
const user = {
  id: 1,
  name: "Анна Петрова",
  email: "anna.petrova@company.ru",
  phone: "+7 (999) 123-45-67",
  avatar: "https://i.pravatar.cc/150?img=5",
  role: "Менеджер",
  department: "Продажи",
  joinDate: "15.03.2024",
  lastActive: "Сегодня, 14:30"
};
```

### Avatar Services

| Service | URL | Notes |
|---------|-----|-------|
| Pravatar | `https://i.pravatar.cc/150?img={1-70}` | 70 faces |
| UI Faces | `https://uifaces.co/` | API |
| RandomUser | `https://randomuser.me/api/` | Full profiles |

---

## E-commerce

### Product

```javascript
const product = {
  id: 1,
  name: "Кровать Askona Orion",
  sku: "ASK-ORI-160",
  price: 45990,
  oldPrice: 52990,
  discount: "-13%",
  rating: 4.8,
  reviews: 124,
  inStock: true,
  badge: "Хит продаж",
  image: "product-1.jpg",
  category: "Кровати",
  description: "Ортопедическая кровать с подъёмным механизмом"
};
```

### Price Formatting

```javascript
function formatPrice(num) {
  return num.toLocaleString('ru-RU') + ' ₽';
}
// 45990 → "45 990 ₽"
```

### Cart Item

```javascript
const cartItem = {
  product: { /* product object */ },
  quantity: 2,
  size: "160×200",
  color: "Серый",
  total: 91980
};
```

### Order

```javascript
const order = {
  id: "ORD-2024-001234",
  date: "21.01.2026",
  status: "В обработке",
  items: 3,
  total: 156990,
  delivery: "Доставка курьером",
  address: "Москва, ул. Примерная, д. 15, кв. 42"
};
```

---

## Dashboard Stats

### Metrics

```javascript
const stats = {
  revenue: { value: 1250000, change: "+12%", trend: "up" },
  orders: { value: 347, change: "+8%", trend: "up" },
  conversion: { value: 3.2, change: "-0.4%", trend: "down" },
  avgCheck: { value: 3602, change: "+5%", trend: "up" },
  visitors: { value: 12450, change: "+15%", trend: "up" }
};
```

### Chart Data

```javascript
const chartData = {
  labels: ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'],
  values: [4200, 5100, 4800, 6200, 5900, 3100, 2800]
};
```

### Activity Feed

```javascript
const activities = [
  { icon: "📦", text: "Новый заказ #1234", time: "5 мин назад", type: "order" },
  { icon: "👤", text: "Регистрация: Иван П.", time: "12 мин назад", type: "user" },
  { icon: "💬", text: "Отзыв на товар", time: "1 час назад", type: "review" },
  { icon: "⚠️", text: "Товар заканчивается", time: "2 часа назад", type: "alert" }
];
```

---

## Forms

### Contact Form

```javascript
const formData = {
  name: "Сергей Волков",
  email: "sergey@example.com",
  phone: "+7 (916) 555-12-34",
  company: "ООО «Технологии»",
  message: "Интересует оптовое сотрудничество. Прошу связаться для обсуждения условий."
};
```

### Validation Messages

```javascript
const messages = {
  required: "Обязательное поле",
  email: "Введите корректный email",
  phone: "Введите корректный телефон",
  minLength: "Минимум {n} символов",
  success: "Форма отправлена!",
  error: "Ошибка отправки"
};
```

---

## Navigation

### Menu Items

```javascript
const menu = [
  { label: "Главная", href: "#", icon: "🏠" },
  { label: "Каталог", href: "#catalog", icon: "📦", badge: "New" },
  { label: "О компании", href: "#about", icon: "ℹ️" },
  { label: "Контакты", href: "#contacts", icon: "📞" }
];
```

### Breadcrumbs

```javascript
const breadcrumbs = [
  { label: "Главная", href: "#" },
  { label: "Каталог", href: "#catalog" },
  { label: "Кровати", href: "#beds" },
  { label: "Askona Orion", href: null } // current
];
```

---

## Status & Tags

### Order Status

| Status | Color | Icon |
|--------|-------|------|
| Новый | blue | 🆕 |
| В обработке | yellow | ⏳ |
| Отправлен | purple | 📦 |
| Доставлен | green | ✓ |
| Отменён | red | ✕ |

### User Roles

```javascript
const roles = {
  admin: { label: "Админ", color: "#ef4444" },
  manager: { label: "Менеджер", color: "#3b82f6" },
  user: { label: "Пользователь", color: "#6b7280" },
  vip: { label: "VIP", color: "#f59e0b" }
};
```

---

## Date & Time

### Relative Time

```javascript
function relativeTime(date) {
  const diff = Date.now() - date;
  const mins = Math.floor(diff / 60000);
  
  if (mins < 1) return "Только что";
  if (mins < 60) return `${mins} мин назад`;
  if (mins < 1440) return `${Math.floor(mins/60)} ч назад`;
  return new Date(date).toLocaleDateString('ru-RU');
}
```

### Format Patterns

| Pattern | Example |
|---------|---------|
| Short | 21.01.2026 |
| Medium | 21 января 2026 |
| With time | 21.01.2026, 14:30 |
| Relative | 5 мин назад |

---

## Placeholder Images

| Type | Service |
|------|---------|
| Products | `https://placehold.co/400x300/EEE/999?text=Product` |
| Avatars | `https://i.pravatar.cc/150?img={n}` |
| Abstract | `https://picsum.photos/400/300?random={n}` |

---

---

## CBS HOME Platform Data

### Investment Products

```javascript
const products = {
  ipiAg: {
    name: "IPI AG Shares",
    company: "IPI AG",
    pricePerUnit: 1.00,
    currency: "EUR",
    available: 500000,
    description: "Инвестиционные юниты IPI AG, обеспеченные портфелем строительных проектов в Германии"
  },
  immoProInvest: {
    name: "Immo-Pro-Invest",
    company: "Immo-Pro-Invest GmbH",
    pricePerUnit: 1.00,
    currency: "EUR",
    available: 300000,
    description: "Инвестиции в портфель объектов недвижимости"
  },
  cbsHomeFranchise: {
    name: "CBS Home Franchise",
    company: "CBS Home AG",
    pricePerUnit: 1.00,
    currency: "EUR",
    available: 200000,
    description: "Франшиза CBS Home — запатентованная строительная технология (EP 3 574 160 B1)"
  }
};
```

### Platform Roles

```javascript
const roles = {
  investor: { label: "Инвестор", icon: "📊", color: "var(--primary)" },
  agent: { label: "Агент", icon: "🤝", color: "var(--accent)" },
  company: { label: "Компания", icon: "🏢", color: "var(--primary-dark)" },
  staff: { label: "Staff", icon: "🛡️", color: "var(--danger)" }
};
```

### EUR Price Formatting

```javascript
function formatEUR(cents) {
  return '€' + (cents / 100).toLocaleString('de-DE');
}
// 524000 → "€5.240" or use space: "€5 240"
```

### Commission Levels

```javascript
const commissions = {
  l1: { label: "L1", percent: 10, color: "var(--accent)" },
  l2: { label: "L2", percent: 3, color: "var(--primary)" },
  l3: { label: "L3", percent: 1, color: "var(--text-secondary)" }
};
```

### German + Russian Names Mix

```javascript
const names = {
  german: ['Sergej Seider', 'Viktor Braun', 'Admin Müller', 'Erste Kapital GmbH'],
  russian: ['Анна Петрова', 'Дмитрий Козлов', 'Елена Морозова', 'Максим Иванов', 'Наталья Сидорова', 'Ольга Лебедева']
};
```

*data v1.6.1*
