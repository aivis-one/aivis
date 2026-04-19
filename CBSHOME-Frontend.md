# CBSHOME — Техническое задание: Frontend

**Версия:** 2.5
**Дата:** 18 апреля 2026
**Статус:** Active
**Репозиторий:** https://github.com/aivis-one/cbshome

**Зависимости (читать перед работой):**
- `CBSHOME-Design-Document.md` — Конституция v1.5
- `CBSHOME-Backend.md` — Backend ТЗ v2.9
- `CBSHOME-Financial-System.md` — финансовая логика
- `CBSHOME-State-Machines.md` — переходы статусов
- `CBSHOME-Installment.md` — механика рассрочки
- `CBSHOME-Share-Pool-Refactor.md` — TD-F07 follow-up (обязательно перед стартом F5)
- `mockups/` — UI-прототипы (auth-flow, investor-shell, agent-shell, company-shell, staff-shell)

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
| HTTP | Fetch (обёртка) | native | Запросы к API (CORS → api.cbshome.org) |
| i18n | vue-i18n | v10 | en/ru/de/ar + RTL |
| PWA | vite-plugin-pwa | latest | Manifest + Service Worker |
| Стили | Свой CSS | — | Дизайн-система из мокапов (variables.css v1.8.0) |
| Линтинг | ESLint + Prettier | latest | Качество кода |
| Иконки | lucide-vue-next | ^0.460 | SVG-иконки из мокапов (Lucide) |
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
- [x] `install_cbshome.sh`: Nginx-блок для `cbshome.org` → `localhost:3000`

**Обновления (F1):**
- Dockerfile: `npm ci` → `npm install` (автоматическое подтягивание новых зависимостей при `cbshome update`)
- Dockerfile: `ENV VITE_API_BASE_URL=https://api.cbshome.org` + `ENV VITE_TELEGRAM_BOT_URL=https://t.me/cbshome_bot` — baked into build stage
- `.env.production` — Vite production env vars (дублирует Dockerfile ENV для dev-сборки)
- `.dockerignore` — разрешён `.env.production`
- `install_cbshome.sh`: убран `--no-cache` из `case_update()` (оставлен при первичной установке)

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

**Критерий готовности:** `$t('app.name')` рендерит "CBS HOME" на en. Переключение на ar → RTL.

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
  - `role: UserRole | null` (computed из `user.role ?? null`)
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
- Dockerfile: `npm ci` → `npm install` для автоматического подтягивания новых зависимостей при `cbshome update`

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

### ✅ F4.1: Витрина продуктов

**Цель:** Инвестор видит доступные продукты.

**Задачи:**
- [x] src/stores/products.ts (Pinia) — `products`, `total`, `filters`, `loading`, `fetchProducts()`
- [x] src/api/products.ts — `listProducts(params)`, `getProduct(id)`
- [x] src/api/companies.ts — `listCompanies(params)` для фильтра
- [x] src/components/shared/ProductCard.vue — обложка + название + компания + цена + `sold_units`, клик → `/investor/products/:id`
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

**После F4.4 → Sprint 4.3 + TD-F07** (Share Pool Refactor). Views F4.2 подлежат ревизии по TD-F07b/c: поля `units`/`sold_units` → `package_size`/`available_packages`, availability-вычисления мигрируют.

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

### F4.4: Портфель + Дашборд

**Цель:** Инвестор видит свой портфель и главную страницу.

**Прогресс:** B0 ✅ · B1 ✅ · B1-post ✅ · B2 ✅ · B3 ⚠️ pushed (2 hotfixes pending, см. ниже) · B4–B7 pending.

**Задачи:**
- [x] **B0 grooming (F4.4):** extract `formatSignedPrice` в `src/utils/format.ts` + extract `tOrRaw` в `src/utils/i18n.ts` (новый файл). Миграция 7 call-site'ов (2 для signed-price, 5 для tOrRaw). Семантика `cents === 0` → без знака (фикс бага TransactionsView «+$0.00»). Закрывает **TD-F09a + TD-F09b**, вводит правило **FP-15** (server-driven enums → tOrRaw). Параллельный CC-аудит выявил staff-side долг → **TD-F10** (4 пункта, не в скоупе F4.4).
- [x] **B1 API layer + stores + types (F4.4):** `api/portfolio.ts` (2 endpoint'а), `api/certificates.ts` (fetchCertificateBlob через raw fetch → blob URL для iframe, emailCertificate через api.post), `api/agent-apps.ts` (2 investor endpoint'а), `stores/portfolio.ts` (один store, positions + per-company paginated, epoch-guard), расширение `api/types.ts` (6 новых типов для F4.4), минимальная правка `api/client.ts` (экспорт `API_BASE_URL` для non-JSON endpoint'ов). Code review score 7/10 — основные замечания закрыты в B1-post.
- [x] **B1-post (B1 review follow-up):** (1) split `fetchEpoch` в `stores/portfolio.ts` на `portfolioEpoch` + `currentEpoch` (было: залипание `positionsLoading` при конкурентных операциях), (2) timeout coverage в `fetchCertificateBlob` теперь охватывает `response.blob()` (было: стук на медленной сети → вечный спиннер), (3) **loadMore retry-storm brake** — новое правило `loadMoreErrored` + `clearLoadMoreError()` в паджинированных stores, `paused?: Ref<boolean>` параметр в `useInfiniteScroll`, Retry-баннер в view. Применено к `stores/portfolio.ts` и `stores/transactions.ts` одновременно (консистентность), view-миграция в `TransactionsView.vue`. Вводит правило **FP-16**.
- [x] **B2 — InvestorDashboardView + store rename:** новый `src/stores/dashboard.ts` (заменяет `stores/balance.ts`) с полным `DashboardSummaryResponse` payload + legacy `activeBalance`/`passiveBalance` computed getters для миграции без переписывания темплейтов. `stores/balance.ts` удалён. Новый `src/views/investor/InvestorDashboardView.vue` — 4 виджета: portfolio hero card (gradient, тап → `/investor/portfolio`, empty-state CTA на первую покупку), balance card (active confirmed + frozen hint), quick actions (Deposit + Market), posts preview (5 последних через `api/posts.ts`, новый модуль с narrow probe — без store, не переиспользуется). Миграция `PurchaseView.vue` / `InstallmentView.vue` с inline `getDashboardSummary()` → `useDashboardStore` (balance никогда не десинкнётся между экранами в одной сессии). Новый `api/posts.ts` (F9.1), расширение `api/types.ts` (F9.1 Posts/Events section, 939 lines total). +17 ключей `inv.dashboard.*` в en.json. Events отложены до F9.2.
- [x] **B3 — PortfolioView + CompanyPositionView + Certificates:** новый `src/views/investor/PortfolioView.vue` (rewrite stub) — hero card с client-side profit % (`(current - paid) / paid * 100`, null при invested === 0, помечено TD-F11d) + positions list с тапом на детали. Новый `src/views/investor/CompanyPositionView.vue` — sub-route `/investor/portfolio/:id` (+ agent дубль), CHeader back + aggregate block + paginated purchases через FP-16 retry-storm brake + certificate flow. Новый `src/components/shared/CertificateSheet.vue` — bottom-sheet overlay (не inline, не full-screen modal — решение по Q3), iframe с **`sandbox=""`** (закрывает TD-F11b), email CTA без confirmation (решение Q4) с 3-секундным локальным cooldown поверх backend rate-limit. Новый `src/composables/useCertificateBlob.ts` — auto-revoke `URL.createObjectURL` через `onScopeDispose` + revoke-before-overwrite на повторный `load()`. Новый route `investor-company-position` + parный `agent-company-position`. +25 ключей `inv.portfolio.*` / `inv.companyPosition.*` / `inv.certificate.*` в en.json. Empty state PortfolioView → CTA на market (решение Q5).
  - ⚠ **Хотфиксы после push'а B3** (применить до релиза):
    1. В `CompanyPositionView.vue` импорт `@/components/investor/CertificateSheet.vue` → `@/components/shared/CertificateSheet.vue` (старая версия файла попала в репо до правки конвенции).
    2. Применить `ROUTER-CHANGES.txt` из B3-zip: два `str_replace` в `src/router/index.ts` добавляют маршруты `investor-company-position` и `agent-company-position` (без них `router.push({ name: 'investor-company-position' })` не матчит).
    Санити: `grep "components/investor" frontend/src/views/investor/CompanyPositionView.vue` → 0 строк; `grep -c "company-position" frontend/src/router/index.ts` → 2.
- [ ] **B4** — src/views/investor/InvestorDocsView.vue:
  - GET /api/v1/documents → список документов
  - Статус подписания (signed / pending)
  - POST /api/v1/documents/{id}/sign
- [ ] **B5** — src/views/investor/InvestorSettingsView.vue:
  - Профиль: аватар, имя, роль
  - PATCH /api/v1/users/me — редактирование
  - Переключение языка (en/ru/de/ar)
  - Переключение темы (light/dark)
  - Кнопка "Стать агентом" (если роль = investor, KYC approved):
    - POST /api/v1/agent-applications → подать заявку
    - GET /api/v1/agent-applications/me → статус заявки
    - Cooldown 30 дней после отклонения (показать таймер)
  - **B5 review checkpoint:** validate `AgentApplicationStatusType` usage — тип добавлен в B1 как подготовка, первый реальный потребитель появится здесь.
- [ ] **B6** — src/views/investor/InvestorMoreView.vue:
  - Навигация к: Documents, Settings, Notifications, Agent Application
- [ ] **B7** — i18n catchup ru/de/ar для всех новых ключей B2–B6.

**Зависимость от бэкенда:** Dashboard (Sprint 9.2 ✅), Portfolio (Sprint 9.2 ✅), Documents (Phase 2.2 ✅), Users (Phase 1.3 ✅), Agent Applications (Sprint 7.1 ✅), Certificates (Sprint 9.2 ✅).

**Критерий готовности:** Инвестор видит дашборд, портфель, документы, настройки, сертификаты.

**Commit chain (по состоянию на B3 push):** B0 (`refactor(frontend): extract formatSignedPrice and tOrRaw utilities before F4.4`) → docs коммит (`docs(frontend): add FP-15 and TD-F10 ...`) → B1 (`feat(frontend): portfolio + certificates + agent-apps API layer and store (F4.4 B1)`) → B1-post (`fix(frontend): portfolio store race, blob timeout, loadMore retry storm (B1 review follow-up)`) → docs коммит #2 (`docs(frontend): add FP-16 and TD-F11 ...`) → B2 (`feat(frontend): investor dashboard + rename balance store to dashboard (F4.4 B2)`) → B3 (`feat(frontend): investor portfolio + company position + certificates (F4.4 B3)`) → [pending] B3-hotfix (CertificateSheet import + router routes).

**Follow-ups (TD-F11 секция):** ✅ iframe sandbox в B3 (TD-F11b закрыт). Миграция certificates на общий `api.client` через `responseType` опцию — когда появится второй не-JSON endpoint (TD-F11c). Новый — client-side profit calc в PortfolioView, мигрировать когда backend эмитит per-company profit (TD-F11d).

---

## PHASE F5: Company

> ⚠ **BLOCKER:** перед стартом F5 должен быть завершён backend Sprint 4.3 (TD-071) — рефакторинг модели акций / пакетов. Витрины Company оперируют теми же `Product`-сущностями, но от лица владельца компании: там нельзя показывать заведомо неверные цифры `sold_units` / `units`. Детали — `CBSHOME-Share-Pool-Refactor.md`. После merge бэка на фронте остаётся парная follow-up задача (`TD-F07`): переименование поля в `api/types.ts` + точечные правки `ProductCard.vue`, `ProductDetailView.vue`, локалей. Формально отдельным спринтом во Frontend ТЗ не оформляется — это механическое переименование, идущее сразу после backend merge.

### F5.1: Дашборд компании

**Цель:** Компания видит свою статистику.

**Задачи:**
- [ ] src/views/company/CompanyDashboardView.vue:
  - GET /api/v1/dashboard/summary → балансы и агрегаты (работает для любой роли)
  - Виджеты: количество продуктов, passive balance, current_value_cents
  - Последние транзакции: GET /api/v1/transactions

**Зависимость от бэкенда:** Dashboard (Sprint 9.2 ✅), Transactions (Sprint 6.4 ✅).

**Критерий готовности:** Компания видит дашборд с метриками.

---

### F5.2: Продукты + Аналитика + Баланс

**Цель:** Компания видит свои продукты, аналитику и управляет балансом.

**Задачи:**
- [ ] src/views/company/CompanyProductsView.vue:
  - GET /api/v1/products?company_id={my_company_id} → список продуктов
- [ ] src/views/company/CompanyProductEditView.vue:
  - GET /api/v1/products/{id} — детали (readonly, редактирование через Staff)
- [ ] src/views/company/CompanyAnalyticsView.vue:
  - GET /api/v1/portfolio/me/company/{id} — аналитика продаж
- [ ] src/views/company/CompanyBalanceView.vue:
  - Passive balance из GET /api/v1/dashboard/summary → passive_balance
  - Список выводов: GET /api/v1/withdrawals/me
  - Кнопка "Вывести": POST /api/v1/withdrawals (body: `{ amount_cents }`)
  - Настройка реквизитов: GET/PUT /api/v1/users/me/payout-details
- [ ] src/views/company/CompanySettingsView.vue:
  - GET /api/v1/companies/{id} — профиль компании (readonly)

**Зависимость от бэкенда:** Products (Phase 4.2 ✅), Companies (Phase 4.1 ✅), Dashboard (Sprint 9.2 ✅), Withdrawals (Sprint 6.3 ✅).

**Критерий готовности:** Компания видит продукты, аналитику, управляет выводами.

---

## PHASE F6: Agent

### F6.1: Agent Hub

**Цель:** Агент управляет реферальными ссылками.

**Задачи:**
- [ ] src/views/agent/AgentDashboardView.vue:
  - Виджеты: комиссии за месяц, количество рефералов, ранг в лидерборде
  - GET /api/v1/dashboard/summary — балансы
  - Quick actions: Создать ссылку, Мои комиссии
- [ ] src/views/agent/AgentHubView.vue:
  - POST /api/v1/referrals/links → ReferralLinkResponse (code generated server-side)
  - GET /api/v1/referrals/links/me → ReferralLinkListResponse (paginated)
  - Каждая ссылка: код, copy button, is_active flag
  - GET /api/v1/referrals/stats/me → ReferralStatsResponse — общая статистика
- [ ] src/views/agent/ReferralsView.vue:
  - Список привлечённых инвесторов (L1/L2/L3)

**Зависимость от бэкенда:** Referrals (Sprint 7.2 ✅). Permission: только role=agent.

**Критерий готовности:** Агент создаёт ссылки, видит рефералов.

---

### F6.2: Комиссии + Лидерборд + Пассивный баланс

**Цель:** Агент видит заработок и рейтинг.

**Задачи:**
- [ ] src/views/agent/CommissionsView.vue:
  - GET /api/v1/agent/commissions/me → CommissionListResponse (limit/offset)
  - Каждая запись: type (commission/volume_bonus), amount_cents, level, investor_name, product_name, status, created_at
  - Фильтры: уровень, период
- [ ] src/views/agent/LeaderboardView.vue:
  - GET /api/v1/agent/leaderboard → LeaderboardResponse
  - Каждая запись: rank, agent_name, volume_cents, is_me
  - Подсветка своей позиции (is_me = true)
  - snapshot_at, period_start для контекста
- [ ] src/views/agent/BalanceView.vue (passive):
  - Passive balance из GET /api/v1/dashboard/summary → passive_balance
  - Кнопка "Вывести" → POST /api/v1/withdrawals (body: `{ amount_cents }`)
  - GET /api/v1/withdrawals/me — история выводов
  - Настройка реквизитов: GET/PUT /api/v1/users/me/payout-details
- [ ] src/views/agent/AgentMoreView.vue:
  - Навигация к: Settings, Leaderboard, Investor Portfolio, Notifications

**Зависимость от бэкенда:** Commissions (Sprint 7.3 ✅), Leaderboard (Sprint 7.3 ✅), Withdrawals (Sprint 6.3 ✅).

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
| F4: Investor | 4.2, 5.1, 5.2, 6.1, 6.2, 6.4, 9.2 | ✅ | Нет |
| F5: Company | 4.1, 4.2, 6.3, 6.4, 9.2 | ✅ | Нет |
| F6: Agent | 7.1, 7.2, 7.3, 6.3 | ✅ | Нет |
| F7: i18n | — | — | Нет |
| F8: Notifications | 8.1–8.3 | ✅ | Нет |
| F9: Полировка + Posts | 9.1, 6.4 | ✅ | Нет |

**Стратегия:** Все фазы можно начинать — бэкенд полностью готов. Все backend gaps (G1–G5) закрыты.

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

---

## 8. Tech Debt (Frontend)

Выявлен в ходе code review Phase F3 (score 6.5 → 9/10). Не блокирует MVP, закрывается после F4–F6.

### TD-F01: Инфраструктура

| # | Описание | Приоритет | Когда |
|---|----------|-----------|-------|
| TD-F01a | `Dockerfile:13` — `npm install` → `npm ci` (детерминированные сборки) | 🟡 | Перед staging |
| TD-F01b | `nginx.conf:46` — `connect-src 'self' https://api.cbshome.org` захардкожен. Параметризовать через ENV / nginx template при смене `VITE_API_BASE_URL` | 🟡 | Перед staging |
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

### TD-F07: Share Pool Alignment (follow-up к backend Sprint 4.3)

Парная задача к backend TD-071. После merge backend-рефакторинга поле `sold_units` исчезает из API, появляется `available_packages`; `Product.units` переименовывается в `package_size`. На фронте это чисто механический rename + обновление текстов UI.

| # | Описание | Приоритет | Когда |
|---|----------|-----------|-------|
| TD-F07a | `frontend/src/api/types.ts` — в `PublicProductResponse` / `PublicProductDetailResponse`: `units` → `package_size`, `sold_units` → `available_packages`. Импортеры TypeScript покажут все места использования — пройтись по ним | 🔴 | Сразу после backend Sprint 4.3 merge |
| TD-F07b | `frontend/src/components/shared/ProductCard.vue` — вместо расчёта `available = p.units - p.sold_units` использовать `p.available_packages` напрямую. Переписать ключ i18n из `inv.market.available` («N available» — акции) на `inv.market.packsAvailable` («N packs available» — пакеты) | 🔴 | С TD-F07a |
| TD-F07c | `frontend/src/views/investor/ProductDetailView.vue` — те же правки что в ProductCard. Availability-статистика в `<CStat>` блоке: label из «AVAILABILITY» в «PACKS AVAILABLE», значение из `product.available_packages`. Sold-out условие (disabled CTA) → `product.available_packages === 0` | 🔴 | С TD-F07a |
| TD-F07d | `frontend/src/i18n/locales/{en,ru,de,ar}.json` — добавить ключ `inv.market.packsAvailable` с вариантами пакетов во всех 4 локалях. Старый `inv.market.available` можно оставить — он может пригодиться для других контекстов (или удалить, если нигде более не используется — проверить grep'ом) | 🔴 | С TD-F07a |
| TD-F07e | `frontend/src/stores/products.ts` — убедиться что store корректно прокидывает новое поле из API-ответа без трансформаций. Типы автоматически проверятся | 🔴 | С TD-F07a |
| TD-F07f | Ручная проверка: seed-скрипт после `--reset` + `docker compose restart app` — все 18 видимых продуктов должны показывать realistic `available_packages` (ниже `total_shares_issued / package_size` если были покупки, равно — если не было) | 🔴 | После всех TD-F07a..e |

Детальная спецификация, включая пример до/после диффов кода и текстов локалей — в `CBSHOME-Share-Pool-Refactor.md`, раздел «Frontend changes».

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

### TD-F11: F4.4 B1 review follow-ups

Выявлены в ходе code review F4.4 B1 (score 7/10 — один латентный баг в гонке epoch-счётчиков, один незакрытый таймаут, один архитектурный долг про retry-шторм). Пункты a/b закрыты: a в B1-post, b в B3. TD-F11d появился в B3 как осознанное упрощение.

| # | Описание | Приоритет | Когда |
|---|----------|-----------|-------|
| TD-F11a | ✅ **Закрыт в F4.4 B1-post.** Infinite-scroll retry-storm brake. `loadMoreErrored` + `clearLoadMoreError()` добавлены в `stores/portfolio.ts` и `stores/transactions.ts`; `useInfiniteScroll` получил опциональный 4-й параметр `paused?: Ref<boolean>`; `TransactionsView` мигрирован на новый контракт с Retry-баннером. Паттерн зафиксирован правилом **FP-16**. Сопутствующие фиксы B1-post (не долги, а ревью-замечания): split epoch в portfolio store (был общий счётчик — залипание loading при конкурентных fetchPortfolio/setCompanyId), timeout coverage до конца `response.blob()` в `fetchCertificateBlob` (был unbounded download на медленной сети), JSDoc про `missingWarn` invariant в `tOrRaw`, cleanup dual-import в certificates | 🟢 | ✅ Done |
| TD-F11b | ✅ **Закрыт в F4.4 B3.** `CertificateSheet.vue` рендерит сертификат в iframe с `sandbox=""` (empty — запрещает всё). Blob URL наследует origin SPA → без sandbox любая ошибка в `autoescape` Jinja2 дала бы скрипту доступ к `localStorage` + JWT. Релаксация до `allow-same-origin` в будущем допустима только с узким allow-list под конкретную нужду (например CSS backgrounds от API origin); явный коммент в компоненте предупреждает об этом | 🟢 | ✅ Done |
| TD-F11c | `api/certificates.ts:fetchCertificateBlob` дублирует error-taxonomy из `api/client.ts` (ApiResponseError/Network/Timeout, Authorization header, timeout) — raw `fetch` потому что `api.client` всегда делает `response.json()`. Будущий источник дрифта: изменения в `client.ts` (например, `Accept-Language`, correlation-id, retries) не подхватятся certificates-путём. Миграция: расширить `api.client` опцией `responseType: 'json' \| 'blob' \| 'text'`, переписать `fetchCertificateBlob` через новый клиент. Преждевременно делать ради одного consumer'а — триггер миграции: появление второго не-JSON endpoint'а в проекте | 🟢 | По триггеру (второй не-JSON endpoint) |
| TD-F11d | `PortfolioView.vue` считает profit % клиентски (`(current_value - total_paid) / total_paid * 100`), потому что `PortfolioResponse` / `PortfolioPositionResponse` на бэке не эмитят profit field. Null-guard на `total_paid_cents <= 0` (gift-only позиции) — profit блок не рендерится. Когда backend добавит per-company / total profit (с учётом комиссий / налогов / возможных fee-корректировок), заменить computed на чтение из response и дропнуть локальную формулу. Переход сдвинет отображаемые цифры на sub-cent величины из-за округления — callers не должны сравнивать с кэшем. Помечено `// TD-F11d` в коде | 🟡 | Когда backend эмитит profit field в Portfolio* ответах |



