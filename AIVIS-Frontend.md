# AIVIS.ONE — Техническое задание: Frontend

**Версия:** 2.12-F6
**Дата:** 25 июля 2026
**Статус:** Active
**Репозиторий:** https://github.com/aivis-one/aivis

**Зависимости (читать перед работой):**
- `AIVIS-Design-Document.md` — Конституция v1.6 (§4.7 "Принципы проверяются на каждом решении")
- `AIVIS-Backend.md` — Backend ТЗ v3.7
- `AIVIS-Refactor-Investor-Market-And-Staff.md` v0.7 final (R1, fully implemented)
- `AIVIS-Refactor-Company-Docs.md` v0.9 final (R2, fully implemented)
- Документ по observability фронтенда так и не был написан (анонсированный черновик v0.3 планировался после F6); нужен ли он вообще — открытый вопрос.
- `AIVIS-Financial-System.md` — финансовая логика
- `AIVIS-State-Machines.md` — переходы статусов
- `AIVIS-Installment.md` — механика рассрочки
- `AIVIS-Share-Pool-Refactor.md` — архитектурный референс OptionPool / Product Inventory (✅ closed Sprint 4.4, deployed `b539ee8`)
- `mockups/` — UI-прототипы (auth-flow, investor-shell, agent-shell, company-shell, staff-shell)

---

## 1. Обзор

### 1.1. Цель

Фронтенд AIVIS.ONE — единое SPA-приложение с ролевым роутингом, работающее в двух режимах:

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
| `investor` | InvestorShell | Главная, Портфель, Маркет, Баланс, Ещё | Витрина, покупка, рассрочка, active balance |
| `agent` | AgentShell | Главная, Hub, Комиссии, Баланс, Ещё | Всё инвесторское + реферальные ссылки, комиссии L1/L2/L3, лидерборд |
| `company` | CompanyShell | Главная, Продукты, Аналитика, Баланс, Настройки | Управление продуктами, аналитика продаж, passive balance |
| `staff` | StaffShell | Главная, Юзеры, KYC, Платежи, Ещё | Управление всеми пользователями, KYC-очередь, аватаринг |

Agent имеет доступ ко всем инвесторским экранам (он тоже инвестор). Переключение через навигацию, не отдельное приложение.

**"Ещё" (More)** — отдельный экран MoreView с навигацией к: Documents, Settings, Notifications, и ролеспецифичные пункты (Agent Application для investor, Leaderboard для agent).

### 1.5. UserResponse — структура ответа бэкенда

```typescript
interface UserResponse {
  id: string             // UUID
  role: string           // 'investor' | 'agent' | 'company' | 'staff' | 'platform'
  email: string | null   // extracted from credentials.email.email (null for Telegram-only)
  is_active: boolean
  onboarding_step: string // 'registered' | 'email_verified' | 'profile_complete' | 'role_selected' | 'kyc_done' | 'onboarding_complete'
  kyc_status: string     // 'not_started' | 'submitted' | 'approved' | 'rejected'
  profile: Record<string, any>  // JSONB: first_name, last_name, country, phone...
  payout_details: Record<string, any> | null
  language: string       // 'en' | 'ru' | 'de' | 'ar'
  created_at: string
  updated_at: string | null
}
```

`email` извлекается из `credentials.email.email` через `@property` на модели User. Telegram-only юзеры получают `null`. Хэши паролей и токены остаются скрытыми.

---

## 2. Технологический стек

| Компонент | Технология | Версия | Назначение |
|-----------|-----------|--------|------------|
| Фреймворк | Vue 3 | latest | Composition API, SFC |
| Язык | TypeScript | 5.x | Строгая типизация |
| Сборка | Vite | latest | HMR, быстрая сборка |
| Роутинг | Vue Router | 4.x | Role-based guards |
| Стейт | Pinia | latest | Реактивные хранилища |
| HTTP | Fetch (обёртка) | native | Запросы к API (CORS → api.aivis.one) |
| i18n | vue-i18n | v10 | en/ru/de/ar + RTL |
| PWA | vite-plugin-pwa | latest | Manifest + Service Worker |
| Стили | Свой CSS | — | Дизайн-система из мокапов (variables.css v1.8.0) |
| Линтинг | ESLint + Prettier | latest | Качество кода |
| Иконки | lucide-vue-next | ^0.460 | SVG-иконки из мокапов (Lucide) |
| Платформа | Telegram WebApp SDK | latest | initData, тема, haptic |
| Шрифты | Montserrat + Noto Sans Arabic | Google Fonts | LTR + RTL |

### 2.1. Почему CORS, а не proxy

Фронтенд (`app.aivis.one`) и API (`api.aivis.one`) — разные домены. Запросы идут напрямую на `api.aivis.one` с CORS.

Причина: при переходе на микросервисы API Gateway будет за `api.aivis.one`, фронтенд не поменяется.

Бэкенд: `CORSMiddleware` с whitelist `["https://app.aivis.one"]`. Credentials allowed.

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
aivis/                                -- GitHub repo root (существует)
├── backend/                          -- Бэкенд (существует)
├── frontend/                         -- Фронтенд (новый)
│   ├── src/
│   │   ├── api/                      -- HTTP-клиент + типизированные методы
│   │   │   ├── client.ts             -- Base fetch обёртка, CORS, interceptors
│   │   │   ├── types.ts              -- TypeScript-интерфейсы (все типы API)
│   │   │   ├── utils.ts              -- Shared helpers (buildQuery)
│   │   │   ├── auth.ts               -- POST /auth/email/*, POST /auth/telegram
│   │   │   ├── users.ts              -- GET/PATCH /users/me, payout-details
│   │   │   ├── kyc.ts                -- KYC submit, status
│   │   │   ├── documents.ts          -- Documents list, sign
│   │   │   ├── products.ts           -- Products list, detail
│   │   │   ├── purchases.ts          -- Purchase, installment
│   │   │   ├── payments.ts           -- Crypto address, history
│   │   │   ├── referrals.ts          -- Referral links, stats
│   │   │   ├── commissions.ts        -- Commission history, leaderboard
│   │   │   ├── companies.ts          -- Company profile, products
│   │   │   ├── withdrawals.ts        -- Withdrawal request, history
│   │   │   ├── notifications.ts      -- Notification list, read, unread-count
│   │   │   ├── posts.ts              -- Posts feed, dismiss
│   │   │   ├── events.ts             -- Events list, upcoming
│   │   │   ├── dashboard.ts          -- GET /dashboard/summary
│   │   │   ├── portfolio.ts          -- GET /portfolio/me, company detail
│   │   │   ├── certificates.ts       -- GET/POST /purchases/{id}/certificate
│   │   │   ├── transactions.ts       -- GET /transactions
│   │   │   ├── agent-apps.ts         -- POST /agent-applications, GET .../me
│   │   │   └── admin.ts              -- Staff endpoints
│   │   │
│   │   ├── components/               -- Переиспользуемые UI-компоненты
│   │   │   ├── ui/                   -- Примитивы: CButton, CInput, CCard...
│   │   │   │   ├── icons/            -- SVG-иконки из мокапов (Vue-компоненты)
│   │   │   │   └── index.ts          -- Barrel export
│   │   │   ├── layout/               -- CHeader, CTabBar, InvestorShell, AgentShell...
│   │   │   └── shared/               -- ВСЕ reusable компоненты, не делим по ролям: ProductCard, CompanyFilterSheet, TransactionDetailSheet, CertificateSheet...
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
│   │   │   ├── dashboard.ts          -- full /dashboard/summary payload (balances + portfolio aggregate) -- replaces balance.ts (F4.4 B2)
│   │   │   ├── portfolio.ts          -- investor portfolio (positions + per-company paginated purchases)
│   │   │   ├── agent.ts              -- referrals, commissions, leaderboard
│   │   │   ├── company.ts            -- company profile, products
│   │   │   ├── transactions.ts       -- transaction history with filters
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
│   └── install_aivis.sh            -- Целевой артефакт поставки
└── AIVIS-Frontend.md                 -- ЭТОТ ДОКУМЕНТ
```

### 3.2. Интеграция с бэкендом

```
Browser / Telegram
      │
      ▼
   Nginx (app.aivis.one)
      │
      └── /*         → frontend:3000 (Vue SPA)

   Nginx (api.aivis.one)
      │
      └── /*         → app:8000 (FastAPI)

Фронтенд → CORS → api.aivis.one/api/v1/*
```

Два домена, два Nginx-блока. CORS `CORSMiddleware` на бэкенде с whitelist `["https://app.aivis.one"]`.

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

## PHASE F0: Инфраструктура ✅

### ✅ F0.1: Инициализация проекта

**Цель:** Проект собирается, деплоится на VPS, пустая страница открывается.

**Задачи:**
- [x] `npm create vite@latest frontend -- --template vue-ts`
- [x] Установка зависимостей: vue-router, pinia, vue-i18n
- [x] vite.config.ts: `server.host: '0.0.0.0'`, `server.port: 3000`, `resolve.alias: {'@': '/src'}`
- [x] tsconfig.json: `strict: true`, `paths: {"@/*": ["./src/*"]}`
- [x] ESLint flat config + Prettier (.prettierrc)
- [x] .env.example: `VITE_API_BASE_URL=https://api.cbshome.org`
- [x] .gitignore: node_modules, dist, .env

**Критерий готовности:** `npm run dev` → localhost:3000 показывает пустую страницу.

---

### ✅ F0.2: Docker + Nginx

**Цель:** Фронтенд собирается в Docker, раздаётся через Nginx.

**Задачи:**
- [x] Dockerfile: multi-stage (node:22-alpine build → nginx:alpine serve)
- [x] nginx.conf: SPA fallback, gzip, cache headers, CSP с Telegram SDK, health check `/health`
- [x] docker-compose.yml: сервис `frontend` с build context `./frontend`
- [x] `install_aivis.sh`: Nginx-блок для `cbshome.org` → `localhost:3000`

**Обновления (F1):**
- Dockerfile: `npm ci` → `npm install` (автоматическое подтягивание новых зависимостей при `aivis update`)
- Dockerfile: `ENV VITE_API_BASE_URL=https://api.cbshome.org` + `ENV VITE_TELEGRAM_BOT_URL=https://t.me/cbshome_bot` — baked into build stage
- `.env.production` — Vite production env vars (дублирует Dockerfile ENV для dev-сборки)
- `.dockerignore` — разрешён `.env.production`
- `install_aivis.sh`: убран `--no-cache` из `case_update()` (оставлен при первичной установке)

**Критерий готовности:** `docker compose up frontend` → cbshome.org отдаёт SPA.

---

### ✅ F0.3: Стили (дизайн-токены)

**Цель:** CSS-переменные из мокапов подключены, темизация работает.

**Задачи:**
- [x] src/styles/variables.css — скопирован из `mockups/css/variables.css` 1:1
- [x] src/styles/global.css — reset, Google Fonts (Montserrat + Noto Sans Arabic), base styles
- [x] Тёмная тема: `[data-theme="dark"]` переопределяет переменные (из mockups)
- [x] RTL: `[dir="rtl"]` базовые overrides

**Критерий готовности:** CSS-переменные доступны, тема переключается.

---

### ✅ F0.4: PWA-манифест

**Цель:** Приложение устанавливается на Home Screen.

**Задачи:**
- [x] vite-plugin-pwa: `registerType: 'autoUpdate'`, `workbox.globPatterns: ['**/*.{js,css,html,ico,png,svg,woff2}']`, `navigateFallback: 'index.html'`, `navigateFallbackDenylist: [/^\/api\//]`
- [x] Placeholder-иконки: сплошной оранжевый (#cc3203) PNG 192x192 и 512x512

**Обновления (F1):**
- `vite.config.ts`: добавлен `runtimeCaching` для Google Fonts (без него production build падал: "Couldn't find configuration for either precaching or runtime caching")

**Критерий готовности:** iPhone Safari → "Добавить на экран" → приложение открывается в standalone-режиме.

---

### ✅ F0.5: i18n каркас

**Цель:** vue-i18n настроен, переключение языков работает, RTL layout переключается.

**Задачи:**
- [x] src/i18n/index.ts: `createI18n()` с `legacy: false` (Composition API)
- [x] Locale detection: `localStorage.getItem('cbs-lang')` → `navigator.language` → `'en'` fallback
- [x] RTL detection: `locale === 'ar'` → `document.documentElement.dir = 'rtl'`
- [x] Базовые ключи во всех 4 локалях (en, ru, de, ar)
- [x] main.ts: `app.use(i18n)`

**Критерий готовности:** `$t('app.name')` рендерит "AIVIS.ONE" на en. Переключение на ar → RTL.

---

## PHASE F1: Auth + Платформа ✅

### ✅ F1.1: Платформенная абстракция

**Цель:** Приложение знает, где запущено, и адаптируется.

**Задачи:**
- [x] src/platform/types.ts — интерфейс Platform (9 методов, включая `getStorageDriver()`)
- [x] src/platform/telegram.ts — обёртка над `window.Telegram.WebApp`:
  - `init()` — `WebApp.ready()`, `expand()`, `setHeaderColor('#1A6B6A')`, `setBackgroundColor('#F5F5F5')`
  - `getInitData()` — `WebApp.initData || null`
  - `getTheme()` — `WebApp.colorScheme || 'light'`
  - `hapticFeedback(style)` — `WebApp.HapticFeedback.impactOccurred(style)` в try/catch
  - `showBackButton(cb) / hideBackButton()` — `WebApp.BackButton` с onClick/offClick cleanup
  - `close()` — `WebApp.close()`
  - `getStorageDriver()` → `'sessionStorage'`
  - `getStartParam()` → `WebApp.initDataUnsafe?.start_param || null` (для referral_code)
- [x] src/platform/standalone.ts — полноценная standalone-реализация:
  - `getInitData()` → `null`
  - `hapticFeedback()` → no-op
  - `showBackButton(cb)` → `window.history.back()` fallback
  - `getStorageDriver()` → `'localStorage'`
  - `getStartParam()` → `null`
- [x] src/platform/index.ts — автодетект по `window.Telegram?.WebApp.initData`, экспорт singleton `platform`

**Решения реализации:**
- Детект Telegram: проверяем `wa && wa.initData` (не только `wa`). SDK скрипт создаёт `window.Telegram.WebApp` даже в обычном браузере, но `initData` — непустая строка только в реальном Telegram
- TelegramWebApp type declarations встроены в `types.ts` (subset используемых полей)
- BackButton callback cleanup через `offClick` перед `onClick` — предотвращает стекирование

**Критерий готовности:** `platform.name === 'telegram'` в Telegram, `platform.name === 'standalone'` в браузере. ✅

---

### ✅ F1.2: API-клиент

**Цель:** Типизированный HTTP-клиент для общения с бэкендом через CORS.

**Задачи:**
- [x] src/api/client.ts:
  - `BASE_URL` из `import.meta.env.VITE_API_BASE_URL` с fallback `'https://api.cbshome.org'`
  - Обёртка над fetch: `get<T>()`, `post<T>()`, `patch<T>()`, `put<T>()`, `delete()`
  - Авто-подстановка `Authorization: Bearer {token}` через модульный `_token`
  - Обработка 401 → callback `_onUnauthorized()` → auth store очищает сессию
  - Обработка 422 → парсинг массива ValidationError → join в строку
  - Обработка 204 → `return undefined as T`
  - Обработка сетевых ошибок → `ApiNetworkError`
  - `AbortController` + 15s timeout → `ApiTimeoutError`
  - `Accept-Language` header из текущей vue-i18n locale
  - Non-JSON error (502/503) → `HTTP {status}: non-JSON response`
- [x] src/api/types.ts — TypeScript-интерфейсы:
  - `EmailRegisterRequest { email, password, referral_code? }` — referral_code: string | null
  - `EmailLoginRequest { email, password }`
  - `TelegramAuthRequest { init_data, referral_code? }` — referral_code: string | null
  - `AuthResponse { user: UserResponse, session_token: string }`
  - `UserResponse` (см. раздел 1.5)
  - `UserUpdate { profile?, language? }`
  - `PaginatedResponse<T> { items: T[], total, page, per_page }`
  - `VerifyEmailRequest { code: string }`
  - `ValidationErrorItem { loc, msg, type }`

**Решения реализации:**
- `credentials: 'include'` убран — Bearer token auth, cookies не нужны. Закрывает CSRF-вектор
- `BASE_URL` fallback через `??` — защита от undefined при отсутствии env var (Vite Docker build)
- Dockerfile: `ENV VITE_API_BASE_URL=https://api.cbshome.org` — baked into build stage

**Критерий готовности:** `api.get<UserResponse>('/api/v1/users/me')` возвращает типизированный ответ через CORS. ✅

---

### ✅ F1.3: Auth flow (Email + Telegram)

**Цель:** Юзер авторизуется через email/password или через Telegram WebApp.

**Задачи:**
- [x] src/stores/auth.ts (Pinia):
  - `user: UserResponse | null`
  - `token: string | null`
  - `loading: boolean`
  - `isAuthenticated: boolean` (computed: `!!token && !!user`)
  - `role: UserRole | null` (computed через `asUserRole(user.value?.role)` — runtime guard из `api/types.ts`; неизвестное значение становится `null`, не unsafe-cast)
  - `kycStatus: KycStatus | null` (computed через `asKycStatus(user.value?.kyc_status)` — тот же паттерн; добавлено в Sprint 4.4 follow-up)
  - `loginViaEmail(email, password)` — POST /auth/email/login → set token + user
  - `registerViaEmail(email, password, referral_code?)` — POST /auth/email/register → set token + user
  - `loginViaTelegram(initData, referral_code?)` — POST /auth/telegram → set token + user
  - `restoreSession()` — storage → set token → GET /users/me → set user
  - `fetchMe()` — GET /users/me (обновление профиля)
  - `logout()` — POST /auth/logout + очистка store
  - Персистенция token в storage (driver из `platform.getStorageDriver()`) под ключом `cbs_token`
  - Регистрация `_onUnauthorized` callback в API client
- [x] Referral code handling:
  - При первом визите: сохранить `?ref=` из URL или `platform.getStartParam()` в `sessionStorage('cbs_referral_code')`
  - Передать в `registerViaEmail()` и `loginViaTelegram()`
  - Очистить после успешной регистрации
- [x] src/composables/useAuth.ts — объединяет platform + auth store:
  - `initAuth()` — вызывается один раз из App.vue `onMounted`:
    1. `platform.init()`
    2. Сохранить referral code если есть
    3. `authStore.restoreSession()` — если сохранённый токен валиден → готово
    4. Если Telegram: `platform.getInitData()` → `authStore.loginViaTelegram(initData, referral_code)`
    5. Если standalone и нет токена → показать LoginView
  - Module-level refs `isReady`, `isStandalone`, `authError`
  - `waitUntilReady()` — Promise.race(isReady watcher, 10s timeout) для router guards
  - `retryAuth()` — повторная попытка (для Telegram error state)
- [x] src/views/auth/LoginView.vue:
  - Email + password form
  - Кнопка "Войти"
  - Ссылка "Нет аккаунта? Зарегистрироваться"
  - Loading state, error display
  - Кнопка "Войти через Telegram" — отложена (бот есть, UI позже)
- [x] src/views/auth/RegisterView.vue:
  - Email + password + password confirm
  - Кнопка "Зарегистрироваться"
  - Ссылка "Уже есть аккаунт? Войти"
- [x] src/views/auth/LoadingView.vue — экран загрузки (лого + spinner)
- [x] src/components/ui/CbsLogo.vue — SVG лого как shared компонент
- [x] src/App.vue — auth-шлюз:
  - `!isReady` → LoadingView
  - `authError && !isStandalone` → Error screen + retry button
  - `!isAuthenticated` → LoginView / RegisterView (standalone)
  - Authenticated → `<RouterView />`

**Решения реализации:**
- Storage driver: явный ternary `sessionStorage / localStorage` вместо `window[driver]` — TypeScript type safety
- Telegram auth failure: `authError` ref + `retryAuth()` — пользователь видит ошибку + retry вместо вечного спиннера
- i18n ключи auth.* из `mockups/js/i18n.js` — 4 локали (en/ru/de/ar), включая error messages
- Кнопка "Войти через Telegram" отложена: `VITE_TELEGRAM_BOT_URL=https://t.me/cbshome_bot` готов в env

**Зависимость от бэкенда:** POST /auth/email/register, POST /auth/email/login, POST /auth/telegram, POST /auth/logout, GET /users/me. Phase 1 ✅.

**Критерий готовности:** Юзер входит через email/password в браузере. Юзер автоматически авторизован в Telegram WebApp. Referral code сохраняется и передаётся при регистрации. ✅

---

## PHASE F2: UI-компоненты + Layout ✅

### ✅ F2.1: UI-компоненты (дизайн-система)

**Цель:** Библиотека переиспользуемых компонентов из мокапов.

**Задачи:**
- [x] Компоненты из мокапов (1:1 перенос визуала):

**Примитивы (src/components/ui/):**

| Компонент | Пропсы | Описание |
|-----------|--------|----------|
| CButton | variant (primary/secondary/outline/danger/telegram/link), size, disabled, loading | Кнопка с состояниями. `btn-primary` = orange accent из мокапов |
| CInput | label, placeholder, error, type, modelValue | Текстовое поле с password toggle |
| CTextarea | label, placeholder, error, rows, modelValue | Многострочное поле |
| CSelect | label, options, error, placeholder, modelValue | Выпадающий список с custom arrow |
| CCheckbox | label, modelValue | Чекбокс (v-model) |
| CCard | hoverable, padding (slot) | Карточка-контейнер |
| CBadge | variant (success/warning/danger/primary/accent/neutral), text | Статусный бейдж |
| CAvatar | name, url, size | Аватар (инициалы или фото) |
| CLoader | size | Спиннер загрузки |
| CDivider | text | Горизонтальный разделитель с опциональным текстом |
| CEmptyState | title, description (icon slot) | Пустое состояние |
| CToast | — (composable useToast) | Всплывающее уведомление (Teleport to body) |
| CStatCard | value, label, sub, change, changeDir (icon slot) | Числовая карточка статистики |
| CProgressBar | value, max, color | Полоска прогресса |
| CModal | open, closeOnOverlay, showClose | Модальное окно (Teleport, Transition) |
| CIconBox | variant (teal/orange/green/yellow/red/blue/neutral) | Иконка в цветном квадрате (из mockups/css/components.css) |

- [x] src/components/ui/index.ts — barrel export всех 17 компонентов (включая CbsLogo)
- [x] src/composables/useToast.ts — singleton state, showToast(message, variant), auto-hide 3s

**Layout-компоненты (src/components/layout/):**

| Компонент | Описание |
|-----------|----------|
| CHeader | Sticky header с лого, title, back button, right slot. Lucide ChevronLeft |
| CTabBar | Нижняя навигация (TabItem[], route-aware active state). Lucide иконки, RTL-aware |
| InvestorShell | CHeader + `<RouterView>` + CTabBar (INVESTOR_TABS) + CToast |
| AgentShell | CHeader + `<RouterView>` + CTabBar (AGENT_TABS) + CToast |
| CompanyShell | CHeader + `<RouterView>` + CTabBar (COMPANY_TABS) + CToast |
| StaffShell | CHeader + `<RouterView>` + CTabBar (STAFF_TABS) + CToast |

- [x] src/router/tabs.ts — TabItem interface + конфигурации для 4 ролей
- [x] i18n ключи tab.* из mockups/js/i18n.js (4 локали)

**Решения реализации:**
- Все стили 1:1 из `mockups/css/components.css` через CSS-переменные (`variables.css`)
- Lucide-vue-next (^0.460) для иконок — все мокапы используют Lucide
- CTabBar: `iconMap` Record маппит строковые имена иконок из tabs.ts на Lucide-компоненты
- Shell'ы: minimal composition (CHeader + RouterView + CTabBar + CToast), контент рендерится через nested routes
- Dockerfile: `npm ci` → `npm install` для автоматического подтягивания новых зависимостей при `aivis update`

**Критерий готовности:** Все компоненты рендерятся корректно в обеих темах (light/dark) и в RTL. ✅

---

### ✅ F2.2: Роутинг + Layout

**Цель:** Навигация между экранами, role-based доступ.

**Задачи:**
- [x] src/router/index.ts — 43 маршрута с lazy loading:

```
/                          → редирект по роли (beforeEnter)
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
/investor/transactions     → TransactionsView
/investor/docs             → InvestorDocsView
/investor/settings         → InvestorSettingsView
/investor/more             → InvestorMoreView

-- Agent (extends investor) --
/agent/dashboard           → AgentDashboardView
/agent/hub                 → AgentHubView
/agent/referrals           → ReferralsView
/agent/commissions         → CommissionsView
/agent/leaderboard         → LeaderboardView
/agent/balance             → AgentBalanceView
/agent/market              → MarketView (shared)
/agent/portfolio           → PortfolioView (shared)
/agent/settings            → AgentSettingsView
/agent/more                → AgentMoreView
-- Agent investor screens (products, purchase, installment) duplicated under AgentShell

-- Company --
/company/dashboard         → CompanyDashboardView
/company/products          → CompanyProductsView
/company/products/:id      → CompanyProductEditView
/company/analytics         → CompanyAnalyticsView
/company/balance           → CompanyBalanceView
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
/:pathMatch(.*)*           → redirect /404
```

- [x] src/router/guards.ts — единый `globalGuard` (beforeEach):
  - `waitUntilReady()` → ожидание auth init
  - Auth: `!isAuthenticated` → `/login`. Authenticated users на /login → redirect по роли
  - Onboarding: `ONBOARDING_REDIRECTS` map → redirect на текущий шаг (skip для `meta.skipOnboarding`)
  - Role: `meta.roles` → redirect если роль не совпадает
  - Route meta: `{ public?, roles?, skipOnboarding? }`
- [x] 38 stub-views для всех маршрутов (investor, agent, company, staff, onboarding, 404)
- [x] NotFoundView — 404 страница с CSS-переменными
- [x] Tab bar конфигурация по ролям (src/router/tabs.ts) — уже готова в F2.1

**Решения реализации:**
- Shell'ы как parent routes с children — agent дублирует investor screens (market, portfolio, products/:id, purchase/:id, installment/:id) под AgentShell для правильного tab bar
- `meta.roles: ['investor', 'agent']` на InvestorShell — агенты видят investor экраны
- Root `/` → `beforeEnter` redirect по `authStore.role` (guard уже прождал auth)
- `getRoleDashboard(role)` — утилита для маппинга роли → путь дашборда
- `ONBOARDING_REDIRECTS` — маппинг `onboarding_step` → redirect path, защита от infinite loop
- Stub-views: `$t('i18n.key')` + badge с фазой реализации (F3–F6)

**Зависимость от бэкенда:** GET /api/v1/users/me (role, onboarding_step). Phase 1 ✅.

**Критерий готовности:** После логина юзер видит layout с tab bar по своей роли. Переходы между экранами работают. Чужие роли → redirect. ✅

---

### ✅ F2.3: Onboarding flow

**Цель:** Новый пользователь проходит онбординг: верификация email → профиль → выбор роли → KYC → документы.

**Задачи:**
- [x] src/views/auth/VerifyEmailView.vue:
  - 6 отдельных digit-input'ов с auto-focus, paste support, backspace navigation
  - Email пользователя из `authStore.user.email` (добавлено в UserResponse)
  - POST /api/v1/auth/verify-email → body: `{ code: "123456" }`
  - POST /api/v1/auth/verify-email/resend → 204 (rate limited)
  - Resend button с 60s cooldown timer (стартует на mount)
  - После успеха: `fetchMe()` → guard redirect
- [x] src/views/auth/OnboardingProfileView.vue:
  - first_name + last_name (side-by-side), phone, country (select), language (select)
  - Pre-fill из существующего profile (Telegram-юзеры)
  - PATCH /api/v1/users/me → `fetchMe()` → guard redirect
  - Валидация: first_name + last_name + country обязательны
- [x] src/views/auth/OnboardingRoleView.vue:
  - 3 карточки ролей из мокапа: investor, agent, company
  - Каждая: emoji-иконка, название, описание, feature-чипы
  - Selected state с чекмарком + accent border
  - Кнопка disabled → "Continue as {role}" при выборе
  - POST /api/v1/users/me/select-role → `fetchMe()` → guard redirect
- [x] src/views/auth/OnboardingKYCView.vue:
  - 4 состояния: not_started (submit button), submitted (pending card + polling 10s), approved (green card + continue), rejected (red card + retry)
  - POST /api/v1/kyc/submit → polling GET /api/v1/kyc/status
  - Polling при `approved` автоматически вызывает `authStore.fetchMe()` для auto-redirect
  - `onUnmounted` cleanup polling timer
- [x] src/views/auth/OnboardingDocsView.vue:
  - GET /api/v1/documents → `DocumentResponse[]` (бэк уже резолвит `language` под юзера с fallback на `en`)
  - Чекбоксы напротив каждого документа + общая кнопка "Sign documents" (не клик-подписывай-сразу)
  - "Read" button → CModal: `fetch('/legal/${doc.language}/${doc.type}.html')` → `new DOMParser().parseFromString(raw, 'text/html')` → `dom.body.innerHTML` в `v-html`. Атрибуты `<html>`, `<meta name="cbs-*">`, `<title>` и `<!DOCTYPE>` в DOM не попадают
  - При нажатии на общую кнопку — последовательные POST /api/v1/documents/{id}/sign по всем неподписанным (409 → continue как уже подписанный)
  - После всех подписей: `authStore.fetchMe()` → `router.push('/')` (guard доведёт до дашборда)
  - Arabic RTL наследуется из `document.documentElement.dir='rtl'` (см. `i18n/index.ts`) — специальных wrap'ов вокруг `v-html` не требуется, т.к. UI-локаль == локаль документа по контракту с бэком
- [x] Onboarding guard: реализован в guards.ts (F2.2) — `ONBOARDING_REDIRECTS` map
- [x] api/types.ts: + `SelectRoleRequest`, `KYCSubmitResponse`, `KYCStatusResponse`, `DocumentResponse` (`+language`, `+required_for_roles: string[]`, `-content_url` — см. Sprint 2.2 UPDATE на бэкенде), `DocumentSigningResponse`, `email` в `UserResponse`, fix `KycStatus` ('not_started' вместо 'none')
- [x] i18n: ~46 onboarding ключей × 4 локали (auth.verify.*, auth.profile.*, auth.role.*, auth.kyc.*, auth.docs.*, `auth.docs.read`, error.pageNotFound)

**Решения реализации:**
- Email в VerifyEmailView: `authStore.user.email` — добавлено в UserResponse через `@property` на бэкенде (credentials не экспозится)
- Onboarding step progression реализована на бэкенде (F2.3-Backend):
  - verify_email_code() → `registered` → `email_verified`
  - update_user() → `email_verified` → `profile_complete` (когда first_name + last_name + country заполнены)
  - select_role() → `profile_complete` → `role_selected` (POST /users/me/select-role)
  - process_webhook(approved) → `role_selected` → `kyc_done`
  - sign_document() → `kyc_done` → `onboarding_complete` (когда все docs роли подписаны)
- Role selection: POST /users/me/select-role (не PATCH /users/me) — отдельный endpoint с валидацией (investor/agent/company, step guard)
- KYC polling: `setInterval(10s)` с auto-fetchMe на approved для seamless redirect
- Все auth views используют raw HTML (form-input, btn-primary) — consistent с LoginView/RegisterView из F1.3

**Зависимость от бэкенда:** PATCH /users/me (✅), POST /users/me/select-role (✅ F2.3-Backend), KYC (✅), Documents (✅), Verify-email (✅).

**Критерий готовности:** Новый юзер проходит полный онбординг от регистрации до готовности. ✅

---

## PHASE F3: Staff ✅

### ✅ F3.1: Дашборд + статистика

**Цель:** Staff видит ключевые метрики.

**Задачи:**
- [x] src/views/staff/StaffDashboardView.vue:
  - GET /api/v1/staff/dashboard/stats → DashboardStatsResponse
  - GET /api/v1/staff/agent-applications → `.length` для реального счётчика заявок
  - CStatCard: total_users, pending_kyc_count, pendingApps (параллельная загрузка через `Promise.all`)
  - Чипы: users_by_role breakdown
  - Алертовый баннер если pending_kyc_count > 0
  - Quick actions: Process KYC, Check Payments, Avatar Mode
  - Навигационные ссылки: в юзеры → /staff/users, в KYC → /staff/kyc, в agent apps → /staff/agent-apps
- [x] src/api/admin.ts — 19 типизированных API-функций для всех staff endpoints
- [x] src/api/types.ts — 25 интерфейсов staff (Dashboard, Users, KYC, Payments, Withdrawals, Avatar, AgentApps)

**Зависимость от бэкенда:** GET /api/v1/staff/dashboard/stats. Phase 3.3 ✅.

**Критерий готовности:** Staff видит статистику. ✅

---

### ✅ F3.2: Управление юзерами

**Цель:** Staff видит и управляет пользователями.

**Задачи:**
- [x] src/views/staff/StaffUsersView.vue:
  - GET /api/v1/staff/users — список юзеров с пагинацией (?role=, ?page=, ?per_page=)
  - Role filter chips (All / investor / agent / company / staff)
  - Каждый item: CAvatar, имя, email, роль (CBadge), kyc_status
  - Platform user скрыт (бэкенд исключает из списка)
  - Клик → detail modal (CModal):
    - GET /api/v1/staff/users/{id} → UserDetailResponse
    - PATCH /api/v1/staff/users/{id}/block — блокировка с reason modal (permission: `user_block`)
    - POST /api/v1/staff/users — создать staff с confirmation modal (только Admin)
    - Permissions — все 8 ключей (`ALL_PERMISSION_KEYS`) через checkbox toggles (только Admin)
  - Pagination: prev/next с page counter

**Решения реализации:**
- F3-01: `ALL_PERMISSION_KEYS: StaffPermissionKey[]` — итерация по полному набору ключей, а не по ответу бэкенда. Гарантирует, что UI покажет все toggles даже если backend не вернул `false`-значения.
- F3-02: `common.all` i18n ключ для фильтра — никогда не определять язык через сравнение строки перевода.

**Зависимость от бэкенда:** Phase 3.1 ✅.

**Критерий готовности:** Staff видит всех юзеров, может заблокировать и промоутить. ✅

---

### ✅ F3.3: KYC-очередь

**Цель:** Staff одобряет и отклоняет KYC-заявки.

**Задачи:**
- [x] src/views/staff/StaffKYCView.vue:
  - GET /api/v1/staff/kyc/queue → list[KYCQueueItem] (permission: `kyc_approve`)
  - Каждый item: CAvatar, имя, email, дата подачи
  - Действия:
    - POST /api/v1/staff/kyc/{id}/approve — одобрить (inline button)
    - POST /api/v1/staff/kyc/{id}/reject — отклонить (CModal с optional reason)
  - Double-submit guard: `processingIds: Set<string>`
  - Toast: "KYC одобрен" / "KYC отклонён"
  - Hint banner с инструкцией
  - CEmptyState при пустой очереди

**Зависимость от бэкенда:** Phase 3.3 ✅.

**Критерий готовности:** Staff одобряет и отклоняет KYC-заявки. ✅

---

### ✅ F3.4: Платежи + Аватаринг + Agent Apps

**Цель:** Staff видит историю платежей, может входить под другим пользователем, управляет заявками агентов.

**Задачи:**
- [x] src/views/staff/StaffPaymentsView.vue:
  - GET /api/v1/staff/payments → StaffPaymentListResponse (paginated, filters: ?status=, ?user_id=)
  - Status filter chips (All / frozen / confirmed / reversed / failed)
  - Каждый item: amount (formatted), payment_type, provider, status (CBadge), user_id (truncated), date
  - POST /api/v1/staff/payments/{id}/reverse — chargeback через CModal с optional reason
  - Pagination
- [x] src/views/staff/StaffMoreView.vue:
  - Профиль staff (CAvatar, имя, email, CBadge "Staff")
  - Навигация: Agent Apps → /staff/agent-apps (с badge count), Avatar Mode → /staff/avatar
  - System info: platform version, language
  - Logout action
- [x] src/views/staff/StaffAvatarView.vue:
  - Форма старта: input User ID + кнопка "Start Session"
  - Список ограничений (5 пунктов из мокапа)
  - Логика swap токена → через `useAvatar` composable → redirect
- [x] src/composables/useAvatar.ts — avatar mode composable:
  - `startAvatarSession(userId)` → save staff token → POST start → persist avatar token → fetchMe → redirect to target dashboard
  - `endAvatarSession()` → restore staff token → POST end → fetchMe → redirect /staff/dashboard
  - Zombie guard: если `cbs_staff_token` отсутствует при end → сброс флага без вызова backend
  - Rollback: при ошибке start — восстанавливает staff token в память И storage
  - Catch в end: при ошибке — восстанавливает staff token, backend session истечёт по TTL
- [x] src/composables/avatarState.ts — shared reactive flag:
  - `STAFF_TOKEN_KEY`, `avatarActive: Ref<boolean>`, `setAvatarActive(value)` — единая точка мутации
  - Импортируется из `useAvatar.ts` и `stores/auth.ts` без цикла
- [x] src/App.vue — avatar overlay banner:
  - Fixed z-index:9999 при `isAvatarActive && isAuthenticated`
  - Ghost icon + target user name + "Return to Staff" button
  - Content push: `padding-top: 40px` на authenticated wrapper
- [x] src/views/staff/StaffAgentAppsView.vue:
  - GET /api/v1/staff/agent-applications — pending queue
  - Approve: inline button (✓), double-submit guard
  - Reject: CModal с required reason
  - CEmptyState при пустой очереди, hint banner
- [x] i18n: секция `staff.*` (~60 ключей × 4 локали: en, ru, de, ar) + `common.all`

**Решения реализации:**
- F3-03: Avatar token swap через `sessionStorage('cbs_staff_token')`. На reload: `restoreSession()` подхватит avatar token из `cbs_token`, баннер увидит маркер в sessionStorage.
- F3-04: `avatarState.ts` — отдельный модуль для shared reactive flag. Разрывает потенциальный цикл `useAvatar → stores/auth → useAvatar`.
- F3-05: `stores/auth._clearSession()` вызывает `setAvatarActive(false)` — сбрасывает флаг на logout / 401 / restore fail. Закрывает сценарий "zombie banner после повторного логина".
- F3-06: `endAvatarSession` zombie guard — если `cbs_staff_token` отсутствует (после 401 + re-login), сбрасывает флаг и редиректит без вызова backend.
- F3-07: Dashboard загружает agent applications count параллельно со stats (`Promise.all`), а не показывает `active_avatar_sessions` под ложным лейблом.
- F3-08: `CIconBox.vue` (F2.1 компонент) — создан с 7 вариантами из mockups/css/components.css.

**Дополнительные изменения (F3):**
- `stores/auth.ts` — import `setAvatarActive` из `avatarState`
- `public/theme-init.js` + `index.html` — inline script вынесен для CSP compliance
- `OnboardingKYCView.vue` — polling обёрнут в try/catch (предотвращение unhandledrejection)
- `.env.example` — `http://localhost:8000` вместо прод URL
- Удалён дубль `components/ui/CHeader.vue` (используется только `components/layout/CHeader.vue`)

**Зависимость от бэкенда:** Payments (Phase 5.2 ✅, G2 ✅), Avatar (Phase 3.2 ✅), Agent apps (Phase 7.1 ✅), Withdrawals (Phase 6.3 ✅).

**Критерий готовности:** Staff видит все платежи, может аватариться, управлять agent apps и withdrawals. ✅

**Phase F3 завершена.** 7 views + 2 composables + api/admin.ts + api/types.ts + i18n (4 локали) + App.vue (banner) + CIconBox.vue + avatarState.ts. 8 коммитов code review, score: 9/10.

---

### ✅ F3.5: Live Testing Fixes (post-deploy)

**Цель:** Фиксы найденные при live testing на production VPS.

**Баги найдены и закрыты:**

| # | Severity | Баг | Фикс |
|---|----------|-----|------|
| BUG-01 | 🔴 | Все onboarding views не редиректят после успеха (`fetchMe()` не инициирует навигацию) | +`useRouter` + `router.push('/')` после `fetchMe()` в 4 файлах: VerifyEmailView, OnboardingProfileView, OnboardingRoleView, OnboardingDocsView |
| BUG-02 | 🔴 | KYC блокирует онбординг — юзер застревает на экране ожидания | Бэкенд: `submit_kyc()` сразу ставит `kyc_done`. Фронт: "Понятно" кнопка → redirect, убран polling |
| BUG-03 | 🔴 | DocsView — при 0 документов кнопка disabled, юзер застревает | `canComplete = signedCount === documents.length` (0 === 0 = true) |
| BUG-04 | 🟡 | Raw JSON в ошибке (`{"error":"bad_request","message":"..."}`) | `extractErrorMessage()` парсит `detail` (FastAPI) + `message` (middleware) + fallback `JSON.stringify` |
| BUG-05 | 🟡 | Пропущен i18n ключ `auth.profile.language` | Добавлен в 4 локали |
| BUG-07 | 🔴 | После `POST /auth/email/register` пользователь оставался на `/register` (дублирующий рендер, тапы на "Verify" не работали) | `RegisterView.vue`: `await router.push({ name: 'verify' })` сразу после `registerViaEmail()`. Явная навигация к `/verify` — экономит раунд через `root.beforeEnter` + `globalGuard` |
| BUG-08 | 🔴 | `OnboardingDocsView` залипал на "Sign documents" — POST подписывал, но список не обновлялся без ручного рефреша | Полный рерайт вьюхи: чекбоксы + один общий sign-all (последовательные POST с 409-continue) + `fetchMe()` + `router.push('/')`. Тело документа — в CModal через `DOMParser → body.innerHTML`, fetch `/legal/{doc.language}/{doc.type}.html` |

**Изменённые файлы:**
- `src/api/client.ts` — unified error parsing
- `src/api/types.ts` — `DocumentResponse`: `+language`, `+required_for_roles`, `-content_url`
- `src/views/auth/VerifyEmailView.vue` — +`router.push('/')`
- `src/views/auth/OnboardingProfileView.vue` — +`router.push('/')`
- `src/views/auth/OnboardingRoleView.vue` — +`router.push('/')`
- `src/views/auth/OnboardingKYCView.vue` — non-blocking KYC, убран polling, кнопка "Понятно"
- `src/views/auth/RegisterView.vue` — `+router.push({ name: 'verify' })` после регистрации (BUG-07)
- `src/views/auth/OnboardingDocsView.vue` — полный рерайт: чекбоксы + sign-all + CModal с DOMParser (BUG-08)
- `src/i18n/locales/{en,ru,de,ar}.json` — +`language`, +`noDocs`, +`auth.docs.read` ("Read" / "Читать" / "Lesen" / "قراءة")
- `public/legal/{en,ru,de,ar}/*.html` — 20 HTML-болванок (5 типов × 4 локали) с `cbs-document-type` / `cbs-language` / `cbs-required-for-roles` meta-тегами; содержимое — Lorem ipsum placeholder (TD-F06a, юрист заменит перед production)
- `public/legal/*.html` — 5 старых flat-файлов **удалены** (структура теперь per-locale)

---

## PHASE F4: Investor

**Статус:** F4.1 переписана в R1 iter 2.5 (MarketView удалён → CompanyListView + CompanyOverviewView + ProductsByCompanyView). См. trailer для деталей. F4.2-F4.4 — closed как было.

### ✅ F4.1: Витрина продуктов (R1 iter 2.5 — реструктуризация)

**Цель:** Инвестор видит доступные продукты.

**Задачи:**
- [x] src/stores/products.ts (Pinia) — `products`, `total`, `filters`, `loading`, `fetchProducts()`
- [x] src/api/products.ts — `listProducts(params)`, `getProduct(id)`
- [x] src/api/companies.ts — `listCompanies(params)` для фильтра
- [x] src/components/shared/ProductCard.vue — обложка + название + компания + двухуровневый price block (pack primary + per-unit reference, Sprint 4.4) + `available_packages` (Sprint 4.3 — было `sold_units`), клик → `/investor/products/:id`
- [x] src/components/shared/CompanyFilterSheet.vue — bottom-sheet фильтр по компании
- [x] src/composables/usePagination.ts — бесконечный скролл / страницы
- [x] src/views/investor/MarketView.vue — список + фильтр + пагинация + empty states (`inv.market.empty.*`)
- [x] src/views/investor/ProductDetailView.vue — hero + stats + description + installment plans list + CTAs

**Polish (интегрированы в F4.1 scope):**
- **F4.1.1:** N+1 guard в public router на бэке — batch-load `CompanyProfile` за одну SELECT на страницу. Ответы `GET /products` / `GET /products/{id}` денормализуют `company_name`, `company_logo_url`, `company_cover_url` — витрина рендерится без второго round-trip.
- **F4.1.4:** Formatters вынесены в `src/utils/format.ts` (`formatPrice`, `formatNumber`, `resolveCoverImage`) — убран дубль из ProductCard + ProductDetailView. Role-aware routing через `src/router/helpers.ts::isAgentShell` — ни одного `path.startsWith` в views. CHeader truncate на длинных product.name. Buy CTA показывает "Sold out" при `available <= 0`. Hero fallback stack + `overflow-wrap: break-word` на description.
- **F4.1.5:** RouteMeta augmentation — `shell?: Shell` объявлен в `router/guards.ts`, `route.meta.shell` типизирован нативно без runtime cast в helpers.

**Зависимость от бэкенда:** GET /products (Sprint 4.2 ✅ + denormalisation F4.1), GET /companies (Sprint 4.1 ✅).

**Критерий готовности:** Инвестор видит витрину, открывает карточку продукта с полной информацией. ✅

**Commit chain:** до `bf4f1e5` (F4.1 main) + `b1171bc` (F4.1.5 RouteMeta patch). Score ревьюера: 9.9/10.

---

### ✅ F4.2: Покупка + Рассрочка

**Цель:** Инвестор покупает продукт (инстант или рассрочка).

**Роли:** доступно для `investor` и `agent` (агенты тоже могут инвестировать).

**Задачи:**
- [x] src/api/purchases.ts — `createPurchase(productId, body)` → `Promise<PurchaseResponse[]>` (sale + gift purchases из `purchase_config.bonuses`)
- [x] src/api/installments.ts — `createInstallmentPlan(productId, body)`, `listMyPlans(params)`, `getPlanDetail(id)`
- [x] src/api/dashboard.ts — `getDashboardSummary()` для balance probe
- [x] src/api/types.ts — `PurchaseResponse/CreatePurchaseRequest`, `InstallmentPlanResponse/Detail/List`, `InstallmentTrancheResponse`, `CreateInstallmentPlanRequest`, `BalanceResponse`, `CompanySummaryResponse`, `DashboardSummaryResponse`. Enum-поля (`legal_basis`, `status`) — union `| string` escape hatch для защиты от неизвестных бэковских значений
- [x] src/views/investor/PurchaseView.vue — instant-buy: order summary (`units × price = total`), balance card, Confirm/Cancel, role-aware redirect на portfolio при успехе
- [x] src/views/investor/InstallmentView.vue — two-mode: CONFIRM (deep-link `?plan=<id>` → подтверждение одного плана со schedule + first-tranche + balance) / SELECT (fallback без query: список планов как tappable cards). `router.replace` + `watch(queryPlanId)` для URL-sync без remount
- [x] src/views/investor/ProductDetailView.vue — план-карточки стали tappable CTAs (role="button" + tabindex + keyboard handlers), deep-link в `/investor/installment/:id?plan=<template_id>`. Secondary "Pay in installments" кнопка удалена — tap-target сама карточка
- [x] src/utils/installmentPlans.ts — shared `parsePlanConfig` (typed PlanConfig из JSONB), `getPlanBonus(plan)`, `getTrancheUnits(config, total, index)` (mirror backend scheduler math: `floor(percent × total / 100)` + остаток последнему траншу)
- [x] i18n: ~50 ключей × 4 локали (`inv.purchase.*`, `inv.installment.*`); удалён устаревший `inv.product.installment` (кнопки больше нет)

**Integration contracts:**
- Roles guard на бэке: `_BUYER_ROLES = {investor, agent}` — staff/company отвергаются `403`.
- KYC gate: UI перехватывает `400 "KYC verification required ..."` → warning toast + `router.push('/onboarding/kyc')`.
- Balance probe: `active_balance.confirmed` из `/dashboard/summary` (frozen excluded — бэк при execute_purchase не учитывает).
- `referral_link_id` — reserved optional field в request bodies (Sprint 7.2 stub).

**Error taxonomy (унифицирована PurchaseView + InstallmentView):**
- `instanceof ApiResponseError` → discriminate 400 sub-cases regex'ом на `message` (регексы — временный discriminator, см. TD-F08c):
  - `/kyc/i` → warning toast + redirect `/onboarding/kyc`
  - `/insufficient/i` → error toast + `await refreshBalance()` (ловит «другая вкладка съела»)
  - `/(template\|does not belong)/i` → error toast `templateMismatch` (InstallmentView only — race при soft-delete template)
  - `/not active/i` или `404` → error toast `productInactive`
  - fall-through → generic toast

**Маркетинговый приоритет:** installment plan cards на ProductDetail — главная CTA, не secondary link. Deep-link сокращает путь «ProductDetail → Confirm» до 1 тапа. "Buy now" остаётся primary CTA рядом для инстант-пути.

**Зависимость от бэкенда:** Purchase (Sprint 6.1 ✅), Installments (Sprint 6.2 ✅), Dashboard (Sprint 9.2 ✅).

**Критерий готовности:** Инвестор покупает продукт и оформляет рассрочку. ✅

**Commit chain:** B1 (`3202f68` API + types) → B2 (`fac96da` PurchaseView) → B2.1 (`157a972` typed error handling via `ApiResponseError`) → B3 (`3a39c14` InstallmentView + ProductDetail refactor) → B3.1 (extract `utils/installmentPlans`). Score ревьюера: 9.7 → 9.8 → 9.9 по ходу патчей.

**Follow-ups (TD-F08 блок, секция 8):** TD-F08a currency multi-value contract, TD-F08b YAGNI wrappers, TD-F08c backend `error_code`, TD-F08d `/installments/preview`, TD-F08e `buildQueryString` util.

**После F4.4 → Sprint 4.3 + TD-F07** (Share Pool Refactor) → **закрыты в Sprint 4.4**: `units` / `sold_units` мигрированы на `package_size` / `available_packages` во всех 5 затронутых вьюхах, добавлены `UserRole` / `KycStatus` typed guards в `auth.ts`, ProductDetailView и InstallmentView дропнули `?? []` после schema cleanup на бэке (installments стал required). Двухуровневый pack-pricing (B7 UX) deployed.

---

### ✅ F4.3: Баланс + Пополнение + Транзакции

**Цель:** Инвестор видит active balance, пополняет его криптой (TRC20), просматривает историю платежей и журнал транзакций.

**Роли:** инвестор. Agent-side balance/transactions (дубль под AgentShell) — отложен до F6 polish (см. Open Backlog).

**Задачи:**
- [x] src/api/payments.ts — `createCryptoAddress({ network })`, `listPaymentHistory(params)`
- [x] src/api/transactions.ts — `listTransactions(params)`, `getTransaction(id)` — через `buildQueryString`, весь фильтр surface (type/date_from/date_to/amount_min/amount_max) прокинут даже при том, что UI F4.3 драйвит только `type`
- [x] src/api/types.ts — расширен блоком F4.3: `PaymentResponse`, `PaymentHistoryResponse`, `DepositAddressResponse`, `CreateAddressRequest`, `CryptoNetwork` union (`TRC20|ERC20|BEP20|PoS`), `TransactionType` union (14 значений), `ReferenceType`, `TransactionResponse`, `TransactionListResponse`
- [x] src/stores/balance.ts (Pinia) — `activeBalance: BalanceResponse`, `passiveBalance: BalanceResponse` (nested объекты camelCase), `refresh()` → GET /api/v1/dashboard/summary, `error` flag
- [x] src/stores/transactions.ts (Pinia) — `items`/`total`/`page`/`typeFilter: string | null`/`loading`/`errored`, `fetchFirstPage()`/`loadMore()`/`setTypeFilter(prefix)` с fetch-epoch guard (паттерн из products store)
- [x] src/utils/querystring.ts — `buildQueryString(params)`: skip undefined/null/'', emits 0 для будущих range-фильтров. Закрывает TD-F08e
- [x] Миграция 5 existing API-функций на `buildQueryString`: `listProducts`, `listCompanies`, `listMyPlans`, `fetchUsers`, `fetchPayments`. Ни одного ручного `URLSearchParams` не осталось в `api/*`
- [x] src/views/investor/BalanceView.vue (перепись из stub) — balance card с active.confirmed + frozen (только если > 0), "Deposit" CTA → `investor-deposit`, payment history: local `ref<PaymentResponse[]>` + `useInfiniteScroll` + epoch-guard (per_page=20), 5 состояний (initial-loading / first-page-error / empty / list / load-more), status/type labels через `inv.balance.status.*` / `inv.balance.type.*` с raw-token fallback
- [x] src/views/investor/InvestorDepositView.vue (новый) — TRC20 hardcoded (multi-network selector отложен), `createCryptoAddress({ network: 'TRC20' })` on mount, QR via `qrcode.toString({ type: 'svg' })` с forced light palette (камеры кошельков не читают тёмные QR), injected через `v-html` в белом контейнере; monospace-адрес (`user-select: all`) + copy-button через `navigator.clipboard`; `ShieldAlert`-warning «send only USDT via TRC20»; `router.back()` с fallback `push('investor-balance')` (симметрично с PurchaseView cancel)
- [x] src/views/investor/TransactionsView.vue (перепись из stub) — 5 category-tabs (All / Deposits / Purchases / Installments / Withdrawals) → backend prefix-match (`deposit:`, `purchase:`, `installment:`, `withdrawal:`); icon per group (ArrowDownLeft/ArrowUpRight/ShoppingBag/Repeat/RefreshCw); signed amount с `+`/`-` prefix + success/danger color; tap → detail sheet через `selectedId` ref; i18n labels с raw fallback
- [x] src/components/shared/TransactionDetailSheet.vue (новый) — `CBottomSheet` с fetch on open (`watch([open, id])` с epoch-guard), key-value рендер `details` JSONB: known keys → i18n (`inv.transactions.detail.keys.*`), unknown → humanised snake_case (`trigger_tranche_number` → «Trigger Tranche Number»), `*_cents` suffix → `formatPrice`, `tx_hash` → middle-truncate + copy button; reset on close для fresh refetch при повторном открытии того же id
- [x] src/router/index.ts — добавлен child-route `balance/deposit` → `investor-deposit` (nested под `balance/` → URL читается как subsection, history-chain ведёт обратно к BalanceView). Agent shell не дублирует — deposit остаётся investor-scope в F4.3
- [x] src/i18n/index.ts — **critical fix:** `setupI18n()` теперь pre-loads DEFAULT_LOCALE параллельно с активной через `Promise.all`. Без этого vue-i18n `fallbackLocale` резолвит только messages в памяти — пропущенный ключ в ru/de/ar рендерился как raw dotted path (`inv.balance.title` вместо текста). Теперь fallback всегда доступен, стратегия «en обязателен в каждом feature-батче, ru/de/ar могут догонять» становится безопасной
- [x] qrcode package + @types/qrcode в package.json (регенерирован `package-lock.json` через `npm install --package-lock-only`)
- [x] i18n: 91 новых ключа × 4 локали (`inv.balance.*` 40 ключей, `inv.deposit.*` 11 ключей, `inv.transactions.*` 40 ключей включая 14 type-label'ов для всех `TransactionType` значений + 12 `detail.keys.*`)

**UI-паттерны (соблюдение конвенции):**
- **BalanceView и TransactionsView — top-level tab views** → CHeader НЕ добавляется, шапку рисует shell один раз; inline page-header в стиле MarketView (`<h1 class="__title">` + `<p class="__subtitle">`). После первой итерации B2 был замечен двойной header (shell CHeader + view CHeader) — поправлено в UI fix коммите: `CHeader` убран из BalanceView.
- **InvestorDepositView — sub-route под balance/** → CHeader с `:show-back="true"` + `:show-logo="false"` + `:title="..."`. Паттерн идентичен InstallmentView / PurchaseView.
- **Epoch-guard** применён везде где есть async + tab-switch / re-fetch: balance payment history, transactions store, transaction detail fetch, deposit address fetch.

**Error taxonomy (консистентно с F4.2):**
- `instanceof ApiResponseError` во всех error-handlers.
- Generic fallback-toast для deposit fetch (backend issue: fine-grained `error_code` не эмитит, TD-F08c).
- Silent swallow на `loadMore` ошибках — уже-загруженные страницы остаются видимыми.

**XSS surface:**
- `v-html` только для QR SVG от `qrcode` (чистый `<path>`, zero-surface).
- Transaction `details` JSONB — никогда через `v-html`, только interpolation `{{ formatValue(key, value) }}` + `JSON.stringify` для вложенных объектов.

**Зависимость от бэкенда:** Dashboard (Sprint 9.2 ✅), Crypto address (Sprint 5.2 ✅), Payments (Sprint 5.2 ✅), Transactions (Sprint 6.4 ✅).

**Критерий готовности:** Инвестор видит баланс, получает крипто-адрес с QR для пополнения, просматривает историю платежей и журнал транзакций с фильтром по категориям и деталями per-event. ✅

**Commit chain:** B1 (`f61882d` API + types + store + querystring util) → B1-polish (balance store camelCase, strict CryptoNetwork, PurchaseView/InstallmentView cancel fix) → B1.1 (`7c57ba7` buildQueryString migration, **TD-F08e closed**) → B2 (BalanceView + DepositView + QR + i18n + qrcode dep) → B2 UI fix (drop redundant CHeader in BalanceView, hide logo in DepositView) → i18n fallback preload → B3 (TransactionsView + DetailSheet + store + en.json) → B3.1 (TransactionsView storeToRefs migration) → i18n catchup ru/de/ar. Final score ревьюера: **9.8/10**.

**Follow-ups для F4.4 grooming-коммита (TD-F09 секция):** extract `formatSignedPrice` + `tOrRaw` в utils до старта Portfolio views.

**Side-fix вне frontend-скоупа:** `scripts/seed_storefront.py` — добавлен пропущенный `import base64` (NameError при генерации SVG-логотипа компаний через base64-encoded data URI).

---

### ✅ F4.4: Портфель + Дашборд

**Цель:** Инвестор видит свой портфель, дашборд, документы, настройки, сертификаты.

**Прогресс:** B0 ✅ · B1 ✅ · B1-post ✅ · B2 ✅ · B3 ✅ · B3-hotfix ✅ · B4 ✅ · B5 ✅ · B5-post ✅ · B6 ✅ · B6-hotfix ✅ · B7 ✅ — **F4.4 завершён**.

**Финальный score ревьюера:** 9/10 (после B5-post — все 🟡 и 🟢 из двух последовательных ревью закрыты, готово к merge; B6 и B7 — косметика на уже стабильной базе).

**Задачи:**
- [x] **B0 grooming (F4.4):** extract `formatSignedPrice` в `src/utils/format.ts` + extract `tOrRaw` в `src/utils/i18n.ts` (новый файл). Миграция 7 call-site'ов (2 для signed-price, 5 для tOrRaw). Семантика `cents === 0` → без знака (фикс бага TransactionsView «+$0.00»). Закрывает **TD-F09a + TD-F09b**, вводит правило **FP-15** (server-driven enums → tOrRaw). Параллельный CC-аудит выявил staff-side долг → **TD-F10** (4 пункта, не в скоупе F4.4).
- [x] **B1 API layer + stores + types (F4.4):** `api/portfolio.ts` (2 endpoint'а), `api/certificates.ts` (fetchCertificateBlob через raw fetch → blob URL для iframe, emailCertificate через api.post), `api/agent-apps.ts` (2 investor endpoint'а), `stores/portfolio.ts` (один store, positions + per-company paginated, epoch-guard), расширение `api/types.ts` (6 новых типов для F4.4), минимальная правка `api/client.ts` (экспорт `API_BASE_URL` для non-JSON endpoint'ов). Code review score 7/10 — основные замечания закрыты в B1-post.
- [x] **B1-post (B1 review follow-up):** (1) split `fetchEpoch` в `stores/portfolio.ts` на `portfolioEpoch` + `currentEpoch` (было: залипание `positionsLoading` при конкурентных операциях), (2) timeout coverage в `fetchCertificateBlob` теперь охватывает `response.blob()` (было: стук на медленной сети → вечный спиннер), (3) **loadMore retry-storm brake** — новое правило `loadMoreErrored` + `clearLoadMoreError()` в паджинированных stores, `paused?: Ref<boolean>` параметр в `useInfiniteScroll`, Retry-баннер в view. Применено к `stores/portfolio.ts` и `stores/transactions.ts` одновременно (консистентность), view-миграция в `TransactionsView.vue`. Вводит правило **FP-16**.
- [x] **B2 — InvestorDashboardView + store rename:** новый `src/stores/dashboard.ts` (заменяет `stores/balance.ts`) с полным `DashboardSummaryResponse` payload + legacy `activeBalance`/`passiveBalance` computed getters для миграции без переписывания темплейтов. `stores/balance.ts` удалён. Новый `src/views/investor/InvestorDashboardView.vue` — 5 виджетов: greeting row (time-of-day), portfolio hero card (gradient, тап → `/investor/portfolio`, empty-state CTA на первую покупку), balance card (active confirmed + frozen hint), quick actions (Deposit + Market), posts preview (5 последних через `api/posts.ts`, новый модуль с narrow probe — без store, не переиспользуется). Миграция `PurchaseView.vue` / `InstallmentView.vue` с inline `getDashboardSummary()` → `useDashboardStore` (balance никогда не десинкнётся между экранами в одной сессии). Новый `api/posts.ts` (F9.1), расширение `api/types.ts` (F9.1 Posts/Events section, 939 lines total). +17 ключей `inv.dashboard.*` в en.json. Events отложены до F9.2.
- [x] **B3 — PortfolioView + CompanyPositionView + Certificates:** новый `src/views/investor/PortfolioView.vue` (rewrite stub) — hero card с client-side profit % (`(current - paid) / paid * 100`, null при invested === 0, помечено TD-F11d) + positions list с тапом на детали. Новый `src/views/investor/CompanyPositionView.vue` — sub-route `/investor/portfolio/:id` (+ agent дубль), CHeader back + aggregate block + paginated purchases через FP-16 retry-storm brake + certificate flow. Новый `src/components/shared/CertificateSheet.vue` — bottom-sheet overlay, iframe с **`sandbox=""`** (закрывает TD-F11b), email CTA без confirmation, 3-секундный локальный cooldown поверх backend rate-limit. Новый `src/composables/useCertificateBlob.ts` — auto-revoke `URL.createObjectURL` через `onScopeDispose` + revoke-before-overwrite на повторный `load()`. Новый route `investor-company-position` + парный `agent-company-position`. +25 ключей `inv.portfolio.*` / `inv.companyPosition.*` / `inv.certificate.*` в en.json.
- [x] **B3-hotfix** (применён до релиза): (1) `CompanyPositionView.vue` import `@/components/investor/CertificateSheet.vue` → `@/components/shared/CertificateSheet.vue` (convention fix), (2) `router/index.ts`: добавлены маршруты `investor-company-position` + `agent-company-position` (без них `router.push({ name: ... })` не матчил).
- [x] **B4 — InvestorDocsView:** новый `src/views/investor/InvestorDocsView.vue` (rewrite stub). Sub-route `/investor/docs`, CHeader back. GET `/api/v1/documents` → список с фильтрацией по role на бэке, resolver locale'а (user_language + en fallback). Тап на row → модалка с содержимым документа. Sign flow: POST `/api/v1/documents/{id}/sign`, 409 как идемпотентный success (concurrent tab / replay). Новый `api/documents.ts` (listDocuments / getDocument / signDocument). Новый тип документа `risk_disclosure` — добавлен в `[investor, agent]` × 4 локали (4 legal HTML stub'а в `frontend/public/legal/{en,ru,de,ar}/risk_disclosure.html`). Company role оставлена с одним `company_agreement` (staff-managed technical user, покупок нет). Marketing consent → user preference в Settings (не документ). +15 ключей `inv.docs.*` в en.json.
- [x] **B5 — InvestorSettingsView + marketing consent:** новый `src/views/investor/InvestorSettingsView.vue` (rewrite stub) и backend whitelist fix. Профиль **read-only** (аватар через CAvatar с url/initials fallback — upload endpoint'а на бэке нет, показываем только; имя/email/role badge). **Язык locked at registration** (FOREVER — не меняется из Settings, UI switcher отсутствует). Профиль-детали (phone, country) — read-only rows без edit (Q7: «абсолютно запрещено менять личные данные»). Preferences: 3-state theme toggle (auto/light/dark) через новый `composables/useTheme.ts` (module-level singleton, `cbs-theme` localStorage ключ, совместим с `public/theme-init.js` pre-mount скриптом), marketing consent toggle (optimistic PATCH `/users/me` + revert on fail). Agent programme: state machine kyc_required → can_apply → pending → cooldown → can_reapply (N-days-left с ceiling) с подачей через `submitAgentApplication()`. Actions: Мои документы + Logout. Новый `api/users.ts` (getMe / updateMe). **Backend:** добавлен `"marketing_consent"` в `_ALLOWED_PROFILE_KEYS` (`app/modules/users/service.py`) — без этого PATCH возвращал 400. +25 ключей `inv.settings.*` в en.json.
- [x] **B5-post (B5+B3 review follow-up, 🟡+🟢):** (1) **Security:** `InvestorDocsView` — v-html снят, legal HTML рендерится в iframe с `sandbox=""` через blob URL (тот же паттерн что CertificateSheet, TD-F11b extended). `doc.type`/`doc.language` валидируются `SAFE_TOKEN = /^[a-z0-9_-]{1,64}$/i` + encodeURIComponent перед fetch path. Локальный epoch guard + revoke на unmount/close. (2) **Гонки:** epoch guard добавлен в `useCertificateBlob.load()` (перекрывающийся вызов не публикует проигравший URL, сам revoke'ает) — **TD-F11e closed**. Epoch guard добавлен в `useDashboardStore.refresh()` + `reset()` бампит epoch (post-logout refresh не перезапишет очищенный state) — **TD-F11f closed**. (3) **Дубликаты:** `frontend/src/views/investor/CertificateSheet.vue` удалён (байт-в-байт копия `components/shared/` версии). (4) **a11y:** clickable rows в Settings → `<button type="button">` с CSS-reset; marketing toggle получил `aria-labelledby`. (5) **Reactive greeting** (Dashboard): `ref(Date.now())` + `setInterval(60_000)` + `clearInterval` в `onBeforeUnmount` (раньше greeting computed не реагировал на пересечение границ morning/afternoon/evening при открытой вкладке). (6) `DocumentResponse.is_signed: boolean | null` → `boolean` (бэкенд всегда возвращает bool для list endpoint'а). (7) `fetchAgentApps` silent catch → `agentLoadErrored` state + inline retry row. (8) Удалены мёртвые `if (err instanceof ApiResponseError) ... else ...` ветки с одинаковыми toast'ами (2 места).
- [x] **B6 — InvestorMoreView + Settings header fix:** новый `src/views/investor/InvestorMoreView.vue` (rewrite stub). Grid `auto-fit, minmax(220px, 1fr)` с 2 live-плитками (Documents, Settings). Sign-out НЕ в More — остаётся только в Settings (редкое действие, защита от accidental tap в tab-reachable экране). Notifications отложены до F9.2 (роут не существует). Agent Application живёт внутри Settings (не отдельный top-level). **Critical finding через твой вопрос «а как попасть в Settings?»:** до B6 `/investor/settings` был orphaned route — `INVESTOR_TABS.more` ведёт на `/investor/more`, а More был stub'ом без ссылок. B6 wire'ит Settings обратно в UI. **Fix двойного header в Settings:** shell рисует CHeader глобально, а мой B5-Settings зашил свой `<CHeader>` → после B6-активации Settings покажет два header'а. Fix: убран CHeader + import, добавлен inline `<h1>` + `<p>` блок в стиле MarketView/TransactionsView. Шапка файла обновлена с объяснением регрессии. **Consistency fixes в Docs:** `void fetchDocuments()` → `onMounted(() => void fetchDocuments())`; `++openEpoch` переехал в самое начало `openDoc()` до SAFE_TOKEN guard + `_revokeBlob()` в early-return ветку невалидных идентификаторов. +8 ключей: `inv.more.*` (6) + `inv.settings.subtitle` + `inv.settings.agent.loadError` (B5-post).
- [x] **B6-hotfix:** build-блокер из-за `vue-tsc`. CButton принимает только `size?: 'default' | 'sm'` — я использовал `size="md"` в трёх местах (Docs modal × 2, Settings agent button × 1). Убраны строки `size="md"` (дефолт и так default). Регрессия была с B5, но невидима до build-time проверки на VPS.
- [x] **B7 — i18n catchup ru/de/ar:** 118 новых ключей × 3 локали = 354 перевода (7 блоков: dashboard, portfolio, companyPosition, certificate, docs, settings, more). Все locale JSON выросли с 350 до 468 leaf keys. Существующие переводы не тронуты (только добавлены отсутствовавшие ключи). Терминология якорилась на существующих ключах (RU: Портфель/Баланс/Маркет/Агент/Инвестор; DE: Portfolio/Kontostand/Marktplatz/Agent/Investor; AR: المحفظة/الرصيد/السوق/وكيل/مستثمر). `{days}` placeholder в `cooldown` сохранён во всех локалях. **Disclaimer:** DE/AR — best effort без nativespeaker-ревью, требуют professional vetting перед prod release (помечено в **TD-F12**). RU подлежит self-review.

**Зависимость от бэкенда:** Dashboard (Sprint 9.2 ✅), Portfolio (Sprint 9.2 ✅), Documents (Phase 2.2 ✅), Users (Phase 1.3 ✅ + B5 whitelist patch), Agent Applications (Sprint 7.1 ✅), Certificates (Sprint 9.2 ✅), Posts (Sprint 9.1 ✅).

**Критерий готовности:** Инвестор видит дашборд, портфель, документы, настройки, сертификаты. ✅

**Commit chain (финал):** B0 → docs → B1 → B1-post → docs #2 → B2 → B3 → B3-hotfix → B4 → B5 → B5-post → B6 → B6-hotfix → B7. Точные commit messages — в git log.

**Follow-ups (закрытые / открытые):**
- ✅ TD-F11a (loadMore retry-storm brake) — B1-post
- ✅ TD-F11b (iframe sandbox для CertificateSheet + InvestorDocsView) — B3 + B5-post
- ✅ TD-F11e (useCertificateBlob epoch guard) — B5-post
- ✅ TD-F11f (useDashboardStore epoch guard) — B5-post
- 🟡 TD-F11c (certificates → общий api.client с responseType) — ждём второй non-JSON endpoint
- 🟡 TD-F11d (PortfolioView client-side profit %) — ждём backend profit field
- 🟡 **TD-F12** (новый) — DE/AR i18n professional review перед prod release
- 🟡 **TD-F13** (новый) — migrate `OnboardingProfileView` inline `api.patch('/api/v1/users/me')` → новый `api/users.ts:updateMe()` (для консистентности; B5 не трогал за пределами scope)

**Уроки F4.4 (для следующих фаз):**
1. **CButton size="md" build-блокер (B6-hotfix)** — типы компонентов проверять в начале батча, не в конце. `size?: 'default' | 'sm'`, ни md ни lg. Удалить из мышечной памяти.
2. **Shell рисует CHeader глобально** (`InvestorShell.vue` / `AgentShell.vue`). Views **никогда** не рендерят свой `<CHeader>` — см. **FP-19** (Single CHeader policy, закреплена в iter 2.7 B1+B2). Это правило **универсально** для top-level tabs и sub-route views. Был инцидент двойного header в 8 views (iter 2.4-2.5 эпоха), исправлено batch'ем iter 2.7. Title через hero `<h1>` или inline `.<prefix>__page-header` с back-link (FP-19 + FP-20).
3. **Orphaned routes** — каждый новый роут должен иметь **входную точку** (ссылку из другого view или tab bar item). В F4.4 `/investor/settings` был orphaned до B6. Добавлять запись «Как попасть в этот экран:» при создании роута.
4. **Backend whitelist для JSONB fields** — `_ALLOWED_PROFILE_KEYS` в `users/service.py` нужно расширять при добавлении нового ключа в profile. Фронт падает с 400 на PATCH. Проверять до писания frontend-фичи.
5. **Epoch guard теперь стандарт** — применён в `stores/portfolio` (two-epoch), `stores/dashboard`, `stores/transactions`, `composables/useCertificateBlob`, inline `openDoc` в InvestorDocsView. Любой async + re-entrance сценарий должен иметь epoch. Правило кодифицировано в **FP-17** (ниже).

---

## PHASE F5: Company

> ✅ **Backend готов.** Sprint 4.5 deployed `b9d1fee` дал `GET /api/v1/companies/me` (canonical путь к собственному профилю с `distribution_config`, без 404 на non-active статусах). Sprint 4.3 B5 (`b9d1fee` ранее) дал `GET /api/v1/company/dashboard` + `GET /api/v1/company/analytics` — два специализированных company-side endpoint'а с правильным auth gate (`get_current_company_profile` → 403 без `CompanyProfile`). Sprint 4.6 hotfix (`75168f0`) починил installment_tranche-агрегацию в обоих response'ах. Sprint 4.5 frontend prep (`0f11197`) добавил `getMyCompany()` wrapper и Phase F5 type re-exports.
>
> **TD-F07 — закрыт в Sprint 4.4.** Пакет / pool-ребрендинг полей (`sold_units` → `available_packages`, `units` → `package_size`) выполнен на бэке (Sprint 4.3) и на фронте (Sprint 4.4) перед стартом F5.

### F5.1: Дашборд компании

**Цель:** Компания видит дашборд с метриками: passive balance, lifetime revenue, total options sold, active pool snapshot, последние транзакции.

**API контракт (готов):**
- `GET /api/v1/companies/me` → `CompanyResponse` — staff-side полный профиль (Sprint 4.5).
- `GET /api/v1/company/dashboard` → `CompanyDashboardResponse` (Sprint 4.3 B5) — single-payload агрегат: `passive_balance`, `total_revenue_cents`, `total_options_sold` (sale + installment_tranche, Sprint 4.6 hotfix), `products_count`, `pool` (active OptionPool snapshot или `null` если pool ещё не создан staff'ом), `recent_transactions[20]` (last 20 по `user_id` company, newest first).

**Задачи:**
- [ ] `src/api/company.ts` — **новый**: `getCompanyDashboard()`, `getCompanyAnalytics()` для `/company/dashboard` + `/company/analytics`. Тонкие wrapper'ы поверх `api.get`.
- [ ] `src/stores/companyDashboard.ts` — **новый**: Pinia store, `summary: CompanyDashboardResponse | null`, `refresh()` с epoch-guard pattern (FP-17, F4.4 B5-post). `reset()` бампит epoch — post-logout in-flight fetch не repopulate'ит state.
- [ ] `src/stores/companyProfile.ts` — **новый**: Pinia store, `profile: CompanyResponse | null`, `loadIfMissing()` идемпотентен (cached). Используется F5.1 для company name/logo в header, F5.2 для Settings и для `company_id` фильтрации в Products view.
- [ ] `src/views/company/CompanyDashboardView.vue` — **новый**:
  - `onMounted` → `loadIfMissing()` (companyProfile) + `refresh()` (companyDashboard) параллельно через `Promise.all`.
  - Hero: company logo + name из `companyProfile.value`.
  - Виджеты: `passive_balance.confirmed_cents` (доступно к выводу), `passive_balance.frozen_cents` (заморожено), `total_revenue_cents`, `total_options_sold`, `products_count`.
  - Pool widget: `summary.pool` — `total_options`, `consumed`, `remaining`, `equity_percent`. Если `pool === null` → плашка «Pool не создан, обратитесь в support».
  - Recent transactions: `summary.recent_transactions` (уже встроены в payload, отдельный fetch не нужен).

**Зависимости от бэкенда:** Sprint 4.3 B5 (Company Dashboard endpoint) ✅, Sprint 4.5 (`/companies/me`) ✅, Sprint 4.6 hotfix (installment_tranche в options_sold) ✅.

**Не использовать:**
- ❌ `GET /api/v1/dashboard/summary` — это endpoint Sprint 9.2 для **investor**-роли (active+passive balance, holdings across companies). Для company-роли он отдаст пустую `companies[]` и нерелевантные active_balance.
- ❌ `GET /api/v1/transactions` — отдельный fetch не нужен, последние 20 уже embed'ятся в `dashboard` payload.
- ❌ `GET /api/v1/companies/{id}` (public) для собственного профиля — 404'ится на non-active, не отдаёт `distribution_config`. Используй `getMyCompany()`.

**Критерий готовности:** Компания видит дашборд с балансом, метриками продаж, snapshot'ом pool'а и последними 20 транзакциями. Один HTTP round trip на `/company/dashboard` + один на `/companies/me`.

**Commit chain (план):**
- B0: `api/company.ts` + types check.
- B1: `companyProfile` store + `companyDashboard` store с epoch-guard.
- B2: `CompanyDashboardView.vue` — каркас + hero + balance widgets.
- B3: Pool widget + recent transactions list.
- B4: i18n keys (`company.dashboard.*`), null-states (no pool, empty transactions).

---

### F5.2: Продукты + Аналитика + Баланс + Settings

**Цель:** Компания видит свои продукты, аналитику продаж, управляет выводами и видит профиль (read-only в MVP — редактирование через Staff).

**API контракт (готов):**
- `GET /api/v1/products?company_id={my_id}&active_only=true|false` (Sprint 4.2) — список продуктов компании.
- `GET /api/v1/company/analytics` → `CompanyAnalyticsResponse` (Sprint 4.3 B5) — `total_revenue_cents`, `revenue_this_month_cents`, `total_options_sold` (Sprint 4.6 fix), `sales_by_month[]` (last 12 месяцев с продажами, oldest first), `sales_by_product[]` (ВСЕ продукты компании включая archived и zero-sales, sorted by revenue DESC).
- `GET /api/v1/companies/me` → `CompanyResponse` (Sprint 4.5) — full профиль для Settings.
- `GET /api/v1/withdrawals/me` (Sprint 6.3) — список выводов.
- `POST /api/v1/withdrawals` (Sprint 6.3) — запрос вывода с body `{amount_cents}`.
- `GET/PUT /api/v1/users/me/payout-details` — реквизиты.

**Задачи:**
- [ ] `src/views/company/CompanyProductsView.vue` — **новый**:
  - `companyProfile.loadIfMissing()` → `company_id`.
  - `GET /products?company_id={my_id}` (по умолчанию public endpoint отдаёт `active_only=true` → активные в продаже). Для company-роли это OK для MVP — компания видит свои активные продукты как они показываются инвесторам. **Note:** для draft / archived продуктов нужен staff endpoint (`GET /api/v1/staff/products?...`) — за пределами F5 scope, в MVP компания управляет статусом продукта через staff.
  - Карточки: pack-pricing (как в `ProductCard.vue` для Investor), `available_packages`, статус.
- [ ] `src/views/company/CompanyAnalyticsView.vue` — **новый**:
  - Использует `companyDashboard.refresh()` если ещё не загружено + `getCompanyAnalytics()`.
  - Top metrics: `total_revenue_cents`, `revenue_this_month_cents`, `total_options_sold`.
  - `sales_by_month` chart (last 12 months, oldest → newest).
  - `sales_by_product` table (ВСЕ продукты, sorted by revenue DESC) — позволяет компании увидеть какие продукты не продаются (revenue=0 не скрыт).
- [ ] `src/views/company/CompanyBalanceView.vue` — **новый**:
  - `passive_balance` берётся из **уже-загруженного** `companyDashboard` store — не делать второй вызов `/company/dashboard` (или `/dashboard/summary`) ради того же объекта.
  - Список выводов: `GET /api/v1/withdrawals/me`.
  - Кнопка "Вывести" → `POST /api/v1/withdrawals`.
  - Реквизиты: `GET/PUT /api/v1/users/me/payout-details`.
- [ ] `src/views/company/CompanySettingsView.vue` — **новый**:
  - `getMyCompany()` → `CompanyResponse`. **Не** `getCompany(id)` — public endpoint скрывает `distribution_config` и 404'ится на non-active.
  - Read-only render: name, description, price_per_unit_cents, total_supply, shares_per_option, distribution_config (форматированный JSON view).
  - Note: «Для редактирования профиля обратитесь в support» — редактирование через staff endpoints (Sprint 4.1), не через company-side UI в MVP.

**Зависимости от бэкенда:** Sprint 4.1 (`/companies` public) ✅, Sprint 4.2 (`/products`) ✅, Sprint 4.3 B5 (`/company/analytics`) ✅, Sprint 4.5 (`/companies/me`) ✅, Sprint 4.6 hotfix (installment в options_sold) ✅, Sprint 6.3 (`/withdrawals`) ✅.

**Не использовать:**
- ❌ `GET /api/v1/portfolio/me/company/{id}` для company-аналитики — это **investor**-side endpoint (показывает покупки одного investor'а в одной компании). Для аналитики продаж компании используй `/company/analytics`.
- ❌ `GET /api/v1/companies/{id}` для собственного профиля — public projection без `distribution_config`. Используй `getMyCompany()`.
- ❌ Двойной fetch `passive_balance` через `/dashboard/summary` — уже есть в `companyDashboard` store.

**Критерий готовности:** Компания видит продукты, аналитику с графиками, управляет выводами, видит профиль (read-only).

**Commit chain (план):**
- B0: `CompanyProductsView.vue` (re-используем существующий `ProductCard.vue`).
- B1: `CompanyAnalyticsView.vue` — top metrics + sales_by_month chart.
- B2: `CompanyAnalyticsView.vue` — sales_by_product table.
- B3: `CompanyBalanceView.vue` — passive balance + withdrawals list + payout details.
- B4: `CompanyBalanceView.vue` — POST /withdrawals form.
- B5: `CompanySettingsView.vue` — read-only profile render.

---

### Сводная таблица F5 endpoints

| Endpoint | Метод | Schema | Sprint |
|---|---|---|---|
| `/api/v1/companies/me` | GET | `CompanyResponse` | 4.5 |
| `/api/v1/company/dashboard` | GET | `CompanyDashboardResponse` | 4.3 B5 |
| `/api/v1/company/analytics` | GET | `CompanyAnalyticsResponse` | 4.3 B5 |
| `/api/v1/products?company_id=...` | GET | `PublicProductListResponse` | 4.2 |
| `/api/v1/withdrawals/me` | GET | `WithdrawalListResponse` | 6.3 |
| `/api/v1/withdrawals` | POST | `WithdrawalResponse` | 6.3 |
| `/api/v1/users/me/payout-details` | GET/PUT | `PayoutDetailsResponse` | — |

Все типы re-export'ятся из `frontend/src/api/types.ts` (секция `Phase F5 -- Company UI`, добавлена в Sprint 4.5 prep, `0f11197`).

---

## PHASE F6: Agent

### F6.1: Agent Hub

**Цель:** Агент управляет реферальными ссылками.

**Задачи:**
- [x] src/views/agent/AgentDashboardView.vue:
  - Виджеты: комиссии за месяц, количество рефералов, ранг в лидерборде
  - GET /api/v1/dashboard/summary — балансы
  - Quick actions: Создать ссылку, Мои комиссии
- [x] src/views/agent/AgentHubView.vue:
  - POST /api/v1/referrals/links → ReferralLinkResponse (code generated server-side)
  - GET /api/v1/referrals/links/me → ReferralLinkListResponse (paginated)
  - Каждая ссылка: код, copy button, is_active flag
  - GET /api/v1/referrals/stats/me → ReferralStatsResponse — общая статистика
- [x] src/views/agent/ReferralsView.vue:
  - Список привлечённых инвесторов (L1/L2/L3)

**Зависимость от бэкенда:** Referrals (Sprint 7.2 ✅). Permission: только role=agent.

**Критерий готовности:** Агент создаёт ссылки, видит рефералов.

---

### F6.2: Комиссии + Лидерборд + Пассивный баланс

**Цель:** Агент видит заработок и рейтинг.

**Задачи:**
- [x] src/views/agent/CommissionsView.vue:
  - GET /api/v1/agent/commissions/me → CommissionListResponse (limit/offset)
  - Каждая запись: type (commission/volume_bonus), amount_cents, level, investor_name, product_name, status, created_at
  - Фильтры: уровень, период
- [x] src/views/agent/LeaderboardView.vue:
  - GET /api/v1/agent/leaderboard → LeaderboardResponse
  - Каждая запись: rank, agent_name, volume_cents, is_me
  - Подсветка своей позиции (is_me = true)
  - snapshot_at, period_start для контекста
- [x] src/views/agent/BalanceView.vue (passive):
  - Passive balance из GET /api/v1/dashboard/summary → passive_balance
  - Кнопка "Вывести" → POST /api/v1/withdrawals (body: `{ amount_cents }`)
  - GET /api/v1/withdrawals/me — история выводов
  - Настройка реквизитов: GET/PUT /api/v1/users/me/payout-details
- [x] src/views/agent/AgentMoreView.vue:
  - Навигация к: Settings, Leaderboard, Investor Portfolio, Notifications

**Зависимость от бэкенда:** Commissions (Sprint 7.3 ✅), Leaderboard (Sprint 7.3 ✅), Withdrawals (Sprint 6.3 ✅).

**Критерий готовности:** Агент видит комиссии, лидерборд, может запросить вывод.

---

### F6 — статус реализации (✅ shipped + review follow-up)

**Реализовано (blocks A–F).** Shipped views: `ReferralsView` (downline L1/L2/L3 — маскированные investor'ы + sub-agents с never-summed метриками, sub-route CBackLink), `CommissionsView` (paginated, reversed → danger «Clawed back» badge, server total, enum'ы через `tOrRaw` — FP-15), `LeaderboardView` (is_me highlight, empty-state, period caption), `AgentBalanceView` (passive balance из shared `useDashboardStore`, история выводов на `useInfiniteScroll`, withdraw-форма с FP-04 guard, Balance→Settings CTA при отсутствии реквизитов), `AgentSettingsView` (read-only профиль + payout-details JSON-редактор + logout), `AgentMoreView` (3 tile'а — точки входа к Settings/Leaderboard/Notifications). Factual drift vs план: реализованные имена — `AgentBalanceView`/`AgentSettingsView` (не `BalanceView`), Settings — отдельный sub-route. i18n: `agent.*` ключи — en-only по policy i18n catch-up.

**Review follow-up (external code review, score 8/10):**
- **§2** (латентный баг, `AgentBalanceView`): full-screen error при закэшированном `summary` + транзиентной ошибке shared dashboard'а, retry не чистил. Фикс: `hasError` завязан на shared error только при `summary===null` + безусловный `refresh()` в loadAll (паритет с investor BalanceView).
- **§6** (`AgentSettingsView`): пустой `{}` сохранялся как «реквизиты заданы», гейт вывода залипал. Фикс: ветка `'empty'` в `payoutValidation` + `agent.settings.payout.form.errorEmpty`.
- **§3** (`AgentBalanceView`): ошибка дозагрузки истории глоталась молча. Фикс: FP-16 brake (`withdrawalsLoadMoreErrored` как `paused` в `useInfiniteScroll`) + retry-баннер + `agent.balance.withdrawals.loadMoreError`.
- **Полировка:** shared `formatDateTime`/`formatDate`/`parseAmountToCents` (float-safe парсер) вынесены в `utils/format.ts`, 4 вью (Balance/Commissions/Referrals/Leaderboard) мигрированы; commission-строки keyed по выставленному backend'ом `CommissionEntry.id` (⚠ порядок: backend id-exposure + regen `generated.ts` ДО фронт-билда); load-more спиннер в CommissionsView. Bundle: 10 файлов, 5 коммитов. Открытые ноты → TD-F19 / TD-F20 + FP-20 gap (InvestorSettings back-link).

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
  - `notifications: NotificationDeliveryResponse[]`
  - `fetchUnreadCount()` — GET /api/v1/notifications/unread-count → `{ unread_count }`
  - `fetchNotifications(page, per_page, type?, channel?)` — GET /api/v1/notifications → NotificationListResponse
  - `markRead(deliveryId)` — POST /api/v1/notifications/{id}/read → 204
  - `markAllRead()` — POST /api/v1/notifications/read-all → `{ marked_count }`
- [ ] Badge counter в CTabBar (на иконке "Главная" или bell icon)
- [ ] Notification list (slide-in panel или dedicated view):
  - Каждое уведомление: title, body, type, priority, time ago, read_at
  - Свайп или клик → markRead
  - "Отметить все прочитанными"
- [ ] Polling: `setInterval` refresh unread count каждые 30 секунд

**Зависимость от бэкенда:** Notifications REST (Sprint 8.3 ✅).

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
  - GET /api/v1/posts → PostListResponse (paginated, filters: owner_type, company_id, tag)
  - GET /api/v1/posts/{id} → PostResponse
  - Баннеры (is_banner) с кнопкой dismiss → POST /api/v1/posts/{id}/dismiss → 204
  - Анонимный доступ разрешён (get_optional_user)
- [ ] Список событий:
  - GET /api/v1/events → EventListResponse (paginated, all published)
  - GET /api/v1/events/upcoming → list[EventResponse] (next 30 days)
  - Карточка: title, дата, location, ссылка

**Зависимость от бэкенда:** Posts (Sprint 9.1 ✅), Events (Sprint 9.1 ✅).

**Критерий готовности:** Юзер видит новости и события.

---

### F9.3: Staff Content Management

**Цель:** Staff управляет постами и событиями.

**Задачи:**
- [ ] Staff CRUD для постов (permission: `content_manage`):
  - POST /api/v1/staff/posts → создать
  - PATCH /api/v1/staff/posts/{id} → редактировать
  - DELETE /api/v1/staff/posts/{id} → soft-delete
- [ ] Staff CRUD для событий (permission: `content_manage`):
  - POST /api/v1/staff/events → создать
  - PATCH /api/v1/staff/events/{id} → редактировать
  - DELETE /api/v1/staff/events/{id} → soft-delete
- [ ] Staff consistency tool (StaffMoreView):
  - GET /api/v1/staff/consistency → 18 семафоров целостности данных

**Зависимость от бэкенда:** Sprint 9.1 ✅, Sprint 6.4 ✅.

**Критерий готовности:** Staff создаёт и редактирует контент.

---

## 5. Сводка зависимостей

| Frontend Phase | Backend Phase | Статус бэка | Блокирует? |
|---------------|---------------|-------------|------------|
| F0: Инфра | — | — | Нет |
| F1: Auth | 1.1, 1.2, 1.3 | ✅ | Нет |
| F2: Компоненты + Layout | 1.3 | ✅ | Нет |
| F3: Staff | 3.1–3.3, 5.2, 5.3, 7.1 | ✅ | Нет |
| F4: Investor | 4.2, 5.1, 5.2, 6.1, 6.2, 6.4, 9.2 | ✅ | ⚠ части F4 (CompanyOverviewView, CompanyPositionView, MarketView) переписываются в Refactor 1 §1 + Refactor 2 §5.5/§7.1 |
| F5: Company | 4.1, 4.2, 6.3, 6.4, 9.2 | ✅ | Нет |
| F6: Agent | 7.1, 7.2, 7.3, 6.3 | ✅ | ⚠ Agent зеркалит investor-views; ждёт переписи Refactor 1 §1.4 + Refactor 2 §5.5/§7.1 |
| F7: i18n | — | — | Нет |
| F8: Notifications | 8.1–8.3 | ✅ | Нет |
| F9: Полировка + Posts | 9.1, 6.4 | ✅ | Нет |

**Стратегия:** F1-F5 закрыты (F5 deployed по итогам Sprint 4.5 → 4.6 → F5.1 → F5.2, см. trailer v3.7). F4 части (CompanyOverviewView, CompanyPositionView, MarketView) переписываются внутри Refactor 1 §1 + Refactor 2 §5.5/§7.1. После закрытия R1+R2 (iter 2.5 Investor frontend, iter 2.6 Public frontend, iter 2.7 Staff frontend) возвращаемся к плановым phases — F6 (Agent), F7+ далее. Новый раздел **F-Staff: Platform tab** (Refactor 1 §2-4) — расширение F3, в Frontend ТЗ v2.8 не описан, реализуется по тексту Refactor 1. Все backend gaps (G1–G5) закрыты.

---

## 6. Backend Gaps — все закрыты (v3.0)

| # | Модуль | Описание | Статус |
|---|--------|----------|--------|
| G1 | auth | `POST /auth/verify-email` + `/resend` — 6-значный код, TTL, rate limit | ✅ Закрыт |
| G2 | staff/payments | `GET /staff/payments` — list all с фильтрами (status, user_id) | ✅ Закрыт |
| G3 | purchases | `_BUYER_ROLES = {INVESTOR, AGENT}` — агенты могут покупать | ✅ Закрыт |
| G4 | installments | `_BUYER_ROLES = {INVESTOR, AGENT}` — агенты могут оформлять рассрочку | ✅ Закрыт |
| G5 | staff/kyc | `KYCRejectRequest {reason?}` — reason в audit_log | ✅ Закрыт |

---

## 7. LLM Code Review Guide (Frontend)

### FP-01: Не хардкодить API URL

```typescript
// ЗАПРЕЩЕНО:
fetch('https://api.aivis.one/api/v1/users/me')

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

// ЗАПРЕЩЕНО — window[driver] (bypasses TypeScript):
const driver = platform.getStorageDriver()
window[driver].setItem('cbs_token', token)

// ПРАВИЛЬНО — явный ternary:
const storage = platform.getStorageDriver() === 'sessionStorage'
  ? sessionStorage
  : localStorage
storage.setItem('cbs_token', token)
```

### FP-13: Referral code persistence

```typescript
// ЗАПРЕЩЕНО — потерять referral code:
router.push('/register')  // ref= query param пропал

// ПРАВИЛЬНО — сохранить при первом визите:
const ref = route.query.ref || platform.getStartParam()
if (ref) sessionStorage.setItem('cbs_referral_code', ref as string)

// Передать при регистрации:
const referral_code = sessionStorage.getItem('cbs_referral_code')
api.post('/auth/email/register', { email, password, referral_code })
```

### FP-14: После async действия → всегда `router.push('/')`

```typescript
// ЗАПРЕЩЕНО — надеяться что guard/реактивность подхватит:
await authStore.fetchMe()
// Guard will redirect... (НЕТ! Guard не срабатывает без навигации)

// ПРАВИЛЬНО — явный redirect через корневой маршрут:
await authStore.fetchMe()
await router.push('/')
// globalGuard проверит onboarding_step → redirect на нужный экран
```

Vue Router guards срабатывают только на **навигацию**, не на мутацию Pinia store. Корневой `/` + `globalGuard` = единый маршрутизатор. Применять после: регистрации, верификации, профиля, выбора роли, KYC, подписания документов — любого действия, меняющего `user.onboarding_step` или `user.role`.

### FP-15: Server-driven enums → `tOrRaw`

Любое поле от бэкенда с ограниченным набором значений (status, type, role, payment_type, kyc_status, network, provider и т.п.) рендерится в UI **строго** через `tOrRaw(t, 'scope.field.' + value, value)` из `@/utils/i18n`. Два антипаттерна исторически встречались в кодовой базе — оба эквивалентны и оба запрещены.

```typescript
// ЗАПРЕЩЕНО — raw-рендер без i18n:
<CBadge :text="item.status" />
<span>{{ item.payment_type }}</span>

// ЗАПРЕЩЕНО — инлайн идиома «translated-or-raw»:
function statusLabel(s: string): string {
  const key = `inv.balance.status.${s}`
  const translated = t(key)
  return translated === key ? s : translated
}

// ПРАВИЛЬНО:
import { tOrRaw } from '@/utils/i18n'

function statusLabel(s: string): string {
  return tOrRaw(t, `inv.balance.status.${s}`, s)
}

// В template прямой вызов тоже разрешён:
<CBadge :text="tOrRaw(t, `inv.balance.status.${item.status}`, item.status)" />
```

Почему именно raw fallback. Бэкенд может добавить значение enum'а раньше, чем i18n-catalogue догонит — обычный рассинхрон релизов. Raw-токен (`approved`, `frozen`) в UI читается не идеально, но не ломает экран и сразу опознаётся QA как «i18n отстаёт». Hard-fail (blank badge или литеральный dotted-path `inv.balance.status.approved`) хуже по обоим критериям.

Исключения. Сырой ID (UUID, hash, user_id slice) — не enum, `tOrRaw` к нему не применяется. Форматирование цифр/денег/дат — через свои утилиты (`formatPrice`, `formatSignedPrice`, `formatNumber`), правила FP-06/FP-07. Свободный пользовательский текст (имя, описание, комментарий) рендерится как есть.

### FP-16: Infinite scroll — retry-storm brake

Любой Pinia-store с пагинацией через `useInfiniteScroll` обязан выдавать флаг `loadMoreErrored: Ref<boolean>` и action `clearLoadMoreError()`, а также **самостоятельно** выставлять флаг при ошибке в `loadMore()`. View прокидывает этот флаг в `useInfiniteScroll` как четвёртый параметр (`paused`). Это останавливает бесконечные повторные попытки при устойчивой ошибке сети/бэкенда — без флага IntersectionObserver переигрывает каждое пересечение сентинела и может быстро уронить бэкенд 429'кой или сгенерировать каскад идентичных fetch'ей.

```typescript
// ❌ ЗАПРЕЩЕНО — silent swallow + три-аргументный useInfiniteScroll:
async function loadMore() {
  try { /* ... */ } catch {
    // user can scroll back and retry
  }
}
useInfiniteScroll(sentinelRef, hasMore, loadMore)

// ✅ ПРАВИЛЬНО — store:
const loadMoreErrored = ref(false)

async function fetchFirstPage() {
  loadMoreErrored.value = false  // fresh start clears stale pause
  /* ... */
}

async function loadMore() {
  if (loading.value || !hasMore.value || loadMoreErrored.value) return
  try { /* ... */ } catch {
    if (epoch !== fetchEpoch) return
    loadMoreErrored.value = true
  }
}

function clearLoadMoreError(): void {
  loadMoreErrored.value = false
}

// ✅ ПРАВИЛЬНО — view:
const { hasMore, loadMoreErrored } = storeToRefs(store)

useInfiniteScroll(sentinelRef, hasMore, store.loadMore, loadMoreErrored)

function retryLoadMore(): void {
  store.clearLoadMoreError()
  void store.loadMore()
}
```

```vue
<!-- Retry-баннер рядом с sentinel'ом: -->
<div
  v-if="hasItems && store.loadMoreErrored && !store.loading"
  class="loadmore-error"
>
  <span>{{ t('...errorTitle') }}</span>
  <CButton variant="outline" size="sm" @click="retryLoadMore">
    {{ t('common.retry') }}
  </CButton>
</div>
```

Когда применять. Строго для stores, управляющих paginated списками с infinite-scroll сентинелом (`stores/transactions`, `stores/portfolio`, будущие `stores/agent-commissions` и т.п.). Локальные `ref`-based paginated списки внутри view (например, `BalanceView` payment history) могут отложить миграцию до появления реальных жалоб — объём истории у одного юзера мал, шторм маловероятен.

Совместимость. `useInfiniteScroll(sentinelRef, hasMore, loadMore)` — трёхаргументный вызов — остаётся легитимным для не-paginated кейсов и старых call-site'ов (`MarketView` и др.). Четвёртый параметр опциональный.

### FP-17: Epoch guard на async re-entrance

Введено и кодифицировано в F4.4 (применено в `stores/portfolio` two-epoch, `stores/dashboard`, `stores/transactions`, `composables/useCertificateBlob`, inline `openDoc` в `InvestorDocsView`).

**Правило.** Любой async actor (store action / composable `load` / view-local fetch), который может быть **вызван повторно** до разрешения предыдущего await-chain, обязан иметь epoch guard.

**Паттерн.**

```ts
let epoch = 0

async function doThing(arg: string): Promise<void> {
  const mine = ++epoch
  loading.value = true
  try {
    const next = await fetchSomething(arg)
    if (mine !== epoch) return          // superseded — drop result
    data.value = next
  } catch (err) {
    if (mine !== epoch) return          // superseded — don't flip errored
    errored.value = true
  } finally {
    if (mine === epoch) {                // only the winner touches loading
      loading.value = false
    }
  }
}

function reset(): void {
  epoch += 1                             // invalidate any in-flight call
  data.value = null
  loading.value = false
}
```

**Ключевые моменты:**
- Epoch — `let`, не `ref` (не нужна реактивность, только монотонность).
- Инкремент **в начале** action'а (до любых early return'ов — иначе параллельный вызов может затереть error-state).
- `reset()` / `clear()` тоже бампит epoch (post-logout fetch не должен repopulate).
- Если action создаёт ресурс (blob URL, WebSocket, AbortController) — проигравший epoch должен **сам освободить ресурс** перед выходом (`URL.revokeObjectURL` для blob, `.abort()` для controller).

**Когда НЕ нужен.** Строго однократные fetch'и за жизнь компонента (один `onMounted` без Retry-кнопки, без зависимости от reactive prop'а).

**Нарушение = латентный баг** — сразу не проявится, всплывёт на медленной сети / rage-tap'е / быстром табе. Ревью обязано проверять этот паттерн.

---

### FP-18: Все навигации через `safeNavigate`

Закреплено в iter 2.7 (R28-R33). Закрывает BUG-28-01, BUG-29-01 и весь класс "NavigationFailure leaked into outer ApiResponseError catch → false error toast".

**Правило:** каждый `router.push()` / `router.replace()` в codebase — **только** через helper `safeNavigate(...)` из `frontend/src/composables/safeNavigate.ts`. Без исключений, кроме одного документированного (см. ниже).

```typescript
// ЗАПРЕЩЕНО — void router.push:
void router.push({ name: 'investor-companies' })

// ЗАПРЕЩЕНО — inline .catch с собственным фильтром:
router.push({ name: 'investor-companies' }).catch(err => {
  if (isNavigationFailure(err, NavigationFailureType.duplicated)) return
  console.error(err)
})

// ПРАВИЛЬНО — fire-and-forget:
void safeNavigate(
  router.push({ name: 'investor-companies' }),
  '[InvestorDashboardView] to companies list',
)

// ПРАВИЛЬНО — await, когда UI-state должен дождаться навигации
// (submitting flag, finally блок):
async function confirm() {
  submitting.value = true
  try {
    await api.submit(...)
    await safeNavigate(
      router.push({ name: 'portfolio' }),
      '[PurchaseView] post-submit to portfolio',
    )
  } catch (err) {
    submitting.value = false
    handleError(err)
  }
}
```

**Контракт `safeNavigate`:**
- **No-throw, no-rethrow.** Даже на hard error (network, internal Vue Router error) helper не пробрасывает — логирует `console.error` с `context` prefix. Это критично: иначе NavigationFailure пробивается в outer `try { ... } catch (err) { handlePlanError(err) }` и юзеру показывается "purchase failed" вместо реальной природы (BUG-28-01).
- `context` — строка `'[ComponentName] short description'`. Grep-friendly.
- Не расширять helper. Если возникнет use-case с fallback URL / retry logic — создавать **параллельный** helper (`safeNavigateWithFallback`), не перегружать canonical. Anti-creep policy.
- Импорты `isNavigationFailure` / `NavigationFailureType` из `vue-router` — **только** в `safeNavigate.ts` и в единственном документированном исключении.

**Единственное исключение — `useAvatar.ts:145`.** Zombie-staff-token guard намеренно трактует `NavigationFailureType.aborted` как **ожидаемый** результат (route-guard отверг redirect), а всё остальное — `console.warn`. Filter shape отличается от `safeNavigate`'s (там `aborted` — benign noise). Документировано inline-комментарием с ссылкой на этот FP.

**Note (iter 2.8 closure):** до iter 2.8 в public-flow было ещё 6 файлов с inline `isNavigationFailure` (TD-FP18-PUBLIC-FLOW). Iter 2.8 (`e7238f5`) мигрировал их все на `safeNavigate`, −110 строк boilerplate. Теперь **`useAvatar.ts:145` — действительно единственное** разрешённое отступление. Если новый код хочет inline `isNavigationFailure` — это **bug в подходе**, не feature; см. §4.1.2 (anti-creep policy).

**Не добавлять новые исключения.** Если кажется что нужно — 90% случаев это `safeNavigate`-совместимая ситуация, и нужно перечитать docstring. 9% — нужен параллельный helper. 1% — действительно one-off, inline `.catch` с явным комментарием `// SPECIAL CASE -- NOT using safeNavigate, see <reason>`.

---

### FP-19: Single CHeader policy

Внутри `InvestorShell`, `AgentShell`, `CompanyShell`, `StaffShell`, `PublicShell` — **только shell** рендерит `<CHeader>`. Views **не имеют собственного `<CHeader>`**.

Закреплено в iter 2.7 (B1+B2, R32). До этого 8 views рендерили свой CHeader поверх shell'ового — две parallel sticky-полосы ~104px (~15.5% iPhone viewport).

**Как view предоставляет title:**

- **С hero-блоком** — page title это `<h1>` hero (`pd__hero-title`, `co__hero-name`, `iv__hero-title`). Дополнительного title-элемента не нужно.
- **Без hero, с back-link** — inline `<.<prefix>__page-header>` блок содержит back-link + `<h1>`:

```vue
<div class="cp__page-header">
  <CBackLink :label="t('inv.companyPosition.backLink')" @click="goBack" />
  <h1 class="cp__page-title">{{ headerTitle }}</h1>
</div>
```

- **Без hero, без back-link (top-level tab)** — просто inline `<h1>` сверху. Pattern из `InvestorMoreView`, `InvestorSettingsView`.

**Когда добавлять back-link:**

- Sub-route reached via tap / deep-link → back-link обязателен.
- Top-level tab via CTabBar → **без** back-link (нет originating screen).
- Intentional design exception → без back-link, документировать template-комментарием (пример: `PurchaseView`).

**Trade-off:** sticky-title regression. Старый paradigm имел sticky `<CHeader>` с title. Новый — title inline в hero/page-header, **не sticky**. Принято. Если в будущем конкретный view потребует sticky title — pre-designed Variant B fallback через Teleport в shell-CHeader. **Не добавлять Teleport infrastructure превентивно** — ждать real UX-signal.

---

### FP-20: Все inline back-links через `<CBackLink>`

Закреплено в iter 2.7 (B3, R33). До этого 7 views имели локальные `.pd__back`, `.co__back`, `.cp__back` etc. — каждый с ~25 строками дублированной CSS.

**Файл:** `frontend/src/components/ui/CBackLink.vue`, экспорт через `@/components/ui` barrel.

**API:**

```vue
<CBackLink :label="t('inv.product.backLink')" @click="goBack" />
```

- `label` — **уже переведённая** строка. Caller владеет i18n (зеркало `CButton` со slot-content, `CEmptyState` с `:title`/`:description`).
- `@click` — propagation от root `<button>` через Vue 3 native event inheritance, без `emits` declaration.
- Focus ring (WCAG 2.1 §2.4.7) — `:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }` **внутри** компонента, применяется ко всем consumer'ам.

**Margin-less.** Positioning — забота view, не компонента. Два positioning idiom'а:

**Sub-pattern A — back-link над hero** (используется когда view имеет hero с `<h1>`):

```vue
<div class="pd__back-row">
  <CBackLink :label="t('inv.product.backLink')" @click="goBack" />
</div>

<style>
.pd__back-row {
  display: flex;
  margin: var(--space-md, 16px) var(--space-md, 16px) 0;
}
</style>
```

**Sub-pattern B — back-link внутри inline page-header** (когда нет hero):
см. FP-19 пример выше.

**ЗАПРЕЩЕНО:** новые `.<prefix>__back` CSS-классы, inline `<button>` markup с копией стилей.

**Lesson `extract first, fix a11y once`:** focus-ring был добавлен через одну правку в `CBackLink`. До extraction это была бы 7-местная правка с риском забыть. Pattern: при extracting shared UI с a11y requirements — extract first, потом делаешь a11y fix в одном месте.

---

### FP-21: History-aware `goBack()` handler

Стандартный pattern для back-link, который должен идти "куда юзер пришёл, fallback на sensible target при deep-link":

```typescript
function goBack(): void {
  if (window.history.state?.back) {
    router.back()
    return
  }
  void safeNavigate(
    router.push({ name: fallbackRouteName.value }),
    '[ComponentName] back fallback to <target>',
  )
}
```

**Правила:**

- `window.history.state?.back` — платформенный API, **не** `router.options.history.state.back` (Vue Router wrapper, функционально идентичный, но less idiomatic — R32 STYLE-32-03 deprecated его).
- Optional chain `?.` — защита от custom history implementations где `state` может быть `null`.
- Fallback push **всегда** через `safeNavigate` (FP-18).
- Fallback target name обязателен. Никогда не использовать `router.back()` без fallback — на deep-link entry он silent fail.

**Defensive guards для route params.** Если fallback target требует params которые могут быть malformed:

```typescript
const id = companyId.value
if (!id) {
  // onMounted guard уже redirect'нул для empty id, но если как-то
  // оказались тут — отправляем юзера на known-safe route.
  void safeNavigate(
    router.push({ name: companiesListRouteName.value }),
    '[ProductsByCompanyView] back fallback to companies list (no id)',
  )
  return
}
void safeNavigate(
  router.push({ name: companyOverviewRouteName.value, params: { id } }),
  '[ProductsByCompanyView] back fallback to company overview',
)
```

**Переиспользование existing handlers.** Если у view уже есть handler с подходящей semantics (`InstallmentView.cancel()` — history-aware, правильный target) — **переиспользовать его** для back-link. Не плодить дубль `goBack()` с той же логикой.

---

### FP-22: Role-aware route names через computed + `isAgentShell`

Когда shared view рендерится под `/investor/*` и `/agent/*`, и должен push'ить на role-aware target:

```typescript
const fooRouteName = computed<string>(() =>
  isAgentShell(route) ? 'agent-foo' : 'investor-foo',
)
```

**Правила:**

- Резолвить через `isAgentShell(route)` из `@/router/helpers` (читает `route.meta.shell`), **не** string-matching по `route.path`.
- `computed`, не constant — `route.meta.shell` приходит от shell-wrapper, зависит от того какой shell mounted view.
- Naming `<feature>RouteName` для grep-friendliness.

Несколько таких computed'ов в shared view (`companiesListRouteName`, `productDetailRouteName`, `companyOverviewRouteName`) — норма. Каждый именует конкретный role-bridged route.

---

### FP-23: Role-conditional CTA — template guard + defensive role check

Закреплено в iter 2.6 (R26, FE-26-01) после реального UX-бага "кнопка ничего не делает".

**Контекст бага.** Standard `safeNavigate`/NavigationFailure filter (`duplicated | cancelled | aborted`) поглощает rejection от `globalGuard::meta.roles` — это тип `aborted`. То есть если CTA пушит на route куда роль visitor'а попасть **не может**, silent swallow создаёт UX-баг "кнопка ничего не делает".

**Двойная защита (обязательна для role-conditional CTA):**

1. **Template guard** через `canNavigateTo*` computed — скрывает CTA для несовместимых ролей.
2. **Defensive role check** в handler с `console.warn` — на случай если template guard пропустил.

```typescript
const canNavigateToPurchase = computed<boolean>(() => {
  if (!authStore.isAuthenticated) return true  // visitor: push на register
  return authStore.role === 'investor' || authStore.role === 'agent'
})

function onBuyNow() {
  if (!authWall.requireAuth('purchase')) return  // visitor → register
  if (!canNavigateToPurchase.value) {
    console.warn('[PublicProductDetailView] buyNow blocked: role=', authStore.role)
    return
  }
  void safeNavigate(
    router.push({ name: 'investor-purchase', params: { id: product.value.id } }),
    '[PublicProductDetailView] to purchase',
  )
}
```

```vue
<CButton
  v-if="canNavigateToPurchase"
  :label="buyButtonLabel"
  @click="onBuyNow"
/>
```

**Применять для любой role-conditional навигации.** Перед каждым role-aware `router.push` сверять с `router/guards.ts::globalGuard` + `meta.roles` целевого route'а. Если visitor попасть не может — CTA скрыта через template, plus defensive check в handler.

---

### FP-24: Lazy import — stub-файл обязателен в том же батче

Закреплено в iter 2.6 (Batch 2 build-fix).

Vite/Rollup при production build резолвит **все** dynamic imports (`() => import('@/views/...')`). Несуществующий target → пустой chunk → `vite-plugin-pwa` падает с `"Couldn't find configuration for either precaching or runtime caching"`. **Не** runtime error при открытии route — **build-time crash**.

**Правило:** если router вводит route name в Batch N с расчётом на view, реализуемый в Batch N+1 — **в Batch N обязан лежать stub-файл** по реальному пути. Stub — тривиальный "Coming soon" компонент. Реальная имплементация заменит в следующем батче.

**ЗАПРЕЩЕНО:** "разрешится в следующем батче, build пройдёт runtime-resolve". Не пройдёт.

---

### FP-25: Self-hiding sections pattern

Закреплено в iter 2.6 (R2 §7.1/§7.2). Применяется ко всем "опциональным" секциям view (Roadmap, Products teaser, Attachments, etc.):

- `loading` → секция рендерится (spinner внутри).
- `errored` → секция рендерится (error + retry внутри).
- `success && empty` → секция **не рендерится** (`<!---->`).
- `success && items` → секция рендерится.

**Parent view не оборачивает в `v-if`.** Секция сама знает рендериться ей или нет. Иначе parent тащит знание о data state каждой секции.

---

### FP-26: Auth-state branching CTA pattern

Закреплено в iter 2.6 (Batch 5, Batch 6).

Для CTA, поведение которой зависит от auth-state visitor'а (например, "Buy" на public product detail):

- **Аноним:** CTA видна, label = `t('public.<view>.purchaseCTA')` ("Register to buy") → `useAuthWall().requireAuth(action)` → push на register с `?next=<current path>&intent=<action>`.
- **investor / agent:** CTA видна, label = `t('inv.<view>.<action>')` ("Buy now") → выполняется action как обычно (push на authenticated route).
- **staff / company / other:** CTA **скрыта** через FP-23 template guard.

```typescript
const buyButtonLabel = computed(() => 
  authStore.isAuthenticated
    ? t('inv.product.buyNow')
    : t('public.productDetail.purchaseCTA')
)
```

Этот pattern применяется **превентивно**, не после ревью-замечания. Любая CTA на public surface, ведущая к auth-required action — через FP-26 + FP-23 связку.

---

### FP-27: i18n reuse — domain-neutral vs domain-specific

Закреплено в iter 2.6.

При выборе "новый ключ под `public.*` / переиспользовать existing `inv.*`":

- **Domain-specific** под `public.*` — marketing-tone ("Discover companies", "Register to ..."), error messages, текста с public-контекстом.
- **Domain-neutral** — переиспользовать существующее (`inv.path.*` для documents L1 labels, `inv.product.*` для product detail fields like "Price per pack", "Description", "Buy now", "+N bonus units", "Sold out").

Принцип: **семантика** определяет ключ. Если phrase идентична в public и auth flow по смыслу — переиспользуем. Если phrase domain-specific — отдельный ключ под `public.*`.

**i18n keys для back-link.** Naming pattern: `<scope>.<viewname>.backLink`. Value — human-context-specific "Back to X" string ("Back to companies", "Back to portfolio"), не generic "Back".

**Семантически разные ключи могут иметь одинаковое translation value — это нормально.** Например:

| Key | Context | Phrasing intent |
|---|---|---|
| `inv.product.backToMarket` | Empty-state CTA когда product не загрузился | "this product is gone, get back to catalogue" |
| `inv.product.backLink` | Inline back-link над hero, loaded product | "step out of this product, back to catalogue" |

Оба переводятся как "Back to companies", но контексты разные. UX может перефразировать один без другого. **Не дедуплицировать i18n values** — keys семантические, values отображательные.

---

### Policy — i18n catch-up

**Решение (May 2026, boss):** новые ключи добавляются **только в `en.json`** во время feature-работы. `ru.json`, `de.json`, `ar.json` будут batch'ем в конце, перед public launch.

Это **не tech debt** — это policy. Не флажить в review как "deferred", не записывать в TD-list. `vue-i18n` `fallbackLocale: 'en'` работает корректно, single-user (boss) до launch'а — отсутствие переводов не блокер.

Catch-up batch перед launch:
- Все ключи добавленные с iter 2.6 и далее.
- RTL audit для `ar.json` (back-link arrow-icon направление).
- Native-speaker review для tone consistency.

---

### Self-check checklist для review

Перед презентацией каждого батча — пройти этот checklist. Каждый пункт с §-ссылкой на FP / lesson.

```
[ ] Нет <CHeader> внутри view (shell рендерит)                          FP-19
[ ] Каждый router.push / router.replace обёрнут в safeNavigate          FP-18
[ ] isNavigationFailure / NavigationFailureType импортированы только
    в safeNavigate.ts и useAvatar.ts                                    FP-18
[ ] Все back-links через <CBackLink>, не inline <button>                FP-20
[ ] Нет новых .<prefix>__back CSS-классов                               FP-20
[ ] History-aware handlers используют window.history.state?.back        FP-21
[ ] safeNavigate context = '[ComponentName] description'                FP-18
[ ] Role-aware route names — computed через isAgentShell                FP-22
[ ] Role-conditional CTA имеет template guard + defensive role check    FP-23
[ ] try/catch вокруг submit+navigate — await safeNavigate (не void)     FP-18
[ ] Новые i18n keys — только в en.json (policy, не debt)
[ ] Lazy import target существует физически в том же батче              FP-24
[ ] Back-link target route name существует в router/index.ts
[ ] Удалённый prop binding — проверить computed/ref на dead-code
[ ] Baseline check: git status + git fetch + сверка локального HEAD     iter 2.7 D lesson
    с origin/main ДО старта блока
[ ] Backend rename → grep на orphan frontend компоненты                 iter 2.7 lesson
    (lesson из CertificateSheet.vue — backend переименовался в iter 2.4,
    frontend orphan жил до iter 2.7)
```

**Grep-команды для self-check:**

```bash
# 1. Любой router.push/replace без safeNavigate wrap:
grep -rnE "(void |await )?router\.(push|replace)\(" frontend/src \
  | grep -v "safeNavigate"

# 2. isNavigationFailure импорт вне разрешённых файлов:
grep -rn "isNavigationFailure\|NavigationFailureType" frontend/src \
  | grep -v "safeNavigate.ts\|useAvatar.ts"

# 3. Inline <CHeader> в views (не layouts/):
grep -rn "<CHeader" frontend/src/views/

# 4. Старые back-link классы:
grep -rnE "__back[^-]" frontend/src/

# 5. Baseline check ДО старта работы:
git status              # должно быть clean
git fetch origin
git log HEAD..origin/main --oneline  # пусто? значит локальный = origin
# Если что-то выводится — git merge --ff-only origin/main перед началом
```

Если хоть один grep что-то нашёл — fix перед презентацией. Lesson iter 2.7 Block D: локальная база может отставать от `origin/main` на несколько коммитов (предыдущий блок запушился пока чат не fetch'нул) → "свежие" файлы из брифа окажутся stale → потерянное время на confusion. Fast-forward проверка дешевле отлова расхождения по ходу.

---

## 8. Tech Debt (Frontend)

Выявлен в ходе code review Phase F3 (score 6.5 → 9/10). Не блокирует MVP, закрывается после F4–F6.

### TD-F01: Инфраструктура

| # | Описание | Приоритет | Когда |
|---|----------|-----------|-------|
| TD-F01a | `Dockerfile:13` — `npm install` → `npm ci` (детерминированные сборки) | 🟡 | Перед staging |
| TD-F01b | `nginx.conf:46` — `connect-src 'self' https://api.aivis.one` захардкожен. Параметризовать через ENV / nginx template при смене `VITE_API_BASE_URL` | 🟡 | Перед staging |
| TD-F01c | `nginx.conf` — добавить `Strict-Transport-Security`, `gzip_static on` | 🟢 | При production |
| TD-F01d | `manifest.json` — добавить `id`, `scope`, `lang` (PWA Lighthouse) | 🟢 | При production |
| TD-F01e | `package.json` — добавить `"engines": { "node": ">=22" }` | 🟢 | При production |

### TD-F02: Тесты

| # | Описание | Приоритет | Когда |
|---|----------|-----------|-------|
| TD-F02a | Установить `vitest` + `@vue/test-utils` | 🟡 | Отдельный спринт после F5 |
| TD-F02b | `router/guards.test.ts` — таблица сценариев auth × onboarding × role | 🟡 | С TD-F02a |
| TD-F02c | `stores/auth.test.ts` — restoreSession, loginViaEmail, 401 → _clearSession | 🟡 | С TD-F02a |
| TD-F02d | `api/client.test.ts` — 401, 422, 204, timeout (vi.useFakeTimers) | 🟡 | С TD-F02a |
| TD-F02e | `views/staff/StaffKYCView.test.ts` — approve/reject + double-submit guard | 🟢 | После TD-F02a |

### TD-F03: Рефакторинг

| # | Описание | Приоритет | Когда |
|---|----------|-----------|-------|
| TD-F03a | `AuthShell.vue` + `assets/auth.css` — извлечь общий layout для 7 auth/onboarding views. ~1500 строк дублированного CSS | 🟡 | После F4, перед F6 |
| TD-F03b | Inline SVG в auth-views → заменить на `lucide-vue-next` (уже используется в staff views) | 🟢 | С TD-F03a |
| TD-F03c | `useDisplayName(user)` composable — дублируется в StaffDashboardView, StaffMoreView, App.vue | 🟢 | С TD-F03a |
| TD-F03d | `UserProfile` typed interface вместо `Record<string, unknown>` + `as` cast повсюду | 🟢 | С TD-F03a |
| TD-F03e | `CTabBar` — иконки как Vue-компоненты в `tabs.ts`, убрать `iconMap` dictionary | 🟢 | Nice-to-have |
| TD-F03f | `api/types.ts` — генерация из OpenAPI бэкенда (`openapi-typescript`) | 🟢 | После стабилизации API |
| TD-F03g | `ALL_PERMISSION_KEYS` в `StaffUsersView` — добавить `satisfies readonly StaffPermissionKey[]` для защиты от type drift при добавлении новых permission | 🟢 | С F4 |

### TD-F04: UX-полировка (avatar mode)

| # | Описание | Приоритет | Когда |
|---|----------|-----------|-------|
| TD-F04a | UUID-валидация `target_user_id` на клиенте (regex check перед POST) | 🟡 | С F4 |
| TD-F04b | Avatar-баннер скрыть поверх LoadingView (`&& isReady`) или добавить `isReady` в условие | 🟢 | С F4 |
| TD-F04c | Дашборд грузит полный `agent-applications` ради `.length` — рассмотреть отдельный count-endpoint или включить в `DashboardStatsResponse` на бэке | 🟢 | После F6 |

### TD-F05: Прочее

| # | Описание | Приоритет | Когда |
|---|----------|-----------|-------|
| TD-F05a | `OnboardingKYCView` polling — нет лимита попыток / экспоненциального backoff при долгой недоступности бэка | 🟢 | F9 (полировка) |
| TD-F05b | `api/client.ts:154` — `parseValidationErrors` для не-массива возвращает `String(detail)`, что для объекта даст `"[object Object]"`. Заменить на `JSON.stringify` | 🟢 | С TD-F03a |
| TD-F05c | `CButton` — при `loading=true` + `variant="outline"` белый спиннер не виден на прозрачном фоне | 🟢 | F9 (полировка) |
| TD-F05d | `_saveReferralCode` (`useAuth.ts`) — валидировать формат referral code на клиенте (`/^[A-Za-z0-9_-]{4,40}$/`) | 🟢 | С F6 (Agent) |
| TD-F05e | UI "Logout from all sessions" — бэкенд `POST /auth/logout-all` существует, но не используется | 🟢 | F9 (полировка) |

### TD-F06: Legal + Verify

| # | Описание | Приоритет | Когда |
|---|----------|-----------|-------|
| TD-F06a | `public/legal/{en,ru,de,ar}/*.html` × 20 файлов содержат Lorem ipsum. Placeholder до юриста. Pre-launch blocker, не код-блокер. CI-гейта на Lorem намеренно нет — проверяется в release checklist перед production | 🟡 | Pre-launch |
| TD-F06b | `VerifyEmailView` resend cooldown не персистентный: таймер 60s живёт в компонентном `ref`, `F5` / navigate away / обратно — сброс. Надо: сохранять `cooldownUntil` timestamp в `sessionStorage`, при mount сверяться с `Date.now()`. Дополнительно — очищать cooldown когда бэк возвращает `code_expired` (смысл ждать пропадает) | 🟡 | С F4 |
| TD-F06c | `OnboardingDocsView` не использует `doc.required_for_roles` в UI. Поле есть в типе, но никакой chip `"For agents only"` рядом с названием не показывается. Решение: не показывать — юзер и так видит только свои документы. Оставлено как nice-to-have только если продукт потребует | 🟢 | Nice-to-have |
| TD-F06d | Нет frontend-тестов вообще (backend: 33 файла `test_*`). Установка `vitest` + тесты на guards / stores / api.client — TD-F02a/b/c/d уже заведены | 🟡 | Отдельный спринт после F5 |

### TD-F07: Share Pool Alignment (follow-up к backend Sprint 4.3) — ✅ Closed in Sprint 4.4

Парная задача к backend TD-071 — закрыта полностью одним каскадом коммитов в Sprint 4.4 (после VELO Migration). Все шесть подпунктов реализованы; механический rename `units`/`sold_units` → `package_size`/`available_packages` плюс пара UX-апгрейдов из B7 (двухуровневый pack-price) сверху.

| # | Описание | Приоритет | Когда |
|---|----------|-----------|-------|
| TD-F07a | ✅ **Закрыт в Sprint 4.4 (B7 + VELO).** `frontend/src/api/types.ts` — handwritten unions удалены, `PublicProductResponse` и `PublicProductDetailResponse` берутся напрямую из `generated.ts` (single source of truth = backend OpenAPI). Поля `package_size` / `available_packages` приходят из бэка через автоген, drift невозможен. | 🔴 | ✅ Done |
| TD-F07b | ✅ **Закрыт в Sprint 4.4 B7.** `frontend/src/components/shared/ProductCard.vue` использует `p.available_packages` напрямую (без вычитания). Двухуровневый price block: `inv.pricePerPack` (primary) + `inv.priceLabel` per-unit reference (secondary). Ключ `inv.market.packsAvailable` добавлен. | 🔴 | ✅ Done |
| TD-F07c | ✅ **Закрыт в Sprint 4.4 B7.** `frontend/src/views/investor/ProductDetailView.vue` мигрирован: первый stat — pack price, sold-out CTA через `product.available_packages === 0`, label «AVAILABILITY» → «PACKS AVAILABLE». В Sprint 4.4 follow-up здесь же дропнут `?? []` на `product.installments` (бэк сделал поле required). | 🔴 | ✅ Done |
| TD-F07d | ✅ **Закрыт в Sprint 4.4 B7.** `frontend/src/i18n/locales/{en,ru,de,ar}.json` — `inv.pack`, `inv.pricePerPack` (×2 контекста — карточка + детали), `inv.market.packsAvailable` добавлены. Старые `inv.priceLabel` / `inv.pricePerUnit` удалены за ненужностью. | 🔴 | ✅ Done |
| TD-F07e | ✅ **Закрыт в Sprint 4.4 B7.** `frontend/src/stores/products.ts` прокидывает поля без трансформаций — типы автоматически проверились через `vue-tsc` (zero errors на финальном build'е). | 🔴 | ✅ Done |
| TD-F07f | ✅ **Закрыт в Sprint 4.4 deploy.** Реальная VPS-проверка: `cbshome update` выполнен, `seed_storefront` создаёт 21 продукт + 6 пулов с `equity_percent=100%`, `available_packages` показывает realistic числа (`1_000_000 / 100 = 10_000` packages по дефолту). 362/362 теста зелёные, фронт собирается чистым vue-tsc. | 🔴 | ✅ Done |

**Дополнительно в Sprint 4.4 (за рамками изначального TD-F07 scope):**
- `auth.ts` получил `role: UserRole | null` через `asUserRole()` runtime guard и новый `kycStatus: KycStatus | null` через `asKycStatus()`. Compile-time exhaustiveness на union'ах (паттерн `as const satisfies readonly UserRole[]`) — добавление новой роли в union без обновления runtime массива становится ошибкой компиляции.
- `InvestorSettingsView.vue` использует `authStore.role === 'investor'` / `authStore.kycStatus === 'approved'` (typed compares вместо raw user-объекта).
- `InstallmentView.vue` дропнул `?? []` в `noPlans` computed (schema-cleanup на бэке гарантирует массив).
- ProductCard.vue получил `align-self: flex-start` вместо magic-number `padding-top: 4px` для выравнивания availability-counter с pack-price line.
- 2 новых backend теста на `price_per_pack_cents` (round-trip через list + detail) — `tests/test_products_pack_pricing.py`.
- Регресс fix: `sessionStorage.removeItem('cbs_referral_code')` восстановлен в обоих flow `auth.ts` (был потерян при rewrite в коммите B7).

Детальная спецификация — в `AIVIS-Share-Pool-Refactor.md` (v2.4).

### TD-F08: F4.2 Polish & Follow-ups

Выявлены в ходе code review Phase F4.2 (score 9.8–9.9). Не блокируют F4.3/F4.4, фиксируются для консолидации в соответствующих спринтах или при появлении ≥N потребителей.

| # | Описание | Приоритет | Когда |
|---|----------|-----------|-------|
| TD-F08a | `BalanceResponse` и `Public*` (products, companies) не эмитят поле `currency`. UI опирается на соглашение «всё USD cents»; `formatPrice(cents, product.currency)` вызывается с `currency === undefined`, падает на дефолт `'USD'`. При введении мультивалютности — добавить `currency?: string` в Pydantic-схемы на бэке и в TypeScript-типы на фронте, параметризовать потребителей. Пометки `// TD-F08a` в F4.2 views (PurchaseView / InstallmentView / ProductDetailView) | 🟡 | С мультивалютным контрактом |
| TD-F08b | `api/installments.ts` — `listMyPlans` / `getPlanDetail` написаны в F4.2 задел под F4.4 без текущего потребителя. Если F4.4 Portfolio задействует — снять TD; если нет — удалить | 🟢 | F4.4 |
| TD-F08c | Backend issues `error_code` в 4xx `detail` payload (`kyc_required`, `insufficient_balance`, `product_inactive`, `template_mismatch`). Frontend error handlers в PurchaseView / InstallmentView (и будущих withdraw / transaction flows) заменяют regex-discriminator на switch по `code`. Сейчас в каждом `handleXError` стоит `// TD-F08c: replace regex with backend error_code` | 🟡 | BE + FE совместно, после Sprint 4.3 |
| TD-F08d | Backend `/installments/preview` endpoint (или аналогичное поле в `InstallmentPlanResponse` ответа `POST /products/{id}/installment` — preview до создания не существует сейчас) возвращает материализованный tranche breakdown с точным `units_unlocked` per tranche. Frontend `utils/installmentPlans.getTrancheUnits` уходит в архив — зеркало scheduler math в двух языках устраняется. Пометка `// TD-F08d` в util | 🟢 | BE + FE совместно, после F4.4 |
| TD-F08e | ✅ **Закрыт в F4.3 B1.1** (`7c57ba7`). `src/utils/querystring.ts` создан, 6 потребителей мигрированы (2 новых из F4.3 + 4 существующих: products, companies, installments, admin). Ни одного ручного `URLSearchParams` в `api/*` не осталось | 🟢 | ✅ Done |

### TD-F09: F4.3 Polish & Follow-ups

Выявлены в ходе code review Phase F4.3 (score 9.8). Не блокируют F4.4, фиксируются для консолидации одним grooming-коммитом в начале F4.4 Portfolio.

| # | Описание | Приоритет | Когда |
|---|----------|-----------|-------|
| TD-F09a | ✅ **Закрыт в F4.4 B0.** `formatSignedPrice(cents, currency?)` извлечён в `src/utils/format.ts`. Семантика `cents === 0` зафиксирована как «без знака» (фикс бага TransactionsView, которая показывала `+$0.00`). Мигрированы 2 call-site'а: `TransactionsView.formatAmount` (функция удалена, вызов в template прямой), `TransactionDetailSheet.signedAmount` (computed упростился до одной строки) | 🟢 | ✅ Done |
| TD-F09b | ✅ **Закрыт в F4.4 B0.** `tOrRaw(t, key, raw)` создан в новом `src/utils/i18n.ts`. Мигрированы 5 call-site'ов: `BalanceView.statusLabel` + `BalanceView.typeLabel`, `TransactionsView.typeLabel`, `TransactionDetailSheet.typeLabel` + `TransactionDetailSheet.keyLabel`. Паттерн зафиксирован правилом **FP-15** | 🟢 | ✅ Done |
| TD-F09c | `TransactionDetailSheet.copyValue` не имеет `copying` ref (в отличие от `InvestorDepositView.copyAddress`). Double-tap показывает множественные toast'ы — `useToast` singleton их replace'ит, видимых багов нет, но консистентность страдает | 🟢 | Nice-to-have |
| TD-F09d | QR-код в `InvestorDepositView` рендерится через `v-html` (qrcode → SVG string). Альтернатива для эстетики: `QRCode.toDataURL(address)` + `<img :src="dataUrl">` — избавит от `v-html` полностью. Security-equivalent (qrcode генерирует только `<path>`), но меньше нужен `:deep(svg)` CSS. Overkill для MVP, оставлен | 🟢 | Nice-to-have |

### TD-F10: Staff-side i18n gap (F4.4 B0 audit findings)

Обнаружены архитектурным аудитом после F4.4 B0 grooming-коммита (параллельный скан кодовой базы на соответствие только что введённому правилу FP-15). Инвестор-скоуп был мигрирован в B0; staff-side остался с 7 raw-enum рендерами и одним локальным дублем `formatPrice`. Не блокирует F4.4 / F5.x / F6.x — миграция ждёт захода в staff-side полировку.

| # | Описание | Приоритет | Когда |
|---|----------|-----------|-------|
| TD-F10a | `StaffPaymentsView.vue` — три server enum'а рендерятся raw без i18n: `item.payment_type` и `item.provider` (mustache, ~стр. 141) + `item.status` (`:text` на CBadge, ~стр. 147). 3 call-site'а в одной вьюхе. Миграция: добавить `staff.payments.type.*` / `staff.payments.provider.*` / `staff.payments.status.*` в en.json + обернуть в `tOrRaw` (FP-15) | 🟢 | С началом staff-side полировки |
| TD-F10b | `StaffAgentAppsView.vue` — `item.status` rendered raw (~стр. 119), 1 call-site. Добавить `staff.agentApps.status.*` + `tOrRaw` | 🟢 | С TD-F10a |
| TD-F10c | `StaffUsersView.vue` — `item.role` + `detailUser.role` (2 call-site'а, ~стр. 212 / 249) и `item.kyc_status` + `detailUser.kyc_status` (2 call-site'а, ~стр. 216 / 260) — итого 4 call-site'а. Добавить `staff.users.role.*` + `staff.users.kycStatus.*` + `tOrRaw` | 🟢 | С TD-F10a |
| TD-F10d | `StaffPaymentsView.vue:41–43` — локальная `formatCents(cents, currency)` → `"12.34 USD"` без `$`-префикса. Дубль `formatPrice`, но **семантически отличающийся**: `formatPrice(1234, 'USD')` выдаёт `"$12.34"`, `formatCents` — `"12.34 USD"`. Миграция **не чистый code swap** — требует product/design decision (формат в staff-UI намеренный или исторический долг?). Если намеренный — вынести отдельной `formatStaffCents` utility и задокументировать; если долг — мигрировать на `formatPrice`. Не закрывать без решения | 🟢 | С TD-F10a + design review |

### TD-F11: F4.4 review follow-ups

Выявлены в ходе code review F4.4 B1 (score 7/10) и последующих ревью B3/B5 (9/10 after B5-post). Пункты a, b, e, f закрыты. Пункты c, d — открытые триггер-based.

| # | Описание | Приоритет | Когда |
|---|----------|-----------|-------|
| TD-F11a | ✅ **Закрыт в F4.4 B1-post.** Infinite-scroll retry-storm brake. `loadMoreErrored` + `clearLoadMoreError()` добавлены в `stores/portfolio.ts` и `stores/transactions.ts`; `useInfiniteScroll` получил опциональный 4-й параметр `paused?: Ref<boolean>`; `TransactionsView` мигрирован на новый контракт с Retry-баннером. Паттерн зафиксирован правилом **FP-16**. Сопутствующие фиксы B1-post (не долги, а ревью-замечания): split epoch в portfolio store (был общий счётчик — залипание loading при конкурентных fetchPortfolio/setCompanyId), timeout coverage до конца `response.blob()` в `fetchCertificateBlob` (был unbounded download на медленной сети), JSDoc про `missingWarn` invariant в `tOrRaw`, cleanup dual-import в certificates | 🟢 | ✅ Done |
| TD-F11b | ✅ **Закрыт в F4.4 B3 + расширен в B5-post.** `CertificateSheet.vue` рендерит сертификат в iframe с `sandbox=""` (empty — запрещает всё). Blob URL наследует origin SPA → без sandbox любая ошибка в `autoescape` Jinja2 дала бы скрипту доступ к `localStorage` + JWT. В B5-post тот же паттерн применён к `InvestorDocsView`: `v-html` снят, legal HTML рендерится в iframe с sandbox через blob URL, `doc.type`/`doc.language` валидируются `SAFE_TOKEN = /^[a-z0-9_-]{1,64}$/i` + encodeURIComponent перед fetch path. Релаксация до `allow-same-origin` в будущем допустима только с узким allow-list под конкретную нужду; явные комменты в компонентах предупреждают об этом | 🟢 | ✅ Done |
| TD-F11c | `api/certificates.ts:fetchCertificateBlob` дублирует error-taxonomy из `api/client.ts` (ApiResponseError/Network/Timeout, Authorization header, timeout) — raw `fetch` потому что `api.client` всегда делает `response.json()`. Будущий источник дрифта: изменения в `client.ts` (например, `Accept-Language`, correlation-id, retries) не подхватятся certificates-путём. Миграция: расширить `api.client` опцией `responseType: 'json' \| 'blob' \| 'text'`, переписать `fetchCertificateBlob` через новый клиент. Сейчас **три** non-JSON call-site (certificates blob + email, legal HTML fetch в InvestorDocsView) — достаточный кворум чтобы начать думать об общем клиенте, но ещё не принудительный триггер (DocsView использует `fetch` напрямую без auth header — legal HTML public) | 🟢 | Когда появится четвёртый non-JSON endpoint или authorized non-JSON endpoint |
| TD-F11d | `PortfolioView.vue` считает profit % клиентски (`(current_value - total_paid) / total_paid * 100`), потому что `PortfolioResponse` / `PortfolioPositionResponse` на бэке не эмитят profit field. Null-guard на `total_paid_cents <= 0` (gift-only позиции) — profit блок не рендерится. Когда backend добавит per-company / total profit (с учётом комиссий / налогов / возможных fee-корректировок), заменить computed на чтение из response и дропнуть локальную формулу. Переход сдвинет отображаемые цифры на sub-cent величины из-за округления — callers не должны сравнивать с кэшем. Помечено `// TD-F11d` в коде | 🟡 | Когда backend эмитит profit field в Portfolio* ответах |
| TD-F11e | ✅ **Закрыт в F4.4 B5-post.** Epoch guard в `useCertificateBlob.load()`. Ранее перекрывающийся второй вызов `load()` (prop churn в `CertificateSheet` при быстрой смене `purchaseId`) мог: (a) записать проигравший URL в `blobUrl` без revoke (утечка до unmount), (b) сбросить `loading` в false пока winner ещё в полёте, (c) затереть `errored` loser'а поверх winner'а. Fix: monotonic per-instance epoch, проигравший revoke'ает свой URL сам, не касается shared state. `clear()` бампит epoch — in-flight `load()` после `clear()` revoke'нёт свой результат, не repopulate. Паттерн зафиксирован **FP-17** | 🟢 | ✅ Done |
| TD-F11f | ✅ **Закрыт в F4.4 B5-post.** Epoch guard в `useDashboardStore.refresh()` + `reset()` бампит epoch. Ранее быстрые переключения между Dashboard и Balance (оба делают `refresh()` в `onMounted`) могли резолвиться вне порядка — старый fetch приходил после нового и подменял `summary` устаревшими цифрами («прыгающие» балансы). Post-logout сценарий: `reset()` очищал state, но in-flight `refresh()` мог repopulate summary пользовательскими данными после вызова `clearSession()`. Fix: `refresh()` захватывает epoch, только winner пишет; `reset()` инкрементит epoch, так что любой пост-logout fetch становится noop | 🟢 | ✅ Done |

### TD-F12: i18n professional review (DE/AR)

В F4.4 B7 добавлено 118 ключей × 3 локали (ru/de/ar) как best-effort перевод без nativespeaker-ревью. RU подлежит self-review (автор проекта). DE и AR требуют профессионального vetting перед prod release — финансовая терминология чувствительна к нюансам (Kontostand vs Guthaben, محفظة vs رصيد), а AR дополнительно имеет **pluralization проблему**: `inv.settings.agent.cooldown` = `متاح بعد {days} يوم` грамматически корректно только для 1-10 (единственное число), арабский требует разных форм для 1, 2, 3-10, 11+. vue-i18n поддерживает pluralization через `|` разделитель — если нужны точные AR плюралы, отдельная задача.

| # | Описание | Приоритет | Когда |
|---|----------|-----------|-------|
| TD-F12a | DE review: native speaker / professional translator проходит по всем 118 ключам в `de.json` из F4.4 B7. Особое внимание: финансовые термины (Kontostand, Gewinn, Einheiten), UI-стандарты (Weiter/Zurück vs Fortfahren/Abbrechen), формальность обращения (Sie vs du — проект использует Sie) | 🟡 | До prod release |
| TD-F12b | AR review: native speaker проходит по всем 118 ключам в `ar.json`. Дополнительно: RTL-специфичные фразы, согласование родов, религиозно-корректная терминология для финансовых операций (возможно shariah-compliance в будущем) | 🟡 | До prod release |
| TD-F12c | AR pluralization: ключи с `{days}` / `{count}` переписать через vue-i18n plural syntax `'форма1 | форма2 | форма3'`, если feedback от AR-reviewer'а подтвердит что текущая форма неприемлема | 🟢 | После TD-F12b, опционально |

### TD-F13: OnboardingProfileView inline PATCH migration

`src/views/auth/OnboardingProfileView.vue` дёргает `api.patch('/api/v1/users/me', {...})` напрямую вместо нового `api/users.ts:updateMe()`. B5 намеренно не трогал за пределами scope, но модуль `api/users.ts` создан именно для централизации работы с `/users/me` — inline-вызов теперь выглядит как долг.

| # | Описание | Приоритет | Когда |
|---|----------|-----------|-------|
| TD-F13 | Заменить `api.patch<UserResponse>('/api/v1/users/me', { profile, language })` на `updateMe({ profile, language })` в `OnboardingProfileView.vue`. Чистый code swap, без изменения поведения, тип отдаётся через UserResponse от updateMe | 🟢 | В любом следующем grooming-коммите (до F5) |

### TD-F14: Withdrawal bounds duplicated frontend↔backend

`CompanyBalanceView.vue` (F5.2 B4) объявляет `MIN_WITHDRAWAL_CENTS = 1000` / `MAX_WITHDRAWAL_CENTS = 10_000_000` как локальные константы. Реальные значения живут в `backend/app/core/config.py` (`min_withdrawal_cents` / `max_withdrawal_cents`). Если backend поменяет лимит — frontend выдаст устаревшую валидацию + неточный hint в форме («Min $10.00, max $100,000.00»), пользователь упрётся в backend 400 или, наоборот, не сможет ввести валидную сумму.

| # | Описание | Приоритет | Когда |
|---|----------|-----------|-------|
| TD-F14 | Добавить `GET /api/v1/config` endpoint (или включить `withdrawal_min_cents` / `withdrawal_max_cents` в `/company/dashboard` response). Frontend читает значения при mount или хранит в `companyDashboard` store. Заменить локальные константы в `CompanyBalanceView` на reactive bindings. Code review F5.2 follow-up | 🟡 | Перед prod release / после backend `/config` endpoint'а |

### TD-F15: vue-i18n placeholder pitfall в локалях

Во время F5.2 B4 (Edit payout details bottom sheet) обнаружен runtime SyntaxError vue-i18n при первом вызове `t('comp.balance.payout.form.placeholder')`. Причина: ключ содержал JSON-пример `"{\\n  \\"method\\": \\"iban\\"\\n}"` — vue-i18n считает `{` началом плейсхолдера для интерполяции (`{name}`) и требует валидный идентификатор после. `{\\n` → SyntaxError на лексере. В production build error съедается Vue error-boundary молча — рендер ломается без diagnostic, кнопка визуально «мёртвая», повторные клики не дают эффекта. В dev-режиме видно сразу.

**Правило:** любой `{` в локали-строке должен быть либо валидным `{name}` плейсхолдером для известного параметра, либо escape'нут как `{{` (рендерится как литерал `{`). Никаких JSON-примеров, кодовых snippet'ов, CSS-фрагментов, формул в локалях.

| # | Описание | Приоритет | Когда |
|---|----------|-----------|-------|
| TD-F15a | Документировать правило в Style Guide / Frontend.md секцию `7. LLM Code Review Guide`. Любая локаль-строка с `{` без валидного `{name}` идентификатора — баг | 🟡 | В следующий grooming-коммит |
| TD-F15b | Добавить CI-проверку `pnpm i18n:lint` (или ручной `pre-commit` hook): regex-сканер всех `*.json` локалей на подозрительные `{` (не за `{{` escape, не часть `{validIdent}`). Альтернатива — vue-i18n предоставляет `@intlify/eslint-plugin-vue-i18n`, у которого есть rule `valid-message-syntax` | 🟢 | После TD-F15a, опционально |
| TD-F15c | F5.2 B4 baseline: `comp.balance.payout.form.placeholder = "Enter JSON object"` (заменено с JSON-примера). Если позже найдутся другие случаи «строка с `{`» в `{en,ru,de,ar}.json` — починить точечно | 🟢 | На каждом ru/de/ar catchup |



---

### TD-F16: TD-ROADMAP-LINKING

iter 2.7 Block D реализовал базовый CRUD roadmap items + reorder + cover upload. **Не реализован UI для linking** этапа с Post (`post_id`) или Product (`linked_product_id`). Backend принимает оба поля опционально (ON DELETE SET NULL). Целевой UX по R1 §5.7 — combobox с поиском по company-scope постам/продуктам + опция "+ Создать связанный пост".

| # | Описание | Приоритет | Когда |
|---|----------|-----------|-------|
| TD-F16 | Combobox с search'ем для post_id + linked_product_id в RoadmapEditor edit modal. Включая "+ Создать связанный пост" sub-flow (reuse PostListEditor create-form через emit, pre-fill owner_type=company + owner_id=companyId). | 🟢 (feature) | Post-MVP feature |

### TD-F17: TD-CHIP-DEDUP

`.filter-chip` CSS дублируется в 3 view: `EventEditor.vue`, `TemplatesSection.vue` (iter 2.7 Block C), `InvestorEventsView.vue` (iter 2.7b). Каждый ≈25 строк CSS. Существующий паттерн extraction: CBackLink в iter 2.7 (B3) — extract on 2nd-3rd duplication.

| # | Описание | Приоритет | Когда |
|---|----------|-----------|-------|
| TD-F17 | Extract в shared `CFilterChip.vue` либо utility-классы. Pattern: caller передаёт `:options + :modelValue + @update`. | 🟢 | В следующий drive-by cleanup |

### TD-F18: TD-FORMAT-BYTES-DEDUP

`formatBytes` функция дублируется между auth-flow `AttachmentsSection` (iter 2.5) и public-flow `PublicAttachmentsSection` (iter 2.6). Shared util `utils/format.ts::formatBytes` существует — обе локальные копии byte-identical. iter 2.7 Block D (Roadmap cover) **НЕ добавил** новой копии (использует число `COVER_MAX_BYTES` без человекочитаемого форматирования), так что долг не усугубил.

| # | Описание | Приоритет | Когда |
|---|----------|-----------|-------|
| TD-F18 | Заменить локальные копии `formatBytes` на импорт из `@/utils/format`. | 🟢 | В следующий drive-by cleanup |

### TD-F19: Company-views на shared date/amount хелперы (F6 follow-up) — ✅ ЗАКРЫТ

F6 follow-up вынес `formatDateTime` / `formatDate` / `parseAmountToCents` (float-safe парсер) в `utils/format.ts` и мигрировал 4 agent-вью. `CompanyBalanceView` и shared `TransactionDetailSheet` всё ещё несут инлайн-копии `formatDate` и `Math.round(Number(...)*100)`-парсинг ввода суммы — тот же класс дублирования, что TD-F18 / TD-F09a.

**✅ Закрыт (Version 2.12-F6):** `CompanyBalanceView` (`formatDate`→`formatDateTime`, `Math.round`→`parseAmountToCents`) и shared `components/shared/TransactionDetailSheet.vue` (`formatDate`→`formatDateTime`) переведены на shared-хелперы.

| # | Описание | Приоритет | Когда |
|---|----------|-----------|-------|
| ~~TD-F19~~ | ~~Заменить инлайн `formatDate` в `CompanyBalanceView` + `TransactionDetailSheet` на `formatDateTime`/`formatDate` из `@/utils/format`; заменить `Math.round`-парсинг ввода суммы на `parseAmountToCents`.~~ ✅ | 🟢 | ✅ done (2.12-F6) |

### TD-F20: usePaginatedList extraction + frontend unit-test infra

Список выводов в `AgentBalanceView` — локальный `ref`-based paginated список (FP-16 позволяет локальным view-спискам отложить brake; brake для него всё же добавлен в §3). Паттерн «page/total/hasMore/loadMore + epoch + FP-16 paused» повторяется по вью. Отдельно: на фронте до сих пор нет unit-тест-инфры.

| # | Описание | Приоритет | Когда |
|---|----------|-----------|-------|
| TD-F20a | Вынести общий `composables/usePaginatedList.ts` (page/total/hasMore/loadMore + epoch guard + FP-16 paused), мигрировать локальные ref-списки. | 🟢 | Grooming, когда появится 3-й локальный ref-список |
| TD-F20b | Завести фронтовую unit-тест-инфру (Vitest); начать с `utils/format.ts` (`parseAmountToCents` edge-cases) и `usePaginatedList`. | 🟡 | Before Scale |

---

> **О нумерации записей ниже.** Две самые старые записи журнала — `Version 3.7` (2026-05-05) и
> `Version 3.6` (2026-05-03) — сделаны под прежней схемой нумерации, общей с бэкенд-документом.
> Собственная последовательность `2.x` этого документа началась позже, поэтому номера в конце списка
> выше, чем в начале. Записи оставлены как есть: номер, под которым запись была сделана, — часть записи.

*Version 2.12-F6 | 2026-07-25 | Code-review round-2 fixes + company-balance consistency. **Agent (round-2):** retry-кнопка вынесена соседом slotless `CEmptyState` в Commissions/Leaderboard/Referrals — был мёртвый retry (2.1); `AgentBalanceView.hasError` локальные флаги гейтнуты на «данных нет» → транзиентный сбой рефетча после успешного вывода больше не сносит денежный экран (2.2); `CommissionsView` показывает ошибку дозагрузки (`loadMoreError`, 2.3); `AgentSettingsView` пишет сохранённый payout локально вместо рефетча + parse в try (2.4/2.7); `format.ts` `formatDate`/`formatDateTime` через `Number.isNaN(getTime())` (`new Date` не бросает — старый try/catch был мёртвый, 2.7); `LeaderboardView` ranked-list гейтнут на non-null (после reset нет пустого списка без подписи, 2.7). **Company:** `CompanyBalanceView` оказался нетронутым близнецом денежного экрана агента — сложены ВСЕ те же фиксы (§6 пустой payout + §2/2.2 error-gate + 2.4 payout-local + 2.7) для консистентности; **TD-F19 закрыт** — `CompanyBalanceView` + shared `components/shared/TransactionDetailSheet.vue` мигрированы на shared `formatDateTime`/`parseAmountToCents`. Гейт зелёный: 313 backend tests + frontend build.*

*Version 2.11-F6 | 2026-07-24 | PHASE F6 (Agent shell) реализован + review follow-up. Blocks A–F: `ReferralsView` (downline L1/L2/L3 + sub-agents), `CommissionsView` (paginated, «Clawed back» badge), `LeaderboardView` (is_me highlight), `AgentBalanceView` (passive balance + история выводов + withdraw-форма), `AgentSettingsView` (payout JSON-редактор), `AgentMoreView` (точки входа). Имена реализации: `AgentBalanceView`/`AgentSettingsView` (не `BalanceView`), Settings — отдельный sub-route. Review follow-up (score 8/10): §2 balance error-gate stale-error trap (hasError на `summary===null` + безусловный refresh), §6 reject пустого payout `{}` (+`errorEmpty`), §3 withdrawal load-more errors через FP-16 brake (+`loadMoreError` + retry-баннер), shared `formatDateTime`/`formatDate`/`parseAmountToCents` в `utils/format.ts` (4 вью мигрированы), commission `:key` по выставленному backend'ом `CommissionEntry.id`, load-more спиннер. Bundle 10 файлов / 5 коммитов. +TD-F19 (company-views на shared хелперы), +TD-F20 (usePaginatedList + Vitest unit-инфра). FP-20 gap отмечен: InvestorSettingsView back-link. Agent i18n en-only по catch-up policy. Гейт зелёный: 312 backend tests + build.*

*Version 2.10 | 2026-05-13 | iter 2.7 (Staff Platform Tab) + iter 2.7b (Events widget) + iter 2.8 (TD-FP18-PUBLIC-FLOW) закрыты. R1+R2 рефакторинг **полностью завершён** — все спеки переведены в v0.7/v0.9 final / fully implemented. FP-18 уточнён: useAvatar.ts — действительно единственное разрешённое исключение после iter 2.8 migration. Self-check checklist расширен: baseline check (git status + fetch + сверка с origin/main) и orphan component check после backend rename (lessons из iter 2.7 Block D + iter 2.7 B3). Добавлены TD-F16 (ROADMAP-LINKING), TD-F17 (CHIP-DEDUP), TD-F18 (FORMAT-BYTES-DEDUP).*

*Version 2.9 | 2026-05-13 | iter 2.6 (Public Flow Frontend) + iter 2.5 (Investor frontend для R1) + iter 2.7 (Cleanup) закрыты. Добавлены 10 новых FP (FP-18 — FP-27): safeNavigate canonical helper, single CHeader policy, CBackLink shared component, history-aware goBack, role-aware route names через computed, role-conditional CTA с двойной защитой (template guard + defensive role check), lazy import stub policy, self-hiding sections, auth-state branching CTA, i18n reuse domain-neutral/specific. Closed BUG-28-01 (NavigationFailure → false purchase toast) и BUG-29-01 (NavigationFailure → ApiResponseError rethrow в auth). Двойной CHeader в 8 views — закрыт. ~60 navigation call-sites переведены на safeNavigate. CBackLink — единый компонент back-link (раньше 7 копий локального CSS). i18n catch-up зафиксирован как **policy** (не tech debt) — новые ключи только в en.json, ru/de/ar batch'ем перед public launch. Self-check checklist + grep команды добавлены в §7.*

*Version 2.8 | 2026-05-11 | Frontend ТЗ обновлён после iter 2.5 (Investor frontend, R1 §1) — F4.1 структурно переписана: MarketView удалён, заменён цепочкой CompanyListView → CompanyOverviewView → ProductsByCompanyView. AgentShell зеркала под /agent/*. CompanyPositionView с ownership + agreement buttons (R2 §5.5 carryover). Backend gaps (G1-G5) все закрыты. R1+R2 backend полностью закрыты в iter 2.4. Strategy: iter 2.6 (Public flow) → iter 2.7 (Staff Platform tab) → F6 (Agent shell) → F8 (Notifications) → F7 (i18n) → F9 (polish).*

*Version 3.7 | 2026-05-05 | Phase F5 (Company UI) closed. F5.1 deployed: dashboard with hero / balance / pool widget / metrics row / recent transactions. F5.2 deployed: B0 Products list (read-only), B1+B2 Analytics (top metrics + sales-by-month chart + sales-by-product table), B3+B4 Balance (passive balance card + withdrawals history with status badges + payout details preview + write forms for POST /withdrawals and PUT /users/me/payout-details), B5 Settings (read-only profile). Code review TD batch: +TD-F14 (withdrawal bounds frontend↔backend duplication) + TD-F15 (vue-i18n placeholder pitfall, обнаружен в B4 — JSON-пример в локали ломал bottom sheet рендер). en.json: +comp.{dashboard,products,settings,analytics,balance}.* (~75 keys). ru / de / ar — i18n catchup отложен до отдельного спринта (объём + native-speaker review).*

*Version 3.6 | 2026-05-03 | Sprint 4.5 prep: Phase F5 re-exports в types.ts (CompanyDashboardResponse, CompanyAnalyticsResponse, CompanyTransactionResponse, PoolEmbedResponse, SalesByMonthEntry, SalesByProductEntry). `getMyCompany()` wrapper в companies.ts (singular vs plural file split mirrors backend module split: `companies` для public storefront + `/me`, `company` для company-side dashboard + analytics). Frontend готов к Phase F5 имплементации.*
