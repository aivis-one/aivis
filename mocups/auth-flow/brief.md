# Brief: CBS HOME — Auth Flow

## Overview

| Field | Value |
|-------|-------|
| Type | Auth / Onboarding flow |
| Primary | Phone (390px) |
| Devices | Phone, Tablet, Desktop |
| Brand | CBS HOME (Teal #1A6B6A + Orange #E8651A, Montserrat) |
| Language | RU primary |

## Screens

| # | Screen | Description |
|---|--------|-------------|
| 1 | **Login** | Email + пароль, кнопка "Войти", ссылка "Регистрация", опция Telegram login |
| 2 | **Register** | Email, пароль, подтверждение пароля, согласие с условиями, кнопка "Создать аккаунт" |
| 3 | **Email Verification** | Иконка письма, текст "Проверьте почту", поле ввода кода / ссылка "Отправить повторно" |
| 4 | **Role Selection** | Карточки ролей: Инвестор, Агент, Компания. Описание каждой роли, кнопка выбора |
| 5 | **Profile Setup** | Имя, фамилия, телефон, страна (select), язык. Кнопка "Продолжить" |
| 6 | **KYC Status** | Статус верификации: ожидание / одобрено / отклонено. Кнопка "Начать верификацию" (SumSub) |
| 7 | **Document Signing** | Список документов для подписи, чекбоксы согласия, кнопка "Подписать" |

## Interactions

| Element | Behavior |
|---------|----------|
| Login form → submit | Toast "Вход выполнен" → переход на Role Selection |
| Register form → submit | Toast "Аккаунт создан" → переход на Email Verification |
| Email verify → confirm | Toast "Email подтверждён" → переход на Profile Setup |
| Resend code button | Toast "Код отправлен повторно" |
| Role cards → click | Подсветка выбранной роли, кнопка "Продолжить" активируется |
| Role confirm → click | Toast "Роль выбрана: {role}" → переход на KYC Status |
| Profile form → submit | Toast "Профиль сохранён" → переход на Role Selection |
| KYC → начать | Toast "📌 SumSub — внешний сервис верификации" (endpoint) |
| KYC approved state | Зелёный статус, кнопка → Document Signing |
| Document checkboxes | Все отмечены → кнопка "Подписать" активна |
| Document sign → click | Toast "Документы подписаны" → Toast "📌 Onboarding завершён — переход в кабинет" (endpoint) |
| Telegram login button | Toast "📌 Telegram WebApp — внешний сервис" (endpoint) |

## Navigation Map Structure

```
Auth Flow
├── 🟢 Login
│   ├── 🟢 Register
│   │   └── 🟢 Email Verification
│   └── 🔴 Telegram Login (endpoint)
├── 🟢 Profile Setup
├── 🟢 Role Selection
├── 🟢 KYC Status
│   └── 🔴 SumSub Verification (endpoint)
└── 🟢 Document Signing
    └── 🔴 Onboarding Complete (endpoint)
```

## Data Plan

| Entity | Fields | Count |
|--------|--------|-------|
| User credentials | email, password | 1 prefilled example |
| Roles | name, icon, description, features list | 3 (Investor, Agent, Company) |
| Profile fields | firstName, lastName, phone, country, language | 1 prefilled |
| KYC statuses | pending, approved, rejected (показываем approved) | 3 states |
| Documents | title, description, required flag | 3 documents |
| Countries | name | 5 options (Deutschland, Schweiz, Österreich, Russland, Other) |
| Languages | code, label | 4 (EN, RU, DE, AR) |

### Role Descriptions

| Role | Icon | Title | Description |
|------|------|-------|-------------|
| Investor | 📊 | Инвестор | Покупка продуктов, портфель, рассрочки, активный баланс |
| Agent | 🤝 | Агент | Все возможности инвестора + реферальные ссылки, комиссии L1/L2/L3, лидерборд |
| Company | 🏢 | Компания | Размещение продуктов, аналитика продаж, управление доходами |

### Documents for Signing

| # | Document | Required |
|---|----------|----------|
| 1 | Пользовательское соглашение cbshome.org | Да |
| 2 | Политика конфиденциальности | Да |
| 3 | Согласие на обработку персональных данных | Да |

## Notes

- Стиль CBS HOME: инженерный, точный, teal/orange палитра
- Шрифт: Montserrat (web)
- Все формы с валидацией (фокус + ошибка)
- Telegram login — endpoint (внешний сервис, не мокапируется внутри)
- SumSub KYC — endpoint (внешний сервис)
- Финальный экран onboarding — endpoint (переход в основной кабинет)
- Поддержка dark mode через CSS variables
- Данные в EUR (€) — европейская платформа, не рубли
