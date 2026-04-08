# CBSHOME — Техническое задание: Frontend

**Версия:** 1.0
**Дата:** 8 апреля 2026
**Статус:** Draft
**Репозиторий:** https://github.com/aivis-one/cbshome

**Зависимости (читать перед работой):**
- `CBSHOME-Design-Document.md` — Конституция v1.5
- `CBSHOME-Backend.md` — Backend ТЗ v1.5
- `CBSHOME-Financial-System.md` — финансовая логика
- `CBSHOME-State-Machines.md` — переходы статусов
- `CBSHOME-Installment.md` — механика рассрочки
- `mockups/` — UI-прототипы (auth-flow, investor-shell, agent-shell, company-shell, staff-shell)
- `mockups/project-map/manifest.yaml` — screen→endpoint маппинг

---

## 1. Обзор

### 1.1. Цель

Фронтенд CBSHOME — единое SPA-приложение с ролевым роутингом, работающее в двух режимах:

1. **Standalone PWA** — основной канал. Устанавливается на Home Screen, авторизация через email/password
2. **Telegram WebApp** — второй канал. Открывается внутри Telegram, авторизация через initData

Оба режима используют один и тот же код. Различия инкапсулированы в платформенной абстракции.

### 1.2. Критерии готовности MVP (Frontend)

| Критерий | Описание |
|----------|----------|
| Auth | Email + Telegram авторизация работает |
| KYC | Юзер проходит KYC-заглушку |
| Витрина | Инвестор видит продукты, может фильтровать |
| Покупка | Инвестор покупает продукт (инстант + рассрочка) |
| Баланс | Пополнение через крипто, отображение active balance |
| Agent Hub | Агент создаёт реферальные ссылки, видит комиссии |
| Staff | KYC-очередь, управление юзерами, аватаринг |
| i18n | Четыре языка (en/ru/de/ar), включая RTL |
| PWA | Приложение добавляется на Home Screen |

### 1.3. Вне scope MVP (Frontend)

- Офлайн-режим (кроме заглушки "Нет подключения")
- Push-уведомления через Service Worker
- Анимации переходов между экранами (Phase F9)
- Банковские платежи (только крипто в MVP)

### 1.4. Четыре роли — одно приложение

Приложение определяет роль из `GET /api/v1/users/me` и показывает соответствующий интерфейс:

| Роль | Shell | Tab Bar | Доступ |
|------|-------|---------|--------|
| `investor` | InvestorShell | Главная, Портфель, Баланс, Документы, Настройки | Витрина, покупка, рассрочка, active balance |
| `agent` | AgentShell | Главная, Hub, Комиссии, Пассив, Настройки | Всё инвесторское + реферальные ссылки, комиссии L1/L2/L3, лидерборд |
| `company` | CompanyShell | Главная, Продукты, Аналитика, Настройки | Управление продуктами, аналитика продаж, passive balance |
| `staff` | StaffShell | Главная, Юзеры, KYC, Платежи, Ещё | Управление всеми пользователями, KYC-очередь, аватаринг |

Agent имеет доступ ко всем инвесторским экранам (он тоже инвестор). Переключение через навигацию, не отдельное приложение.

---

## 2. Технологический стек

| Компонент | Технология | Версия | Назначение |
|-----------|-----------|--------|------------|
| Фреймворк | Vue 3 | latest | Composition API, SFC |
| Язык | TypeScript | 5.x | Строгая типизация |
| Сборка | Vite | latest | HMR, быстрая сборка |
| Роутинг | Vue Router | 4.x | Role-based guards |
| Стейт | Pinia | latest | Реактивные хранилища |
| HTTP | Fetch (обёртка) | native | Запросы к API (CORS → api.cbshome.org) |
| i18n | vue-i18n | latest | en/ru/de/ar + RTL |
| PWA | vite-plugin-pwa | latest | Manifest + Service Worker |
| Стили | Свой CSS | — | Дизайн-система из мокапов (variables.css v1.8.0) |
| Линтинг | ESLint + Prettier | latest | Качество кода |
| Платформа | Telegram WebApp SDK | latest | initData, тема, haptic |
| Шрифты | Montserrat + Noto Sans Arabic | Google Fonts | LTR + RTL |

### 2.1. Почему CORS, а не proxy

Фронтенд (`cbshome.org`) и API (`api.cbshome.org`) — разные домены. Запросы идут напрямую на `api.cbshome.org` с CORS.

Причина: при переходе на микросервисы API Gateway будет за `api.cbshome.org`, фронтенд не поменяется.

Бэкенд: `CORSMiddleware` с whitelist `["https://cbshome.org"]`. Credentials allowed.

### 2.2. Token storage

| Среда | Storage | Причина |
|-------|---------|---------|
| Standalone (email auth) | `localStorage` | Закрытие вкладки не должно разлогинивать |
| Telegram WebApp | `sessionStorage` | Telegram закрывает вкладку при выходе — sessionStorage очищается автоматически |

Платформенная абстракция определяет какой storage использовать.

---

## 3. Архитектура

### 3.1. Структура проекта

```
cbshome/                              -- GitHub repo root (существует)
├── backend/                          -- Бэкенд (существует)
├── frontend/                         -- Фронтенд (новый)
│   ├── src/
│   │   ├── api/                      -- HTTP-клиент + типизированные методы
│   │   │   ├── client.ts             -- Base fetch обёртка, CORS, interceptors
│   │   │   ├── types.ts              -- TypeScript-интерфейсы (все типы API)
│   │   │   ├── utils.ts              -- Shared helpers (buildQuery)
│   │   │   ├── auth.ts               -- POST /auth/email/*, POST /auth/telegram
│   │   │   ├── users.ts              -- GET/PATCH /users/me
│   │   │   ├── kyc.ts                -- KYC submit, status
│   │   │   ├── documents.ts          -- Documents list, sign
│   │   │   ├── products.ts           -- Products list, detail
│   │   │   ├── purchases.ts          -- Purchase, installment
│   │   │   ├── payments.ts           -- Crypto address, history
│   │   │   ├── referrals.ts          -- Referral links, stats
│   │   │   ├── commissions.ts        -- Commission history, leaderboard
│   │   │   ├── companies.ts          -- Company profile, products
│   │   │   ├── withdrawals.ts        -- Withdrawal request, history
│   │   │   ├── notifications.ts      -- Notification list, read
│   │   │   ├── posts.ts              -- Posts feed, dismiss
│   │   │   └── admin.ts              -- Staff endpoints
│   │   │
│   │   ├── components/               -- Переиспользуемые UI-компоненты
│   │   │   ├── ui/                   -- Примитивы: CButton, CInput, CCard...
│   │   │   │   ├── icons/            -- SVG-иконки из мокапов (Vue-компоненты)
│   │   │   │   └── index.ts          -- Barrel export
│   │   │   ├── layout/               -- CHeader, CTabBar, InvestorShell, AgentShell...
│   │   │   └── shared/               -- ProductCard, PaymentCard, KYCBanner...
│   │   │
│   │   ├── views/                    -- Экраны (по ролям)
│   │   │   ├── auth/                 -- LoginView, RegisterView, VerifyView...
│   │   │   ├── investor/             -- Dashboard, Portfolio, Market, Product...
│   │   │   ├── agent/                -- Dashboard, Hub, Referrals, Commissions...
│   │   │   ├── company/              -- Dashboard, Products, Analytics...
│   │   │   └── staff/                -- Dashboard, Users, KYC, Payments...
│   │   │
│   │   ├── stores/                   -- Pinia хранилища
│   │   │   ├── auth.ts               -- user, token, role, isAuthenticated
│   │   │   ├── products.ts           -- list, filters, selected
│   │   │   ├── portfolio.ts          -- investor portfolio
│   │   │   ├── balance.ts            -- active_balance, passive_balance
│   │   │   ├── agent.ts              -- referrals, commissions, leaderboard
│   │   │   ├── company.ts            -- company profile, products
│   │   │   └── notifications.ts      -- unread count, list
│   │   │
│   │   ├── router/                   -- Vue Router
│   │   │   ├── index.ts              -- Маршруты + guards
│   │   │   ├── guards.ts             -- Auth guard, role guard
│   │   │   └── tabs.ts               -- INVESTOR_TABS, AGENT_TABS, COMPANY_TABS, STAFF_TABS
│   │   │
│   │   ├── platform/                 -- Абстракция Telegram / Standalone
│   │   │   ├── index.ts              -- Автодетект среды, экспорт
│   │   │   ├── telegram.ts           -- Реальный Telegram WebApp SDK
│   │   │   ├── standalone.ts         -- Полноценная standalone-реализация
│   │   │   └── types.ts              -- Общий интерфейс Platform
│   │   │
│   │   ├── composables/              -- Vue composables
│   │   │   ├── useAuth.ts            -- Login/logout flow + waitUntilReady()
│   │   │   ├── usePagination.ts      -- Пагинация + infinite scroll
│   │   │   ├── useToast.ts           -- Всплывающие уведомления
│   │   │   └── useForm.ts            -- Валидация форм
│   │   │
│   │   ├── i18n/                     -- Локализация
│   │   │   ├── index.ts              -- vue-i18n setup, locale detection
│   │   │   └── locales/
│   │   │       ├── en.json           -- English (base)
│   │   │       ├── ru.json           -- Русский
│   │   │       ├── de.json           -- Deutsch
│   │   │       └── ar.json           -- العربية (RTL)
│   │   │
│   │   ├── styles/                   -- Глобальные стили
│   │   │   ├── variables.css         -- Дизайн-токены (из mockups/css/variables.css 1:1)
│   │   │   ├── global.css            -- Reset, typography, Google Fonts, RTL
│   │   │   └── telegram.css          -- Telegram-specific overrides (если нужно)
│   │   │
│   │   ├── utils/                    -- Утилиты
│   │   │   ├── format.ts             -- Форматирование дат, валют, чисел
│   │   │   ├── currency.ts           -- usdStringToCents(), centsToUsdString()
│   │   │   ├── validation.ts         -- Общие валидаторы форм
│   │   │   ├── constants.ts          -- Статусы, роли, магические числа
│   │   │   └── staffHelpers.ts       -- Хелперы для staff-вью
│   │   │
│   │   ├── App.vue                   -- Корневой компонент
│   │   └── main.ts                   -- Точка входа: createApp, router, pinia, i18n
│   │
│   ├── public/
│   │   ├── manifest.json             -- PWA-манифест
│   │   ├── icons/                    -- Иконки приложения (192, 512)
│   │   └── assets/
│   │       └── logo.svg              -- Логотип из мокапов
│   │
│   ├── index.html                    -- SPA entry point + Telegram SDK script
│   ├── vite.config.ts                -- Vite + PWA plugin config
│   ├── tsconfig.json                 -- TypeScript config
│   ├── eslint.config.js              -- ESLint flat config
│   ├── .prettierrc                   -- Prettier config
│   ├── package.json                  -- Dependencies
│   ├── .env.example                  -- VITE_API_BASE_URL, VITE_TELEGRAM_BOT_URL
│   ├── .gitignore                    -- node_modules, dist
│   ├── Dockerfile                    -- Multi-stage: node build → nginx
│   └── README.md                     -- Инструкция
│
├── mockups/                          -- UI-прототипы (существуют, read-only reference)
├── docker-compose.yml                -- Весь стек (backend + frontend + postgres + redis)
├── scripts/
│   └── install_cbshome.sh            -- Целевой артефакт поставки
└── CBSHOME-Frontend.md               -- ЭТОТ ДОКУМЕНТ
```

### 3.2. Интеграция с бэкендом

```
Browser / Telegram
      │
      ▼
   Nginx (cbshome.org)
      │
      └── /*         → frontend:3000 (Vue SPA)

   Nginx (api.cbshome.org)
      │
      └── /*         → app:8000 (FastAPI)

Фронтенд → CORS → api.cbshome.org/api/v1/*
```

Два домена, два Nginx-блока. CORS `CORSMiddleware` на бэкенде с whitelist `["https://cbshome.org"]`.

### 3.3. Платформенная абстракция

```typescript
// src/platform/types.ts
interface Platform {
  name: 'telegram' | 'standalone'
  init(): Promise<void>
  getInitData(): string | null         // Telegram initData или null
  getTheme(): 'light' | 'dark'
  hapticFeedback(type: string): void
  showBackButton(cb: () => void): void
  hideBackButton(): void
  close(): void
  getStorageDriver(): 'localStorage' | 'sessionStorage'
}
```

Telegram WebApp обнаруживается по наличию `window.Telegram?.WebApp`. Если нет — standalone-режим.

`getStorageDriver()` — определяет storage для token: `sessionStorage` в Telegram, `localStorage` в standalone.

### 3.4. Соглашения

**Именование файлов:**
- Компоненты: PascalCase (`ProductCard.vue`, `CButton.vue`)
- Утилиты, stores, api: camelCase (`auth.ts`, `usePagination.ts`)
- Стили: kebab-case (`variables.css`, `global.css`)
- Локализация: kebab-case (`en.json`, `ar.json`)

**Префикс C для UI-примитивов:**
- `CButton`, `CInput`, `CCard` — собственные компоненты дизайн-системы
- Без префикса — доменные компоненты (`ProductCard`, `KYCBanner`)

**Комментарии:** на английском (как в бэкенде).

**Валюта:** все суммы в USD cents (integer). Отображение через `formatMoney()`.

**i18n:** все строки через `$t('key')`. Хардкод текста в шаблонах запрещён.

---

## 4. Фазы разработки

---

## PHASE F0: Инфраструктура

### F0.1: Инициализация проекта

**Цель:** Проект собирается, деплоится на VPS, пустая страница открывается.

**Задачи:**
- [ ] package.json с TypeScript, Vue Router, Pinia, vue-i18n
- [ ] Структура папок (src/api, components, views, stores, router, platform, styles, composables, utils, i18n)
- [ ] ESLint flat config + Prettier (единый стиль кода)
- [ ] tsconfig.json — strict mode, path aliases (`@/` → `src/`)
- [ ] vite.config.ts — base path, env переменные
- [ ] .env.example (`VITE_API_BASE_URL=https://api.cbshome.org`, `VITE_TELEGRAM_BOT_URL=...`)
- [ ] .gitignore (node_modules, dist, .env)
- [ ] README.md (команды: install, dev, build, lint)

**Результат:**
```
frontend/
├── src/
│   ├── App.vue                -- Корневой компонент (<RouterView />)
│   ├── main.ts                -- createApp + router + pinia + i18n + стили
│   ├── router/
│   │   └── index.ts           -- / → HomeView, catch-all → /
│   ├── views/
│   │   ├── HomeView.vue       -- Плейсхолдер (лого + "CBS HOME" + v0.1.0)
│   │   ├── auth/.gitkeep
│   │   ├── investor/.gitkeep
│   │   ├── agent/.gitkeep
│   │   ├── company/.gitkeep
│   │   └── staff/.gitkeep
│   ├── styles/
│   │   ├── variables.css      -- Дизайн-токены из mockups/css/variables.css (1:1)
│   │   └── global.css         -- CSS reset + typography + Google Fonts + RTL base
│   ├── i18n/
│   │   ├── index.ts           -- vue-i18n setup
│   │   └── locales/
│   │       ├── en.json        -- {}
│   │       ├── ru.json        -- {}
│   │       ├── de.json        -- {}
│   │       └── ar.json        -- {}
│   ├── api/.gitkeep
│   ├── components/{ui,layout,shared}/.gitkeep
│   ├── stores/.gitkeep
│   ├── platform/.gitkeep
│   ├── composables/.gitkeep
│   └── utils/.gitkeep
├── public/
│   ├── icons/favicon.svg
│   └── assets/logo.svg
├── index.html                 -- Telegram SDK script + PWA meta-теги
├── vite.config.ts
├── tsconfig.json
├── eslint.config.js
├── .prettierrc
├── package.json
├── package-lock.json          -- Для детерминированных билдов (npm ci)
├── env.d.ts                   -- TypeScript декларации для .vue и Vite env
├── .env.example
├── .gitignore
└── README.md
```

**Критерий готовности:** `npm run build` проходит, `npm run lint` без ошибок.

---

### F0.2: Дизайн-система (перенос из мокапов)

**Цель:** CSS-переменные и базовые стили из мокапов перенесены в проект. Тёмная тема работает.

**Задачи:**
- [ ] src/styles/variables.css — полный перенос из mockups/css/variables.css v1.8.0:
  - Orange Triad: `--o-primary: #cc3203`, `--o-accent: #E8651A`, `--o-light: #EFB44C`
  - Teal System: `--t-500` → `--t-950`, tints
  - Semantic aliases: `--primary`, `--accent`, `--bg`, `--text`, `--border`
  - Shadows: `--shadow-sm` → `--shadow-xl`, `--shadow-focus`
  - Spacing: 8px base system (`--space-xs` → `--space-4xl`)
  - Radius: `--radius-sm` (4px) → `--radius-full` (9999px)
  - `[data-theme="dark"]` — полный набор dark-переменных
  - `@media (prefers-color-scheme: dark)` — system preference fallback
- [ ] src/styles/global.css:
  - CSS reset
  - Google Fonts: `Montserrat:wght@400;500;600;700;800` + `Noto+Sans+Arabic:wght@400;500;600;700`
  - Base typography: `font-family: var(--font)` (`'Montserrat', system-ui, sans-serif`)
  - RTL base: `[dir="rtl"] { font-family: 'Noto Sans Arabic', 'Montserrat', sans-serif; }`
  - Scrollbar стилизация
- [ ] main.ts — импорт стилей (variables.css первым, потом global.css)
- [ ] Theme detection: initial script в index.html (как в мокапах — `localStorage.getItem('cbs-theme')`)

**Критерий готовности:** HomeView.vue использует CSS-переменные. Тёмная тема переключается через `[data-theme="dark"]` на `<html>`.

---

### F0.3: Docker + деплой на VPS

**Цель:** Фронтенд деплоится через `cbshome update`, доступен по HTTPS.

**Задачи:**
- [ ] frontend/Dockerfile (multi-stage: node:22-alpine build → nginx:alpine serve)
- [ ] frontend/nginx.conf (внутренний nginx: SPA fallback, gzip, кеш assets, порт 3000)
- [ ] frontend/.dockerignore
- [ ] docker-compose.yml — раскомментировать сервис `frontend`:
  - build: ./frontend, порт 127.0.0.1:3000:3000
  - depends_on: app (condition: service_healthy)
  - healthcheck: `wget -q --spider http://localhost:3000/`
- [ ] Nginx на хосте: `cbshome.org/*` → frontend:3000
- [ ] install_cbshome.sh — обновить: два upstream в nginx, `cbshome update` собирает оба сервиса

**Docker-сервисы (после F0.3):**
```
cbshome-app        → 127.0.0.1:8000  (FastAPI)
cbshome-frontend   → 127.0.0.1:3000  (Nginx + Vue SPA)
cbshome-postgres   → internal only
cbshome-redis      → internal only
```

**Маршрутизация (Nginx на хосте):**
```
https://cbshome.org/*             → cbshome-frontend:3000
https://api.cbshome.org/*         → cbshome-app:8000
```

**Критерий готовности:** `curl https://cbshome.org/` → HTML-страница с "CBS HOME".

---

### F0.4: PWA-заготовка

**Цель:** Приложение можно добавить на Home Screen.

**Задачи:**
- [ ] vite-plugin-pwa в vite.config.ts
- [ ] public/manifest.json (name: "CBS HOME", icons, theme_color: `#1A6B6A`, display: standalone)
- [ ] Иконки: 192x192, 512x512 (placeholder — заменим на брендинг заказчика)
- [ ] Service Worker: precache статики (только кеширование, без офлайна)
- [ ] meta-теги в index.html (apple-mobile-web-app-capable, viewport)

**Критерий готовности:** iPhone Safari → "Добавить на экран" → приложение открывается в standalone-режиме.

---

### F0.5: i18n каркас

**Цель:** vue-i18n настроен, переключение языков работает, RTL layout переключается.

**Задачи:**
- [ ] src/i18n/index.ts:
  - `createI18n()` с `legacy: false` (Composition API)
  - Locale detection: `localStorage.getItem('cbs-lang')` → `navigator.language` → `'en'` fallback
  - RTL detection: `locale === 'ar'` → `document.documentElement.dir = 'rtl'`, `document.documentElement.lang = 'ar'`
- [ ] src/i18n/locales/en.json — базовые ключи (app.name, common.save, common.cancel, common.loading...)
- [ ] src/i18n/locales/ru.json — русские переводы
- [ ] src/i18n/locales/de.json — немецкие переводы
- [ ] src/i18n/locales/ar.json — арабские переводы
- [ ] src/styles/global.css — RTL utilities:
  - `[dir="rtl"] .mr-auto { margin-right: 0; margin-left: auto; }`
  - `[dir="rtl"]` overrides для flex direction, text-align, padding/margin
- [ ] main.ts — `app.use(i18n)`

**Критерий готовности:** `$t('app.name')` рендерит "CBS HOME" на en, "ЦБС ХОУМ" на ru. Переключение на ar → layout зеркалится (RTL).

---

## PHASE F1: Auth + Платформа

### F1.1: Платформенная абстракция

**Цель:** Приложение знает, где запущено, и адаптируется.

**Задачи:**
- [ ] src/platform/types.ts — интерфейс Platform (9 методов, включая `getStorageDriver()`)
- [ ] src/platform/telegram.ts — обёртка над `window.Telegram.WebApp`:
  - `init()` — `WebApp.ready()`, `expand()`, `setHeaderColor('#1A6B6A')`, `setBackgroundColor('#F5F5F5')`
  - `getInitData()` — `WebApp.initData || null`
  - `getTheme()` — `WebApp.colorScheme || 'light'`
  - `hapticFeedback(style)` — `WebApp.HapticFeedback.impactOccurred(style)` в try/catch
  - `showBackButton(cb) / hideBackButton()` — `WebApp.BackButton` с onClick/offClick cleanup
  - `close()` — `WebApp.close()`
  - `getStorageDriver()` → `'sessionStorage'`
- [ ] src/platform/standalone.ts — полноценная standalone-реализация:
  - `getInitData()` → `null`
  - `hapticFeedback()` → `console.debug` (no-op)
  - `showBackButton(cb)` → `window.history.back()` fallback
  - `getStorageDriver()` → `'localStorage'`
- [ ] src/platform/index.ts — автодетект по `window.Telegram?.WebApp`, экспорт singleton `platform`

**Критерий готовности:** `platform.name === 'telegram'` в Telegram, `platform.name === 'standalone'` в браузере.

---

### F1.2: API-клиент

**Цель:** Типизированный HTTP-клиент для общения с бэкендом через CORS.

**Задачи:**
- [ ] src/api/client.ts:
  - `BASE_URL` из `import.meta.env.VITE_API_BASE_URL` (e.g. `https://api.cbshome.org`)
  - Обёртка над fetch: `get<T>()`, `post<T>()`, `patch<T>()`, `delete()`
  - `credentials: 'include'` — CORS with credentials
  - Авто-подстановка `Authorization: Bearer {token}` через модульный `_token`
  - Обработка 401 → callback `_onUnauthorized()` → auth store очищает сессию
  - Обработка 422 → парсинг массива ValidationError → join в строку
  - Обработка 204 → `return undefined as T`
  - Обработка сетевых ошибок → `ApiNetworkError`
  - `AbortController` + 15s timeout → `ApiTimeoutError`
  - `Accept-Language` header из текущей vue-i18n locale
- [ ] src/api/types.ts — TypeScript-интерфейсы:
  - `EmailRegisterRequest`, `EmailLoginRequest`, `TelegramAuthRequest`, `AuthResponse`
  - `UserResponse`, `UserUpdate`, `UserRole` (`investor | agent | company | staff | platform`)
  - `PaginatedResponse<T>` (generic)
  - `ApiError` (string | ValidationError[])

**Экспорты client.ts:**
```typescript
// Error classes
export class ApiResponseError extends Error { status: number; detail: string }
export class ApiNetworkError extends Error {}
export class ApiTimeoutError extends Error {}

// Token management (decoupled from Pinia)
export function setAuthToken(token: string | null): void
export function getAuthToken(): string | null

// 401 callback registration
export function setOnUnauthorized(cb: () => void): void

// HTTP methods
export const api = {
  get<T>(path: string): Promise<T>,
  post<T>(path: string, body?: unknown): Promise<T>,
  patch<T>(path: string, body?: unknown): Promise<T>,
  delete(path: string): Promise<void>,
}
```

**Зависимость от бэкенда:** Любой endpoint (для проверки CORS). Phase 1 ✅.

**Критерий готовности:** `api.get<UserResponse>('/api/v1/users/me')` возвращает типизированный ответ через CORS.

---

### F1.3: Auth flow (Email + Telegram)

**Цель:** Юзер авторизуется через email/password или через Telegram WebApp.

**Задачи:**
- [ ] src/stores/auth.ts (Pinia):
  - `user: UserResponse | null`
  - `token: string | null`
  - `loading: boolean`
  - `isAuthenticated: boolean` (computed: `!!token && !!user`)
  - `role: UserRole | null` (computed из `user.role ?? null` — `null` для неавторизованных)
  - `loginViaEmail(email, password)` — POST /auth/email/login → set token + user
  - `registerViaEmail(email, password)` — POST /auth/email/register → set token + user
  - `loginViaTelegram(initData)` — POST /auth/telegram → set token + user
  - `restoreSession()` — storage → set token → GET /users/me → set user
  - `fetchMe()` — GET /users/me (обновление профиля)
  - `logout()` — POST /auth/logout + очистка store
  - Персистенция token в storage (driver из `platform.getStorageDriver()`) под ключом `cbs_token`
  - Регистрация `_onUnauthorized` callback в API client
- [ ] src/composables/useAuth.ts — объединяет platform + auth store:
  - `initAuth()` — вызывается один раз из App.vue `onMounted`:
    1. `platform.init()`
    2. `authStore.restoreSession()` — если сохранённый токен валиден → готово
    3. Если Telegram: `platform.getInitData()` → `authStore.loginViaTelegram(initData)`
    4. Если standalone и нет токена → показать LoginView
  - Module-level refs `isReady`, `isStandalone`
  - `waitUntilReady()` — Promise.race(isReady watcher, 10s timeout) для router guards
- [ ] src/views/auth/LoginView.vue:
  - Email + password form
  - Кнопка "Войти"
  - Ссылка "Нет аккаунта? Зарегистрироваться"
  - Кнопка "Войти через Telegram" → deep link в Telegram бот
  - Loading state, error display
- [ ] src/views/auth/RegisterView.vue:
  - Email + password + password confirm
  - Кнопка "Зарегистрироваться"
  - Ссылка "Уже есть аккаунт? Войти"
- [ ] src/views/auth/LoadingView.vue — экран загрузки (лого + spinner)
- [ ] src/components/ui/CbsLogo.vue — SVG лого как shared компонент
- [ ] src/App.vue — auth-шлюз:
  - `!isReady` → LoadingView
  - `!isAuthenticated` → LoginView (standalone) или LoadingView (telegram, auto-login)
  - Authenticated → `<RouterView />`

**Зависимость от бэкенда:** POST /auth/email/register, POST /auth/email/login, POST /auth/telegram, POST /auth/logout, GET /users/me. Phase 1 ✅.

**Критерий готовности:** Юзер входит через email/password в браузере. Юзер автоматически авторизован в Telegram WebApp.

---

## PHASE F2: UI-компоненты + Layout

### F2.1: UI-компоненты (дизайн-система)

**Цель:** Библиотека переиспользуемых компонентов из мокапов.

**Задачи:**
- [ ] Компоненты из мокапов (1:1 перенос визуала):

**Примитивы (src/components/ui/):**

| Компонент | Пропсы | Описание |
|-----------|--------|----------|
| CButton | variant (primary/secondary/outline/danger/telegram), size, disabled, loading | Кнопка с состояниями. `btn-primary` = orange accent из мокапов |
| CInput | label, placeholder, error, type | Текстовое поле |
| CTextarea | label, placeholder, error, rows | Многострочное поле |
| CSelect | label, options, error | Выпадающий список |
| CCheckbox | label, checked | Чекбокс |
| CCard | — (slot) | Карточка-контейнер |
| CBadge | variant (success/warning/error/info), text | Статусный бейдж |
| CAvatar | name, url, size | Аватар (инициалы или фото) |
| CLoader | size | Спиннер загрузки |
| CDivider | — | Горизонтальный разделитель |
| CEmptyState | icon, title, description | Пустое состояние |
| CToast | — (composable) | Всплывающее уведомление |
| CStatCard | value, label, icon | Числовая карточка статистики |
| CProgressBar | value, max, color | Полоска прогресса |
| CModal | open, closeOnOverlay, showClose | Модальное окно |
| CIconBox | variant (teal/orange/green/yellow/red/blue/neutral) | Иконка в цветном квадрате (из mockups/css/components.css) |

**Layout-компоненты (src/components/layout/):**

| Компонент | Описание |
|-----------|----------|
| CHeader | Заголовок с кнопкой назад и action-слотом справа. Лого слева |
| CTabBar | Нижняя навигация (конфигурируется через `items` пропс). RTL-aware |
| InvestorShell | CHeader + `<slot>` + CTabBar (INVESTOR_TABS) |
| AgentShell | CHeader + `<slot>` + CTabBar (AGENT_TABS) |
| CompanyShell | CHeader + `<slot>` + CTabBar (COMPANY_TABS) |
| StaffShell | CHeader + `<slot>` + CTabBar (STAFF_TABS) |

Все layout-компоненты поддерживают RTL через `[dir="rtl"]` CSS selectors.

**Критерий готовности:** Все компоненты рендерятся корректно в обеих темах (light/dark) и в RTL.

---

### F2.2: Роутинг + Layout

**Цель:** Навигация между экранами, role-based доступ.

**Задачи:**
- [ ] src/router/index.ts — маршруты:

```
/                          → редирект по роли
/loading                   → LoadingView
/login                     → LoginView
/register                  → RegisterView

-- Auth flow (onboarding) --
/verify                    → VerifyEmailView
/onboarding/profile        → OnboardingProfileView
/onboarding/role           → OnboardingRoleView
/onboarding/kyc            → OnboardingKYCView
/onboarding/docs           → OnboardingDocsView

-- Investor --
/investor/dashboard        → InvestorDashboardView
/investor/portfolio        → PortfolioView
/investor/market           → MarketView
/investor/products/:id     → ProductDetailView
/investor/purchase/:id     → PurchaseView
/investor/installment/:id  → InstallmentView
/investor/balance          → BalanceView
/investor/docs             → InvestorDocsView
/investor/settings         → InvestorSettingsView

-- Agent (extends investor) --
/agent/dashboard           → AgentDashboardView
/agent/hub                 → AgentHubView
/agent/referrals           → ReferralsView
/agent/commissions         → CommissionsView
/agent/leaderboard         → LeaderboardView
/agent/passive             → PassiveBalanceView
/agent/settings            → AgentSettingsView
-- Agent также имеет доступ к /investor/* экранам (market, product, purchase...)

-- Company --
/company/dashboard         → CompanyDashboardView
/company/products          → CompanyProductsView
/company/products/:id      → CompanyProductEditView
/company/analytics         → CompanyAnalyticsView
/company/settings          → CompanySettingsView

-- Staff --
/staff/dashboard           → StaffDashboardView
/staff/users               → StaffUsersView
/staff/kyc                 → StaffKYCView
/staff/payments            → StaffPaymentsView
/staff/more                → StaffMoreView
/staff/agent-apps          → StaffAgentAppsView
/staff/avatar              → StaffAvatarView

/404                       → NotFoundView
```

- [ ] src/router/guards.ts:
  - `authGuard` — не авторизован → /login
  - `roleGuard('investor')` — role не investor/agent → redirect по роли
  - `roleGuard('agent')` — role не agent → redirect по роли
  - `roleGuard('company')` — role не company → redirect по роли
  - `roleGuard('staff')` — role не staff → redirect по роли
  - `onboardingGuard` — onboarding не завершён → /onboarding/*

- [ ] Tab bar конфигурация по ролям (src/router/tabs.ts):

| Роль | Таб 1 | Таб 2 | Таб 3 | Таб 4 | Таб 5 |
|------|-------|-------|-------|-------|-------|
| investor | Главная | Портфель | Баланс | Документы | Настройки |
| agent | Главная | Hub | Комиссии | Пассив | Настройки |
| company | Главная | Продукты | Аналитика | Настройки | — |
| staff | Главная | Юзеры | KYC | Платежи | Ещё |

**Зависимость от бэкенда:** GET /api/v1/users/me (role). Phase 1 ✅.

**Критерий готовности:** После логина юзер видит layout с tab bar по своей роли. Переходы между экранами работают. Чужие роли → redirect.

---

### F2.3: Onboarding flow

**Цель:** Новый пользователь проходит онбординг: верификация email → профиль → выбор роли → KYC → документы.

**Задачи:**
- [ ] src/views/auth/VerifyEmailView.vue:
  - Code input (6 цифр, из мокапа auth-flow/screen-verify)
  - POST /api/v1/auth/verify-email
  - Resend button с cooldown timer
- [ ] src/views/auth/OnboardingProfileView.vue:
  - Имя, фамилия, страна, телефон
  - PATCH /api/v1/users/me
- [ ] src/views/auth/OnboardingRoleView.vue:
  - Карточки ролей из мокапа auth-flow/screen-role: Investor, Agent, Company
  - Каждая карточка: иконка, название, описание, feature-чипы
  - PATCH /api/v1/users/me (role selection)
- [ ] src/views/auth/OnboardingKYCView.vue:
  - POST /api/v1/kyc/submit (заглушка)
  - Статус из GET /api/v1/kyc/status
- [ ] src/views/auth/OnboardingDocsView.vue:
  - Список документов для подписания
  - GET /api/v1/documents, POST /api/v1/documents/{id}/sign
- [ ] Onboarding guard: проверяет `user.credentials.onboarding.step` и редиректит на нужный шаг

**Зависимость от бэкенда:** POST /auth/verify-email (gap — нужна реализация), PATCH /users/me (Phase 1.3 ✅), KYC (Phase 2.1 ✅), Documents (Phase 2.2 ✅).

**Критерий готовности:** Новый юзер проходит полный онбординг от регистрации до готовности.

---

## PHASE F3: Staff

### F3.1: Дашборд + статистика

**Цель:** Staff видит ключевые метрики.

**Задачи:**
- [ ] src/views/staff/StaffDashboardView.vue:
  - GET /api/v1/staff/dashboard/stats
  - Карточки: users_count, pending_kyc, pending_payments, pending_agent_apps
  - CStatCard с CIconBox, алертовый баннер если pending_kyc > 0
  - Навигационные ссылки: в юзеры → /staff/users, в KYC → /staff/kyc

**Зависимость от бэкенда:** GET /api/v1/staff/dashboard/stats. Phase 3.3 ✅.

**Критерий готовности:** Staff видит статистику.

---

### F3.2: Управление юзерами

**Цель:** Staff видит и управляет пользователями.

**Задачи:**
- [ ] src/views/staff/StaffUsersView.vue:
  - GET /api/v1/staff/users — список юзеров с пагинацией
  - Фильтры: role, kyc_status, search (имя/email)
  - Каждый item: аватар, имя, email, роль (CBadge), kyc_status, дата регистрации
  - Клик → detail sheet или modal:
    - PATCH /api/v1/staff/users/{id}/block — блокировка
    - POST /api/v1/staff/users/{id}/promote — промоция в staff (с permission matrix)
  - Platform user не отображается в списке (скрыт)

**Зависимость от бэкенда:** GET /api/v1/staff/users, PATCH /staff/users/{id}/block, POST /staff/users/{id}/promote. Phase 3.1 ✅.

**Критерий готовности:** Staff видит всех юзеров, может заблокировать и промоутить.

---

### F3.3: KYC-очередь

**Цель:** Staff одобряет и отклоняет KYC-заявки.

**Задачи:**
- [ ] src/views/staff/StaffKYCView.vue:
  - GET /api/v1/staff/kyc/queue — очередь (pending first)
  - Каждый item: аватар, имя, дата подачи
  - Действия:
    - POST /api/v1/staff/kyc/{id}/approve — одобрить
    - POST /api/v1/staff/kyc/{id}/reject — отклонить (с полем причины)
  - Double-submit guard
  - Toast: "KYC одобрен" / "KYC отклонён"
  - `error` ref + CEmptyState с кнопкой "Повторить" при ошибке загрузки

**Зависимость от бэкенда:** Staff KYC endpoints. Phase 3.3 ✅.

**Критерий готовности:** Staff одобряет и отклоняет KYC-заявки.

---

### F3.4: Платежи + Аватаринг

**Цель:** Staff видит историю платежей и может входить под другим пользователем.

**Задачи:**
- [ ] src/views/staff/StaffPaymentsView.vue:
  - GET /api/v1/payments/history — список платежей
  - Фильтры: status, user, дата
  - Каждый item: сумма, тип (crypto/bank), статус (CBadge), дата
  - Staff-действия (Sprint 5.3, 6.3 — когда бэкенд готов):
    - POST /api/v1/staff/payments/{id}/reverse — chargeback
    - POST /api/v1/staff/withdrawals/{id}/confirm — одобрить вывод
    - POST /api/v1/staff/withdrawals/{id}/reject — отклонить вывод
- [ ] src/views/staff/StaffMoreView.vue:
  - Профиль staff (аватар, имя, роль)
  - Навигация: Agent Apps → /staff/agent-apps, Avatar → /staff/avatar
- [ ] src/views/staff/StaffAvatarView.vue:
  - POST /api/v1/staff/avatar/start — начать сессию (user_id input)
  - POST /api/v1/staff/avatar/end — завершить сессию
  - Баннер "Вы работаете под пользователем X" когда avatar active
- [ ] src/views/staff/StaffAgentAppsView.vue:
  - GET /api/v1/staff/agent-applications — список заявок
  - POST /api/v1/staff/agent-applications/{id}/approve — одобрить
  - POST /api/v1/staff/agent-applications/{id}/reject — отклонить (с причиной)
  - **Зависимость:** Sprint 7.1 (не реализован) — показывать CEmptyState до готовности бэкенда

**Зависимость от бэкенда:** Payments history (Phase 5.2 ✅), Avatar (Phase 3.2 ✅), Agent apps (Phase 7.1 — план).

**Критерий готовности:** Staff видит платежи, может аватариться. Agent apps — заглушка до Sprint 7.1.

---

## PHASE F4: Investor

### F4.1: Витрина продуктов

**Цель:** Инвестор видит доступные продукты.

**Задачи:**
- [ ] src/stores/products.ts (Pinia):
  - `products: PublicProductResponse[]`
  - `total: number`
  - `filters: { company_id? }`
  - `loading: boolean`
  - `fetchProducts()` — GET /api/v1/products с фильтрами и пагинацией
- [ ] src/api/products.ts — типизированные методы API
- [ ] src/components/shared/ProductCard.vue:
  - Карточка продукта (из мокапа investor-shell/screen-market):
    - Обложка, название, компания
    - Цена за юнит, статус
    - Бейдж типа
  - Клик → /investor/products/:id
- [ ] src/views/investor/MarketView.vue:
  - Список продуктов
  - Фильтр по компании
  - Бесконечный скролл (usePagination)
- [ ] src/views/investor/ProductDetailView.vue:
  - GET /api/v1/products/{id}
  - Полная информация: описание, компания, цена, юниты, планы рассрочки
  - Кнопка "Купить" → /investor/purchase/:id
  - Кнопка "Рассрочка" → /investor/installment/:id
  - Документация компании, roadmap

**Зависимость от бэкенда:** GET /api/v1/products, GET /api/v1/products/{id}. Phase 4.2 ✅.

**Критерий готовности:** Инвестор видит витрину, открывает карточку продукта с полной информацией.

---

### F4.2: Покупка + Рассрочка

**Цель:** Инвестор покупает продукт (инстант или рассрочка).

**Задачи:**
- [ ] src/views/investor/PurchaseView.vue:
  - Подтверждение покупки: продукт, сумма, баланс
  - POST /api/v1/products/{id}/purchase
  - Обработка ошибок: недостаточно средств (→ предложить пополнить), KYC не пройден
  - Success: toast + redirect на портфель
- [ ] src/views/investor/InstallmentView.vue:
  - Выбор плана рассрочки из списка ProductInstallment
  - Отображение: число траншей, сумма каждого, бонусные юниты
  - POST /api/v1/products/{id}/installment (body: `{product_installment_id}`)
  - GET /api/v1/installments/me — мои планы рассрочки
  - Детали плана: транши с датами и статусами

**Зависимость от бэкенда:** Purchase (Sprint 6.1 — план), Installments (Sprint 6.2 — план).

**Критерий готовности:** Инвестор покупает продукт и оформляет рассрочку.

---

### F4.3: Баланс + Пополнение

**Цель:** Инвестор видит active balance и пополняет его криптой.

**Задачи:**
- [ ] src/stores/balance.ts (Pinia):
  - `active_confirmed: number` (cents)
  - `active_frozen: number` (cents)
  - `refresh()` — GET /api/v1/ledgers/active/balance (или из users/me)
- [ ] src/views/investor/BalanceView.vue:
  - Active balance: confirmed (зелёный) + frozen (серый, если > 0)
  - Кнопка "Пополнить" → крипто-адрес
  - Сеть: TRC-20 USDT (из мокапа investor-shell/screen-balance)
  - GET /api/v1/payments/crypto-address/{network} → QR-код + адрес + кнопка "Скопировать"
  - История транзакций: GET /api/v1/transactions (когда Sprint 6.4 готов)
  - Каждая транзакция: сумма, тип, статус (CBadge), дата

**Зависимость от бэкенда:** Crypto address (Sprint 5.2 ✅), Transactions (Sprint 6.4 — план).

**Критерий готовности:** Инвестор видит баланс, получает крипто-адрес для пополнения.

---

### F4.4: Портфель + Дашборд

**Цель:** Инвестор видит свой портфель и главную страницу.

**Задачи:**
- [ ] src/views/investor/InvestorDashboardView.vue:
  - Приветствие с именем
  - Виджет портфеля: общая стоимость, количество продуктов
  - Виджет баланса: active balance
  - Последние новости (GET /api/v1/posts — когда Sprint 9.1 готов)
  - Quick actions: Пополнить, Витрина
- [ ] src/views/investor/PortfolioView.vue:
  - GET /api/v1/portfolio/me — список позиций по компаниям
  - Каждая позиция: компания, количество юнитов, текущая стоимость
  - Клик → детали по компании
- [ ] src/views/investor/InvestorDocsView.vue:
  - GET /api/v1/documents — список документов
  - Статус подписания (signed / pending)
  - POST /api/v1/documents/{id}/sign
- [ ] src/views/investor/InvestorSettingsView.vue:
  - Профиль: аватар, имя, email, роль
  - PATCH /api/v1/users/me — редактирование
  - Переключение языка (en/ru/de/ar)
  - Переключение темы (light/dark)
  - Кнопка "Стать агентом" (если роль = investor, KYC approved)

**Зависимость от бэкенда:** Dashboard/Portfolio (Sprint 9.2 — план), Documents (Phase 2.2 ✅), Users (Phase 1.3 ✅).

**Критерий готовности:** Инвестор видит дашборд, портфель, документы, настройки. Экраны без готового бэкенда показывают заглушки.

---

## PHASE F5: Company

### F5.1: Дашборд компании

**Цель:** Компания видит свою статистику.

**Задачи:**
- [ ] src/views/company/CompanyDashboardView.vue:
  - Название компании, статус
  - Виджеты: количество продуктов, общие продажи, passive balance
  - Последние транзакции (когда Sprint 6.4 готов)

**Зависимость от бэкенда:** Dashboard (Sprint 9.2 — план), Transactions (Sprint 6.4 — план).

**Критерий готовности:** Компания видит дашборд с метриками.

---

### F5.2: Управление продуктами

**Цель:** Компания видит свои продукты (readonly — управление через Staff).

**Задачи:**
- [ ] src/views/company/CompanyProductsView.vue:
  - GET /api/v1/products?company_id={my_company_id}
  - Список продуктов компании: название, статус, цена, sold_units
- [ ] src/views/company/CompanyProductEditView.vue:
  - GET /api/v1/products/{id} — детали
  - Readonly view (редактирование — через Staff endpoints)
  - Планы рассрочки, roadmap
- [ ] src/views/company/CompanyAnalyticsView.vue:
  - GET /api/v1/portfolio/me/company/{id} — аналитика продаж
  - GET /api/v1/agent/leaderboard — топ агентов по компании
- [ ] src/views/company/CompanySettingsView.vue:
  - GET /api/v1/companies/{id} — профиль компании
  - Readonly (редактирование — через Staff)

**Зависимость от бэкенда:** Products (Phase 4.2 ✅), Companies (Phase 4.1 ✅), Analytics (Sprint 9.2 — план).

**Критерий готовности:** Компания видит свои продукты и аналитику.

---

## PHASE F6: Agent

### F6.1: Agent Hub

**Цель:** Агент управляет реферальными ссылками.

**Задачи:**
- [ ] src/views/agent/AgentDashboardView.vue:
  - Виджеты: комиссии за месяц, количество рефералов, ранг в лидерборде
  - Quick actions: Создать ссылку, Мои комиссии
- [ ] src/views/agent/AgentHubView.vue:
  - POST /api/v1/referrals/links — создать реферальную ссылку
  - GET /api/v1/referrals/links/me — мои ссылки
  - Каждая ссылка: код, копирование, статистика (клики, конверсии)
  - GET /api/v1/referrals/stats/me — общая статистика
- [ ] src/views/agent/ReferralsView.vue:
  - Список привлечённых инвесторов (L1/L2/L3)
  - Иерархия: tree view или flat list с уровнем

**Зависимость от бэкенда:** Referrals (Sprint 7.2 — план).

**Критерий готовности:** Агент создаёт ссылки, видит рефералов.

---

### F6.2: Комиссии + Лидерборд + Пассивный баланс

**Цель:** Агент видит заработок и рейтинг.

**Задачи:**
- [ ] src/views/agent/CommissionsView.vue:
  - GET /api/v1/agent/commissions/me — история комиссий
  - Каждая запись: сумма, уровень (L1/L2/L3), инвестор, продукт, дата
  - Фильтры: уровень, период
- [ ] src/views/agent/LeaderboardView.vue:
  - GET /api/v1/agent/leaderboard — топ агентов
  - Ранг, имя, объём продаж
  - Подсветка своей позиции
- [ ] src/views/agent/PassiveBalanceView.vue:
  - Passive balance: confirmed + frozen
  - Кнопка "Вывести" → запрос вывода
  - POST /api/v1/withdrawals — создать запрос
  - GET /api/v1/withdrawals/me — история выводов
  - Каждый вывод: сумма, статус (CBadge), дата
- [ ] src/views/agent/AgentSettingsView.vue:
  - Всё из InvestorSettingsView + реквизиты выплат (payout details)
  - IBAN / email / crypto address

**Зависимость от бэкенда:** Commissions (Sprint 7.3 — план), Leaderboard (Sprint 7.3 — план), Withdrawals (Sprint 6.3 — план).

**Критерий готовности:** Агент видит комиссии, лидерборд, может запросить вывод.

---

## PHASE F7: i18n полировка

### F7.1: Полная локализация

**Цель:** Все строки переведены на 4 языка.

**Задачи:**
- [ ] Ревизия всех views — замена хардкод-строк на `$t()` ключи
- [ ] Заполнение en.json, ru.json, de.json, ar.json для всех экранов
- [ ] Форматирование дат: `Intl.DateTimeFormat` с locale из vue-i18n
- [ ] Форматирование валют: `formatMoney(cents, 'USD', locale)`
- [ ] RTL тестирование всех экранов в ar locale
- [ ] Fallback: если ключ не найден → en.json

**Критерий готовности:** Все 4 языка работают. RTL корректен на всех экранах.

---

## PHASE F8: Notifications UI

### F8.1: Уведомления

**Цель:** Юзер видит и управляет уведомлениями.

**Задачи:**
- [ ] src/stores/notifications.ts (Pinia):
  - `unreadCount: number`
  - `notifications: NotificationDelivery[]`
  - `fetchUnreadCount()` — GET /api/v1/notifications/unread-count
  - `fetchNotifications()` — GET /api/v1/notifications
  - `markRead(id)` — POST /api/v1/notifications/{id}/read
  - `markAllRead()` — POST /api/v1/notifications/read-all
- [ ] Badge counter в CTabBar (на иконке "Главная" или bell icon)
- [ ] Notification list (slide-in panel или dedicated view):
  - Каждое уведомление: иконка типа, title, body, time ago
  - Свайп или клик → markRead
  - "Отметить все прочитанными"
- [ ] Polling: `setInterval` refresh unread count каждые 30 секунд

**Зависимость от бэкенда:** Notifications REST (Sprint 8.3 — план).

**Критерий готовности:** Юзер видит уведомления и badge с количеством непрочитанных.

---

## PHASE F9: Полировка

### F9.1: UX-улучшения

**Цель:** Приложение ощущается как нативное.

**Задачи:**
- [ ] Skeleton-загрузки (вместо спиннеров) на основных экранах
- [ ] Анимации переходов (Vue `<Transition>`)
- [ ] Pull-to-refresh
- [ ] Haptic feedback в Telegram (на кнопках, на успешных действиях)
- [ ] Error boundary (глобальная обработка ошибок Vue)
- [ ] Offline-заглушка ("Нет подключения" + кнопка "Повторить")
- [ ] Keyboard accessibility: `role="button"`, `tabindex="0"`, `@keydown` на clickable divs

**Критерий готовности:** Приложение ощущается как нативное на iPhone и Android.

---

### F9.2: Posts + Events

**Цель:** Лента новостей платформы и компаний.

**Задачи:**
- [ ] Лента постов на дашбордах (investor, agent):
  - GET /api/v1/posts — фильтр по owner_type
  - Баннеры (is_banner) с кнопкой dismiss → POST /api/v1/posts/{id}/dismiss
- [ ] Список событий:
  - GET /api/v1/events/upcoming
  - Карточка: title, дата, location, ссылка

**Зависимость от бэкенда:** Posts (Sprint 9.1 — план).

**Критерий готовности:** Юзер видит новости и события.

---

## 5. Сводка зависимостей

| Frontend Phase | Backend Phase | Статус бэка | Блокирует? |
|---------------|---------------|-------------|------------|
| F0: Инфра | — | — | Нет |
| F1: Auth | 1.1, 1.2, 1.3 | ✅ | Нет (verify-email = gap, обходим) |
| F2: Компоненты + Layout | 1.3 (users/me) | ✅ | Нет |
| F3: Staff | 3.1–3.3, 5.2 | ✅ | Частично (withdrawals, agent-apps — заглушки) |
| F4: Investor | 4.2, 5.2 | ✅ | Частично (purchase 6.1, installment 6.2, transactions 6.4, portfolio 9.2 — заглушки) |
| F5: Company | 4.1, 4.2 | ✅ | Частично (analytics 9.2 — заглушка) |
| F6: Agent | 7.1, 7.2, 7.3, 6.3 | ❌ Не начато | Да (основная функциональность) |
| F7: i18n | — | — | Нет |
| F8: Notifications | 8.1–8.3 | ❌ Не начато | Да |
| F9: Полировка + Posts | 9.1 | ❌ Не начато | Частично |

**Стратегия:** Фазы F3–F5 можно начинать сразу — бэкенд готов на 70%+. Экраны с негативными бэкенд-зависимостями показывают `CEmptyState` ("Скоро") до готовности API. F6 стартует когда бэкенд Phase 7 готов.

---

## 6. LLM Code Review Guide (Frontend)

### FP-01: Не хардкодить API URL

```typescript
// ЗАПРЕЩЕНО:
fetch('https://api.cbshome.org/api/v1/users/me')

// ПРАВИЛЬНО:
const BASE_URL = import.meta.env.VITE_API_BASE_URL
fetch(`${BASE_URL}/api/v1/users/me`)
```

### FP-02: Не мутировать Pinia store напрямую из компонентов

```typescript
// ЗАПРЕЩЕНО:
authStore.user = response.data

// ПРАВИЛЬНО — через action:
authStore.setUser(response.data)
```

### FP-03: Не забывать обработку ошибок API

```typescript
// ЗАПРЕЩЕНО:
const data = await api.get('/products')
products.value = data.items

// ПРАВИЛЬНО:
try {
  const data = await api.get<PaginatedResponse<ProductResponse>>('/products')
  products.value = data.items
} catch (error) {
  if (error instanceof ApiResponseError) {
    toast.error(error.detail)
  }
}
```

### FP-04: Double-submit guard — ДО валидации

```typescript
// ПРАВИЛЬНО — guard первым:
if (submitting.value) return
submitting.value = true
try {
  // validate, then submit
} finally {
  submitting.value = false
}
```

### FP-05: Не использовать `any`

```typescript
// ЗАПРЕЩЕНО:
function handleResponse(data: any) { ... }

// ПРАВИЛЬНО:
function handleResponse(data: ProductResponse) { ... }
```

### FP-06: Cents → отображение (всегда через format)

```typescript
// ЗАПРЕЩЕНО:
<span>{{ user.balance_cents / 100 }}$</span>

// ПРАВИЛЬНО:
<span>{{ formatMoney(user.balance_cents, 'USD', locale) }}</span>
```

### FP-07: Cents input/output — всегда через currency utils

```typescript
// ЗАПРЕЩЕНО — float precision trap:
const cents = Math.round(parseFloat(input) * 100)

// ПРАВИЛЬНО:
import { usdStringToCents, centsToUsdString } from '@/utils/currency'
const cents = usdStringToCents(input)   // '14.57' → 1457
const display = centsToUsdString(cents) // 1457 → '14.57'
```

### FP-08: Не привязываться к Telegram SDK напрямую

```typescript
// ЗАПРЕЩЕНО в компонентах:
window.Telegram.WebApp.HapticFeedback.impactOccurred('medium')

// ПРАВИЛЬНО — через абстракцию:
platform.hapticFeedback('medium')
```

### FP-09: Только CSS-переменные, никаких hex

```css
/* ЗАПРЕЩЕНО: */
color: #1A6B6A;
background: #F5F5F5;

/* ПРАВИЛЬНО: */
color: var(--primary);
background: var(--bg-subtle);
```

### FP-10: Все строки через i18n

```vue
<!-- ЗАПРЕЩЕНО: -->
<span>Настройки</span>

<!-- ПРАВИЛЬНО: -->
<span>{{ $t('common.settings') }}</span>
```

### FP-11: Комментарии — только английский

```typescript
// ЗАПРЕЩЕНО:
// Получаем список продуктов

// ПРАВИЛЬНО:
// Fetch paginated product list
```

### FP-12: Token storage через platform abstraction

```typescript
// ЗАПРЕЩЕНО — хардкод storage:
localStorage.setItem('cbs_token', token)

// ПРАВИЛЬНО — через platform:
const driver = platform.getStorageDriver()
window[driver].setItem('cbs_token', token)
```

---

## 7. Реестр технического долга

### Обозначения

- **Среда:** 🧪 Тест / 🚀 Прод
- **Статус:** ⬜ Open / ✅ Done

### Известные решения (НЕ является долгом)

| Решение | Причина |
|---------|---------|
| Ручная типизация API вместо OpenAPI codegen | Контроль, идиоматичность, проще поддерживать |
| Раздельный token storage (localStorage/sessionStorage) по платформе | Telegram закрывает вкладку — sessionStorage очищается; standalone не должен разлогинивать |
| Свой CSS вместо Tailwind | Дизайн-система готова в мокапах (variables.css v1.8.0), перенос 1:1 проще |
| Внутренний Nginx в Docker фронтенда | SPA fallback + кеширование без усложнения хост-конфига |
| CORS вместо proxy | Подготовка к будущему разделению на микросервисы |
| Token decoupled от Pinia (модульная переменная в client.ts) | Исключает circular dependency client → store → client |
| Noto Sans Arabic для RTL | Тот же CDN (Google Fonts), нейтральный стиль сочетается с Montserrat |

### Инфраструктура — перед публичным запуском 🚀

| ID | Среда | Описание | Решение | Статус |
|----|-------|----------|---------|--------|
| TD-FE-CORS | 🚀 | CORS whitelist содержит только `cbshome.org`. Staging/dev домены нужно добавлять вручную | Переменная `CORS_ORIGINS` в .env бэкенда | ⬜ |
| TD-FE-VERIFY | 🚀 | POST /api/v1/auth/verify-email — gap в бэкенде. Email verification пропускается в MVP | Реализовать эндпоинт на бэкенде | ⬜ |

---

**Конец документа**
