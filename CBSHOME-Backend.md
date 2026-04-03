# CBSHOME -- Техническое задание (Backend)

**Версия:** 0.9
**Дата:** 3 апреля 2026
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

### ✅ Sprint 0.1: Репозиторий + структура проекта

**Цель:** Базовая структура репозитория, готовая к разработке на VPS.

**Задачи:**
- [x] GitHub репозиторий `aivis-one/cbshome`
- [x] `.gitignore` (PyCharm, VS Code, .env, __pycache__)
- [x] Структура папок:
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
├── backend/
│   └── app/modules/notifications/templates/  -- Sprint 8.2
├── diagrams/
├── docker-compose.yml
├── scripts/
│   └── install_cbshome.sh
└── CBSHOME-Design-Document.md
```
- [x] `pyproject.toml` — зависимости, ruff, mypy, pytest конфиг
- [x] `app/core/config.py` — pydantic-settings, загрузка из .env
- [x] `app/core/exceptions.py` — `CBSError -> NotFound / Forbidden / Conflict / BadRequest / Unauthorized`
- [x] `app/core/mixins.py` — `UUIDMixin`, `TimestampMixin`, `JSONBMixin` (с `set_jsonb` + `flag_modified`)
- [x] `app/core/constants.py` — `LedgerReason` (все канонические reasons из Financial System Codex)
- [x] `tests/conftest.py` — async client fixture
- [x] `tests/test_root.py` — базовый тест
- [x] `.env.example`
- [x] `README.md` — только VPS инструкции

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

### ✅ Sprint 0.2: Docker + FastAPI скелет

**Цель:** Работающее приложение в Docker с health checks.

**Задачи:**
- [x] `docker-compose.yml` — app + postgres:16 + redis:7-alpine
- [x] Postgres/Redis без published портов (только Docker internal network)
- [x] App на `127.0.0.1:8000`
- [x] `Dockerfile` — multi-stage, dev зависимости всегда устанавливаются (тесты в контейнере)
- [x] `.dockerignore`
- [x] `app/core/database.py` — AsyncEngine + AsyncSession + `get_db_session()` + `get_db_reader()` + `Base`
- [x] `app/core/redis.py` — async Redis client + lifecycle
- [x] `app/core/logging.py` — structlog (JSON в prod, Console в dev)
- [x] `app/core/middleware.py` — `TraceIdMiddleware` (X-Trace-ID + ip_address + user_agent + avatar_session_id в contextvars)
- [x] CORS middleware (origins из config)
- [x] `GET /` — версия API
- [x] `GET /health` — DB (SELECT 1) + Redis (PING), всегда 200
- [x] `GET /ready` — 503 если деградация
- [x] Lifespan: startup (structlog + Redis) -> shutdown (Redis close + engine dispose)
- [x] `tests/test_health.py` — 7 тестов (all ok, db down, redis down, /ready 503, trace-id echo)

**Endpoints:**
```
GET /        -> {"name": "CBSHOME API", "version": "0.1.0"}
GET /health  -> {"status": "ok", "db": "ok", "redis": "ok"}    (200 always)
GET /ready   -> {"status": "ok", "db": "ok", "redis": "ok"}    (200 or 503)
```

**Критерий готовности:** `docker compose up` поднимает стек, `curl localhost:8000/health` возвращает 200.

---

### ✅ Sprint 0.3: Alembic + Core Models

**Цель:** Схема БД для всего фундамента платформы. Это самый важный спринт Phase 0.

**Задачи:**

**Alembic:**
- [x] `alembic.ini` — URL из config, не хардкод
- [x] `migrations/env.py` — async runner

**Модели (все в одной миграции `initial_schema`):**

- [x] `app/modules/users/models.py` — `User`:
```python
User:
    id: UUID
    role: enum        -- investor | agent | company | staff | platform
    -- Системный пользователь идентифицируется по role=platform,
    -- отдельного поля is_system нет
    is_active: bool   -- default True
    onboarding_step: enum  -- registered | email_verified | profile_complete | kyc_done | role_selected
    kyc_status: enum  -- not_started | submitted | approved | rejected
    -- kyc_status -- денормализованный кэш KYCApplication.status для hot path
    credentials: JSONB  -- {email: {...}, telegram: {...}, onboarding: {...}}
    profile: JSONB      -- {first_name, last_name, country, phone, ...}
    language: str       -- "en" (default)
    created_at, updated_at
```

- [x] `app/modules/ledgers/models.py` — `ActiveLedger`, `PassiveLedger`:
```python
LedgerEntry:  -- базовые поля для обоих леджеров; иммутабельно, нет updated_at
    id: UUID
    user_id: UUID     -- FK users.id
    amount_cents: int -- BigInteger (64-bit); поддерживает платформенные суммы до ~$92 трлн
    status: enum      -- frozen | confirmed | reversed
    frozen_until: datetime | None
    origin_payment_id: UUID | None  -- FK payments.id (circular, deferrable)
    reason: str       -- из LedgerReason
    created_at: datetime
```

- [x] `app/modules/staff/models.py` — `StaffProfile`, `AvatarSession`:
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

- [x] `app/core/audit.py` — `AuditLog`:
```python
AuditLog:  -- иммутабельно, наследует Base напрямую, нет updated_at
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
    user_agent: str | None  -- String(500), усечение в record_audit()
    trace_id: str | None  -- String(36)
```

- [x] Миграция `initial_schema` — все таблицы разом
- [x] `migrations/env.py` — импорты всех моделей для autogenerate

**Seed системного пользователя Platform:**
- [x] `scripts/seed_platform.py` — создание Platform user (`role=platform`)
- [x] Запускается автоматически при первом деплое

**Критерий готовности:** `alembic upgrade head` применяется без ошибок. Platform user создан в БД.

---

### ✅ Sprint 0.4: VPS + install_cbshome.sh

**Цель:** Приложение работает на сервере с HTTPS. Главный артефакт поставки.

**Задачи:**

**install_cbshome.sh:**
- [x] Preflight: OS (Ubuntu 22.04+), RAM (>= 2GB), disk (>= 10GB), DNS
- [x] Fix locale (en_US.UTF-8)
- [x] System deps: Docker, Nginx, Certbot, UFW, git, curl, dnsutils
- [x] UFW: только 22/80/443
- [x] Deploy user `cbshome` (non-root, в docker group)
- [x] SSH deploy key -> GitHub (`aivis-one/cbshome`) -> clone repo
- [x] Генерация `.env` с рандомными паролями (openssl rand)
- [x] Интерактивный ввод секретов:
  - `SUMSUB_API_KEY` (placeholder, можно пропустить)
  - `SUMSUB_SECRET_KEY` (placeholder)
  - `TELEGRAM_BOT_TOKEN`
  - `EMAP_API_KEY` (placeholder)
  - `MAILGUN_API_KEY` (placeholder)
- [x] Nginx reverse proxy: `api.cbshome.org` -> `127.0.0.1:8000`, `cbshome.org` -> `127.0.0.1:3000`
- [x] SSL (Let's Encrypt, оба домена) + auto-renewal cron
- [x] `docker compose up` -> healthcheck poll -> migrations -> seed Platform user
- [x] Management script -> symlink `/usr/local/bin/cbshome`
- [x] Backup cron (4 AM, ротация 7 дней)
- [x] Проверка previous installation (предложить удалить)

**Management script (`cbshome`):**
```
cbshome status                    -- Docker ps + uptime + memory + disk + health + external access
cbshome logs [app|db|redis|all]   -- Docker logs -f
cbshome test [backend|all]        -- pytest внутри контейнера
cbshome lint                      -- ruff + mypy внутри контейнера
cbshome update                    -- git fetch -> diff -> pull -> build --no-cache -> down -> up -> migrate -> seed -> test
cbshome restart [service]         -- restart all or specific service
cbshome backup                    -- pg_dump + .env -> tar.gz (7-day rotation)
cbshome db connect                -- psql в контейнер
cbshome db dump                   -- SQL dump в файл
cbshome db restore <file>         -- восстановление из dump с подтверждением
cbshome db migrate                -- alembic upgrade head
cbshome seed                      -- python scripts/seed_platform.py
cbshome seed --reset              -- clean + re-seed
cbshome ssl renew                 -- certbot renew + nginx reload
cbshome ssl status                -- certbot certificates info
cbshome nginx reload              -- nginx -t + systemctl reload
cbshome version                   -- git log + runtime versions + image list
```

**Особенности реализации:**
- `cbshome update` выходит с `exit 0` если Already up to date (нет новых коммитов)
- `cbshome update` не делает `git reset --hard` при ошибке — выводит инструкцию для ручного разрешения
- `.env` генерируется атомарно через temp file + mv (пароли генерируются один раз до heredoc)
- Docker build всегда `--no-cache` (и при install, и при update)
- Nginx: `X-Real-IP $remote_addr` прокидывается в app для достоверного IP в audit log

**Критерий готовности:** `curl https://api.cbshome.org/health` -> `{"status":"ok"}`.

---

### ✅ Sprint 0.5: Logging + Audit Service

**Цель:** Production-quality логирование и аудит финансовых операций.

**Задачи:**
- [x] `app/core/logging.py` — фильтрация по LOG_LEVEL (`make_filtering_bound_logger`), идемпотентность `setup_logging()`
- [x] `TraceIdMiddleware` — pure ASGI; кладёт в contextvars: `trace_id`, `ip_address`, `user_agent`, `avatar_session_id` (если присутствует в сессии); structlog подхватывает автоматически — каждое лог-сообщение в avatar режиме помечается без изменений в бизнес-логике
- [x] Trace_id guard: входящий X-Trace-ID > 36 символов -> генерируем новый uuid4
- [x] `app/core/audit.py` — `record_audit()` читает trace_id/ip/user_agent из contextvars, не коммитит (P-01)
- [x] `tests/test_audit.py` — 4 теста

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

**Критерий готовности:** LOG_LEVEL=WARNING фильтрует debug/info. trace_id и avatar_session_id (при наличии) в каждом лог-сообщении. Аудит пишется в БД.

---

## PHASE 1: Auth + Users

---

### ✅ Sprint 1.1: Email Auth

**Цель:** Регистрация и вход через email + password.

**Задачи:**
- [x] `app/modules/auth/service.py` — `register_email()`, `login_email()`, `create_session()`, `delete_session()`, `delete_all_sessions()`
- [x] `app/modules/auth/router.py`:
  - `POST /api/v1/auth/email/register`
  - `POST /api/v1/auth/email/login`
  - `POST /api/v1/auth/logout`
  - `POST /api/v1/auth/logout-all`
- [x] Email verification token (сохраняется в `credentials.onboarding.email_token`)
- [x] Password hash: argon2 (`argon2-cffi`)
- [x] Redis сессии: `session:{token}` + `user_sessions:{user_id}` (ZSET for logout-all)
- [x] TTL: `SESSION_TTL_DAYS` из config
- [x] Лимит: `MAX_CONCURRENT_SESSIONS` (5) — при превышении ZPOPMIN закрывает самую старую
- [x] `app/modules/auth/dependencies.py` — `get_current_user`, `get_current_user_write`, `get_optional_user`, `get_current_staff`
- [x] Блокировка логина для `role=platform` в `_load_user_from_request()`
- [x] `tests/test_auth_email.py` — 13 тестов (включая session limit eviction)

**Миграции:**
- [x] `0002_auth_indexes` — partial unique indexes на `credentials` JSONB (email + telegram_id)
- [x] `0003_ledger_amount_bigint` — фикс Phase 0: `amount_cents` INTEGER -> BIGINT

**Решения реализации (не в оригинальном ТЗ):**
- Email и telegram_id хранятся в `credentials` JSONB, не в отдельных колонках. Быстрый lookup через функциональные unique-индексы на JSONB. Позже — возможно вынесение в колонки или внешнюю таблицу (D-01/D-02)
- Timing-safe login: dummy argon2 hash при отсутствии пользователя (предотвращает email enumeration через timing side-channel)
- `IntegrityError` catch проверяет конкретный constraint `ix_users_email`, не маскирует другие ошибки
- `get_current_staff` — Sprint 1.1: проверяет только `role == staff`; Sprint 3.1: расширится permission matrix (D-04)
- Session data в Redis содержит `auth_method` ("email" | "telegram") для логирования
- Атомарные Redis-операции: MULTI/EXEC pipeline для create_session, Lua script для delete_all_sessions
- Known limitation: Redis session создаётся до DB commit; orphan чистится TTL (30 дней)

**Schemas:**
- [x] `app/modules/users/schemas.py` — `UserResponse` (без credentials), `UserUpdate`
- [x] `app/modules/auth/schemas.py` — `EmailRegisterRequest`, `EmailLoginRequest`, `AuthResponse`

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
    "email_token_expires_at": null,
    "email_verification_attempts": 0
  }
}
```

**Результат:**
```
backend/app/modules/auth/
├── __init__.py
├── schemas.py          -- EmailRegisterRequest, EmailLoginRequest, AuthResponse
├── service.py          -- register/login + Redis sessions (ZSET + Lua)
├── dependencies.py     -- get_current_user, _write, optional, staff
└── router.py           -- 4 endpoints

backend/app/modules/users/
└── schemas.py          -- UserResponse, UserUpdate

backend/tests/
├── __init__.py         -- package init
├── helpers.py          -- auth_headers, register_user, login_user, cleanup
└── test_auth_email.py  -- 13 tests
```

**Критерий готовности:** Юзер может зарегистрироваться и войти через email. `role=platform` логин заблокирован. 26 тестов зелёные.

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
- [ ] При изменении статуса KYCApplication — синхронизировать `User.kyc_status` (денормализованный кэш)
- [ ] `POST /api/v1/kyc/submit` — создаёт KYCApplication, статус -> submitted
- [ ] `GET /api/v1/kyc/status` — текущий статус
- [ ] `POST /api/v1/kyc/webhook` — заглушка (SumSub webhook handler, всегда approved в dev)
- [ ] `tests/test_kyc.py` — 5 тестов

**Критерий готовности:** Юзер может подать KYC заявку, статус обновляется через webhook-заглушку. `User.kyc_status` синхронизирован.

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
- [ ] JWT/сессия содержит `avatar_session_id`; `start_avatar()` пишет `avatar_session_id` в Redis-сессию так, чтобы `TraceIdMiddleware` читал его в contextvars на каждом запросе
- [ ] Все мутирующие операции в avatar режиме: `performed_by=staff_id`, `on_behalf_of=target_user_id` в audit_log
- [ ] `require_not_avatar` применяется к запрещённым операциям
- [ ] `tests/test_avatar.py` — 10 тестов

**Endpoints:**
```
POST /api/v1/staff/avatar/start   Body: {target_user_id} -> {avatar_session_id, session_token}
POST /api/v1/staff/avatar/end     -> 204
GET  /api/v1/staff/avatar/active  -> AvatarSession | null
```

**Критерий готовности:** Staff входит под юзером. `avatar_session_id` присутствует в каждом structlog-сообщении в режиме аватара. Все операции логируются в audit_log. Запрещённые операции блокируются.

---

### Sprint 3.3: Admin endpoints

**Цель:** Базовые admin-функции для управления пользователями.

**Задачи:**
- [ ] `GET /api/v1/staff/dashboard/stats` — базовая статистика платформы
- [ ] `GET /api/v1/staff/users` — список юзеров (пагинация, фильтры; `role=platform` исключён)
- [ ] `GET /api/v1/staff/users/{id}` — детали юзера
- [ ] `PATCH /api/v1/staff/users/{id}/block` — блокировка (is_active=false + завершить все сессии)
- [ ] `GET /api/v1/staff/kyc/queue` — очередь KYC заявок
- [ ] `POST /api/v1/staff/kyc/{id}/approve` — одобрить KYC
- [ ] `POST /api/v1/staff/kyc/{id}/reject` — отклонить KYC
- [ ] `tests/test_staff_admin.py` — 12 тестов

**Критерий готовности:** Staff видит и управляет пользователями. Platform user не появляется в списках.

---

## PHASE 4: Companies + Products

---

### Sprint 4.1: Companies

**Цель:** Профили компаний с медиа-материалами и дорожной картой.

**Задачи:**
- [ ] `app/modules/companies/models.py` — `CompanyProfile`, `CompanyPriceHistory`, `CompanyRoadmapItem`
- [ ] `app/modules/companies/service.py` — CRUD + `update_price()` (каскадное обновление Product)
- [ ] Staff endpoints (компания):
  - `POST /api/v1/staff/companies` — создать компанию
  - `PATCH /api/v1/staff/companies/{id}` — редактировать профиль и медиа
  - `PATCH /api/v1/staff/companies/{id}/price` — изменить цену акции (каскад + история)
- [ ] Staff endpoints (дорожная карта):
  - `POST /api/v1/staff/companies/{id}/roadmap` — добавить этап
  - `PATCH /api/v1/staff/companies/{id}/roadmap/{item_id}` — редактировать этап
  - `DELETE /api/v1/staff/companies/{id}/roadmap/{item_id}` — удалить этап
  - `PATCH /api/v1/staff/companies/{id}/roadmap/reorder` — изменить порядок (список id)
- [ ] Public endpoints:
  - `GET /api/v1/companies` — список активных компаний
  - `GET /api/v1/companies/{id}` — детали компании с дорожной картой
- [ ] `tests/test_companies.py` — 10 тестов

**Модели:**
```python
CompanyProfile:
    id, user_id  -- FK users.id (Company как User с role=company)
    name, description
    logo_url: str | None
    cover_url: str | None
    promo_video_url: str | None
    presentation_url: str | None
    price_per_unit_cents: int
    distribution_config: JSONB
    -- Структура: {"company_pct": 0.65, "agent_levels": [0.10, 0.03, 0.01]}
    -- agent_levels: произвольное число уровней, может быть [] (нет агентов)
    -- Остаток до 1.0 автоматически идёт Platform, не хранится
    -- Инвариант: company_pct + SUM(agent_levels) <= 1.0
    status: enum  -- active | hidden | archived
    created_at, updated_at

CompanyPriceHistory:
    id, company_id
    price_per_unit_cents: int
    changed_at: datetime
    changed_by: UUID  -- staff_id

CompanyRoadmapItem:
    id, company_id  -- FK company_profiles.id
    title: str
    description: str | None
    target_date: date | None
    status: enum    -- planned | in_progress | completed
    order: int      -- для сортировки
    created_at, updated_at
```

**Критерий готовности:** Компании создаются с медиа-полями. Цена обновляется каскадно. `distribution_config` валидируется. Дорожная карта управляется Staff и отображается публично.

---

### Sprint 4.2: Products

**Цель:** Продукты компаний с произвольным числом планов рассрочки.

**Задачи:**
- [ ] `app/modules/products/models.py` — `Product`, `ProductInstallment`
- [ ] `app/modules/products/service.py` — CRUD + `PurchaseConfigValidator`:
  - Валидация `distribution_config`: `company_pct + SUM(agent_levels) <= 1.0`
  - Валидация `plan_config`: см. ниже
- [ ] Staff endpoints:
  - `POST /api/v1/staff/products` — создать продукт
  - `PATCH /api/v1/staff/products/{id}` — редактировать
  - `PATCH /api/v1/staff/products/{id}/status` — изменить статус
  - `POST /api/v1/staff/products/{id}/installments` — добавить план рассрочки
  - `PATCH /api/v1/staff/products/{id}/installments/{inst_id}` — редактировать план
  - `DELETE /api/v1/staff/products/{id}/installments/{inst_id}` — удалить план
- [ ] Public endpoints (витрина):
  - `GET /api/v1/products` — список активных продуктов с планами рассрочки
  - `GET /api/v1/products/{id}` — детали продукта
- [ ] Redis кэш social proof (`sold_units` по продукту): TTL = `SOCIAL_PROOF_CACHE_TTL`
- [ ] `tests/test_products.py` — 12 тестов

**Модель `ProductInstallment`:**
```python
ProductInstallment:
    id: UUID
    product_id: UUID  -- FK products.id
    name: str         -- "6-месячный план", "Годовой VIP", etc.
    plan_config: JSONB
    created_at
```

**Структура `plan_config`:**
```json
{
  "tranches": [
    {"amount_cents": 16500, "units_percent": 10},
    {"amount_cents": 16500, "units_percent": 10},
    {"amount_cents": 16500, "units_percent": 10},
    {"amount_cents": 16500, "units_percent": 10},
    {"amount_cents": 16500, "units_percent": 10},
    {"amount_cents": 17500, "units_percent": 50}
  ],
  "bonus_units": 100,
  "agent_bonus_units": 50
}
```

**Семантика траншей:**
- `tranches[0]` — немедленный платёж (day 0, при создании плана)
- `tranches[1..N]` — ежемесячно по february rule
- Количество траншей не ограничено сверху

**Валидация `plan_config` при сохранении (`PurchaseConfigValidator`):**
```python
assert len(tranches) >= 2
assert all(t["amount_cents"] > 0 for t in tranches)
assert all(t["units_percent"] > 0 for t in tranches)
assert sum(t["amount_cents"] for t in tranches) == product.units * company.price_per_unit_cents
assert sum(t["units_percent"] for t in tranches) == 100
```

**Критерий готовности:** Витрина работает. Один продукт может иметь произвольное число планов рассрочки. `plan_config` и `distribution_config` валидируются при сохранении.

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

### Sprint 5.2: Payment Module (закрытый модуль)

**Цель:** Приём входящих платежей инвесторов. Модуль изолирован — внутренняя сложность
(проверки, фоллбэки провайдеров, retry-логика) скрыта за публичным интерфейсом.
Остальные модули взаимодействуют только через `PaymentServiceProtocol`, не напрямую с моделями.

**Архитектурный принцип:**
`payments/` — закрытый модуль. Публичная граница — `PaymentServiceProtocol`.
Таблица `crypto_addresses` — внутренняя, не видна снаружи.
Внутренняя логика (провайдеры, webhook-парсинг, retry) не регламентируется ТЗ —
это зона ответственности разработчика модуля.

**Публичный интерфейс (`app/modules/payments/interface.py`):**
```python
class PaymentServiceProtocol(Protocol):
    async def get_or_create_deposit_address(
        self, user_id: UUID, network: str
    ) -> DepositAddress: ...

    async def get_payment(
        self, payment_id: UUID
    ) -> Payment: ...
```

**Модели:**
```python
Payment:  -- входящие платежи инвесторов только
    id: UUID
    user_id: UUID          -- FK users.id
    payment_type: enum     -- crypto | bank (розетка)
    amount_cents: int      -- в USD cents; конвертация на входе
    status: enum           -- created | frozen | confirmed | reversed | failed
    provider_data: JSONB   -- схема зависит от payment_type (валидируется в сервисе)
    created_at: datetime
    updated_at: datetime

-- Структура provider_data для crypto:
-- {
--   "network": "TRC20",
--   "to_address": "TXxx...",    -- наш кошелёк (из crypto_addresses)
--   "from_address": "TYyy...",  -- кошелёк инвестора (из webhook)
--   "tx_hash": "abc123...",     -- из webhook
--   "confirmed_block": 12345678,
--   "amount_crypto": "100.50",
--   "exchange_rate": "1.00"
-- }
--
-- Структура provider_data для bank (розетка):
-- {
--   "bank_name": "...", "iban": "...", "swift": "...",
--   "bank_reference": "...", "sender_name": "...",
--   "receipt_url": "...", "sender_email": "..."
-- }

CryptoAddress:  -- внутренняя таблица модуля payments/
    id: UUID
    user_id: UUID   -- FK users.id
    network: str    -- TRC20 | ERC20 | BEP20 | PoS
    address: str    -- наш кошелёк для этого юзера и сети
    created_at: datetime
    -- UNIQUE (user_id, network)
```

**Задачи:**
- [ ] `app/modules/payments/interface.py` — `PaymentServiceProtocol`, `DepositAddress`
- [ ] `app/modules/payments/models.py` — `Payment`, `CryptoAddress`
- [ ] `app/modules/payments/service.py` — реализация `PaymentServiceProtocol`
- [ ] `app/modules/payments/router.py`:
  - `GET /api/v1/payments/crypto-address/{network}` — получить/создать адрес
  - `GET /api/v1/payments/history` — история платежей инвестора
- [ ] `app/modules/payments/webhook_router.py`:
  - `POST /api/v1/payments/crypto/webhook` — blockchain webhook
- [ ] Webhook: Payment `created -> frozen`, дополнение `provider_data` через `set_jsonb()`, запись в active_ledger
- [ ] `frozen_until = created_at + FREEZING_HOURS_CRYPTO`
- [ ] `payment_confirmation_worker` — daemon (asyncio.Task в lifespan)
- [ ] `tests/test_crypto_deposits.py` — 10 тестов

**Networks:** TRC20, ERC20, BEP20, PoS (из config)

**Критерий готовности:** Инвестор получает крипто-адрес. Webhook создаёт Payment и запись в active_ledger. Внешняя граница модуля (`PaymentServiceProtocol`) работает корректно.

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
При рассрочке `PurchaseContext` получает данные конкретного транша из снапшота `plan_config`,
а не из `ProductInstallment` напрямую — изменение плана не влияет на активные рассрочки.

`PurchaseContext` содержит `referral_link_id: UUID | None`. Если `None` — покупка органическая,
`ReferralProcessor` не вызывается, Platform получает полный остаток по `distribution_config`.
`None` — валидное состояние, не ошибка.

**Задачи:**
- [ ] `app/modules/processors/base.py` — `ProcessorProtocol`, `PurchaseContext`, `Transaction`, `LedgerEntry`
- [ ] `app/modules/processors/purchase.py` — `PurchaseProcessor`
- [ ] `app/modules/processors/gift.py` — `GiftProcessor`
- [ ] `app/modules/processors/registry.py` — `ProcessorRegistry` (расширяется в Phase 7)
- [ ] `app/modules/purchases/models.py` — `Purchase`:
```python
Purchase:
    id: UUID
    investor_id: UUID        -- FK users.id
    product_id: UUID         -- FK products.id
    company_id: UUID         -- FK company_profiles.id (денормализовано)
    legal_basis: enum        -- sale | gift | installment_tranche
    units: int
    paid_cents: int          -- 0 для gift
    price_per_unit_cents: int -- снапшот цены на момент покупки
    document_id: UUID        -- NOT NULL, PDF генерируется по запросу
    status: enum             -- active | reversed
    created_at: datetime
    -- agent_id отсутствует: реферальная информация только в ReferralAttribution
```
- [ ] `app/modules/purchases/service.py` — `execute_purchase()` (валидация SUM=0, атомарная запись)
- [ ] `POST /api/v1/products/{id}/purchase` — инстант-покупка (body: `{product_installment_id?}`, `{referral_link_id?}`)
- [ ] `tests/test_purchase_processor.py` — 15 тестов (включая invariant SUM=0)

**Инвариант перед записью в БД:**
```python
for transaction in transactions:
    assert sum(e.amount_cents for e in transaction.entries) == 0
```

**Критерий готовности:** Инвестор покупает продукт. PurchaseProcessor распределяет средства.
GiftProcessor создаёт бонусные акции. ProcessorRegistry готов к регистрации новых процессоров.
`Purchase` не содержит `agent_id` — реферальная цепочка только в `ReferralAttribution`.

---

### Sprint 6.2: Installment Plans

**Цель:** Покупка продукта в рассрочку.

**Задачи:**
- [ ] `app/modules/installments/models.py` — `InstallmentPlan`, `InstallmentTranche`
- [ ] `app/modules/installments/service.py` — `create_plan()`, `pay_tranche()`, `complete_plan()`, `default_plan()`
- [ ] `app/modules/installments/scheduler.py` — `calculate_due_date()` (february rule)
- [ ] `installment_payment_worker` — daemon (asyncio.Task в lifespan)
- [ ] `POST /api/v1/products/{id}/installment` — создать план (body: `{product_installment_id}`)
- [ ] `GET /api/v1/installments/me` — мои планы
- [ ] `GET /api/v1/installments/{id}` — детали плана
- [ ] `tests/test_installments.py` — 20 тестов (включая february rule, default, completion)

**Модель `InstallmentPlan`:**
```python
InstallmentPlan:
    id: UUID
    investor_id: UUID
    product_id: UUID
    product_installment_id: UUID
    plan_config_snapshot: JSONB  -- копия plan_config на момент создания плана;
                                 -- изменение ProductInstallment не влияет на активные планы
    total_price_cents: int       -- денормализовано из снапшота для быстрых проверок
    status: enum                 -- active | completed | defaulted | cancelled
    created_at, completed_at, defaulted_at
```

**Логика `create_plan()`:**
```
1. Загрузить ProductInstallment -> скопировать plan_config в plan_config_snapshot
2. Валидировать снапшот (PurchaseConfigValidator)
3. Создать InstallmentPlan (с referral_link_id: UUID | None из запроса)
4. Развернуть tranches из снапшота в записи InstallmentTranche:
   - tranches[0]: due_date = today, status = scheduled (daemon оплатит сразу)
   - tranches[1]: due_date = calculate_due_date(today, 1)
   - tranches[N]: due_date = calculate_due_date(today, N)
5. Daemon в ту же итерацию оплачивает tranches[0];
   referral_link_id передаётся в PurchaseContext каждого транша —
   если None, ReferralProcessor не вызывается
```

**Критерий готовности:** Инвестор выбирает план по `product_installment_id`. Снапшот фиксируется. Транши разворачиваются из снапшота. Daemon платит транши. Дефолт через 7 дней просрочки. Бонусы из снапшота при закрытии.

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
- [ ] `tests/test_referrals.py` — 15 тестов (включая STOP-механику, органические покупки)

**Модели:**
```python
ReferralLink:
    id: UUID
    agent_id: UUID   -- FK users.id (role=agent)
    code: str        -- unique
    created_at: datetime

ReferralAttribution:
    id: UUID
    purchase_id: UUID             -- FK purchases.id
    referral_link_id: UUID | None -- FK referral_links.id; NULL = органический трафик
    created_at: datetime
    -- Создаётся для КАЖДОЙ покупки, включая органические (referral_link_id=NULL)
    -- Это обеспечивает полный аудит: каждая покупка имеет attribution-запись
```

**Логика `resolve_attribution(referral_link_id)`:**
```
if referral_link_id is None:
    -> вернуть пустую цепочку агентов
    -> ReferralProcessor не вызывается
    -> Platform получает полный остаток по distribution_config
else:
    -> загрузить ReferralLink -> get_agent_chain() -> вернуть L1/L2/L3
    -> ReferralProcessor начисляет комиссии по цепочке
```

**Критерий готовности:** Агент создаёт реферальные ссылки. При покупке по ссылке — комиссии L1/L2/L3 начисляются через ReferralProcessor. Органические покупки (без ссылки) корректно обрабатываются: Platform получает полный остаток, `ReferralAttribution` создаётся с `referral_link_id=NULL`.

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
- [ ] Cron очистка: удалять `expiry_at < now()` у доставленных
- [ ] `tests/test_notifications.py` — 15 тестов

**Модели:**
```python
Notification:  -- channel-agnostic, одна запись на событие
    id: UUID
    type: str          -- indexed; system | transaction | commission | news | installment
    title: str
    body: str
    target_type: str   -- user | role | all
    target_value: str  -- user:<uuid> | role:agent | *
    action_data: JSONB | None  -- {"action": "open_purchase", "params": {"id": "uuid"}}
    priority: int      -- default 5 (1=highest)
    scheduled_at: datetime
    expiry_at: datetime | None
    status: enum       -- pending | processing | sent | failed | expired
    created_at: datetime

NotificationDelivery:  -- одна запись на получателя на канал
    id: UUID
    notification_id: UUID  -- FK notifications.id CASCADE
    user_id: UUID          -- FK users.id CASCADE; конкретный получатель
    channel: enum          -- telegram | email | push | in_app
    channel_options: JSONB | None
    -- telegram:  {parse_mode, disable_preview, silent}
    -- email:     {subject_override}
    -- push:      {icon, ttl}
    status: enum       -- pending | sent | failed
    sent_at: datetime | None
    attempts: int      -- default 0
    error_message: str | None
    created_at: datetime
```

**Архитектура pipeline:**
```
resolve:  Notification -> N NotificationDelivery (по target_type/target_value)
deliver:  NotificationDelivery -> ChannelFormatter -> внешний сервис
rollup:   NotificationDelivery statuses -> Notification.status
```

**Критерий готовности:** Уведомления создаются и обрабатываются процессором.

---

### Sprint 8.2: Email + Telegram Formatters

**Цель:** Реальная доставка уведомлений.

**Задачи:**
- [ ] `app/modules/notifications/templates/` — en.yaml (все типы)
- [ ] `app/modules/notifications/template_engine.py` — SafeDict, YAML loading, language fallback
- [ ] `app/modules/notifications/formatters.py` — `TelegramFormatter` (aiogram, send-only), `EmailFormatter` (EMAP + Mailgun fallback)
- [ ] Lazy init: real token -> real formatter, fake -> StubFormatter
- [ ] Permanent failure handling (bot blocked -> immediate failed, attempts не растут)
- [ ] `POST /api/v1/staff/notifications/templates/reload` — Staff reload templates
- [ ] `tests/test_notification_delivery.py` — 12 тестов

**Критерий готовности:** Уведомления приходят в Telegram и email.

---

### Sprint 8.3: Notification REST Endpoints

**Цель:** API для управления уведомлениями на фронте.

**Задачи:**
- [ ] `GET /api/v1/notifications` — список доставок текущего юзера (пагинация 20, фильтры по type/channel)
- [ ] `GET /api/v1/notifications/unread-count` — badge counter (deliveries где status=sent AND не прочитано)
- [ ] `POST /api/v1/notifications/{delivery_id}/read` — отметить delivery прочитанной
- [ ] `POST /api/v1/notifications/read-all` — отметить все delivery текущего юзера прочитанными
- [ ] `tests/test_notification_endpoints.py` — 8 тестов

**Критерий готовности:** Фронт работает с `NotificationDelivery`, а не с `Notification` напрямую.

---

## PHASE 9: Posts + Extras

---

### Sprint 9.1: Posts + Events

**Цель:** Единый модуль контента для платформы и компаний.

**Архитектурный принцип:** Платформенные новости и посты блога компаний — это одна и та же
сущность `Post` с разным `owner_type`. Единый модуль `posts/`, единый рендер на фронте,
единая лента с фильтрацией по владельцу. Staff создаёт посты как от имени платформы,
так и от имени конкретной компании.

**Задачи:**
- [ ] `app/modules/posts/models.py` — `Post`, `PostDismiss`, `Event`
- [ ] `app/modules/posts/service.py` — CRUD + баннерная логика + dismiss
- [ ] Public endpoints:
  - `GET /api/v1/posts` — лента постов (фильтры: `owner_type`, `company_id`, `tag`)
  - `GET /api/v1/posts/{id}` — детали поста
  - `GET /api/v1/events` — список событий
  - `GET /api/v1/events/upcoming` — ближайшие 30 дней
  - `POST /api/v1/posts/{id}/dismiss` — закрыть баннер
- [ ] Staff endpoints:
  - `POST /api/v1/staff/posts` — создать пост (платформа или от имени компании)
  - `PUT /api/v1/staff/posts/{id}` — редактировать
  - `DELETE /api/v1/staff/posts/{id}` — удалить
  - `POST /api/v1/staff/events` — создать событие
  - `PUT /api/v1/staff/events/{id}` — редактировать
  - `DELETE /api/v1/staff/events/{id}` — удалить
- [ ] `tests/test_posts.py` — 12 тестов

**Модели:**
```python
Post:
    id: UUID
    owner_type: enum  -- platform | company
    owner_id: UUID | None  -- NULL если platform, company_profiles.id если company
    title: str
    body: str         -- markdown или HTML
    cover_url: str | None
    tags: JSONB       -- ["investment", "growth"] -- массив строк
    is_banner: bool   -- показывать как баннер на главной
    is_published: bool
    published_at: datetime | None
    created_by: UUID  -- staff_id
    created_at, updated_at

PostDismiss:          -- факт закрытия баннера конкретным юзером
    id: UUID
    post_id: UUID     -- FK posts.id CASCADE
    user_id: UUID     -- FK users.id CASCADE
    dismissed_at: datetime

Event:
    id: UUID
    title: str
    description: str | None
    cover_url: str | None
    starts_at: datetime
    ends_at: datetime | None
    location: str | None
    url: str | None   -- ссылка на регистрацию или трансляцию
    is_published: bool
    created_by: UUID  -- staff_id
    created_at, updated_at
```

**Критерий готовности:** Staff создаёт посты платформы и постит от имени компаний. Инвесторы видят единую ленту с фильтрацией. Баннеры закрываются и не показываются повторно.

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
| TD-011 | `app/core/database.py` | Lazy singleton race condition при concurrent startup — теоретический, asyncio single-threaded, но задокументировать | Backlog | ⬜ |
| TD-012 | `audit_log` | Партиционирование по `created_at` (range partitioning) для long-term performance | Before Prod | ⬜ |
| TD-013 | `app/modules/ledgers/models.py` | LedgerMixin: вынести общие поля ActiveLedger/PassiveLedger в `_LedgerBase` (Abstract) | Backlog | ⬜ |
| TD-014 | `app/core/constants.py` | LedgerReason: заменить `: str` аннотации на `Final[str]` из `typing` | Backlog | ⬜ |
| TD-015 | `app/core/mixins.py` | JSONBMixin.set_jsonb(): уточнить type hint `value: dict` -> `value: dict[str, Any]` | Backlog | ⬜ |
| TD-016 | `tests/` | Добавить тесты: модели (User, Ledger, Staff), middleware (TraceId), config validation, seed_platform.py идемпотентность | Sprint 1+ | ⬜ |
| TD-017 | `app/modules/auth/router.py` | Email enumeration: register возвращает 409 для дубликатов. Mitigation: при наличии email sending (Phase 8) — всегда 201, уведомление на email | Phase 8 | ⬜ |
| TD-018 | `app/modules/auth/` | Rate limiting на auth endpoints (register + login). Отдельно от TD-008 (slowapi на все роутеры) — auth критичнее | Before Prod | ⬜ |
| TD-019 | `app/modules/auth/schemas.py` | Password complexity: добавить требование цифры или mixed case. min_length=8 достаточно для MVP | Before Prod | ⬜ |
| TD-020 | `app/core/middleware.py`, `app/core/audit.py` | `_USER_AGENT_MAX_LEN = 500` определён в двух файлах независимо. Вынести в `constants.py` | Backlog | ⬜ |
| TD-021 | `app/modules/auth/` | Password reset flow (forgot password -> email token -> reset) | After MVP | ⬜ |

---

**Конец документа**

---

*Version 0.9 | 2026-04-03 | cbshome Backend TZ*
