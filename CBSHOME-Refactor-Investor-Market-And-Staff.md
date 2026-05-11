# CBSHOME -- Refactor: Investor Market & Staff Shell

**Версия:** 0.5 final / decision-locked
**Дата:** 11 мая 2026

**Статус:** дизайн зафиксирован, дальше -- только реализация. Изменения в этом документе допускаются только через явный поворот решения (через обсуждение и новый changelog в issue/PR).

**Связанные документы:**
- `CBSHOME-Refactor-Company-Docs.md` v0.4 final -- параллельный refactor (storage, attachments, templates, Purchase docs). **Двусторонняя зависимость:** этот документ ссылается на storage-layer Refactor 2 для cover-загрузок Roadmap-items, Refactor 2 ссылается обратно для public investor flow context.
- `CBSHOME-Design-Document.md` -- Конституция v1.5
- `CBSHOME-Backend.md` -- Backend ТЗ v3.6
- `CBSHOME-Frontend.md` -- Frontend ТЗ v2.7
- `CBSHOME-Share-Pool-Refactor.md` -- архитектурный референс OptionPool

---

## 0. Контекст и цели

Заказчик зафиксировал две жалобы:
1. `/investor/market` "скучный и неполный" -- витрина начинается сразу с Продуктов всех Компаний вперемешку, без отдельной презентации Компаний.
2. У Компаний должен быть Роадмап как самостоятельная фича (модель `CompanyRoadmapItem` существует с Sprint 4.1, но никем не используется и в UI его нет вообще).

В ходе обсуждения вскрылись три глубоких пробела:

1. **Staff-сторона не имеет UI для управления Компаниями, Продуктами, Пулами и Роадмапами**, хотя бэк всё это умеет с Phase 4. Текущий Staff Shell -- 5 табов -- закрывает только KYC, юзеров, платежи и Avatar Mode. Контентной/конфигурационной поверхности нет.
2. **Roadmap и Posts (Sprint 9.1) -- две независимые сущности**, хотя семантически могут пересекаться (значимая новость -- это и пост в ленте, и веха в timeline компании).
3. **Платформа полностью закрыта auth-wall'ом.** Маркетинговая воронка невозможна -- нельзя дать инвестору посмотреть компанию и продукт по прямой ссылке (например, из LinkedIn) без регистрации. Что бьёт по conversion'у на старте.

Поскольку Роадмап -- собственность Staff (Компания не редактирует свои настройки -- см. инвариант "all changes via Staff" в `CBSHOME-Design-Document.md`), мы не можем сделать "просто роадмап-редактор" в отрыве от Staff-инфраструктуры управления Компаниями. Поэтому рефакторинг расширяется до:

- **Investor:** новая навигация Маркета через Компании.
- **Public investor flow:** компании и продукты публичны без auth, auth-wall только на действии "Купить".
- **Staff:** новый таб `Платформа` для всей контентной/конфигурационной работы; слияние KYC в `Пользователи`, чтобы освободить слот.
- **Backend:** доработки модели `CompanyRoadmapItem`, новые public-эндпоинты, embedded post snippet, статистика компании.

Цель -- одна последовательная смена парадигмы, а не четыре отдельных патча.

---

## 1. Investor Market: новая навигация

### 1.1. Текущее состояние

`InvestorShell` tab `Маркет` -> `MarketView.vue` рендерит грид всех активных Продуктов всех Компаний вперемешку. Фильтр по Компании -- через `CompanyFilterSheet` (bottom-sheet). Карточка ведёт в `ProductDetailView`. Никакой сводки по Компании нет.

### 1.2. Целевая навигация

```
Tab "Маркет"
  -> CompanyListView (новая)         -- список Компаний
       -> CompanyOverviewView (новая) -- профиль Компании, статистика, Роадмап, документы
            -> ProductsByCompany     -- текущий MarketView, прибитый к company_id
                 -> ProductDetailView -- без изменений
```

Tab `Маркет` ведёт сразу в `CompanyListView`. Никаких промежуточных переключателей "По компаниям / Все продукты".

### 1.3. Затронутые сущности (auth flow)

| Слой | Что |
|------|-----|
| Frontend view | `CompanyListView.vue` |
| Frontend view | `CompanyOverviewView.vue` (investor-side) |
| Frontend view | `MarketView.vue` |
| Frontend view | `ProductDetailView.vue` |
| Frontend component | `RoadmapTimeline.vue` |
| Frontend route | `/investor/companies` |
| Frontend route | `/investor/companies/:id` |
| Frontend route | `/investor/companies/:id/products` |
| Frontend route | `/investor/market` |
| Backend endpoint | `GET /api/v1/companies` |
| Backend endpoint | `GET /api/v1/companies/{id}` |

### 1.4. Зеркало под `/agent/...`

Agent имеет полный investor-доступ. Все три новых view зеркалятся под AgentShell с теми же route names через паттерн `isAgentShell(route)` (как сейчас сделано для MarketView / ProductDetailView).

### 1.5. Публичная статистика компании

`PublicCompanyDetailResponse` (тот же DTO для auth и public, см. §1.6) расширяется полем `stats`:

```python
class PublicCompanyStatsResponse(BaseModel):
    pool_total_options: int       # OptionPool.total_options
    options_sold: int             # SUM(purchases.units WHERE status != reversed AND legal_basis IN paid_or_gift)
    options_sold_percent: int     # 0..100, denormalized for UI
    price_growth_90d_percent: int # int, может быть отрицательным; computed via CompanyPriceHistory
    founded_at: date              # CompanyProfile.founded_at
```

Метрики числа активных Продуктов и `price_per_unit_cents` уже доступны через существующие поля `PublicCompanyDetailResponse` (products[] и price_per_unit_cents) -- отдельной строкой не дублируем.

**Чего НЕ показываем публично:**
- Revenue компании (коммерческая тайна).
- Количество и список инвесторов (privacy).
- Абсолютные числа продаж за период.

Решение по эндпоинту: расширяем существующий `GET /api/v1/companies/{id}` (и его public-версию, см. §1.6) -- никакого отдельного `/stats` эндпоинта. Лишний round-trip избыточен.

### 1.6. Публичный режим Investor Flow

**Цель.** Маркетинговая воронка: Заказчик публикует ссылку на компанию или продукт в LinkedIn / X / партнёрском сайте -- кто угодно открывает и видит контент без регистрации. Для попытки покупки -- auth-wall с возвратом на исходную страницу после онбординга.

**Уровень 2 публичности (зафиксированный scope):**

Публично (без auth):
- Список компаний.
- Страница компании: профиль, статистика, roadmap, attachments (см. Refactor 2 §3.4 и §7.2), список продуктов.
- Страница продукта: название, описание, цена, units, gift_units, варианты installment.

Только под auth:
- Кнопка "Купить" (приводит к auth-wall).
- Личный дашборд, портфолио, пополнения, выводы, агентская сеть.
- Чувствительные поля компании (`distribution_config`, аналитика продаж).
- Чувствительные поля продукта (`agent_bonus_units` в installment-плане -- агентская тема приватная).

#### 1.6.1. Public роуты на фронте

| Роут | Источник | Auth |
|------|----------|------|
| `/public/companies` | `CompanyListView.vue` (тот же компонент) | нет |
| `/public/companies/:id` | `CompanyOverviewView.vue` (тот же компонент) | нет |
| `/public/companies/:id/products` | `MarketView.vue` (тот же) | нет |
| `/public/products/:id` | `ProductDetailView.vue` (тот же) | нет |

Те же view-компоненты, что в `/investor/...`. Различие -- в auth-aware условном рендере: если не auth, скрываются приватные секции (например, "Мои покупки этого продукта", "Рекомендуемые на основе портфеля"). Кнопка "Купить" заменяется на "Войти и купить", которая делает `router.push({ name: 'register', query: { next: route.fullPath } })`.

После успешного завершения onboarding (verify-email + KYC + первый депозит) фронт читает `route.query.next` и делает `router.replace(route.query.next)`. Юзер оказывается на той же странице продукта, уже залогинен, может покупать.

#### 1.6.2. Public эндпоинты на бэке

Под префиксом `/api/v1/public/...`, без auth, с rate-limit per IP:

| Эндпоинт | Что отдаёт | Rate-limit |
|----------|-----------|------------|
| `GET /api/v1/public/companies` | List[`PublicCompanyResponse`] (без products[]) | 60/мин/IP |
| `GET /api/v1/public/companies/{id}` | `PublicCompanyDetailResponse` (включая stats, roadmap) | 60/мин/IP |
| `GET /api/v1/public/companies/{id}/products` | List[`PublicProductResponse`] | 60/мин/IP |
| `GET /api/v1/public/products/{id}` | `PublicProductDetailResponse` | 60/мин/IP |
| `GET /api/v1/public/companies/{id}/attachments` | см. Refactor 2 §3.4 | -- |
| `GET /api/v1/public/companies/{id}/attachments/{att_id}/download` | см. Refactor 2 §3.4 | -- |

Public-эндпоинты `companies` / `products` отдают **только** компании со статусом `active` (не draft, не archived).

**Почему отдельный префикс `/api/v1/public/*`, а не расширение существующих `/api/v1/companies` и `/api/v1/products` (где list/detail уже no-auth с Sprint 4.1/4.2):**

1. **Уже наполовину сделано в iter 2.2.** Attachments-public пошли под `/api/v1/public/companies/{id}/attachments` (см. Refactor 2 §3.4). Унификация остального под тот же префикс -- завершение начатого паттерна, не введение нового. Альтернатива (откат attachments назад под `/api/v1/companies/{id}/attachments`) -- ломка работающего production-кода с тестами.
2. **Operations.** WAF / Cloudflare / nginx rate-limit / Sentry sampling конфигурируются одним правилом на `/api/v1/public/*`. С mixed-префиксом -- точечно по каждому роуту, легко забыть новый при добавлении.
3. **Rate-limit 60 req/min/IP суммарно** (§1.6.4) -- натурально вешается одним middleware на префикс. Без префикса -- декоратор на каждый no-auth роут вручную.
4. **Frontend `useAuthWall` имеет URL-сигнал.** `PublicShell` распознаёт public-контекст по маршруту, а не по списку имён эндпоинтов которые надо синхронизировать с бэком.
5. **Threat model отличается.** Public-эндпоинты -- anonymous attackers, scraping, DDoS. Изолированный префикс упрощает применение защит, мониторинга, WAF-правил и аналитики "auth traffic vs public traffic".

**Что происходит со старыми `/api/v1/companies` и `/api/v1/products` (list/detail):**

Старые public-эндпоинты `GET /api/v1/companies`, `GET /api/v1/companies/{id}`, `GET /api/v1/products`, `GET /api/v1/products/{id}` **удаляются** в той же итерации, что и добавляются новые `/api/v1/public/*`. Не deprecated, удаляются. Frontend `companies.ts` и `products.ts` перепиываются на новый `public.ts` в той же итерации фронта (см. §1.7). До момента релиза мобильного приложения боевой нагрузки нет, поэтому окно ломки не критично.

Остаются нетронутыми: `GET /api/v1/companies/me` (Sprint 4.5, auth-only, не public), staff-side роуты `/api/v1/staff/companies/*`, company-side `/api/v1/company/*`.

#### 1.6.3. Pydantic-схемы

`PublicCompanyDetailResponse` существует с Sprint 4.1, ревизуется -- проверяем что не утекает чувствительное (`distribution_config` точно вырезаем, если оно там есть).

Новые схемы:
- `PublicProductResponse` -- id, company_id, name, description, cover_url, units, gift_units, price_per_unit_cents, status, has_installment_plans (bool, без раскрытия деталей).
- `PublicProductDetailResponse` -- то же + полные installment_plans, но **без `agent_bonus_units`** (агентская тема приватная).

#### 1.6.4. Rate-limit

Та же реализация Lua-script на Redis, что для auth-эндпоинтов (Sprint 1.x). Но вместо `key=user_id` -- `key=ip_address` (берём из `X-Real-IP` header'а как везде в проекте). Лимит 60 req/min/IP применяется ко всем `/api/v1/public/companies` и `/api/v1/public/products` эндпоинтам суммарно (не на каждый отдельно).

#### 1.6.5. Auth wall и redirect-after-auth

На фронте -- небольшой helper `useAuthWall()`:

```
function useAuthWall() {
  const route = useRoute()
  const router = useRouter()
  const auth = useAuthStore()

  function requireAuth(action: string) {
    if (auth.isAuthenticated) return true
    router.push({ name: 'register', query: { next: route.fullPath, intent: action } })
    return false
  }

  return { requireAuth }
}
```

В `ProductDetailView` кнопка "Купить" вызывает `requireAuth('purchase')` перед открытием purchase-flow. Если не auth -- redirect.

В компоненте `RegisterView` после `onboarding_complete` -- `if (route.query.next) router.replace(route.query.next as string)`.

Параметр `intent` оставляется на будущее (например, `intent=apply_agent` -> redirect на agent application form вместо product detail).

### 1.7. Затронутые сущности (public flow)

| Слой | Что |
|------|-----|
| Backend schema | `PublicCompanyResponse` (короткая, для list) |
| Backend schema | `PublicCompanyDetailResponse` -- ревизия чувствительных полей + добавление `stats` |
| Backend schema | `PublicProductResponse` (новая) |
| Backend schema | `PublicProductDetailResponse` (новая) |
| Backend router | `app/modules/companies/public_router.py` (новый, prefix `/api/v1/public`) |
| Backend router | `app/modules/products/public_router.py` (новый, prefix `/api/v1/public`) |
| Backend router | `app/modules/companies/router.py` -- **удаление** public `list` и `get_company_detail` endpoints (см. §1.6.2). Остаётся `/me` (Sprint 4.5). |
| Backend router | `app/modules/products/router.py` -- **удаление** public `list` и `get_product_detail` endpoints (см. §1.6.2). |
| Backend rate-limit | `check_rate_limit_per_ip()` helper |
| Frontend route | `/public/companies`, `/public/companies/:id`, `/public/products/:id` |
| Frontend layout | `PublicShell.vue` -- минимальный shell без таб-бара, с кнопкой "Войти" в шапке |
| Frontend composable | `useAuthWall()` |
| Frontend api | `frontend/src/api/public.ts` (новый клиент для public-эндпоинтов) |
| Frontend logic | `RegisterView` -- redirect-after-auth по `?next=` |

---

## 2. Staff Shell: новый Tab Bar

### 2.1. Текущий каркас

Сейчас StaffShell держит 5 табов:
`Главная` / `Пользователи` / `KYC` / `Платежи` / `Ещё`

L1-экраны из "Ещё": `Agent Applications`, `Avatar Mode`.

Не покрыто UI вообще: управление Компаниями, Продуктами, Пулами, Роадмапами, Постами, Событиями. Бэк-эндпоинты для всего этого существуют с Sprint 4.1 / 4.2 / 4.3 / 9.1.

### 2.2. Новый каркас

`Главная` / `Пользователи` / `Платежи` / `Платформа` / `Ещё`

| Таб | Что внутри |
|-----|------------|
| Главная | Без изменений (Dashboard со статистикой). |
| Пользователи | + KYC-функциональность как часть юзер-карточки и фильтры. См. §3. |
| Платежи | Без изменений в этой итерации (но см. §9, follow-up). |
| **Платформа** | Новый таб. Управление Компаниями, Продуктами, Пулами, Роадмапами, Постами, Событиями, Документами, Шаблонами. См. §4. |
| Ещё | Agent Applications, Avatar Mode, Consistency tool (Sprint 6.4) -- как сейчас. |

### 2.3. Затронутые сущности

| Слой | Что |
|------|-----|
| Frontend | `frontend/src/router/tabs.ts` -- `STAFF_TABS` |
| Frontend | `StaffKYCView.vue` |
| Frontend route | `/staff/kyc` |
| Frontend | `StaffUsersView.vue` |
| Frontend | `PlatformView.vue` (новый таб) |
| Frontend route | `/staff/platform/*` |
| Frontend i18n | `tab.staff.kyc` -- удалить |
| Frontend i18n | `tab.staff.platform` + соответствующий nav-tree |

---

## 3. Слияние "Пользователи" и "KYC"

### 3.1. Обоснование

KYC -- атрибут User, а не отдельная сущность с lifecycle. На бэке `User.kyc_status` уже денормализован из `KYCApplication.status`. Tab `KYC` -- это, по сути, сохранённый фильтр `users WHERE kyc_status = submitted`. Отдельный таб ради одного фильтра не оправдан.

### 3.2. Что меняется в `StaffUsersView`

- В фильтр-чипы добавляется группа `KYC`: `all / not_started / submitted / approved / rejected`.
- Пресет "Pending KYC" (фильтр `submitted`) виден отдельным быстрым chip'ом, чтобы операторы не теряли свой текущий быстрый сценарий.
- Default view не меняется -- список всех юзеров без KYC-фильтра, как сейчас.
- В detail-модалке юзера появляется секция `KYC Application`:
  - текущий статус, дата подачи последней заявки;
  - список истории (если были re-submits после rejection);
  - кнопки `Approve` / `Reject` -- видны если статус = `submitted`, гейтятся `kyc_approve` permission;
  - reject -- с обязательным полем причины (как сейчас в StaffKYCView).
- Существующие действия в detail (`Block`, `Promote to Staff`) -- без изменений, со своими permission-гейтами.

### 3.3. Backend

- `GET /api/v1/staff/users` -- добавляется опциональный query-параметр `?kyc_status=` (значения: `not_started / submitted / approved / rejected`). Без него список не фильтруется по KYC, как сейчас. С ним -- условие `User.kyc_status == requested_status` в SQLAlchemy-запросе.
- `GET /api/v1/staff/kyc/queue` -- остаётся как pre-built filter для backward-compatibility, не депрекейтится в этой итерации.
- Существующие KYC actions:
  - `POST /api/v1/staff/kyc/{id}/approve` (permission `kyc_approve`)
  - `POST /api/v1/staff/kyc/{id}/reject` (permission `kyc_approve`)

---

## 4. Tab "Платформа": каркас

### 4.1. Назначение

Единая точка для контентной и конфигурационной работы Staff. Всё, что Компания не имеет права редактировать сама.

### 4.2. Структура (вариант C -- гибрид)

```
/staff/platform
  -> News                            -- лента всех Posts (фильтр по owner_type / company)
  -> Events                          -- календарь событий платформы
  -> Companies                       -- список компаний
       -> Company detail             -- детальная карточка одной компании, секции через nested routes
            /profile                 -- профиль (просмотр в MVP, редактирование вне MVP)
            /price                   -- цена + price history
            /roadmap                 -- редактор Роадмапа (см. §5)
            /posts                   -- встроенный PostListEditor с pre-set filter owner_id
            /documents               -- attachments (см. Refactor 2 §3, §6.2)
            /templates               -- doc templates (см. Refactor 2 §4, §6.3)
            /pool                    -- (вне MVP)
            /products                -- (вне MVP)
```

**Layout секций:** nested routes (deeplink-friendly, чище для navigation guards). Каждая секция -- отдельный роут типа `/staff/platform/companies/:id/roadmap`, общий `<router-view>` внутри `StaffCompanyDetailView`.

**Posts of company:** встроенный `PostListEditor.vue` (тот же компонент, что в глобальной News), но с pre-set фильтром `owner_type=company AND owner_id=current_company`. Кнопка "+ Создать пост" pre-fill'ит owner-поля. Никакого deep-link к глобальной News.

### 4.3. MVP scope для Платформы

В MVP входит:

| Раздел | Что | Permissions |
|--------|-----|-------------|
| News | CRUD Posts (platform + company) | `content_manage` |
| Events | CRUD Events (платформенные) | `content_manage` |
| Companies -> list | Просмотр списка компаний | любой staff |
| Companies -> Profile (просмотр) | name, description, status | любой staff |
| Companies -> Price | Изменение цены юнита, просмотр price history | `company_manage` + `financial_operations` |
| Companies -> Roadmap | CRUD roadmap items, drag-and-drop reorder, cover upload | `company_manage` |
| Companies -> Posts of company | Тот же CRUD Posts, prebound | `content_manage` |
| Companies -> Documents | CRUD attachments (см. Refactor 2 §3) | `company_manage` |
| Companies -> Templates | CRUD doc templates (см. Refactor 2 §4) | `company_manage` |

Вне MVP (через seed-скрипт на старте, UI -- post-MVP):

| Раздел | Что | Замечания |
|--------|-----|-----------|
| Companies -> Profile (редактирование) | name, description, медиа, distribution_config, status | Редкая операция, риск каскадных эффектов на Products. Просмотр -- в MVP, редактирование -- нет. |
| Companies -> Pool | Создание / допэмиссия OptionPool | Финансовая операция с прямым влиянием на доступность продуктов. Только seed на старте. |
| Companies -> Products | Создание / редактирование Products + Installment templates | Через seed на старте. |
| Создание Компании | `POST /staff/companies` | Только seed на старте. |

### 4.4. Создание Компаний: текущий флоу остаётся

`POST /api/v1/staff/companies` сейчас атомарно создаёт **нового** User'а с role=company + CompanyProfile + supply + distribution_config + начальную цену. Этот флоу остаётся как есть, не "переназначает роль существующего юзера". UI для этого эндпоинта в MVP не делаем -- staff пока выполняет создание через seed-скрипт (`backend/scripts/seed_storefront.py`).

Замечание про "переназначение роли существующих юзеров" -- зафиксировано как пожелание для post-MVP. Если оно потребуется -- это новый эндпоинт `POST /staff/companies/from-user/{user_id}` или расширение существующего, не часть текущего рефакторинга.

### 4.5. Permissions matrix

Текущая `DEFAULT_STAFF_PERMISSIONS` (после Sprint 9.1):
- `avatar_mode`, `kyc_approve`, `payment_review`, `user_block`, `financial_operations`, `agent_application_review`, `translation_edit` (default false), `company_manage`, `content_manage`.

Что покрывает MVP-операции таба «Платформа»:

| Операция | Permissions |
|----------|-------------|
| Изменить цену юнита Компании | `company_manage` + `financial_operations` |
| CRUD Roadmap (включая cover upload) | `company_manage` |
| CRUD Posts (любого `owner_type`) | `content_manage` |
| CRUD Events | `content_manage` |
| CRUD Attachments (см. Refactor 2) | `company_manage` |
| CRUD Doc Templates (см. Refactor 2) | `company_manage` |
| Hard-delete attachments | admin (см. Refactor 2 Q-ATT-1) |

Никаких изменений в матрице permissions для MVP не требуется -- всё уже на месте.

### 4.6. Затронутые сущности

| Слой | Что |
|------|-----|
| Frontend route | `/staff/platform` (redirect на `/staff/platform/news`) |
| Frontend route | `/staff/platform/news` |
| Frontend route | `/staff/platform/events` |
| Frontend route | `/staff/platform/companies` |
| Frontend route | `/staff/platform/companies/:id/profile|price|roadmap|posts|documents|templates` |
| Frontend view | `StaffNewsView.vue` (общая лента Posts) |
| Frontend view | `StaffEventsView.vue` |
| Frontend view | `StaffCompaniesListView.vue` |
| Frontend view | `StaffCompanyDetailView.vue` (shell для секций, с табами или sidebar навигацией к nested routes) |
| Frontend view | `StaffCompanyProfileSection.vue` |
| Frontend view | `StaffCompanyPriceSection.vue` |
| Frontend view | `StaffCompanyRoadmapSection.vue` |
| Frontend view | `StaffCompanyPostsSection.vue` |
| Frontend view | `StaffCompanyDocumentsSection.vue` |
| Frontend view | `StaffCompanyTemplatesSection.vue` |
| Frontend component | `PostListEditor.vue` (общий для News и Posts of company) |
| Frontend component | `RoadmapEditor.vue` |
| Backend | без изменений в MVP scope (все эндпоинты есть с Sprint 4.1, 4.3, 9.1, плюс расширения см. §7) |

---

## 5. Roadmap: модель и UX

### 5.1. Текущая модель `CompanyRoadmapItem`

Поля: `id, company_id, title, description, target_date, status, order, is_deleted, created_at, updated_at`. Status: `planned / in_progress / completed`. Soft-delete. Reorder через `order`.

State machine у статусов **отсутствует** -- любой переход разрешён.

### 5.2. Существующие эндпоинты (Sprint 4.1, permission `company_manage`)

- `POST /api/v1/staff/companies/{id}/roadmap`
- `PATCH /api/v1/staff/companies/{id}/roadmap/{item_id}`
- `DELETE /api/v1/staff/companies/{id}/roadmap/{item_id}` (soft)
- `PATCH /api/v1/staff/companies/{id}/roadmap/reorder`

### 5.3. Связь с Posts -- вариант C (cross-link)

Roadmap-item и Post -- две независимые сущности с опциональной cross-link.

Семантика:
- **Post** = «новость в общей ленте». Может существовать сам по себе, не связан ни с каким roadmap-item. Виден на дашборде Investor, в News, в карточке компании.
- **Roadmap-item** = «курируемая ключевая точка в timeline компании». Может ссылаться на ноль или один Post. Виден в `RoadmapTimeline` на CompanyOverview.

Три режима создания roadmap-item в UI (соответствуют значениям `kind`):

1. **`milestone`** -- title, description, target_date (опционально), status, без `post_id`. Постоянная веха ("Получили патент"). Может иметь `post_id` если Staff хочет связать с полным блог-постом.
2. **`event`** -- короткоживущее событие (AMA, демо-день). Обязательно `target_date` + `valid_until`. Поле `valid_until` сохраняется в БД на будущее (для post-MVP архивирования). В MVP-фронте оно не используется -- все опубликованные events видны в timeline подряд (см. §6.1).
3. **`announcement`** -- объявление без даты (новое партнёрство, изменение в команде, общий апдейт). Без `target_date`, без `valid_until`. Постоянное короткое сообщение.

### 5.4. Финальный набор полей `CompanyRoadmapItem`

Добавляются к существующим:

| Поле | Тип | Назначение |
|------|-----|------------|
| `kind` | `String(20)` | `milestone | event | announcement` (new enum `RoadmapItemKind`) |
| `cover_storage_key` | `String(1000), nullable` | ключ в MinIO (см. §5.5). NULL = без обложки |
| `external_url` | `String(2000), nullable` | внешняя ссылка (Zoom, новостной портал) |
| `post_id` | `UUID, FK posts.id, nullable, ondelete=SET NULL` | связанный пост |
| `linked_product_id` | `UUID, FK products.id, nullable, ondelete=SET NULL` | связанный продукт |
| `valid_until` | `Date, nullable` | для kind=event: дата выхода из активной части timeline |

Минимальные требования по полям для каждого `kind` (валидация в Pydantic):

| `kind` | Обязательно | Опционально | Не используется |
|--------|-------------|-------------|-----------------|
| `milestone` | `title` | `description, target_date, status, cover_storage_key, external_url, post_id, linked_product_id` | `valid_until` |
| `event` | `title, target_date, valid_until` | `description, status, cover_storage_key, external_url, post_id, linked_product_id` | -- |
| `announcement` | `title` | `description, cover_storage_key, external_url, post_id, linked_product_id` | `target_date, valid_until, status` |

`status` для kind=event и kind=announcement игнорируется UI'ом -- эти kind'ы не имеют lifecycle "запланировано → в работе → завершено".

Валидация `linked_product_id`: продукт должен принадлежать **той же компании** (`product.company_id == roadmap_item.company_id`). Проверка в service layer на create/update -- 400 при mismatch. БД constraint избыточен.

### 5.5. Cover-загрузка через MinIO storage layer

Cover-обложка для roadmap-item -- файл (не URL). Загружается через тот же storage layer, что и attachments в Refactor 2 §2.

- **MinIO путь:** `companies/{company_id}/roadmap/{item_id}/cover.{ext}`
- **API в response:** `RoadmapItemResponse.cover_url: str | None` -- backend на лету генерирует presigned URL (TTL_AUTH = 15min) из `cover_storage_key`. Фронт получает уже готовую ссылку, ничего не знает про MinIO.
- **Эндпоинты:**
  - `PUT /api/v1/staff/companies/{id}/roadmap/{item_id}/cover` -- multipart upload. Backend пишет в MinIO, обновляет `cover_storage_key`. Mime whitelist: `image/png, image/jpeg, image/webp` (covers -- только картинки). Max size: 10MB.
  - `DELETE /api/v1/staff/companies/{id}/roadmap/{item_id}/cover` -- удаляет объект из MinIO, обнуляет `cover_storage_key`.
- **Permissions:** `company_manage` (та же что для всего CRUD roadmap).

**Cross-document зависимость:** Refactor 2 §2 (storage abstraction) -- блокер для этой части Refactor 1. Но storage layer -- thin wrapper, не блокирует параллельную разработку остальных частей Roadmap.

### 5.6. State machine на `RoadmapItemStatus`

Применяется только к `kind=milestone` (event и announcement не имеют status).

Переходы:
- При создании -- всегда `planned` (Pydantic-default, отвергаются другие значения в create body).
- `planned -> in_progress` -- разрешено.
- `planned -> completed` -- разрешено (бывает что что-то делается без явной "in_progress" фазы).
- `in_progress -> planned` -- разрешено (откат до старта).
- `in_progress -> completed` -- разрешено.
- `completed -> *` -- **запрещено** (готовое назад не возвращается). 400 в API. Если Staff ошибся -- soft-delete + создать новый item.

Soft-delete и hard-delete -- независимы от state machine, разрешены из любого статуса (с permission `company_manage`).

### 5.7. UX редактора

Структура секции `Roadmap` в `StaffCompanyDetailView` (на роуте `/staff/platform/companies/:id/roadmap`):

- Список этапов в текущем порядке (`order ASC`).
- Drag-handle на каждом этапе для drag-and-drop reorder (через `vuedraggable` -- уже в стеке).
- На карточке этапа: cover-thumbnail (если есть), title, дата (target_date / valid_until), бейдж kind (цветная плашка milestone/event/announcement), бейдж status (если milestone), кнопки `Edit` и `Delete`.
- Кнопка `+ Добавить этап` -- открывает модалку с табами `milestone | event | announcement`. По табу подставляются нужные поля формы (с обязательными по таблице §5.4).

В форме редактирования:
- Cover -- drag-drop zone или file input.
- Связь с Post -- комбобокс с поиском по постам этой компании + опция "+ Создать связанный пост" (открывает sub-форму создания Post с pre-filled owner_type/owner_id).
- Связь с Product -- комбобокс с поиском по продуктам этой компании.
- External URL -- text input с валидацией http/https.

---

## 6. Roadmap & News: публичная подача на Investor

### 6.1. RoadmapTimeline на CompanyOverviewView

Из `GET /api/v1/companies/{id}` (auth) и `GET /api/v1/public/companies/{id}` (public) приходит `PublicCompanyDetailResponse.roadmap: list[RoadmapItemResponse]`.

**Визуал:** **вертикальная timeline** -- ось слева, карточки справа, прокрутка пальцем сверху вниз. Mobile-first; на desktop тот же layout, шире карточки.

**Сортировка:** простой `order ASC` для всех элементов, без фильтрации по `status` или `valid_until`. Все опубликованные roadmap-items видны инвестору. Сортировку curate'ит Staff в редакторе (§5.7) через drag-drop reorder.

В MVP **нет toggle "Показать архив"**, нет деления на активные/завершённые в UI. Все элементы рендерятся подряд. Если у компании 30 milestone'ов -- все 30 видны на странице. Контентом управляет Staff: если хочется убрать историю с глаз инвестора -- soft-delete старого item'а, а не toggle.

Архивный toggle / inline-сворачивание completed -- post-MVP follow-up, если по UX-метрикам станет нужно.

**Empty state:** если у компании 0 опубликованных roadmap-items -- секция "Дорожная карта" на CompanyOverview **скрывается целиком**. Никакого placeholder'а с текстом "следите за обновлениями" -- инвестор просто не видит блока, страница без него выглядит чисто. Контентом управляет Staff: пока roadmap пустой, секции нет.

Карточка roadmap-item рендерится так:
- Если `cover_storage_key` есть -- картинка сверху.
- Title.
- Дата (`target_date` для milestone, `target_date` для event, без даты для announcement).
- Бейдж kind / status.
- Description (если есть и нет post_id).
- Если `post_id` -- embedded post snippet (см. §6.2): cover Post'а, превью body (200 знаков), кнопка "Читать полностью" -> `/investor/posts/:id`.
- Если `linked_product_id` -- кнопка "Перейти к продукту" -> `ProductDetailView`.
- Если `external_url` -- кнопка "Открыть" с indicator "external link".

В конце timeline -- end-marker: финальная точка на оси + подпись "Начало истории компании · {founded_at year}". Визуально показывает что это нижний край списка, инвестор не ждёт что там есть ещё.

### 6.2. Embedded post snippet

`RoadmapItemResponse` расширяется опциональным полем:

```python
class PostSnippetResponse(BaseModel):
    id: UUID
    title: str
    cover_url: str | None  # presigned via MinIO if Post has its own cover (Sprint 9.1 -- url stored as-is)
    excerpt: str  # first 200 characters of body, plain text (HTML stripped)

class RoadmapItemResponse(BaseModel):
    # ... existing fields ...
    post: PostSnippetResponse | None  # populated if post_id is set; otherwise None
```

В service layer -- LEFT JOIN на posts при загрузке roadmap, без N+1. Один запрос отдаёт roadmap + linked posts.

Полный body Post грузится по клику "Читать полностью" -- отдельный round-trip `GET /api/v1/posts/{id}` (или public-вариант).

### 6.3. Лента News + Events на Investor

На `InvestorDashboardView`:
- Существующий widget "Latest news" (top-5 Posts) -- остаётся (F4.4 B2 уже сделан).
- Новый widget "Upcoming events" -- top-3 events по `starts_at ASC` где `starts_at >= now AND is_published=true`. Источник: `GET /api/v1/events/upcoming?limit=3` (новый эндпоинт или query-параметр существующего).

**Empty state виджета "Upcoming events":** если результат запроса пустой (нет ближайших событий) -- виджет на дашборде **скрывается целиком**. Никакого placeholder'а. Контентом управляет Staff.

Отдельный экран `/investor/events` (с зеркалом `/agent/events`):
- Список всех опубликованных Events с пагинацией.
- Фильтры: `upcoming` / `past`.
- Карточка: cover, title, описание, дата+время, location, кнопка "Перейти" если есть `url`.
- Если фильтр вернул пустой результат -- минимальный fallback "Нет событий". Никакой иллюстрации, CTA или красивого empty-state -- задача в MVP только не крашить фронт.

Никакого отдельного `/investor/feed` (объединённая лента Posts + Events). Posts и Events -- разные сущности с разной семантикой, на дашборде разные виджеты, отдельных экранов в MVP -- только Events. Полный экран "Все posts" -- follow-up (F9.2 в Frontend ТЗ).

### 6.4. Event.company_id

**НЕ добавляем.** Платформенные Events (вебинары CBS HOME) живут как глобальная сущность без company_id. Компанейские "события" (AMA, дедлайны компании) живут как `RoadmapItem.kind=event`. Сущности разделены семантически, никакой опциональный FK на компанию у Event не нужен.

---

## 7. Backend changes: финальный список

| Задача | Источник |
|--------|----------|
| Расширение `CompanyRoadmapItem` 6 новыми полями | §5.4 |
| Миграция: новые колонки + индексы | §5.4 |
| `RoadmapItemKind` enum в `companies/constants.py` | §5.3 |
| Pydantic-валидаторы по `kind` | §5.4 |
| State machine на `status` (только для kind=milestone) | §5.6 |
| Эндпоинты cover upload/delete для roadmap-item | §5.5 |
| `RoadmapItemResponse` расширяется `cover_url` (presigned) и `post: PostSnippetResponse \| None` | §5.5, §6.2 |
| `PublicCompanyStatsResponse` + расширение `PublicCompanyDetailResponse.stats` | §1.5 |
| Public роутер `app/modules/companies/public_router.py` | §1.6 |
| Public роутер `app/modules/products/public_router.py` | §1.6 |
| `PublicProductResponse`, `PublicProductDetailResponse` | §1.6 |
| Ревизия `PublicCompanyDetailResponse` -- удаление чувствительных полей | §1.6 |
| `check_rate_limit_per_ip()` helper | §1.6 |
| Параметр `?kyc_status=` в `GET /staff/users` | §3.3 |
| Storage layer (`app/core/storage.py`) -- зависимость от Refactor 2 §2 | -- |

Миграции:
1. Добавление 6 колонок в `company_roadmap_items` (kind / cover_storage_key / external_url / post_id / linked_product_id / valid_until) + индексов.

Никаких изменений в `Event.company_id` -- остаётся как есть.

---

## 8. Frontend changes: финальный список

| Задача | Источник |
|--------|----------|
| `CompanyListView.vue` (общий для investor / agent / public) | §1, §1.6 |
| `CompanyOverviewView.vue` (общий) | §1, §1.6 |
| `RoadmapTimeline.vue` (вертикальная) | §6.1 |
| `ProductDetailView.vue` -- auth-aware кнопка "Купить" | §1.6.5 |
| Новые роуты `/investor/companies/*` + зеркала `/agent/...` | §1 |
| Новые public роуты `/public/companies/*`, `/public/products/:id` | §1.6 |
| `PublicShell.vue` (минимальный shell для public flow) | §1.6 |
| `useAuthWall()` composable + `RegisterView` redirect-after-auth | §1.6.5 |
| `frontend/src/api/public.ts` (клиент public-эндпоинтов) | §1.6 |
| Редирект `/investor/market` -> `/investor/companies` | §1 |
| `STAFF_TABS` -- замена `kyc` на `platform` | §2.2 |
| Удаление `StaffKYCView.vue` | §2.3 |
| Расширение `StaffUsersView.vue` (KYC-фильтры + KYC-секция в detail) | §3.2 |
| `StaffNewsView.vue` (общая лента Posts) | §4.6 |
| `StaffEventsView.vue` | §4.6 |
| `StaffCompaniesListView.vue` | §4.6 |
| `StaffCompanyDetailView.vue` shell (с nested-route навигацией к секциям) | §4.6 |
| `StaffCompanyProfileSection.vue` (просмотр) | §4.6 |
| `StaffCompanyPriceSection.vue` | §4.6 |
| `StaffCompanyRoadmapSection.vue` + `RoadmapEditor.vue` + drag-drop reorder | §5.7 |
| Cover upload в RoadmapEditor (file input + preview) | §5.5 |
| `StaffCompanyPostsSection.vue` (встроенный `PostListEditor`) | §4.2, §4.6 |
| `PostListEditor.vue` (общий компонент) | §4.6 |
| Widget "Upcoming events" на `InvestorDashboardView` | §6.3 |
| `/investor/events` экран + AgentShell зеркало | §6.3 |

---

## 9. Открытые вопросы / отложенные решения

**Все вопросы закрыты.** Документ decision-locked.

**Closed (решения зафиксированы):**

### v0.5 -- обоснование префикса `/api/v1/public/*`

- **§1.6.2 расширен**: добавлено явное обоснование выбора префикса `/api/v1/public/*` (5 пунктов: уже-наполовину-сделано в iter 2.2, operations, rate-limit middleware, frontend URL-сигнал, threat model). Сам префикс не меняется -- меняется только документация причины. До v0.5 обоснование было неявным, что породило вопрос на старте iter 2.4 ("а спека не ошибается ли?"). Зафиксировано чтобы будущим итерациям не пришлось повторно решать.
- **§1.6.2 + §1.7 уточнены**: явно прописано что старые public-эндпоинты `GET /api/v1/companies`, `GET /api/v1/companies/{id}`, `GET /api/v1/products`, `GET /api/v1/products/{id}` **удаляются** в той же итерации, не помечаются deprecated. Окно ломки контролируется тем, что фронт перепиывается в той же итерации, а боевой мобильной нагрузки до релиза нет. `GET /api/v1/companies/me` (Sprint 4.5) не трогается.

### v0.4 -- UI follow-ups закрыты

- **F-1 (toggle архива roadmap)**: **отменён**. В MVP архивный toggle не делаем. Все опубликованные roadmap-items видны подряд, сортировка `order ASC`. Контентом управляет Staff -- если хочется убрать историю с глаз инвестора, делает soft-delete. Архивный toggle / inline-сворачивание completed-items -- post-MVP follow-up если потребуется по UX-метрикам (§6.1).
- **F-2 (placeholder при пустом roadmap)**: при empty list секция "Дорожная карта" на CompanyOverview **скрывается целиком**. Никакого placeholder'а. Контентом управляет Staff (§6.1).
- **F-3 (empty state events)**: widget "Upcoming events" на дашборде **скрывается целиком** при empty. Экран `/investor/events` -- минимальный fallback "Нет событий", без иллюстраций / CTA. Задача в MVP только не крашить фронт (§6.3).

### v0.3 closed (без изменений в v0.4)

- **5 публичных метрик компании** (§1.5): pool_total_options, options_sold, options_sold_percent, price_growth_90d_percent, founded_at. Расширение существующего эндпоинта `GET /companies/{id}`, никакого отдельного `/stats`.
- **Public Investor flow** (§1.6): уровень 2 публичности -- компании и продукты публичны без auth, auth-wall на "Купить", redirect-after-auth через `?next=`. Public роуты `/public/companies/*`, `/public/products/:id`. Новый `PublicShell`, `useAuthWall()` composable. Public-эндпоинты под `/api/v1/public/`, rate-limit 60 req/min/IP. Новые Pydantic-схемы `PublicProductResponse`, `PublicProductDetailResponse`.
- **Финальные поля `CompanyRoadmapItem`** (§5.4): kind (milestone/event/announcement), cover_storage_key (файл в MinIO, не URL), external_url, post_id (FK), linked_product_id (FK same-company), valid_until.
- **Cover-загрузка через MinIO storage layer** (§5.5): зависимость от Refactor 2 §2. Эндпоинты PUT/DELETE cover. В response отдаётся presigned URL.
- **State machine на `RoadmapItemStatus`** (§5.6): запрещены переходы из `completed`. Применяется только к kind=milestone.
- **Embedded post snippet** (§6.2): `RoadmapItemResponse.post: PostSnippetResponse | None` через LEFT JOIN, без N+1.
- **Vertical RoadmapTimeline** (§6.1): mobile-first, ось слева, карточки справа.
- **Events на Investor** (§6.3): widget "Upcoming events" (top-3) на `InvestorDashboardView` + отдельный экран `/investor/events` с фильтром upcoming/past.
- **Event.company_id НЕ добавляем** (§6.4): компанейские события через `RoadmapItem.kind=event`.
- **`?kyc_status=`** в `GET /staff/users` (§3.3).
- **`StaffCompanyDetailView` layout** (§4.2, §4.6): nested routes для секций.
- **Posts of company section**: встроенный `PostListEditor` с pre-set фильтром, не deep-link.

**Follow-up за пределами текущего рефакторинга:**

- Консолидация таба `Платежи` + Withdrawals review в единый таб `Финансы` (`Deposits` / `Withdrawals`). Бэк готов (Sprint 6.3), UI Withdrawals review отсутствует.
- UI для создания Компаний / Pools / Products в `StaffCompanyDetailView`.
- Эндпоинт `POST /staff/companies/from-user/{user_id}` для "переназначения" роли существующего юзера.
- Полный экран `/investor/posts` с пагинацией всех Posts (F9.2 в Frontend ТЗ).
- Объединённая лента `/investor/feed` (Posts + Events) -- если по UX потребуется после запуска.
- Public роуты с deep-link `?intent=apply_agent` -- для маркетинговых ссылок на agent-application.
- Архивный toggle в RoadmapTimeline -- если по UX-метрикам станет нужно.
