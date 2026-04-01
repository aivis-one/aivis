# CBSHOME -- Техническое задание (Backend)

**Версия:** 0.2
**Дата:** 1 апреля 2026
**Статус:** В работе
**Репозиторий:** https://github.com/aivis-one/cbshome

**Зависимости (читать перед работой):**
- `CBSHOME-Design-Document.md` — Конституция v1.5
- `CBSHOME-Financial-System.md` — финансовая логика
- `CBSHOME-State-Machines.md` — переходы статусов
- `CBSHOME-Installment.md` — механика рассрочки

---

## Стилевое соглашение

- Комментарии в коде: только английский
- Общение / документация: русский
- Стрелки в коде: только `->` (ASCII)
- Тире в коде: только `--` (двойной дефис)
- Unicode-символы: только в документации вне кода
- Formatter: ruff
- Type checker: mypy (strict)

---

## Фазы разработки

---

## PHASE 0: Инфраструктура + Core Models

---

### Sprint 0.1: Репозиторий + структура проекта

**Цель:** Базовая структура репозитория, готовая к разработке на VPS.

**Задачи:**
- [ ] GitHub репозиторий `aivis-one/cbshome`
- [ ] `.gitignore` (PyCharm, VS Code, .env, __pycache__)
- [ ] Структура папок:
```
cbshome/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── core/
│   │   └── modules/
│   ├── tests/
│   ├── migrations/
│   ├── scripts/
│   ├── Dockerfile
│   └── pyproject.toml
├── frontend/
├── notifications/
│   └── templates/
├── diagrams/
├── docker-compose.yml
├── scripts/
│   └── install_cbshome.sh
└── CBSHOME-Design-Document.md
```
- [ ] `pyproject.toml` — зависимости, ruff, mypy, pytest конфиг
- [ ] `app/core/config.py` — pydantic-settings, загрузка из .env
- [ ] `app/core/exceptions.py` — `CBSError -> NotFound / Forbidden / Conflict / BadRequest / Unauthorized`
- [ ] `app/core/mixins.py` — `UUIDMixin`, `TimestampMixin`, `JSONBMixin` (с `set_jsonb` + `flag_modified`)
- [ ] `app/core/constants.py` — `LedgerReason` (все канонические reasons из Financial System Codex)
- [ ] `tests/conftest.py` — async client fixture
- [ ] `tests/test_root.py` — базовый тест
- [ ] `.env.example`
- [ ] `README.md` — только VPS инструкции

**Результат:**
```
backend/app/core/
├── config.py
├── exceptions.py
├── mixins.py       -- UUIDMixin, TimestampMixin, JSONBMixin
└── constants.py    -- LedgerReason
```

**Критерий готовности:** `ruff check .` и `mypy .` проходят без ошибок.

---

### Sprint 0.2: Docker + FastAPI скелет

**Цель:** Работающее приложение в Docker с health checks.

**Задачи:**
- [ ] `docker-compose.yml` — app + postgres:16 + redis:7-alpine
- [ ] Postgres/Redis без published портов (только Docker internal network)
- [ ] App на `127.0.0.1:8000`
- [ ] `Dockerfile` — multi-stage, dev зависимости всегда устанавливаются (тесты в контейнере)
- [ ] `.dockerignore`
- [ ] `app/core/database.py` — AsyncEngine + AsyncSession + `get_db_session()` + `get_db_reader()` + `Base`
- [ ] `app/core/redis.py` — async Redis client + lifecycle
- [ ] `app/core/logging.py` — structlog (JSON в prod, Console в dev)
- [ ] `app/core/middleware.py` — `TraceIdMiddleware` (X-Trace-ID в каждый запрос/ответ)
- [ ] CORS middleware (origins из config)
- [ ] `GET /` — версия API
- [ ] `GET /health` — DB (SELECT 1) + Redis (PING), всегда 200
- [ ] `GET /ready` — 503 если деградация
- [ ] Lifespan: startup (structlog + Redis) -> shutdown (Redis close + engine dispose)
- [ ] `tests/test_health.py` — 3 теста (all ok, db down, redis down)

**Endpoints:**
```
GET /        -> {"name": "CBSHOME API", "version": "0.1.0"}
GET /health  -> {"status": "ok", "db": "ok", "redis": "ok"}    (200 always)
GET /ready   -> {"status": "ok", "db": "ok", "redis": "ok"}    (200 or 503)
```

**Критерий готовности:** `docker compose up` поднимает стек, `curl localhost:8000/health` возвращает 200.

---

### Sprint 0.3: Alembic + Core Models

**Цель:** Схема БД для всего фундамента платформы. Это самый важный спринт Phase 0.

**Задачи:**

**Alembic:**
- [ ] `alembic.ini` — URL из config, не хардкод
- [ ] `migrations/env.py` — async runner

**Модели (все в одной миграции `initial_schema`):**

- [ ] `app/modules/users/models.py` — `User`:
```python
User:
    id: UUID
    role: enum        -- investor | agent | company | staff | platform
    is_system: bool   -- default False (только для Platform)
    is_active: bool   -- default True
    onboarding_step: enum  -- registered | email_verified | profile_complete | kyc_done | role_selected
    kyc_status: enum  -- not_started | submitted | approved | rejected
    credentials: JSONB  -- {email: {...}, telegram: {...}, onboarding: {...}}
    profile: JSONB      -- {first_name, last_name, country, phone, ...}
    language: str       -- "en" (default)
    created_at, updated_at
```

- [ ] `app/modules/ledgers/models.py` — `ActiveLedger`, `PassiveLedger`:
```python
LedgerEntry:  -- базовые поля для обоих леджеров
    id: UUID
    user_id: UUID     -- FK users.id
    amount_cents: int -- отрицательные для списаний
    status: enum      -- frozen | confirmed | reversed
    frozen_until: datetime | None
    origin_payment_id: UUID | None  -- FK payments.id (circular, deferrable)
    reason: str       -- из LedgerReason
    created_at: datetime  -- иммутабельно, нет updated_at
```

- [ ] `app/modules/staff/models.py` — `StaffProfile`, `AvatarSession`:
```python
StaffProfile:
    id: UUID
    user_id: UUID     -- FK users.id, UNIQUE
    permissions: JSONB  -- permission matrix
    is_active: bool
    created_at

AvatarSession:
    id: UUID
    staff_id: UUID    -- FK users.id
    target_user_id: UUID  -- FK users.id
    status: enum      -- active | ended
    ip_address: str
    created_at
    ended_at: datetime | None
```

- [ ] `app/core/audit.py` — `AuditLog`:
```python
AuditLog:  -- иммутабельно, наследует Base напрямую
    id: UUID
    created_at: datetime  -- server_default
    event: str            -- indexed
    actor_id: UUID | None
    actor_type: str       -- "user" | "staff" | "system"
    performed_by: UUID | None  -- staff_id при аватаринге
    on_behalf_of: UUID | None  -- target_user_id при аватаринге
    target_type: str
    target_id: UUID
    data: JSONB
    ip_address: str | None
    user_agent: str | None
    trace_id: str | None  -- String(36)
```

- [ ] Миграция `initial_schema` — все таблицы разом
- [ ] `migrations/env.py` — импорты всех моделей для autogenerate

**Seed системного пользователя Platform:**
- [ ] `scripts/seed_platform.py` — создание Platform user (`is_system=True`, `role=platform`)
- [ ] Запускается автоматически при первом деплое

**Критерий готовности:** `alembic upgrade head` применяется без ошибок. Platform user создан в БД.

---

### Sprint 0.4: VPS + install_cbshome.sh

**Цель:** Приложение работает на сервере с HTTPS. Главный артефакт поставки.

**Задачи:**

**install_cbshome.sh:**
- [ ] Preflight: OS (Ubuntu 22.04+), RAM (>= 2GB), disk (>= 10GB), DNS
- [ ] Fix locale (en_US.UTF-8)
- [ ] System deps: Docker, Nginx, Certbot, UFW, git, curl, dnsutils
- [ ] UFW: только 22/80/443
- [ ] Deploy user `cbshome` (non-root, в docker group)
- [ ] SSH deploy key -> GitHub (`aivis-one/cbshome`) -> clone repo
- [ ] Генерация `.env` с рандомными паролями (openssl rand)
- [ ] Интерактивный ввод секретов:
  - `SUMSUB_API_KEY` (placeholder, можно пропустить)
  - `SUMSUB_SECRET_KEY` (placeholder)
  - `TELEGRAM_BOT_TOKEN`
  - `EMAP_API_KEY` (placeholder)
  - `MAILGUN_API_KEY` (placeholder)
- [ ] Nginx reverse proxy: `api.cbshome.org` -> `127.0.0.1:8000`, `cbshome.org` -> `127.0.0.1:3000`
- [ ] SSL (Let's Encrypt, оба домена) + auto-renewal cron
- [ ] `docker compose up` -> healthcheck poll -> migrations -> seed Platform user
- [ ] Management script -> symlink `/usr/local/bin/cbshome`
- [ ] Backup cron (4 AM, ротация 7 дней)
- [ ] Проверка previous installation (предложить удалить)

**Management script (`cbshome`):**
```
cbshome status              -- Docker ps + health + external access
cbshome logs [app|db|redis] -- Docker logs -f
cbshome test                -- pytest внутри контейнера
cbshome lint                -- ruff внутри контейнера
cbshome update              -- git pull + build + migrate + seed + test + restart
cbshome restart [app]       -- restart all or just app
cbshome backup              -- pg_dump + .env -> tar.gz
cbshome db connect          -- psql в контейнер
cbshome db migrate          -- alembic upgrade head
cbshome seed                -- python scripts/seed.py
cbshome seed --reset        -- clean + re-seed
cbshome ssl renew           -- certbot renew
cbshome version             -- git info + versions
```

**Критерий готовности:** `curl https://api.cbshome.org/health` -> `{"status":"ok"}`.

---

### Sprint 0.5: Logging + Audit Service

**Цель:** Production-quality логирование и аудит финансовых операций.

**Задачи:**
- [ ] `app/core/logging.py` — фильтрация по LOG_LEVEL (`make_filtering_bound_logger`), идемпотентность `setup_logging()`
- [ ] `TraceIdMiddleware` — pure ASGI, X-Trace-ID + ip_address + user_agent в contextvars
- [ ] Trace_id guard: входящий X-Trace-ID > 36 символов -> генерируем новый uuid4
- [ ] `app/core/audit.py` — `record_audit()` читает trace_id/ip/user_agent из contextvars, не коммитит (P-01)
- [ ] `tests/test_audit.py` — 4 теста

**Обязательные события аудита (определяем сейчас, используем в следующих фазах):**

| Событие | Фаза |
|---------|------|
| `user.registered` | Phase 1 |
| `user.login` | Phase 1 |
| `user.role_changed` | Phase 1 |
| `kyc.status_changed` | Phase 2 |
| `payment.deposit_created` | Phase 5 |
| `payment.deposit_confirmed` | Phase 5 |
| `payment.chargeback` | Phase 5 |
| `purchase.created` | Phase 6 |
| `purchase.gift_created` | Phase 6 |
| `installment.plan_created` | Phase 6 |
| `installment.tranche_paid` | Phase 6 |
| `installment.completed` | Phase 6 |
| `installment.defaulted` | Phase 6 |
| `withdrawal.requested` | Phase 6 |
| `withdrawal.confirmed` | Phase 6 |
| `agent_application.submitted` | Phase 7 |
| `agent_application.approved` | Phase 7 |
| `agent_application.rejected` | Phase 7 |
| `staff.avatar_started` | Phase 3 |
| `staff.avatar_ended` | Phase 3 |

**Критерий готовности:** LOG_LEVEL=WARNING фильтрует debug/info. trace_id в каждом лог-сообщении. Аудит пишется в БД.

---

## PHASE 1: Auth + Users

---

### Sprint 1.1: Email Auth

**Цель:** Регистрация и вход через email + password.

**Задачи:**
- [ ] `app/modules/auth/service.py` — `register_email()`, `login_email()`, `logout()`, `logout_all()`
- [ ] `app/modules/auth/router.py`:
  - `POST /api/v1/auth/email/register`
  - `POST /api/v1/auth/email/login`
  - `POST /api/v1/auth/logout`
  - `POST /api/v1/auth/logout-all`
- [ ] Email verification token (сохраняется в `credentials.onboarding.email_token`)
- [ ] Password hash: argon2
- [ ] Redis сессии: `session:{token}` + `user_sessions:{user_id}` (SET for logout-all)
- [ ] TTL: `SESSION_TTL_DAYS` из config
- [ ] Лимит: `MAX_CONCURRENT_SESSIONS` (5) — при превышении закрываем самую старую
- [ ] `app/modules/auth/dependencies.py` — `get_current_user`, `get_optional_user`, `get_current_staff`
- [ ] `tests/test_auth_email.py` — 12 тестов

**Endpoints:**
```
POST /api/v1/auth/email/register  -> AuthResponse {user, session_token}
POST /api/v1/auth/email/login     -> AuthResponse
POST /api/v1/auth/logout          -> 204
POST /api/v1/auth/logout-all      -> 204
```

**Структура credentials при регистрации:**
```json
{
  "email": {
    "email": "user@example.com",
    "password_hash": "argon2:...",
    "verified": false,
    "verified_at": null
  },
  "onboarding": {
    "email_token": "abc123",
    "email_token_expires_at": "2026-03-28T11:00:00Z",
    "email_verification_attempts": 0
  }
}
```

**Критерий готовности:** Юзер может зарегистрироваться и войти через email.

---

### Sprint 1.2: Telegram Auth

**Цель:** Вход через Telegram WebApp.

**Задачи:**
- [ ] `app/modules/auth/telegram.py` — валидация initData (HMAC-SHA256)
- [ ] `POST /api/v1/auth/telegram` — upsert юзера при логине
- [ ] Атомарный upsert: INSERT ON CONFLICT DO UPDATE
- [ ] Обновление `credentials.telegram` при каждом логине (username, photo_url, language_code)
- [ ] `tests/test_auth_telegram.py` — 8 тестов

**Endpoint:**
```
POST /api/v1/auth/telegram  -> AuthResponse {user, session_token}
```

**Критерий готовности:** Telegram WebApp может авторизовать юзера.

---

### Sprint 1.3: User Profile

**Цель:** Чтение и редактирование профиля.

**Задачи:**
- [ ] `app/modules/users/schemas.py` — `UserResponse`, `UserUpdate`
- [ ] `app/modules/users/service.py` — `update_user()` (partial update, exclude_unset)
- [ ] `app/modules/users/router.py`:
  - `GET /api/v1/users/me`
  - `PATCH /api/v1/users/me`
- [ ] `tests/test_users.py` — 10 тестов

**Ограничения аватаринга:**
- [ ] `app/modules/auth/avatar_guard.py` — `require_not_avatar` decorator
- [ ] Список запрещённых операций в config:
```yaml
avatar_mode:
  restricted_operations:
    - change_password
    - change_email
    - delete_account
    - create_payment
    - create_withdrawal
    - sign_document
    - create_installment
    - access_staff_shell
    - modify_kyc
```

**Критерий готовности:** Юзер видит и редактирует свой профиль. Аватаринг-ограничения работают.

---

## PHASE 2: KYC + Documents (заглушки)

---

### Sprint 2.1: KYC заглушка

**Цель:** Структура KYC без реальной интеграции SumSub.

**Задачи:**
- [ ] `app/modules/kyc/models.py` — `KYCApplication` (stub)
- [ ] `app/modules/kyc/service.py` — `submit_kyc()`, `get_kyc_status()`
- [ ] `POST /api/v1/kyc/submit` — создаёт KYCApplication, статус -> submitted
- [ ] `GET /api/v1/kyc/status` — текущий статус
- [ ] `POST /api/v1/kyc/webhook` — заглушка (SumSub webhook handler, всегда approved в dev)
- [ ] `tests/test_kyc.py` — 5 тестов

**Критерий готовности:** Юзер может подать KYC заявку, статус обновляется через webhook-заглушку.

---

### Sprint 2.2: Documents

**Цель:** Модуль документов с версионированием и фактом подписания.

**Задачи:**
- [ ] `app/modules/documents/models.py` — `Document`, `DocumentSigning`
- [ ] CRUD для Staff: `POST/PUT/DELETE /api/v1/staff/documents`
- [ ] `POST /api/v1/documents/{id}/sign` — checkbox consent, запись в DocumentSigning
- [ ] `GET /api/v1/documents` — список активных документов по роли
- [ ] `GET /api/v1/documents/{id}` — документ с контентом
- [ ] Проверка наличия подписей при смене роли
- [ ] `tests/test_documents.py` — 8 тестов

**Модель:**
```python
Document:
    id, type (enum), version: int
    title: str, content_url: str
    is_active: bool
    created_by: UUID  -- staff_id
    created_at, updated_at

DocumentSigning:
    id, user_id, document_id
    signed_at, ip_address, user_agent
    -- Phase 2: docusign_envelope_id
```

**Пакеты по роли:**
- investor: Privacy Policy, Terms, Investment Agreement
- agent: всё инвесторское + агентское соглашение
- company: корпоративный пакет

**Критерий готовности:** Юзер может подписать документы. Staff может управлять документами.

---

## PHASE 3: Staff + Avataring

---

### Sprint 3.1: StaffProfile + Permissions

**Цель:** Профили сотрудников с матрицей прав.

**Задачи:**
- [ ] `app/modules/staff/service.py` — `create_staff()`, `update_permissions()`
- [ ] `app/modules/staff/router.py`:
  - `POST /api/v1/staff/users` — создать Staff юзера
  - `PATCH /api/v1/staff/users/{id}/permissions` — изменить права
  - `GET /api/v1/staff/users` — список Staff
- [ ] Permission matrix из config (дефолты) + override в StaffProfile.permissions
- [ ] `get_current_staff` dependency с проверкой конкретного права
- [ ] `tests/test_staff.py` — 8 тестов

**Дефолтные права:**
```yaml
staff_permissions:
  avatar_mode: true
  kyc_approve: true
  payment_review: true
  user_block: true
  financial_operations: true
  agent_application_review: true
  translation_edit: false
```

**Критерий готовности:** Staff создаётся, права проверяются в зависимостях.

---

### Sprint 3.2: Avataring

**Цель:** Механизм входа Staff под пользователем.

**Задачи:**
- [ ] `app/modules/staff/avatar_service.py` — `start_avatar()`, `end_avatar()`
- [ ] `POST /api/v1/staff/avatar/start` — создание AvatarSession, дочерняя JWT/сессия
- [ ] `POST /api/v1/staff/avatar/end` — завершение AvatarSession
- [ ] JWT/сессия содержит `avatar_session_id`
- [ ] Все мутирующие операции в avatar режиме: `performed_by=staff_id`, `on_behalf_of=target_user_id` в audit_log
- [ ] `require_not_avatar` применяется к запрещённым операциям
- [ ] `tests/test_avatar.py` — 10 тестов

**Endpoints:**
```
POST /api/v1/staff/avatar/start   Body: {target_user_id} -> {avatar_session_id, session_token}
POST /api/v1/staff/avatar/end     -> 204
GET  /api/v1/staff/avatar/active  -> AvatarSession | null
```

**Критерий готовности:** Staff входит под юзером, все операции логируются. Запрещённые операции блокируются.

---

### Sprint 3.3: Admin endpoints

**Цель:** Базовые admin-функции для управления пользователями.

**Задачи:**
- [ ] `GET /api/v1/staff/dashboard/stats` — базовая статистика платформы
- [ ] `GET /api/v1/staff/users` — список юзеров (пагинация, фильтры)
- [ ] `GET /api/v1/staff/users/{id}` — детали юзера
- [ ] `PATCH /api/v1/staff/users/{id}/block` — блокировка (is_active=false + завершить все сессии)
- [ ] `GET /api/v1/staff/kyc/queue` — очередь KYC заявок
- [ ] `POST /api/v1/staff/kyc/{id}/approve` — одобрить KYC
- [ ] `POST /api/v1/staff/kyc/{id}/reject` — отклонить KYC
- [ ] `tests/test_staff_admin.py` — 12 тестов

**Критерий готовности:** Staff видит и управляет пользователями.

---

## PHASE 4: Companies + Products

---

### Sprint 4.1: Companies

**Цель:** Профили компаний.

**Задачи:**
- [ ] `app/modules/companies/models.py` — `CompanyProfile`, `CompanyPriceHistory`
- [ ] `app/modules/companies/service.py` — CRUD + `update_price()` (каскадное обновление Product)
- [ ] Staff endpoints:
  - `POST /api/v1/staff/companies` — создать компанию
  - `PATCH /api/v1/staff/companies/{id}` — редактировать
  - `PATCH /api/v1/staff/companies/{id}/price` — изменить цену акции (каскад + история)
- [ ] Public endpoints:
  - `GET /api/v1/companies` — список активных компаний
  - `GET /api/v1/companies/{id}` — детали компании
- [ ] `tests/test_companies.py` — 8 тестов

**Модель:**
```python
CompanyProfile:
    id, user_id  -- FK users.id (Company как User с role=company)
    name, description
    price_per_unit_cents: int
    distribution_config: JSONB  -- {company_percent, l1_percent, l2_percent, l3_percent}
    status: enum  -- active | hidden | archived
    created_at, updated_at

CompanyPriceHistory:
    id, company_id
    price_per_unit_cents: int
    changed_at: datetime
    changed_by: UUID  -- staff_id
```

**Критерий готовности:** Компании создаются, цена обновляется каскадно.

---

### Sprint 4.2: Products

**Цель:** Продукты компаний с вариантами рассрочки.

**Задачи:**
- [ ] `app/modules/products/models.py` — `Product`, `ProductInstallment`
- [ ] `app/modules/products/service.py` — CRUD + `PurchaseConfigValidator`
- [ ] Staff endpoints:
  - `POST /api/v1/staff/products` — создать продукт
  - `PATCH /api/v1/staff/products/{id}` — редактировать
  - `PATCH /api/v1/staff/products/{id}/status` — изменить статус
  - `POST /api/v1/staff/products/{id}/installments` — добавить вариант рассрочки
  - `DELETE /api/v1/staff/products/{id}/installments/{inst_id}` — удалить вариант
- [ ] Public endpoints (витрина):
  - `GET /api/v1/products` — список активных продуктов с вариантами
  - `GET /api/v1/products/{id}` — детали продукта
- [ ] Redis кэш social proof (`sold_units` по продукту): TTL = `SOCIAL_PROOF_CACHE_TTL`
- [ ] `tests/test_products.py` — 12 тестов

**Валидация ProductInstallment при создании:**
```
SUM(schedule_cents) == product.units * company.price_per_unit_cents
SUM(units_schedule_percent) == 100
len(schedule_cents) == len(units_schedule_percent) == duration_months
```

**Критерий готовности:** Витрина работает. Продукты создаются с вариантами рассрочки.

---

## PHASE 5: Payments: Ledgers + Crypto

---

### Sprint 5.1: Ledger Service

**Цель:** Сервис работы с леджерами. Основа всей финансовой системы.

**Задачи:**
- [ ] `app/modules/ledgers/service.py`:
  - `record_active_ledger()` — запись в active_ledger
  - `record_passive_ledger()` — запись в passive_ledger
  - `get_active_balance()` — confirmed + frozen отдельно
  - `get_passive_balance()` — confirmed + frozen отдельно
  - Проверка AML-матрицы маршрутов при каждой записи
- [ ] `app/modules/ledgers/validators.py` — `validate_route()` (Active -> Passive запрещено)
- [ ] `tests/test_ledgers.py` — 15 тестов (включая AML-матрицу)

**Инварианты (проверяются в service, не в router):**
```python
# AML check перед каждой записью:
if source_ledger == "active" and target_ledger == "passive":
    raise AMLViolationError("Active -> Passive route is forbidden")
```

**Критерий готовности:** Ledger service работает. AML-матрица проверяется. Нельзя создать запись Active -> Passive.

---

### Sprint 5.2: Crypto Deposits

**Цель:** Пополнение active_ledger через крипту.

**Задачи:**
- [ ] `app/modules/payments/models.py` — `Payment` (полная модель из State Machines)
- [ ] `app/modules/payments/crypto.py` — `get_or_create_crypto_address()`, `process_crypto_deposit()`
- [ ] `app/modules/payments/router.py`:
  - `GET /api/v1/payments/crypto-address/{network}` — получить/создать адрес
- [ ] `app/modules/payments/webhook_router.py`:
  - `POST /api/v1/payments/crypto/webhook` — blockchain webhook
- [ ] Webhook: Payment `created -> frozen`, запись в active_ledger
- [ ] `frozen_until = created_at + FREEZING_HOURS_CRYPTO`
- [ ] `payment_confirmation_worker` — daemon (asyncio.Task в lifespan)
- [ ] `tests/test_crypto_deposits.py` — 10 тестов

**Networks:** TRC20, ERC20, BEP20, PoS (из config)

**Критерий готовности:** Инвестор получает крипто-адрес. Webhook создаёт Payment и запись в active_ledger.

---

### Sprint 5.3: Payment Confirmation Daemon + Reversal

**Цель:** Автоматическое подтверждение платежей и механизм чарджбека.

**Задачи:**
- [ ] `payment_confirmation_worker` — batch UPDATE frozen -> confirmed при `frozen_until <= now()`
- [ ] Staff endpoint: `POST /api/v1/staff/payments/{id}/reverse` — chargeback reversal
- [ ] Reversal: зеркальные записи с суффиксом `:reversal`, Payment -> reversed, уведомления
- [ ] `tests/test_payment_confirmation.py` — 8 тестов
- [ ] `tests/test_payment_reversal.py` — 6 тестов

**Критерий готовности:** Daemon подтверждает платежи. Staff может сделать chargeback.

---

## PHASE 6: Purchase + Installment

---

### Sprint 6.1: Distribution Engine (processors/)

**Цель:** Самостоятельный модуль распределения денег. Не принадлежит ни Purchase, ни Agent —
владеет логикой того, как деньги распределяются в момент любой транзакции покупки.
В этом спринте закладывается фундамент и реализуются первые два процессора (Purchase, Gift).
ReferralProcessor и VolumeProcessor добавляются в Sprints 7.2 и 7.3 в ту же папку.

**Архитектурный принцип:** `processors/` получает `PurchaseContext`, возвращает список
`Transaction` с инвариантом `SUM(entries) = 0`. Не знает про HTTP, роутеры, сессии.
Не коммитит. Атомарная запись — ответственность `execute_purchase()` в `purchases/service.py`.

**Задачи:**
- [ ] `app/modules/processors/base.py` — `ProcessorProtocol`, `PurchaseContext`, `Transaction`, `LedgerEntry`
- [ ] `app/modules/processors/purchase.py` — `PurchaseProcessor`
- [ ] `app/modules/processors/gift.py` — `GiftProcessor`
- [ ] `app/modules/processors/registry.py` — `ProcessorRegistry` (расширяется в Phase 7)
- [ ] `app/modules/purchases/models.py` — `Purchase`
- [ ] `app/modules/purchases/service.py` — `execute_purchase()` (валидация SUM=0, атомарная запись)
- [ ] `POST /api/v1/products/{id}/purchase` — инстант-покупка
- [ ] `tests/test_purchase_processor.py` — 15 тестов (включая invariant SUM=0)

**Инвариант перед записью в БД:**
```python
for transaction in transactions:
    assert sum(e.amount_cents for e in transaction.entries) == 0
```

**Критерий готовности:** Инвестор покупает продукт. PurchaseProcessor распределяет средства.
GiftProcessor создаёт бонусные акции. ProcessorRegistry готов к регистрации новых процессоров.

---

### Sprint 6.2: Installment Plans

**Цель:** Покупка продукта в рассрочку.

**Задачи:**
- [ ] `app/modules/installments/models.py` — `InstallmentPlan`, `InstallmentTranche`
- [ ] `app/modules/installments/service.py` — `create_plan()`, `pay_tranche()`, `complete_plan()`, `default_plan()`
- [ ] `app/modules/installments/scheduler.py` — `calculate_due_date()` (february rule)
- [ ] `installment_payment_worker` — daemon (asyncio.Task в lifespan)
- [ ] `POST /api/v1/products/{id}/installment` — создать план
- [ ] `GET /api/v1/installments/me` — мои планы
- [ ] `GET /api/v1/installments/{id}` — детали плана
- [ ] `tests/test_installments.py` — 20 тестов (включая february rule, default, completion)

**Критерий готовности:** Инвестор создаёт план рассрочки. Daemon платит транши. Дефолт через 7 дней просрочки. Бонусы при закрытии.

---

### Sprint 6.3: Withdrawals

**Цель:** Вывод средств с passive_ledger.

**Задачи:**
- [ ] `app/modules/withdrawals/models.py` — `Withdrawal`
- [ ] `app/modules/withdrawals/service.py` — `create_withdrawal()`, `confirm_withdrawal()`, `reject_withdrawal()`
- [ ] `POST /api/v1/withdrawals` — запрос на вывод (confirmed passive_balance >= amount)
- [ ] `GET /api/v1/withdrawals/me` — история выводов
- [ ] Staff: `POST /api/v1/staff/withdrawals/{id}/confirm`
- [ ] Staff: `POST /api/v1/staff/withdrawals/{id}/reject`
- [ ] `tests/test_withdrawals.py` — 10 тестов

**Критерий готовности:** Агент/компания запрашивает вывод. Staff подтверждает.

---

### Sprint 6.4: Transaction History + Semaphores

**Цель:** История операций и семафоры консистентности.

**Задачи:**
- [ ] `GET /api/v1/transactions` — история (фильтры: тип, статус, дата, сумма; пагинация 20)
- [ ] `GET /api/v1/transactions/{id}` — детали транзакции
- [ ] `app/modules/admin/consistency/service.py` — все семафоры S-01..S-15 + IS-01..IS-06
- [ ] `GET /api/v1/staff/consistency` — запуск семафоров
- [ ] `tests/test_transactions.py` — 8 тестов
- [ ] `tests/test_consistency.py` — 10 тестов

**Критерий готовности:** Инвестор видит историю операций с реальными ценами покупки. Все семафоры зелёные.

---

## PHASE 7: Agent Module

---

### Sprint 7.1: Agent Application

**Цель:** Заявка на роль агента.

**Задачи:**
- [ ] `app/modules/agent_applications/models.py` — `AgentApplication`
- [ ] `app/modules/agent_applications/service.py` — `submit_application()`, `approve()`, `reject()`
- [ ] `POST /api/v1/agent-applications` — подать заявку (только investor)
- [ ] `GET /api/v1/agent-applications/me` — история заявок
- [ ] Staff: `GET /api/v1/staff/agent-applications` — очередь
- [ ] Staff: `POST /api/v1/staff/agent-applications/{id}/approve`
- [ ] Staff: `POST /api/v1/staff/agent-applications/{id}/reject`
- [ ] При approve: `user.role = agent` + агентский пакет документов
- [ ] Cooldown: `cooldown_until = now() + AGENT_APPLICATION_COOLDOWN_DAYS`
- [ ] `tests/test_agent_applications.py` — 12 тестов

**Критерий готовности:** Инвестор подаёт заявку. Staff одобряет/отклоняет. Роль меняется автоматически.

---

### Sprint 7.2: Referral Links + Commissions

**Цель:** Реферальные ссылки и комиссионная цепочка L1/L2/L3.

**Задачи:**
- [ ] `app/modules/referrals/models.py` — `ReferralLink`, `ReferralAttribution`
- [ ] `app/modules/referrals/service.py` — `create_link()`, `resolve_attribution()`, `get_agent_chain()`
- [ ] `app/modules/processors/referral.py` — `ReferralProcessor` (расширение Distribution Engine из Sprint 6.1)
- [ ] Зарегистрировать `ReferralProcessor` в `ProcessorRegistry`
- [ ] STOP-механика: 4-е звено цепочки становится корневым
- [ ] `POST /api/v1/referrals/links` — создать реферальную ссылку (только agent)
- [ ] `GET /api/v1/referrals/links/me` — мои ссылки
- [ ] `GET /api/v1/referrals/stats/me` — статистика по ссылкам
- [ ] `tests/test_referrals.py` — 15 тестов (включая STOP-механику)

**Критерий готовности:** Агент создаёт реферальные ссылки. При покупке по ссылке — комиссии L1/L2/L3 начисляются через ReferralProcessor.

---

### Sprint 7.3: Leaderboard + Volume Bonuses

**Цель:** Рейтинг агентов и бонусные пулы.

**Задачи:**
- [ ] `app/modules/commissions/models.py` — `LeaderboardSnapshot`, `VolumePayout`
- [ ] `app/modules/processors/volume.py` — `VolumeProcessor` (расширение Distribution Engine из Sprint 6.1)
- [ ] Зарегистрировать `VolumeProcessor` в `ProcessorRegistry`
- [ ] `leaderboard_worker` — обновление каждые 60 минут (asyncio.Task)
- [ ] `GET /api/v1/agent/leaderboard` — топ агентов (только agent)
- [ ] `GET /api/v1/agent/commissions/me` — история комиссий
- [ ] Cron: месячный + квартальный бонусный пул
- [ ] `tests/test_leaderboard.py` — 8 тестов

**Критерий готовности:** Лидерборд обновляется. Бонусные пулы начисляются.

---

## PHASE 8: Notifications

---

### Sprint 8.1: Notification Models + Processor

**Цель:** Двухуровневая архитектура уведомлений.

**Задачи:**
- [ ] `app/modules/notifications/models.py` — `Notification`, `NotificationDelivery`
- [ ] `app/modules/notifications/service.py` — `create_notification()`, `resolve_notification()`
- [ ] `app/modules/notifications/processor.py` — трёхстадийный pipeline (resolve -> deliver -> rollup)
- [ ] `app/modules/notifications/formatters.py` — `ChannelFormatter` Protocol + `StubFormatter`
- [ ] Background worker в lifespan
- [ ] Cron очистка: удалять `expires_at < now() AND is_read=true`
- [ ] `tests/test_notifications.py` — 15 тестов

**Типы уведомлений:**
system, transaction, commission, news, installment

**Критерий готовности:** Уведомления создаются и обрабатываются процессором.

---

### Sprint 8.2: Email + Telegram Formatters

**Цель:** Реальная доставка уведомлений.

**Задачи:**
- [ ] `app/modules/notifications/templates/` — en.yaml (все типы)
- [ ] `app/modules/notifications/template_engine.py` — SafeDict, YAML loading, language fallback
- [ ] `app/modules/notifications/formatters.py` — `TelegramFormatter` (aiogram, send-only), `EmailFormatter` (EMAP + Mailgun fallback)
- [ ] Lazy init: real token -> real formatter, fake -> StubFormatter
- [ ] Permanent failure handling (bot blocked -> immediate failed)
- [ ] `POST /api/v1/staff/notifications/templates/reload` — Staff reload templates
- [ ] `tests/test_notification_delivery.py` — 12 тестов

**Критерий готовности:** Уведомления приходят в Telegram и email.

---

### Sprint 8.3: Notification REST Endpoints

**Цель:** API для управления уведомлениями на фронте.

**Задачи:**
- [ ] `GET /api/v1/notifications` — список (пагинация 20, фильтры по типу)
- [ ] `GET /api/v1/notifications/unread-count` — badge counter
- [ ] `POST /api/v1/notifications/{id}/read` — отметить прочитанным
- [ ] `POST /api/v1/notifications/read-all` — отметить все
- [ ] `tests/test_notification_endpoints.py` — 8 тестов

**Критерий готовности:** Фронт может читать и управлять уведомлениями.

---

## PHASE 9: News + Extras

---

### Sprint 9.1: News + Events

**Цель:** Модуль новостей и событий.

**Задачи:**
- [ ] `app/modules/news/models.py` — `News`, `Event`, `NewsRead`
- [ ] `app/modules/news/service.py` — CRUD + баннерная логика
- [ ] Public: `GET /api/v1/news`, `GET /api/v1/news/{id}`
- [ ] Public: `GET /api/v1/events`, `GET /api/v1/events/upcoming` (ближайшие 30 дней)
- [ ] `POST /api/v1/news/{id}/dismiss` — закрыть баннер
- [ ] Staff CRUD: `POST/PUT/DELETE /api/v1/staff/news`
- [ ] Staff CRUD: `POST/PUT/DELETE /api/v1/staff/events`
- [ ] `tests/test_news.py` — 10 тестов

**Критерий готовности:** Staff создаёт новости. Инвесторы видят новостную ленту и баннеры.

---

### Sprint 9.2: Dashboard + Portfolio Endpoints

**Цель:** Агрегированные данные для главного экрана.

**Задачи:**
- [ ] `GET /api/v1/dashboard/summary` — виджет портфеля (активы, суммы, по компаниям)
- [ ] `GET /api/v1/portfolio/me` — детальный портфель инвестора
- [ ] `GET /api/v1/portfolio/me/company/{id}` — позиция по компании (количество акций, средняя цена, история)
- [ ] `tests/test_dashboard.py` — 8 тестов

**Критерий готовности:** Фронт получает данные для Dashboard и портфеля.

---

## PHASE 10: Розетки + Полировка

---

### Sprint 10.1: Розетки (Protocol-only)

**Цель:** Заглушки для будущих фич. Интерфейс определён, логика не реализована.

**Задачи:**
- [ ] `app/modules/tokens/interface.py` — `TokenServiceProtocol`
- [ ] `app/modules/ai_trainer/interface.py` — `AITrainerProtocol`
- [ ] `app/modules/payments/providers/interface.py` — `PaymentProviderProtocol` (fiat)
- [ ] `app/modules/auto_translate/interface.py` — `AutoTranslateProtocol`
- [ ] `app/modules/certificates/interface.py` — `CertificateServiceProtocol`
- [ ] `GET /api/v1/transactions/export` — заглушка (501 Not Implemented)

**Критерий готовности:** Все интерфейсы определены. Вызов любой заглушки возвращает корректный stub-ответ.

---

### Sprint 10.2: Финальное тестирование

**Цель:** Все flow работают вместе.

**Задачи:**
- [ ] E2E тесты основных flow:
  1. Регистрация -> KYC -> покупка продукта -> история транзакций
  2. Регистрация -> заявка агента -> реферальная ссылка -> покупка по ссылке -> комиссия
  3. Создание компании -> продукта -> инсталлмент -> оплата траншей -> закрытие
  4. Staff: аватаринг -> просмотр данных -> возврат
  5. Deposit -> покупка -> chargeback -> reversal
- [ ] Все семафоры консистентности: OK
- [ ] `cbshome test` -> все тесты зелёные
- [ ] `cbshome lint` -> 0 ошибок
- [ ] Финальный `cbshome update` на VPS

**Критерий готовности:** Все E2E flow проходят. Семафоры зелёные. VPS обновлён.

---

## Реестр технического долга

| ID | Файл | Проблема | Приоритет | Статус |
|----|------|----------|-----------|--------|
| TD-001 | `installments/` | Досрочное погашение | After MVP | ⬜ |
| TD-002 | `installments/` | Пауза/заморозка плана | After MVP | ⬜ |
| TD-003 | `kyc/` | Реальная SumSub интеграция | Phase 2 | ⬜ |
| TD-004 | `payments/` | Fiat on-ramp (Moonpay/Transak) | Phase 2 | ⬜ |
| TD-005 | `documents/` | DocuSign e-signature | Phase 2 | ⬜ |
| TD-006 | `notifications/` | Cron для expiration waitlist | After MVP | ⬜ |
| TD-007 | `tests/` | Cleanup fixtures через ORM вместо raw SQL | Backlog | ⬜ |
| TD-008 | Все роутеры | Rate limiting (slowapi) | Before Prod | ⬜ |
| TD-009 | `transactions/` | Экспорт в CSV/XLSX | Phase 2 | ⬜ |
| TD-010 | `certificates/` | PDF генерация сертификатов | Phase 2 | ⬜ |

---

**Конец документа**

---

*Version 0.2 | 2026-04-01 | cbshome Backend TZ*
