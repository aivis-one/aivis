# Brief: CBS HOME — Investor Shell

## Overview

| Field | Value |
|-------|-------|
| Type | Dashboard / Investment platform cabinet |
| Primary | Phone (390px) |
| Devices | Phone, Tablet, Desktop |
| Brand | CBS HOME (Teal #1A6B6A + Orange #E8651A, Montserrat) |
| Language | RU primary |

## Screens

| # | Screen | Description |
|---|--------|-------------|
| 1 | **Dashboard** | Приветствие, виджет портфеля (общая стоимость), активный баланс, быстрые действия, последние транзакции, новости |
| 2 | **Portfolio** | Список продуктов в портфеле по компаниям, количество юнитов, средняя цена, текущая стоимость |
| 3 | **Marketplace** | Каталог доступных продуктов (IPI AG, Immo-Pro-Invest, CBS Home Franchise), карточки с ценой/описанием |
| 4 | **Product Detail** | Детали продукта: описание, цена за юнит, доступные юниты, варианты покупки (мгновенная / рассрочка) |
| 5 | **Purchase Modal** | Выбор количества юнитов, итоговая сумма, подтверждение покупки |
| 6 | **Installment Setup** | Выбор плана рассрочки (6/12 мес), расписание платежей, первый платёж |
| 7 | **Balance** | Active balance (пополнения, депозиты), история транзакций, пополнить через crypto |
| 8 | **Documents** | Список документов (инвестиционные соглашения, сертификаты), статус подписания |
| 9 | **Settings** | Профиль, язык, уведомления, заявка на роль агента |

## Tab Bar Navigation

| Tab | Icon | Screen |
|-----|------|--------|
| Главная | 🏠 | Dashboard |
| Портфель | 📊 | Portfolio |
| Маркет | 🛒 | Marketplace |
| Баланс | 💰 | Balance |
| Ещё | ⚙️ | Settings (with Documents link) |

## Interactions

| Element | Behavior |
|---------|----------|
| Tab bar items | Switch screens, yellow toast for tab |
| Dashboard portfolio widget → click | Navigate to Portfolio |
| Dashboard balance widget → click | Navigate to Balance |
| Dashboard transaction item → click | Toast endpoint "Детали транзакции" |
| Dashboard news item → click | Toast endpoint "Новость" |
| Portfolio company card → click | Toast endpoint "Детали по компании" |
| Marketplace product card → click | Navigate to Product Detail |
| Product "Купить" btn → click | Navigate to Purchase Modal |
| Product "Рассрочка" btn → click | Navigate to Installment Setup |
| Purchase confirm → click | Toast "Покупка выполнена" → endpoint |
| Installment confirm → click | Toast "Рассрочка оформлена" → endpoint |
| Balance "Пополнить" btn | Toast endpoint "Crypto deposit" |
| Balance transaction → click | Toast endpoint "Детали транзакции" |
| Documents item → click | Toast endpoint "Просмотр документа" |
| Settings "Стать агентом" → click | Toast endpoint "Заявка на роль агента" |
| Settings notification toggle | Toggle animation |

## Navigation Map Structure

```
Investor Shell
├── 🟡 Tab: Dashboard
│   ├── 🟢 Dashboard
│   │   ├── 🔴 Детали транзакции (endpoint)
│   │   └── 🔴 Новость (endpoint)
├── 🟡 Tab: Portfolio
│   ├── 🟢 Portfolio
│   │   └── 🔴 Детали по компании (endpoint)
├── 🟡 Tab: Marketplace
│   ├── 🟢 Marketplace
│   │   ├── 🟢 Product Detail
│   │   │   ├── 🟢 Purchase Modal
│   │   │   │   └── 🔴 Покупка выполнена (endpoint)
│   │   │   └── 🟢 Installment Setup
│   │   │       └── 🔴 Рассрочка оформлена (endpoint)
├── 🟡 Tab: Balance
│   ├── 🟢 Balance
│   │   ├── 🔴 Crypto deposit (endpoint)
│   │   └── 🔴 Детали транзакции (endpoint)
├── 🟡 Tab: Settings
│   ├── 🟢 Settings
│   │   ├── 🟢 Documents
│   │   │   └── 🔴 Просмотр документа (endpoint)
│   │   └── 🔴 Заявка на роль агента (endpoint)
```

## Data Plan

| Entity | Fields | Count |
|--------|--------|-------|
| User | name, avatar, role (Investor), since date | 1 |
| Portfolio summary | total value (EUR), change %, products count | 1 |
| Active balance | confirmed EUR, frozen EUR | 1 |
| Products | name, company, price/unit EUR, units available, description, image | 3 |
| Portfolio holdings | company, units, avg price, current value, profit% | 2 |
| Transactions | id, type, amount EUR, status, date | 5 |
| Installment plans | 6mo and 12mo schedules | 2 |
| Documents | title, type, status, date | 4 |
| News items | title, date, snippet | 3 |

### Products Data

| Product | Company | Price/Unit | Available |
|---------|---------|-----------|-----------|
| IPI AG Shares | IPI AG | €1.00 | 500 000 |
| Immo-Pro-Invest | Immo-Pro-Invest GmbH | €1.00 | 300 000 |
| CBS Home Franchise | CBS Home AG | €1.00 | 200 000 |

### Installment Plans

| Plan | Duration | Schedule |
|------|----------|----------|
| Standard | 6 мес | 10% × 5 + 50% финальный |
| Extended | 12 мес | 5% × 11 + 45% финальный |

## Notes

- EUR (€) as currency, not rubles
- Dual ledger: Active balance (deposits) shown separately from passive (will be in Agent shell)
- Frozen amounts shown with ❄️ indicator
- KYC approved state assumed (investor already onboarded)
- Tab bar with 5 tabs at bottom (sticky)
- Realistic transaction history with statuses
