# CBSHOME -- Техническое задание (Backend)

**Версия:** 3.7
**Дата:** 13 мая 2026
**Статус:** Active
**Репозиторий:** https://github.com/aivis-one/cbshome

**Зависимости (читать перед работой):**
- `CBSHOME-Design-Document.md` — Конституция v1.6
- `CBSHOME-Financial-System.md` — финансовая логика
- `CBSHOME-State-Machines.md` — переходы статусов
- `CBSHOME-Installment.md` — механика рассрочки
- `CBSHOME-Share-Pool-Refactor.md` — TD-071 / Sprint 4.3 + 4.4 (✅ closed, deployed `b539ee8`)

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
- [x] `app/core/exceptions.py` — `CBSError -> NotFound / Forbidden / Conflict / BadRequest / Unauthorized / InsufficientBalance(BadRequest)` (Sprint 6.2: `+InsufficientBalanceError`)
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
    onboarding_step: enum  -- registered | email_verified | profile_complete | role_selected | kyc_done | onboarding_complete
    kyc_status: enum  -- not_started | submitted | approved | rejected
    -- kyc_status -- денормализованный кэш KYCApplication.status для hot path
    credentials: JSONB  -- {email: {...}, telegram: {...}, onboarding: {...}}
    profile: JSONB      -- {first_name, last_name, country, phone, avatar_url} (whitelist enforced, TD-024)
    language: str       -- "en" (default)
    referred_by: UUID   -- FK users.id (self-ref, NOT NULL, default=platform_id)
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
- [x] UFW: 22/80/443 + Docker→Postfix (172.16.0.0/12 → port 25)
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
cbshome test-email <email>        -- test Mailgun (primary) + SMTP (fallback) delivery
```

**Особенности реализации:**
- `cbshome update` выходит с `exit 0` если Already up to date (нет новых коммитов)
- `cbshome update` не делает `git reset --hard` при ошибке — выводит инструкцию для ручного разрешения
- `.env` генерируется атомарно через temp file + mv (пароли генерируются один раз до heredoc)
- `.env` template включает `MAILGUN_API_URL=https://api.eu.mailgun.net` (v3.3)
- `read` команды читают из `/dev/tty` (v3.3: совместимость с `curl | bash`)
- `docker compose build/up` получают `< /dev/null` (v3.3: предотвращает stdin consumption при pipe)
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
- [x] G1 fix: 6-значный цифровой код вместо `token_urlsafe(32)`. TTL 10 минут, max 5 попыток. Email отправляется при регистрации через `core/email.py`
- [x] G1 fix: `POST /api/v1/auth/verify-email` — проверка кода (timing-safe `secrets.compare_digest`)
- [x] G1 fix: `POST /api/v1/auth/verify-email/resend` — перегенерация + отправка, rate limit `email_verify_resend:{user_id}`
- [x] Password hash: argon2 (`argon2-cffi`)
- [x] Redis сессии: `session:{token}` + `user_sessions:{user_id}` (ZSET for logout-all)
- [x] TTL: `SESSION_TTL_DAYS` из config
- [x] Лимит: `MAX_CONCURRENT_SESSIONS` (5) — ZPOPMIN закрывает самую старую
- [x] `app/modules/auth/dependencies.py` — `get_current_user`, `get_current_user_write`, `get_optional_user`, `get_current_staff`
- [x] Блокировка логина для `role=platform` в `_load_user_from_request()`
- [x] `tests/test_auth_email.py` — 13 тестов (включая session limit eviction)

**Миграции:**
- [x] `0002_auth_indexes` — partial unique indexes на `credentials` JSONB (email + telegram_id)
- [x] `0003_ledger_amount_bigint` — фикс Phase 0: `amount_cents` INTEGER -> BIGINT

**Решения реализации:**
- Email и telegram_id в `credentials` JSONB, не в колонках. Функциональные unique-индексы для lookup + уникальности
- Timing-safe login: dummy argon2 hash при отсутствии пользователя
- `IntegrityError` catch проверяет конкретный constraint `ix_users_email`
- `get_current_staff` — Sprint 1.1: только `role == staff`; Sprint 3.1: permission matrix
- Session data содержит `auth_method` ("email" | "telegram")
- Атомарные Redis-операции: MULTI/EXEC pipeline + Lua script для logout-all
- Known limitation: Redis session до DB commit; orphan чистится TTL (30 дней)

**Endpoints:**
```
POST /api/v1/auth/email/register  -> AuthResponse {user, session_token}  (201)
POST /api/v1/auth/email/login     -> AuthResponse                       (200)
POST /api/v1/auth/verify-email    -> UserResponse                       (200)
POST /api/v1/auth/verify-email/resend -> 204
POST /api/v1/auth/logout          -> 204
POST /api/v1/auth/logout-all      -> 204
```

**Результат:**
```
backend/app/modules/auth/
├── __init__.py
├── schemas.py          -- EmailRegisterRequest, EmailLoginRequest, VerifyEmailRequest, AuthResponse
├── service.py          -- register/login/verify_email_code/resend + Redis sessions (ZSET + Lua)
├── dependencies.py     -- get_current_user, _write, optional, staff
└── router.py           -- 6 endpoints

backend/app/modules/users/
└── schemas.py          -- UserResponse, UserUpdate

backend/tests/
├── __init__.py
├── helpers.py          -- auth_headers, register_user, login_user, cleanup
└── test_auth_email.py  -- 13 tests
```

**Критерий готовности:** Юзер может зарегистрироваться и войти через email. `role=platform` логин заблокирован. 26 тестов зелёные.

---

### ✅ Sprint 1.2: Telegram Auth

**Цель:** Вход через Telegram WebApp. Второй auth-метод.

**Задачи:**
- [x] `app/modules/auth/telegram.py` — валидация initData (HMAC-SHA256), anti-replay (Redis SET NX), rate limiting (делегирует на `core/rate_limit.py` Lua-скрипт)
- [x] `POST /api/v1/auth/telegram` — upsert юзера при логине
- [x] Upsert: SELECT + INSERT с SAVEPOINT (P-05) для race condition (ON CONFLICT невозможен на functional JSONB index)
- [x] Обновление `credentials.telegram` при каждом логине (username, photo_url, language_code)
- [x] `session.refresh(user)` после `set_jsonb` + `flush` (предотвращает MissingGreenlet)
- [x] `tests/test_auth_telegram.py` — 10 тестов (включая clock skew boundary)

**Решения реализации:**
- `telegram.py` — отдельный модуль (валидация + security), `service.py` — бизнес-логика upsert
- Anti-replay: Redis SET NX с TTL = `auth_init_data_ttl_seconds` (300s)
- Rate limit: ~~INCR + EXPIRE~~ → делегирует на `check_rate_limit()` из `core/rate_limit.py` (атомарный Lua-скрипт). `BadRequestError` оборачивается в `TelegramValidationError` (фикс code review)
- Clock skew guard: `auth_clock_skew_seconds` (60s) — отклоняет auth_date из далёкого будущего
- `begin_nested()` (SAVEPOINT) для race condition: INSERT rollback не ломает outer transaction
- Audit записывается во всех ветках: login, register, race-resolved (с `race_resolved: True`)
- `BOT_TOKEN` в тестах читается из `settings.telegram_bot_token` (совпадает с .env на VPS)

**Config (новые настройки):**
```
auth_rate_limit_max_requests: int = 5
auth_rate_limit_window_seconds: int = 60
auth_init_data_ttl_seconds: int = 300
auth_clock_skew_seconds: int = 60
```

**Endpoint:**
```
POST /api/v1/auth/telegram  -> AuthResponse {user, session_token}  (200)
```

**Результат:**
```
backend/app/modules/auth/
└── telegram.py         -- HMAC validation, anti-replay, rate limiting

backend/tests/
├── helpers.py          -- +build_init_data, login_telegram, cleanup_telegram
└── test_auth_telegram.py  -- 10 tests
```

**Критерий готовности:** Telegram WebApp авторизует юзера. Anti-replay и rate limiting работают. 36 тестов зелёные.

---

### ✅ Sprint 1.3: User Profile

**Цель:** Чтение и редактирование профиля. Закладка avatar_guard.

**Задачи:**
- [x] `app/modules/users/schemas.py` — `UserResponse`, `UserUpdate` (созданы в Sprint 1.1)
- [x] `app/modules/users/service.py` — `update_user()` (partial update, exclude_unset, set_jsonb, refresh)
- [x] `app/modules/users/router.py`:
  - `GET /api/v1/users/me`
  - `PATCH /api/v1/users/me`
- [x] `app/modules/auth/avatar_guard.py` — `require_not_avatar` decorator + `RESTRICTED_OPERATIONS` frozenset
- [x] `tests/test_users.py` — 10 тестов (включая avatar guard unit test)

**Решения реализации:**
- `exclude_unset=True` для partial PATCH — различает "не отправлено" и "explicit null"
- `language: null` rejection в service layer, не в schema validator (не конфликтует с default=None)
- `session.refresh(user)` после `set_jsonb` + `flush` (MissingGreenlet prevention)
- TD-029 pattern: `get_current_user_write` + `Depends(get_db_session)` — одна сессия
- Profile merge: `dict.update()` — shallow merge, корректно для flat profile JSONB. `_ALLOWED_PROFILE_KEYS` whitelist: `first_name`, `last_name`, `country`, `phone`, `avatar_url` — неизвестные ключи → `BadRequestError` (TD-024 закрыт, фикс code review)
- `RESTRICTED_OPERATIONS` как `frozenset` с dev guard (`ValueError` при неизвестной операции)
- Avatar guard читает из `structlog.contextvars.get_contextvars()` — тот же механизм что middleware
- Audit: `user.profile_updated` с `data={"fields": [...]}` (без значений — compliance-safe)

**Endpoints:**
```
GET   /api/v1/users/me  -> UserResponse  (200)
PATCH /api/v1/users/me  -> UserResponse  (200)
```

**Результат:**
```
backend/app/modules/users/
├── __init__.py
├── schemas.py      -- UserResponse, UserUpdate (Sprint 1.1)
├── service.py      -- update_user() with audit
└── router.py       -- GET/PATCH /me (TD-029)

backend/app/modules/auth/
└── avatar_guard.py -- require_not_avatar decorator

backend/tests/
└── test_users.py   -- 10 tests
```

**Критерий готовности:** Юзер видит и редактирует свой профиль. Avatar guard создан и протестирован (unit test). Будет применён к endpoints в Sprint 3.2. 46 тестов зелёные.

---

**Phase 1 завершена.** 7 endpoints, 33 теста Phase 1 (+13 Phase 0 = 46 total), 3 миграции.

---

## PHASE 2: KYC + Documents (заглушки)

---

### ✅ Sprint 2.1: KYC заглушка

**Цель:** Структура KYC без реальной интеграции SumSub.

**Задачи:**
- [x] `app/modules/kyc/models.py` — `KYCApplication`, `KYCApplicationStatus` (StrEnum)
- [x] `app/modules/kyc/service.py` — `submit_kyc()`, `get_kyc_status()`, `process_webhook()`
- [x] При изменении статуса KYCApplication — синхронизация `User.kyc_status` (денормализованный кэш)
- [x] `POST /api/v1/kyc/submit` — создаёт KYCApplication, статус -> submitted, **сразу ставит `onboarding_step = kyc_done`** (v3.3: non-blocking KYC, верификация идёт в фоне)
- [x] `GET /api/v1/kyc/status` — текущий статус + последняя заявка
- [x] `POST /api/v1/kyc/webhook` — заглушка (SumSub webhook handler) с `X-Webhook-Secret` защитой
- [x] `tests/test_kyc.py` — 7 тестов

**Миграции:**
- [x] `0004_kyc_and_documents` — `kyc_applications` + `documents` + `document_signings` (одна миграция на всю Phase 2)

**Решения реализации:**
- Минимальная модель KYCApplication: `id, user_id, status, created_at, updated_at`. Поля SumSub (applicant_id, external_status, rejection_reason) добавятся через ALTER ADD COLUMN при реальной интеграции (TD-003)
- История заявок: rejected → повторная подача → новая строка KYCApplication. Полноценная логика заложена сразу, хотя заглушка всегда approved
- Webhook защищён `X-Webhook-Secret` header, секрет генерируется при установке (`install_cbshome.sh`), обязателен в production. В будущем — замена на SumSub signature validation (TD-003)
- `process_webhook()` содержит guard `_VALID_WEBHOOK_STATUSES = {"approved", "rejected"}` — защита от невалидных статусов при вызове из других модулей
- `User.kyc_status` синхронизируется при каждом изменении статуса KYCApplication + audit `kyc.status_changed`
- `KYC_WEBHOOK_SECRET` добавлен в `config.py` (dev default: `"dev-webhook-secret"`, production: ValueError при пустом) и в `install_cbshome.sh` (генерируется через `gen_password`)

**Config (новые настройки):**
```
kyc_webhook_secret: str = ""  -- required in production
```

**Endpoints:**
```
POST /api/v1/kyc/submit   -> KYCSubmitResponse {id, status, created_at}  (201)
GET  /api/v1/kyc/status   -> KYCStatusResponse {kyc_status, application_id?, application_status?}  (200)
POST /api/v1/kyc/webhook  -> {"status": "ok"}  (200, requires X-Webhook-Secret)
```

**Результат:**
```
backend/app/modules/kyc/
├── __init__.py
├── models.py       -- KYCApplication, KYCApplicationStatus
├── schemas.py      -- KYCSubmitResponse, KYCStatusResponse, KYCWebhookRequest
├── service.py      -- submit_kyc, get_kyc_status, process_webhook
└── router.py       -- 3 endpoints

backend/tests/
└── test_kyc.py     -- 7 tests
```

**Критерий готовности:** Юзер может подать KYC заявку, статус обновляется через webhook-заглушку. `User.kyc_status` синхронизирован. Webhook защищён shared secret.

---

### ✅ Sprint 2.2: Documents

**Цель:** Модуль документов с версионированием, статусами и фактом подписания (checkbox consent).

**Задачи:**
- [x] `app/modules/documents/models.py` — `Document`, `DocumentSigning`, `DocumentType`, `DocumentStatus`
- [x] `app/modules/documents/constants.py` — `ROLE_REQUIRED_DOCUMENT_TYPES`, `VALID_STATUS_TRANSITIONS`
- [x] Staff CRUD: `POST/PATCH/DELETE /api/v1/staff/documents`
- [x] `POST /api/v1/documents/{id}/sign` — checkbox consent, запись в DocumentSigning
- [x] `GET /api/v1/documents` — список активных документов по роли (с is_signed flag)
- [x] `GET /api/v1/documents/{id}` — документ с is_signed flag
- [x] `tests/test_documents.py` — 10 тестов

**Решения реализации:**
- `Document.status` — `str` с CHECK constraint (`draft | active | archived`), не `is_active: bool`. State machine из CBSHOME-State-Machines.md v1.4 section 5: `draft -> active, active -> draft, active -> archived, draft -> archived`
- `DocumentType` — конкретные типы (`privacy_policy, terms_of_service, investment_agreement, agent_agreement, company_agreement`). Маппинг ролей в `ROLE_REQUIRED_DOCUMENT_TYPES` dict в `constants.py` — самодокументируемо, легко расширить
- Подпись = запись факта (checkbox consent) в `DocumentSigning`. DocuSign — розетка Phase 2+ (TD-005). `DocumentSigning` — иммутабельная запись, нет `updated_at`
- UNIQUE constraint `(type, version)` на Document — одна версия одного типа. UNIQUE constraint `(user_id, document_id)` на DocumentSigning — одна подпись на документ
- `IntegrityError` catch по конкретному constraint name (паттерн P-05)
- `content_url` валидируется `@field_validator` — только `https://` (предотвращает XSS через `javascript:` и LFI через `file:///`)
- `is_signed` флаг в `DocumentResponse` через `model_copy(update=...)` — идиоматичный Pydantic v2
- Staff endpoints в отдельном файле `staff_router.py` с prefix `/api/v1/staff/documents` — чистое разделение auth scopes
- Staff auth: текущий `get_current_staff` (role == staff). Permission matrix — Phase 3
- Проверка подписей при смене роли — не реализована, роль пока не меняется (Phase 7, TD-025)
- `USER_AGENT_MAX_LEN` вынесен в `core/constants.py` (TD-020 закрыт), используется в `middleware.py`, `audit.py`, `documents/service.py`
- Удаление только draft документов. Active и archived — имеют подписания или audit-значимость
- `list_documents_for_role()` — 2 запроса (документы + подписания), для <20 документов на роль допустимо

**Модели:**
```python
Document:
    id: UUID, type: String(50)  -- CHECK: 5 типов
    version: Integer, title: String(500), content_url: String(2000)
    status: String(20)  -- CHECK: draft | active | archived
    created_by: UUID  -- FK users.id (staff)
    created_at, updated_at
    -- UNIQUE (type, version)

DocumentSigning:  -- иммутабельная, нет updated_at
    id: UUID, user_id: UUID, document_id: UUID
    signed_at: DateTime(tz), ip_address: String(45), user_agent: String(500)
    -- UNIQUE (user_id, document_id)
    -- Future: docusign_envelope_id (TD-005)
```

**Endpoints:**
```
-- User endpoints:
GET  /api/v1/documents          -> list[DocumentResponse]  (200)
GET  /api/v1/documents/{id}     -> DocumentResponse         (200)
POST /api/v1/documents/{id}/sign -> DocumentSigningResponse  (201)

-- Staff endpoints:
POST   /api/v1/staff/documents       -> DocumentResponse  (201)
PATCH  /api/v1/staff/documents/{id}  -> DocumentResponse  (200)
DELETE /api/v1/staff/documents/{id}  -> 204
```

**Результат:**
```
backend/app/modules/documents/
├── __init__.py
├── models.py           -- Document, DocumentSigning, DocumentType, DocumentStatus
├── constants.py        -- ROLE_REQUIRED_DOCUMENT_TYPES, VALID_STATUS_TRANSITIONS
├── schemas.py          -- DocumentResponse, DocumentCreateRequest, DocumentUpdateRequest, DocumentSigningResponse
├── service.py          -- Staff CRUD + user list/get/sign
├── router.py           -- 3 user endpoints
└── staff_router.py     -- 3 staff endpoints

backend/tests/
├── helpers.py          -- +create_staff_user, +_cleanup_user_related_data
└── test_documents.py   -- 10 tests
```

**Критерий готовности:** Юзер видит документы по своей роли и подписывает. Staff управляет документами с валидацией state machine. 63 теста зелёные.

---

### ✅ Sprint 2.2 UPDATE: Legal Body как static-файлы + Role mapping в JSONB + Localisation

**Цель:** убрать внешний `content_url` (ранее S3/URL на стороне), убрать жёсткий enum типов и жёсткий dict `ROLE_REQUIRED_DOCUMENT_TYPES`, добавить локализацию документов (en/ru/de/ar).

**Миграции:**
- [x] `0024_documents_role_metadata.py`:
  - `DROP COLUMN content_url`
  - `ADD COLUMN required_for_roles JSONB NOT NULL DEFAULT '[]'::jsonb`
  - `ADD COLUMN content_hash String(64)` (sha256 от тела HTML)
  - Снят `CHECK ck_documents_type` — `type` теперь свободный String, допустимые значения определяются файлами в `frontend/public/legal/`
- [x] `0025_documents_language.py`:
  - `ADD COLUMN language String(10) NOT NULL DEFAULT 'en'`
  - Пересоздан UNIQUE: было `(type, version)` → стало `(type, version, language)`
  - `CREATE INDEX ix_documents_type_language_status` для запроса онбординга

**Изменения:**
- [x] `app/modules/documents/models.py` — убран `DocumentType` enum; добавлены `language`, `required_for_roles` (JSONB), `content_hash`. `type: String(50)` без CHECK
- [x] `app/modules/documents/constants.py` — **удалена** `ROLE_REQUIRED_DOCUMENT_TYPES`. Роли задаются в `Document.required_for_roles` (JSONB array)
- [x] `app/modules/documents/schemas.py` — `DocumentResponse/CreateRequest` получили `language`, `required_for_roles`; убран `content_url` + `https://` валидатор
- [x] `app/modules/documents/service.py`:
  - `list_documents_for_role(role, user_language, user_id, session)` — JSONB containment `Document.required_for_roles.contains([role])`, фильтр по `language IN (user_language, 'en')`, per-type выбор: user_language если есть, иначе `en`. Если required type не существует ни в user_language, ни в `en` — `RuntimeError` (HTTP 500) + `structlog.error("legal_documents_misconfigured")`. Админ видит поломку сразу, онбординг блокируется
  - `_maybe_complete_onboarding(user_id, session)` — группирует по `Document.type` (не по document_id): юзер, подписавший `privacy_policy` на одной локали, считается выполнившим требование по типу даже если сменил язык в середине онбординга
- [x] `app/modules/documents/router.py` — `GET /documents` передаёт `user.language` в сервис
- [x] `scripts/seed_documents.py` — новый скрипт:
  - Читает `/legal/<lang>/<type>.html` (bind-mounted read-only из `frontend/public/legal`)
  - stdlib `html.parser` извлекает meta-теги: `cbs-document-type` (required), `cbs-language` (required, must match folder name), `cbs-required-for-roles` (CSV), `<title>`
  - sha256 тела файла → сравнение с существующей active-записью (type, language)
  - Идемпотент: нет записи → v1 active; хэш совпал → metadata-only update title/roles; хэш разный → archive current + v+1 active; файл удалён → archive (никогда не delete, чтобы не сломать FK на DocumentSigning)
- [x] `frontend/public/legal/<lang>/<type>.html` × 5 типов × 4 локали = **20 HTML-болванок** с Lorem ipsum (TD-066)
- [x] `docker-compose.yml` — `./frontend/public/legal:/legal:ro` bind mount в сервис `app`
- [x] `scripts/install_cbshome.sh` — `seed_documents.py` вызывается в `install`, `update`, `case_seed` ветках после `seed_platform.py` / `seed_admin.py`
- [x] `tests/test_documents.py` — все прямые POST `/staff/documents` + хелпер `_create_active_document` шлют `"language": "en"`; `_cleanup_documents` фикстура перед/после каждого теста (TD-067)
- [x] `tests/test_onboarding.py` — хелпер `_create_active_doc` принимает `language` (default `en`)
- [x] `tests/test_avatar.py::test_avatar_guard_blocks_in_avatar_mode` — `content_url` → `language: "en"` в POST body

**Решения реализации:**
- **Static HTML вместо content_url/S3.** Тело документа — не сущность БД, а часть артефакта фронта. Релиз legal-текста = PR с правкой HTML + `cbshome update`. Seed сам бампнёт версию по хэшу. Никаких внешних URL, XSS/LFI guard больше не нужен
- **type как free-form String.** Легальная команда может добавить новый тип документа (напр. `risk_disclosure`) без миграции — положить файл, прописать meta. Заодно отпадает дубль `enum DocumentType` ↔ `CHECK ck_documents_type`
- **required_for_roles JSONB.** SQLAlchemy `.contains([role])` транслируется в PostgreSQL `@>` (JSONB containment). Покрыто индексом `(type, language, status)` по первым двум колонкам — выборка `status='active' AND required_for_roles @> [role]` быстрая, containment filter добивается в памяти на небольшом результате
- **en — гарантированный baseline.** Если для типа нет локализованной копии, должна быть `en`. Отсутствие обеих = платформа сломана → 500. Молчаливый skip недопустим (юзер прошёл бы онбординг без подписания документа)
- **_maybe_complete_onboarding группирует по type, не по id.** Иначе смена локали в UI после подписания на старой локали сбивает расчёт
- **Seed читает через stdlib html.parser.** BeautifulSoup/lxml не нужны. Мелкая утилитка, без внешних deps
- **sha256 тела как content_hash.** Любое изменение HTML (включая whitespace) бампит версию. Для legal это приемлемо: каждая правка — новая редакция
- **Никогда не DELETE Document.** Archive-only, чтобы сохранить FK-integrity с `document_signings` (юзер подписал v1, v2 активна, v1 архивна — запись подписи v1 остаётся валидной)

**Endpoints (без изменений):**
```
GET  /api/v1/documents          -> list[DocumentResponse]   (now: language-resolved)
GET  /api/v1/documents/{id}     -> DocumentResponse
POST /api/v1/documents/{id}/sign -> DocumentSigningResponse
POST   /api/v1/staff/documents       -> DocumentResponse  (body: +language, -content_url, +required_for_roles)
PATCH  /api/v1/staff/documents/{id}  -> DocumentResponse
DELETE /api/v1/staff/documents/{id}  -> 204
```

**Модели (актуальные):**
```python
Document:
    id: UUID, type: String(50), version: Integer, language: String(10)
    title: String(500)
    required_for_roles: JSONB  -- ['investor', 'agent', ...]
    content_hash: String(64)    -- sha256, internal
    status: String(20)  -- CHECK: draft | active | archived
    created_by: UUID  -- FK users.id
    -- UNIQUE (type, version, language)
    -- INDEX (type, language, status)
```

**Критерий готовности:** юзер в любой из 4 локалей видит свои документы и подписывает. Смена user.language между подписаниями не ломает прогресс. 336 тестов зелёные.

---

**Phase 2 завершена.** 9 endpoints (3 KYC + 3 documents user + 3 documents staff), 17 тестов Phase 2 (+46 Phase 0-1 = 63 total), 1 миграция (итого 4).

**Обновлённые core-файлы:**
- `core/constants.py` — `+USER_AGENT_MAX_LEN = 500`
- `core/config.py` — `+kyc_webhook_secret`, `+is_dev` property, `+crypto_network_list` property, `+log_level` validation, `+CORS_ORIGINS` production validation
- `core/audit.py` — `USER_AGENT_MAX_LEN` из constants (было локальное `_USER_AGENT_MAX_LEN`)
- `core/middleware.py` — `USER_AGENT_MAX_LEN` из constants (было локальное `_USER_AGENT_MAX_LEN`)
- `main.py` — `+kyc_router`, `+documents_router`, `+staff_documents_router`
- `.env.example` — `+KYC_WEBHOOK_SECRET=`
- `install_cbshome.sh` — `+KYC_WEBHOOK_SECRET` генерация в `.env`

---

## F2.3-Backend: Onboarding State Machine

---

### ✅ Sprint F2.3-B: Onboarding Step Progression + Role Selection

**Цель:** Автоматическое продвижение `onboarding_step` при каждом шаге онбординга + endpoint для выбора роли.

**Задачи:**
- [x] `app/modules/users/models.py` — `OnboardingStep` enum: `+ ONBOARDING_COMPLETE = "onboarding_complete"`, `@property email` на User (извлекает из credentials JSONB)
- [x] `app/modules/users/schemas.py` — `+ email: str | None = None` в `UserResponse`, `+ SelectRoleRequest { role }` с `field_validator` (investor/agent/company)
- [x] `app/modules/users/service.py` — `+ select_role()` (guard: step == profile_complete), `update_user()`: auto-advance к `profile_complete` при заполненном профиле (first_name + last_name + country)
- [x] `app/modules/users/router.py` — `+ POST /api/v1/users/me/select-role`
- [x] `app/modules/auth/service.py` — `verify_email_code()`: `registered` → `email_verified`
- [x] `app/modules/kyc/service.py` — `process_webhook()`: approved + `role_selected` → `kyc_done`
- [x] `app/modules/documents/service.py` — `sign_document()`: `+ _maybe_complete_onboarding()` — все docs роли подписаны → `onboarding_complete`
- [x] `migrations/versions/0023_onboarding_complete.py` — ALTER CHECK constraint + `onboarding_complete`
- [x] `tests/test_onboarding.py` — 7 тестов (full flow + edge cases)

**Onboarding State Machine:**
```
REGISTERED → EMAIL_VERIFIED → PROFILE_COMPLETE → ROLE_SELECTED → KYC_DONE → ONBOARDING_COMPLETE
     ↑              ↑                ↑                 ↑              ↑              ↑
 verify_email   update_user      select_role      submit_kyc     sign_document
 (auth/service) (users/service)  (users/service)  (kyc/service)  (documents/service)
```

**v3.3:** `submit_kyc()` сразу ставит `KYC_DONE` (non-blocking KYC). Верификация идёт в фоне, webhook обновляет только `kyc_status`, не `onboarding_step`.

**Решения реализации:**
- Каждый step advancement проверяет текущий шаг — пропуск шагов невозможен
- **BP-15: Auto-advance при 0 элементов.** Каждый шаг онбординга должен обрабатывать случай "нечего обрабатывать". Если на шаге 0 элементов (0 документов, KYC submit без ожидания) — auto-advance на следующий шаг. Не полагаться на то, что фронт вызовет конкретный endpoint. Правило: если `count == 0` → step++ автоматически
- `select_role()` — отдельный endpoint (не через PATCH /users/me) с Pydantic валидацией: `_SELECTABLE_ROLES = {"investor", "agent", "company"}`. Staff/platform → 422
- `_maybe_complete_onboarding()` — выбирает active `Document`, где `required_for_roles @> [user.role]`, группирует по `type`, сравнивает с подписанными. Только при `step == kyc_done`. Группировка по type (не по document_id) — смена локали между подписаниями не сбивает прогресс
- `email` на UserResponse — `@property` на модели, Pydantic `from_attributes=True` подхватывает. Не колонка в БД, не миграция
- Profile completion: `_REQUIRED_PROFILE_FIELDS = {"first_name", "last_name", "country"}` — auto-advance при заполнении

**Endpoints (добавлено):**
```
POST /api/v1/users/me/select-role  -> UserResponse  (200)
```

**Результат:**
```
Обновлённые файлы (7 сервисов + 1 миграция + 1 тест):
  app/modules/users/models.py      -- +ONBOARDING_COMPLETE, +@property email
  app/modules/users/schemas.py     -- +email в UserResponse, +SelectRoleRequest
  app/modules/users/service.py     -- +select_role(), update_user() auto-advance
  app/modules/users/router.py      -- +POST /me/select-role
  app/modules/auth/service.py      -- verify_email_code() step advance
  app/modules/kyc/service.py       -- process_webhook() step advance
  app/modules/documents/service.py -- sign_document() + _maybe_complete_onboarding()
  migrations/versions/0023_onboarding_complete.py
  tests/test_onboarding.py         -- 7 tests
```

**Критерий готовности:** Полный onboarding flow работает end-to-end. 336 тестов зелёные.

---

## PHASE 3: Staff + Avataring

---

### ✅ Sprint 3.1: StaffProfile + Permissions

**Цель:** Профили сотрудников с матрицей прав.

**Задачи:**
- [x] `app/modules/staff/constants.py` — `DEFAULT_STAFF_PERMISSIONS`, `VALID_PERMISSION_KEYS`, `is_admin()`
- [x] `app/modules/staff/schemas.py` — `CreateStaffRequest`, `UpdatePermissionsRequest`, `StaffProfileResponse`, `StaffListItem`
- [x] `app/modules/staff/service.py` — `create_staff()`, `update_permissions()`, `get_staff_profile()`, `get_effective_permissions()`
- [x] `app/modules/staff/router.py`:
  - `POST /api/v1/staff/users` — создать Staff юзера (admin only)
  - `PATCH /api/v1/staff/users/{id}/permissions` — изменить права (admin only)
  - `GET /api/v1/staff/users` — список Staff (any staff)
- [x] Permission matrix из config (дефолты) + override в StaffProfile.permissions
- [x] `get_current_staff` dependency с проверкой конкретного права
- [x] `scripts/seed_admin.py` — создание первого admin
- [x] `tests/test_staff.py` — 8 тестов

**Дефолтные права (single source в `staff/constants.py`):**
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

**Решения реализации:**
- P3-01: `POST /staff/users` принимает `{user_id}` — промоутит существующего юзера, не создаёт нового. Staff — роль, не отдельная сущность
- P3-02: Admin = staff с ALL permissions True. Нет отдельного admin-флага. `is_admin()` helper в `constants.py`. "Градации определяются конфигурацией, не отдельными ролями в коде"
- P3-03: Только admin может создавать staff и менять permissions. Первый admin — через `seed_admin.py`
- P3-04: Промоция staff необратима. Staff не имеет пользовательской функциональности (документы, KYC)
- P3-05: `get_current_staff` возвращает `User` (не tuple). Дополнительный DB query в `_require_admin` допустим для редких admin-операций
- P3-06: Нет guard последнего admin — staff trusted. Если admin заблокирует себя, `seed_admin.py` восстановит
- P3-07: `seed_admin.py` читает пароль из `ADMIN_PASSWORD` env var или `getpass` prompt (не CLI arg — security)
- P3-08: `require_staff_permission()` — фабрика FastAPI dependency: staff check + конкретный permission. Имя dependency устанавливается для отладки
- P3-09: `staff/constants.py` — единственный source of truth для permissions. `core/constants.py` не дублирует. `auth/dependencies.py` импортирует из `staff/constants.py`

**Endpoints:**
```
POST  /api/v1/staff/users                     -> StaffProfileResponse  (201)
PATCH /api/v1/staff/users/{id}/permissions     -> StaffProfileResponse  (200)
GET   /api/v1/staff/users                      -> list[StaffListItem]   (200)
```

**Результат:**
```
backend/app/modules/staff/
├── __init__.py
├── models.py           -- StaffProfile, AvatarSession (Phase 0)
├── constants.py        -- DEFAULT_STAFF_PERMISSIONS, VALID_PERMISSION_KEYS, is_admin()
├── schemas.py          -- CreateStaffRequest, UpdatePermissionsRequest, StaffProfileResponse, StaffListItem
├── service.py          -- create_staff, update_permissions, get_staff_profile, get_effective_permissions
└── router.py           -- 3 endpoints

backend/scripts/
└── seed_admin.py       -- seed first admin (ADMIN_PASSWORD env or getpass)

backend/tests/
└── test_staff.py       -- 8 tests
```

**Критерий готовности:** Staff создаётся, права проверяются в зависимостях. 71 тест зелёный.

---

### ✅ Sprint 3.2: Avataring

**Цель:** Механизм входа Staff под пользователем.

**Задачи:**
- [x] `app/modules/staff/avatar_schemas.py` — `AvatarStartRequest`, `AvatarStartResponse`, `AvatarSessionResponse`
- [x] `app/modules/staff/avatar_service.py` — `start_avatar()`, `end_avatar()`, `get_active_avatar()`
- [x] `app/modules/staff/avatar_router.py`:
  - `POST /api/v1/staff/avatar/start` — создание AvatarSession + Redis avatar token
  - `POST /api/v1/staff/avatar/end` — завершение AvatarSession (staff's original token)
  - `GET /api/v1/staff/avatar/active` — текущая активная сессия
- [x] Avatar token в Redis с `avatar_session_id` + `avatar_staff_id` в session data
- [x] `avatar_session_id` + `avatar_staff_id` биндятся в `_load_user_from_request()` (dependencies.py) — НЕ в middleware
- [x] `core/audit.py` — auto-fill `performed_by`/`on_behalf_of` из contextvars + defensive UUID parse
- [x] `@require_not_avatar("sign_document")` применён к `documents/router.py`
- [x] `tests/test_avatar.py` — 10 тестов

**Avatar Session Redis Format:**
```json
{
  "user_id": "<target_user_id>",
  "auth_method": "avatar",
  "created_at": "iso",
  "avatar_session_id": "<avatar_session.id>",
  "avatar_staff_id": "<staff.id>"
}
```

**Решения реализации:**
- P3-10: Avatar token отделён от user ZSET — не занимает слот из MAX_CONCURRENT_SESSIONS, не вытесняется user's logout-all
- P3-11: Redis reverse lookup `avatar_token:{avatar_session_id}` → token для cleanup при `/end`. Никаких миграций — сессионные токены живут в Redis, AvatarSession в БД — аудит-запись
- P3-12: `/end` вызывается оригинальным staff-токеном (не аватарным). Аватарный токен привязан к целевому юзеру — через него staff не идентифицируется
- P3-13: Повторный `/start` автоматически закрывает предыдущий активный аватар
- P3-14: Staff не может аватарить другого staff или platform user
- P3-15: Avatar contextvars биндятся в `_load_user_from_request()` (dependencies.py), не в middleware — избегает Redis call на каждом запросе включая health checks. Middleware comment обновлён
- P3-16: `record_audit()` auto-fill: если `avatar_staff_id` в contextvars и caller не передал `performed_by` явно → `performed_by=staff_id`, `on_behalf_of=actor_id`. Существующий код не меняется
- P3-17: Defensive `try/except (ValueError, TypeError)` при UUID parse `avatar_staff_id` из contextvars

**Endpoints:**
```
POST /api/v1/staff/avatar/start   Body: {target_user_id} -> AvatarStartResponse  (200)
POST /api/v1/staff/avatar/end     -> 204
GET  /api/v1/staff/avatar/active  -> AvatarSessionResponse | null                (200)
```

**Результат:**
```
backend/app/modules/staff/
├── avatar_schemas.py    -- AvatarStartRequest, AvatarStartResponse, AvatarSessionResponse
├── avatar_service.py    -- start_avatar, end_avatar, get_active_avatar
└── avatar_router.py     -- 3 endpoints

backend/tests/
└── test_avatar.py       -- 10 tests
```

**Критерий готовности:** Staff входит под юзером. `avatar_session_id` присутствует в каждом structlog-сообщении в режиме аватара. Audit auto-fill работает. Avatar guard блокирует `sign_document`. 81 тест зелёный.

---

### ✅ Sprint 3.3: Admin endpoints

**Цель:** Базовые admin-функции для управления пользователями.

**Задачи:**
- [x] `app/modules/staff/admin_schemas.py` — `UserListItem`, `UserListResponse`, `UserDetailResponse`, `DashboardStatsResponse`, `KYCQueueItem`, `BlockRequest`
- [x] `app/modules/staff/admin_service.py` — `list_users()`, `get_user_detail()`, `block_user()`, `dashboard_stats()`, `kyc_queue()`, `kyc_approve()`, `kyc_reject()`
- [x] `app/modules/staff/admin_router.py`:
  - `GET /api/v1/staff/dashboard/stats` — статистика платформы (any staff)
  - `GET /api/v1/staff/kyc/queue` — очередь KYC (kyc_approve perm)
  - `POST /api/v1/staff/kyc/{id}/approve` — одобрить KYC (kyc_approve perm)
  - `POST /api/v1/staff/kyc/{id}/reject` — отклонить KYC (kyc_approve perm, body: `KYCRejectRequest {reason?: str}`)
- [x] `app/modules/staff/router.py` (расширен):
  - `GET /api/v1/staff/users` — унифицированный список юзеров (?role=, ?page=, ?per_page=)
  - `GET /api/v1/staff/users/{id}` — детали юзера
  - `PATCH /api/v1/staff/users/{id}/block` — блокировка (user_block perm)
- [x] `tests/test_staff_admin.py` — 12 тестов
- [x] `tests/test_staff.py` — обновлён (`test_list_staff` → `test_list_users`, paginated response)

**Решения реализации:**
- P3-18: Унифицированный `GET /staff/users` с `?role=` filter заменяет отдельный staff-only list. Один endpoint, один ресурс. Ответ `UserListItem` с `staff_profile: StaffProfileResponse | null`
- P3-19: Пагинация: `{items, total, page, per_page}`. `per_page` capped at 100. Staff profiles загружаются одним `IN` query для текущей страницы — нет N+1
- P3-20: Block только non-staff юзеров. Staff trusted. `is_active=false` + `delete_all_sessions()` — немедленный эффект
- P3-21: KYC approve/reject делегирует в существующий `process_webhook()` + добавляет staff-specific audit (`kyc.approved_by_staff` / `kyc.rejected_by_staff` с `actor_id=staff.id`). Два audit-записи: system (status change) + staff (кто именно одобрил)
- P3-22: Dashboard stats: 4 COUNT queries (total_users, by_role, pending_kyc, active_avatars). Platform user исключён из всех списков
- P3-23: `list_staff()` удалён из `service.py` (перенесён в `admin_service.py` как `list_users()`)
- P3-24: Platform user скрыт: не появляется в списках, detail возвращает 404

**Endpoints:**
```
GET   /api/v1/staff/users                  -> UserListResponse  (200)
GET   /api/v1/staff/users/{id}             -> UserDetailResponse  (200)
PATCH /api/v1/staff/users/{id}/block       -> 204
GET   /api/v1/staff/dashboard/stats        -> DashboardStatsResponse  (200)
GET   /api/v1/staff/kyc/queue              -> list[KYCQueueItem]  (200)
POST  /api/v1/staff/kyc/{id}/approve       -> 204
POST  /api/v1/staff/kyc/{id}/reject        -> 204 (body: {reason?})
```

**Результат:**
```
backend/app/modules/staff/
├── admin_schemas.py     -- UserListItem, UserListResponse, UserDetailResponse, DashboardStatsResponse, KYCQueueItem, BlockRequest, KYCRejectRequest
├── admin_service.py     -- list_users, get_user_detail, block_user, dashboard_stats, kyc_queue/approve/reject
└── admin_router.py      -- dashboard_router + kyc_admin_router (4 endpoints)

backend/tests/
├── test_staff.py        -- 8 tests (updated: paginated response)
└── test_staff_admin.py  -- 12 tests
```

**Критерий готовности:** Staff видит и управляет пользователями. Platform user не появляется в списках. KYC одобряется/отклоняется с audit trail. 93 теста зелёные.

---

**Phase 3 завершена.** 11 endpoints (3 staff users + 3 avatar + 5 admin/KYC/dashboard), 30 тестов Phase 3 (+63 Phase 0-2 = 93 total), 0 миграций (таблицы из Phase 0, итого 4).

**Новые audit events:**
- `staff.created` — промоция юзера в staff
- `staff.permissions_updated` — изменение прав
- `staff.avatar_started` — начало аватар-сессии
- `staff.avatar_ended` — завершение аватар-сессии
- `user.blocked` — блокировка юзера staff'ом
- `kyc.approved_by_staff` — ручное одобрение KYC
- `kyc.rejected_by_staff` — ручное отклонение KYC

**Обновлённые core-файлы:**
- `core/constants.py` — удалены дубли staff permissions (single source в `staff/constants.py`)
- `core/audit.py` — avatar auto-fill `performed_by`/`on_behalf_of` из contextvars + defensive UUID parse
- `core/middleware.py` — обновлён комментарий: avatar binding в dependencies, не middleware
- `auth/dependencies.py` — `_get_verified_staff()`, `require_staff_permission()`, avatar contextvars binding в `_load_user_from_request()`
- `documents/router.py` — `@require_not_avatar("sign_document")` на sign endpoint
- `main.py` — `+staff_users_router`, `+avatar_router`, `+dashboard_router`, `+kyc_admin_router`
- `tests/helpers.py` — `+create_admin_user()`, StaffProfile в `create_staff_user()`, AvatarSession cleanup

---

## PHASE 4: Companies + Products

---

### ✅ Sprint 4.1: Companies

**Цель:** Профили компаний с медиа-материалами и дорожной картой.

**Задачи:**
- [x] `app/modules/companies/models.py` — `CompanyProfile`, `CompanyPriceHistory`, `CompanyRoadmapItem`
- [x] `app/modules/companies/constants.py` — `CompanyStatus`, `RoadmapItemStatus`, `VALID_COMPANY_STATUS_TRANSITIONS`, `validate_distribution_config()`
- [x] `app/modules/companies/schemas.py` — 6 request + 7 response schemas (PublicCompanyResponse без distribution_config)
- [x] `app/modules/companies/service.py` — CRUD + `update_price()` (каскадное обновление Product) + roadmap management
- [x] Staff endpoints (компания):
  - `POST /api/v1/staff/companies` — создать компанию (company_manage + financial_operations)
  - `PATCH /api/v1/staff/companies/{id}` — редактировать профиль и медиа (company_manage; + financial_operations если distribution_config в body)
  - `PATCH /api/v1/staff/companies/{id}/price` — изменить цену акции (company_manage + financial_operations)
- [x] Staff endpoints (дорожная карта):
  - `POST /api/v1/staff/companies/{id}/roadmap` — добавить этап (company_manage)
  - `PATCH /api/v1/staff/companies/{id}/roadmap/reorder` — изменить порядок (company_manage)
  - `PATCH /api/v1/staff/companies/{id}/roadmap/{item_id}` — редактировать этап (company_manage)
  - `DELETE /api/v1/staff/companies/{id}/roadmap/{item_id}` — soft-delete этап (company_manage)
- [x] Public endpoints:
  - `GET /api/v1/companies` — список активных компаний
  - `GET /api/v1/companies/{id}` — детали компании с дорожной картой
- [x] `tests/test_companies.py` — 10 тестов

**Миграции:**
- [x] `0005_companies` — `company_profiles`, `company_price_history`, `company_roadmap_items` (3 таблицы, CHECK constraints)

**Решения реализации:**
- P4-01: Company = новый `User(role=company)` + `CompanyProfile`, создаётся админом. Не промоция из существующего юзера — компания создаётся целиком, креды передаются представителю
- P4-02: Новая permission `company_manage` в `staff/constants.py`. Двойная проверка: `company_manage` для всех операций, + `financial_operations` для create/price/distribution_config
- P4-03: Если `distribution_config` присутствует в body `PATCH /staff/companies/{id}`, роутер дополнительно проверяет `financial_operations`. Если только name/description/URLs — хватает `company_manage`
- P4-04: Soft-delete для roadmap items через `is_deleted: bool` (не status-based)
- P4-05: `PublicCompanyResponse` без `distribution_config`, `user_id`, `updated_at` — бизнес-чувствительные данные скрыты от публичного API
- P4-06: Route ordering: `/reorder` объявлен ПЕРЕД `/{item_id}` — предотвращает UUID parse conflict в FastAPI
- P4-07: `validate_distribution_config()` — `company_pct + sum(agent_levels) <= 1.0`, unknown keys rejected, все значения `0 < x < 1.0`
- P4-08: `CompanyPriceHistory` — иммутабельная запись, нет `updated_at`. Tracks `changed_by` (staff_id)
- P4-09: Reorder validation: exact set match + duplicate check. Все non-deleted items должны быть в списке

**Модели:**
```python
CompanyProfile:
    id, user_id  -- FK users.id (Company как User с role=company), UNIQUE
    name: String(500), description: String(5000) | None
    logo_url, cover_url, promo_video_url, presentation_url: String(2000) | None
    price_per_unit_cents: BigInteger
    distribution_config: JSONB
    -- {"company_pct": 0.65, "agent_levels": [0.10, 0.03, 0.01]}
    -- Инвариант: company_pct + SUM(agent_levels) <= 1.0
    status: String(20)  -- CHECK: active | hidden | archived
    created_at, updated_at

CompanyPriceHistory:  -- иммутабельная, нет updated_at
    id, company_id  -- FK company_profiles.id
    price_per_unit_cents: BigInteger
    changed_at: DateTime(tz), changed_by: UUID  -- FK users.id (staff)

CompanyRoadmapItem:
    id, company_id  -- FK company_profiles.id
    title: String(500), description: String(5000) | None
    target_date: Date | None
    status: String(20)  -- CHECK: planned | in_progress | completed
    order: Integer
    is_deleted: Boolean  -- soft-delete
    created_at, updated_at
```

**Endpoints:**
```
-- Staff endpoints:
POST   /api/v1/staff/companies                             -> CompanyResponse      (201)
PATCH  /api/v1/staff/companies/{id}                        -> CompanyResponse      (200)
PATCH  /api/v1/staff/companies/{id}/price                  -> CompanyResponse      (200)
POST   /api/v1/staff/companies/{id}/roadmap                -> RoadmapItemResponse  (201)
PATCH  /api/v1/staff/companies/{id}/roadmap/reorder        -> list[RoadmapItemResponse]  (200)
PATCH  /api/v1/staff/companies/{id}/roadmap/{item_id}      -> RoadmapItemResponse  (200)
DELETE /api/v1/staff/companies/{id}/roadmap/{item_id}      -> 204

-- Public endpoints:
GET    /api/v1/companies                                   -> PublicCompanyListResponse   (200)
GET    /api/v1/companies/{id}                              -> PublicCompanyDetailResponse (200)
```

**Матрица permissions:**
```
company_manage                              -> profile/media update, roadmap CRUD
company_manage + financial_operations       -> create company, price change, distribution_config update
```

**Результат:**
```
backend/app/modules/companies/
├── __init__.py
├── constants.py        -- CompanyStatus, RoadmapItemStatus, validate_distribution_config()
├── models.py           -- CompanyProfile, CompanyPriceHistory, CompanyRoadmapItem
├── schemas.py          -- 6 request + 7 response (Public* variants)
├── service.py          -- CRUD + update_price() + roadmap management
├── staff_router.py     -- 7 staff endpoints
└── router.py           -- 2 public endpoints

backend/tests/
└── test_companies.py   -- 10 tests
```

**Критерий готовности:** Компании создаются с медиа-полями. Цена обновляется каскадно. `distribution_config` валидируется. Дорожная карта управляется Staff и отображается публично. 103 теста зелёные.

---

### ✅ Sprint 4.2: Products

**Цель:** Продукты компаний с произвольным числом планов рассрочки.

**Задачи:**
- [x] `app/modules/products/models.py` — `Product`, `ProductInstallment`
- [x] `app/modules/products/constants.py` — `ProductStatus`, `VALID_PRODUCT_STATUS_TRANSITIONS`, `validate_plan_config()`
- [x] `app/modules/products/schemas.py` — 5 request + 8 response schemas (Public* variants + sold_units)
- [x] `app/modules/products/service.py` — CRUD + `cascade_price()` + installment management
- [x] Staff endpoints:
  - `POST /api/v1/staff/products` — создать продукт (company_manage + financial_operations)
  - `PATCH /api/v1/staff/products/{id}` — редактировать (company_manage; + financial_operations если purchase_config в body)
  - `PATCH /api/v1/staff/products/{id}/status` — изменить статус (company_manage)
  - `POST /api/v1/staff/products/{id}/installments` — добавить план рассрочки (company_manage + financial_operations)
  - `PATCH /api/v1/staff/products/{id}/installments/{inst_id}` — редактировать план (company_manage + financial_operations)
  - `DELETE /api/v1/staff/products/{id}/installments/{inst_id}` — soft-delete план (company_manage + financial_operations)
- [x] Public endpoints (витрина):
  - `GET /api/v1/products` — список активных продуктов (+ optional `?company_id=` filter)
  - `GET /api/v1/products/{id}` — детали продукта с планами рассрочки
- [x] Social proof: ~~`sold_units: int = 0` заглушка~~ → реализован `get_sold_units_map()` в Sprint 6.1
- [x] Price cascade: `companies/service.py update_price()` → `products/service.py cascade_price()`
- [x] `tests/test_products.py` — 12 тестов

**Миграции:**
- [x] `0006_products` — `products`, `product_installments` (2 таблицы, CHECK constraints)

**Решения реализации:**
- P4-10: Price cascade = обновление `price_per_unit_cents` на active/hidden Products + soft-delete всех `ProductInstallment` шаблонов. Staff создаёт новые шаблоны по новой цене. Активные `InstallmentPlan` (Sprint 6.2) не затрагиваются — работают по снапшоту
- P4-11: `validate_plan_config()` — context-aware: принимает `product_units` и `price_per_unit_cents`. Инварианты: `len(tranches) >= 2`, `sum(amount_cents) == units * price`, `sum(units_percent) == 100`, `sum(units_percent[i] * product_units // 100) == product_units` (Sprint 6.2: units decomposition check), `bonus_units >= 0`, `agent_bonus_units >= 0`. Unknown keys rejected
- P4-12: `Product.units` иммутабелен после создания — нет в `UpdateProductRequest`
- P4-13: `Product.price_per_unit_cents` копируется из Company при создании, обновляется только через cascade. Прямое редактирование запрещено
- P4-14: `ProductInstallment` без `updated_at` (по ТЗ). plan_config изменяется через `set_jsonb()`. Soft-delete через `is_deleted: bool`
- P4-15: `cascade_price()` использует bulk `update()` с явным `updated_at=datetime.now(UTC)` — ORM `onupdate` не срабатывает на bulk operations
- P4-16: Lazy import `from app.modules.products.service import cascade_price` в `companies/service.py` — избегает circular import
- P4-17: `purchase_config` в body `PATCH /staff/products/{id}` триггерит дополнительную проверку `financial_operations` (аналогично distribution_config в Sprint 4.1)
- P4-18: ~~`sold_units: int = 0` — заглушка в `PublicProductResponse`. Реальный подсчёт из purchases — Sprint 6.1 с Redis кэшем (`SOCIAL_PROOF_CACHE_TTL`)~~ → Sprint 6.1: реализован прямой COUNT из purchases. Redis кэш — при необходимости (TD-031 закрыт)

**Модели:**
```python
Product:
    id, company_id  -- FK company_profiles.id
    name: String(500), description: String(5000) | None
    units: Integer  -- immutable after creation
    purchase_config: JSONB | None  -- nullable, fallback to Company.distribution_config (Sprint 6.1)
    price_per_unit_cents: BigInteger  -- denormalized from Company, cascade-updated
    status: String(20)  -- CHECK: active | hidden | archived
    created_at, updated_at

ProductInstallment:  -- no updated_at per ТЗ
    id, product_id  -- FK products.id
    name: String(500)
    plan_config: JSONB
    is_deleted: Boolean  -- soft-delete on price cascade
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

**Валидация `plan_config` (Sprint 4.2 — `validate_plan_config()`):**
```python
assert len(tranches) >= 2
assert all(t["amount_cents"] > 0 for t in tranches)
assert all(t["units_percent"] > 0 for t in tranches)
assert sum(t["amount_cents"] for t in tranches) == product.units * company.price_per_unit_cents
assert sum(t["units_percent"] for t in tranches) == 100
assert bonus_units >= 0
assert agent_bonus_units >= 0
```

**Endpoints:**
```
-- Staff endpoints:
POST   /api/v1/staff/products                                   -> ProductResponse      (201)
PATCH  /api/v1/staff/products/{id}                               -> ProductResponse      (200)
PATCH  /api/v1/staff/products/{id}/status                        -> ProductResponse      (200)
POST   /api/v1/staff/products/{id}/installments                  -> InstallmentResponse  (201)
PATCH  /api/v1/staff/products/{id}/installments/{inst_id}        -> InstallmentResponse  (200)
DELETE /api/v1/staff/products/{id}/installments/{inst_id}        -> 204

-- Public endpoints:
GET    /api/v1/products                                          -> PublicProductListResponse   (200)
GET    /api/v1/products/{id}                                     -> PublicProductDetailResponse (200)
```

**Матрица permissions:**
```
company_manage                              -> update name/description, status change
company_manage + financial_operations       -> create product, update purchase_config, installment CRUD
```

**Результат:**
```
backend/app/modules/products/
├── __init__.py
├── constants.py        -- ProductStatus, validate_plan_config()
├── models.py           -- Product, ProductInstallment
├── schemas.py          -- 5 request + 8 response (Public* + sold_units)
├── service.py          -- CRUD + cascade_price() + installment management
├── staff_router.py     -- 6 staff endpoints
└── router.py           -- 2 public endpoints

backend/tests/
└── test_products.py    -- 12 tests
```

**Критерий готовности:** Витрина работает. Один продукт может иметь произвольное число планов рассрочки. `plan_config` валидируется при сохранении. Price cascade обновляет продукты и soft-delete'ит installment-шаблоны. 115 тестов зелёные.

---

### ✅ Sprint 4.3: Share Pool & Product Inventory Refactor

**Цель:** Исправить архитектурную ошибку в модели акций. До рефакторинга `Product.units` трактовалось одновременно как «размер пакета» и как «доступный инвентарь», а `sold_units` считался COUNT(Purchase), не SUM. Это противоречило бизнес-реальности: компания выпускает фиксированный пул акций, продукты — лишь правила деноминации этого пула на пакеты разного размера.

**Реализованная модель:**
- `CompanyProfile.total_supply` — эмиссия, фиксированное число акций.
- `CompanyProfile.shares_per_option` — целочисленное соотношение «акций в опционе».
- `OptionPool` — отдельная модель: company_id (FK), equity_percent (Numeric(7,4)), total_options (int), status (active|drained). Partial unique index `uq_one_active_pool_per_company` на `WHERE status='active'`.
- `Product.pool_id` — FK на OptionPool.
- `Product.units` → `Product.package_size` (rename, semantics — размер одного пакета в опционах).
- `available_packages` для продукта вычисляется динамически: `floor((pool.total_options − SUM(active Purchase.units of pool's company including gifts)) / package_size)`.
- `execute_purchase()` валидирует `pool_remaining >= product.package_size` перед списанием.
- Gift overflow: при недостатке пула gift-units «протекают» в owner supply (отрицательный pool_remaining допустим, спецификация §3.7).

**Детальная спецификация, миграция, диффы кода и тестов, acceptance criteria:** `CBSHOME-Share-Pool-Refactor.md` (v2.4).

**Реализация — батчи:**
- B0 (миграция 0027 + модели) — deployed
- B1 (schemas + services + rename + pool wiring) — deployed
- B2 (pool router + main.py + 7 test fixtures) — deployed
- B2.1 (test_posts.py hotfix) — deployed
- B3 (test_pools.py — 11 новых тестов: pool capacity, gift consumption, sold-out path, gift overflow, installment preview invariants) — deployed
- B4 (Installment Calculator + `POST /staff/products/{id}/installments/preview` + 2 теста calculator) — deployed
- B5 (Company Dashboard module: `GET /company/dashboard` + `GET /company/analytics` + 8 тестов) — deployed
- B5-pragmatic: `BalanceResponse` shared между dashboard/company_dashboard (был name-mangled дубль в auto-generated TS типах) — deployed
- B6 (seed_storefront update + новый `seed_test_accounts.py` для test fixtures) — deployed
- B7 — пересмотрен и расширен в отдельный мини-спринт **VELO Migration**, перенесён в Sprint 4.4
- B8 (TS types pipeline + `cbshome-bot` auto-commit) — deployed

**Результат:** 360/360 тестов зелёные, OpenAPI types в sync с бэком, dashboard для company UI работает.

**Sprint 4.3 закрыт.**

---

### ✅ Sprint 4.4: Pack Pricing UX + VELO Migration + Code Review Hardening

**Цель:** Финализировать B7 (frontend) после VELO Migration; точечная UX-полировка цены (pack-pricing двухуровневый); закрыть найденные code-review замечания по архитектуре pool-модуля.

**Что сделано:**

**VELO Migration (frontend types pipeline).**
- `frontend/src/api/types.ts` сжат с 939 строк handwritten union'ов до тонкого re-export слоя над `generated.ts`. Single source of truth = backend OpenAPI → `generated.ts`.
- 24 типа с drift'ом (handwritten vs generated) ликвидированы.
- 8 коммитов миграции, frontend backwards-compat сохранён через aliasing.

**B7 — Pack Pricing UX hardening.**
- `PublicProductResponse` получил поле `price_per_pack_cents: int` (computed в роутере как `package_size * price_per_unit_cents`).
- `PublicProductResponse.available_packages` переведён в required (без `= 0` дефолта). Missing populate = server bug, не soft fallback.
- ProductCard.vue, ProductDetailView.vue, PurchaseView.vue — двухуровневый price block: пакет primary (крупный, жирный), per-unit reference secondary (мелкий, тёмно-серый).
- en.json: `+inv.pack`, `+inv.pricePerPack` (×2 контекста), `−inv.priceLabel`, `−inv.pricePerUnit`.
- 2 новых теста в `tests/test_products_pack_pricing.py` — round-trip `price_per_pack_cents` через list + detail endpoints.

**Schema cleanup.**
- `PublicProductResponse.company_name` — `str = ""` → `str` (required). Empty-string дефолт был placeholder для контракта, который не должен легитимно его выдавать. Missing company = 500, не «render с пустой строкой».
- `PublicProductDetailResponse.installments` — `list[...] = []` → required. Backend всегда возвращает массив (возможно пустой). Дефолт делал поле optional в OpenAPI → требовал `?? []` на фронте в трёх call-sites. Required + явный `installments=[...]` в роутере убрали компенсацию.
- `products/router.py` (public) — ORM mutation antipattern заменён на explicit constructor.

  Pre-review pattern (rejected):
  ```python
  p.available_packages = available_map.get(p.id, 0)   # mutate ORM row
  resp = PublicProductResponse.model_validate(p)      # validate
  resp.company_name = company.name                    # mutate response
  ```
  Two issues: (1) ORM-row dirty-state на read-only сессии safe, но brittle; (2) post-validate assignment обходит Pydantic для post-hoc полей.

  Post-review pattern (этот файл):
  ```python
  PublicProductResponse(
      id=..., name=..., available_packages=..., company_name=..., ...
  )
  ```
  Все поля keyword-args в конструктор. No ORM mutation, no post-validate assignment. Trade-off: новое поле в схеме требует обновления каждого call-site → TypeError при старте. Намеренно громкий сбой против тихого fallback.

**Pool architecture hardening (post-review).**
- `POOL_STATUS_ACTIVE` извлечён в `backend/app/modules/pools/constants.py`. Тройной локальный дубль `_POOL_STATUS_ACTIVE` (pools/service, purchases/service, company_dashboard/service) ликвидирован.
- `_get_active_pool` / `_get_pool_remaining` — приватные копии в `purchases/service.py` удалены. Модуль теперь импортирует публичные `get_active_pool` / `get_pool_remaining` из `pools/service.py`. Комментарий «no upward dependency» снят как устаревший: `products/service.py` уже импортирует из pools, микросервисная нарезка не запланирована.
- `update_pool()` возвращает `tuple[OptionPool, int]` — `consumed` уже вычислялся для `new_total < consumed` guard, теперь повторно используется в роутере. Double SELECT на PATCH /pool устранён.
- `with_consumed_remaining()` — `consumed: int` обязательный аргумент. Helper стал чистой трансформацией без implicit SELECT. Параметр `_session` сохранён в сигнатуре с underscore-префиксом (Python convention для intentionally unused) для forward-compat.
- `_compute_equity_percent()` — guard на `total_supply <= 0` (`ValueError` с явным сообщением вместо `decimal.DivisionByZero`).
- `PoolResponseDict` алиас удалён — `with_consumed_remaining()` декларирует возврат как `dict[str, Any]` напрямую.
- `+ public get_pool_remaining(pool, session)` в `pools/service.py` — encapsulation `total - consumed` для переиспользования.

**Sprint 4.4 follow-up (второй раунд ревью).**
- **Регресс fix:** `sessionStorage.removeItem('cbs_referral_code')` восстановлен в обоих flow `auth.ts` (email register + telegram login). При rewrite строки были потеряны → риск дублирования агентских комиссий при повторной регистрации в той же сессии.
- **Type narrowing:** `UserRole` / `KycStatus` runtime guards с compile-time exhaustiveness assertions (паттерн `as const satisfies readonly UserRole[]` + assert на полное покрытие union'а). `auth.ts` экспонирует `role: UserRole | null` + `kycStatus: KycStatus | null`. `InvestorSettingsView.vue` использует typed compares.
- **Style:** `del session` antipattern → `_session` префикс в `with_consumed_remaining()`.

**Cleanup коммит (`b539ee8`).**
- `ProductDetailResponse` (staff variant detail-with-installments) удалён — ноль call-sites в коде. Импорт в `products/staff_router.py` тоже удалён. Решение лучше дропа класса, чем фикс дефолта `installments = []` на мёртвом коде. Если staff `GET /staff/products/{id}` детальный эндпоинт понадобится — response model пишется с нуля под тот же явный-конструктор паттерн.

**Файлы изменённые (Sprint 4.4):**
- `backend/app/modules/pools/constants.py` — **новый**: `POOL_STATUS_ACTIVE`
- `backend/app/modules/pools/service.py` — refactor (импорт constants, tuple-return, get_pool_remaining, _compute_equity_percent guard, alias drop)
- `backend/app/modules/pools/router.py` — unpack tuple, pass consumed explicitly
- `backend/app/modules/purchases/service.py` — drop dead copies, import from pools
- `backend/app/modules/company_dashboard/service.py` — import POOL_STATUS_ACTIVE, drop local
- `backend/app/modules/products/schemas.py` — required fields (company_name, installments), drop ProductDetailResponse, +Sprint 4.4 follow-up note
- `backend/app/modules/products/router.py` — explicit Pydantic constructors
- `backend/app/modules/products/staff_router.py` — drop dead imports
- `backend/tests/test_products_pack_pricing.py` — **новый**: 2 теста на price_per_pack_cents
- (frontend) `src/api/types.ts`, `src/stores/auth.ts`, `src/views/investor/{InvestorSettingsView,ProductDetailView,InstallmentView,PurchaseView}.vue`, `src/components/shared/ProductCard.vue`, `src/i18n/locales/en.json`

**Тесты:** 362/362 зелёные. VPS deploy log: `d9071ef → b539ee8`, `Generated 116 types`, `Types are in sync, no commit needed`.

**Score ревьюера:** 9.5/10. Единственный незакрытый пункт — TD-066 (legal stubs, **не код-блокер**, ждёт юр-текст).

**Sprint 4.4 закрыт. Refactor TD-071 closed.**

---

### ✅ Sprint 4.5: GET /companies/me

**Цель:** Дать роли `company` канонический путь к собственному полному профилю. Без этого Phase F5 (Company UI) не может ни взять `company_id` для фильтрации продуктов, ни прочитать `distribution_config` для секции Settings.

**Проблема:**
Публичный `GET /api/v1/companies/{id}` (Sprint 4.1) эмитит `PublicCompanyDetailResponse` — без `distribution_config`, без `user_id`, без `updated_at` — и возвращает 404 на non-active статусах. Для company-itself caller'а это неверно: hidden / archived компания должна видеть свой профиль. Staff-side `GET /api/v1/staff/companies/{id}` (Sprint 4.1) подходит по схеме (`CompanyResponse` с `distribution_config`), но требует staff-permission'а — недоступно company-роли.

**Решение:**
Новый endpoint `GET /api/v1/companies/me`, переиспользующий existing dependency `companies/dependencies.py:get_current_company_profile()` (тот же gate что у `/company/dashboard` и `/company/analytics`) и existing schema `CompanyResponse` (staff-side полный профиль). Без новых сервисных функций — endpoint целиком в роутере.

**Что сделано:**
- `backend/app/modules/companies/router.py` — `+GET /me` перед `GET /{company_id}` (route ordering: `/me` должен быть раньше, иначе FastAPI парсит `me` как UUID и падает на 422). Использует `Depends(get_current_company_profile)` → `CompanyResponse.model_validate(profile)`. No service-layer changes.
- `backend/tests/test_companies_me.py` — **новый**: 3 теста (success / forbidden для non-company / unauthorized без токена). EMAIL_PREFIX=`s45_`.

**Endpoints:**
```
GET /api/v1/companies/me  -> CompanyResponse  (auth: company role only)
```

**Ошибки:**
- `401` — нет / невалидный Bearer token
- `403` — auth есть, но `User` не привязан к `CompanyProfile` (investor / agent / staff / platform)

**Сегментация:**
Тот же error contract что у `/company/dashboard` и `/company/analytics`. Frontend получает один canonical путь и одинаковую error UX для всех company-side endpoints.

**Файлы изменённые:**
- `backend/app/modules/companies/router.py` — `+GET /me` route
- `backend/tests/test_companies_me.py` — **новый**, 3 теста

**Тесты:** 365/365 зелёные. VPS deploy log: `b539ee8 → b9d1fee`.

**Sprint 4.5 закрыт.**

---

### ✅ Sprint 4.6: Portfolio + Company Dashboard installment hotfix

**Цель:** Хотфикс продакшен-бага в агрегации портфолио и аналитики. Investor оплативший installment plan видел свои купленные units как «gifted», avg_price = $0.00, при ненулевом invested. Та же логическая ошибка — на стороне компании в `total_options_sold`.

**Симптом (production):**
Investor `cd5db920-6c55-4bd5-aa24-95e7f8024df3` viewing Immo-Pro-Invest GmbH:
- `total_units = 1250`, `total_paid_cents = 118750` ($1187.50)
- `sale_units = 0`, `gift_units = 1250` ❌
- `avg_price_cents = 0` ❌

Self-contradictory: $1187.50 invested, но каждый unit «gifted».

**Root cause:**
Sprint 9.2 (Portfolio) использует `case((Purchase.legal_basis == SALE, units))` для `sale_units` и **`case((Purchase.legal_basis != SALE, units))` для `gift_units`**. Это работало корректно когда было только два basis'а — `SALE` и `GIFT`. Sprint 6.2 (Installment) добавил `INSTALLMENT_TRANCHE`, но aggregate'ы в `portfolio/service.py` не обновили — `installment_tranche` тихо проваливается в `gift_units` через `!= SALE` else-branch.

Та же ошибка реплицирована в `company_dashboard/service.py:_options_sold_sum()` и в `options_aggregate` внутри `sales_by_product` — компания видит revenue растущим (paid_cents всегда суммируется), но `total_options_sold` остаётся 0 при installment-продажах.

**Решение (option A, согласовано):**
Семантика "paid acquisition = sale + installment_tranche". Покупка в рассрочку — коммерческая продажа, юридически и семантически тождественна instant purchase. Объединяем оба в `_PAID_LEGAL_BASES` константу и используем `.in_()` для match'а. `gift_units` теперь явно `== GIFT` (не через `!= SALE`).

Schema полей не меняется (`sale_units` / `gift_units` / `total_options_sold` / `options_sold` остались) — только математика за ними. Frontend type contract held, никаких миграций данных не нужно (агрегаты live-вычисляются по запросу).

**Что сделано:**

**`portfolio/service.py`:**
- `_PAID_LEGAL_BASES = (SALE, INSTALLMENT_TRANCHE)` константа модуля.
- `_sale_units_expr()` / `_gift_units_expr()` — DRY helper'ы, переиспользуются в обоих aggregate'ах (`get_portfolio` + `get_company_position`).
- `sale_units` теперь matches `legal_basis.in_(_PAID_LEGAL_BASES)`.
- `gift_units` теперь matches **explicitly** `legal_basis == GIFT` (никаких `!= SALE`).
- `_compute_avg_price()` — параметр переименован `sale_units` → `paid_units`. Формула `total_paid / paid_units` с тем же `<= 0` guard.
- Module docstring + Sprint 4.6 hotfix секция.

**`company_dashboard/service.py`:**
- `_options_sold_sum()` теперь `legal_basis.in_(_PAID_LEGAL_BASES)`.
- `options_aggregate` в `sales_by_product` — то же самое.
- Sprint 4.6 hotfix комментарии в module docstring и над expressions.

**`tests/test_portfolio_installment.py` (NEW):**
- EMAIL_PREFIX=`s46_`, 3 регрессионных теста.
- `test_portfolio_me_installment_tranche_counts_as_sale` — investor создаёт installment plan (UX-01 платит tranche #1 inline), `GET /portfolio/me` показывает `sale_units > 0`, `gift_units == 0`, `avg_price > 0`.
- `test_portfolio_company_detail_installment_tranche_counts_as_sale` — то же на `/portfolio/me/company/{id}` (separate aggregation query).
- `test_company_dashboard_counts_installment_in_options_sold` — компания видит installment как продажу: `total_options_sold > 0`, `sales_by_product[i].options_sold > 0`.

Все 3 теста используют `create_plan()` напрямую на service layer (UX-01 платит inline) — реалистичный path что воспроизводит production-баг.

**Файлы изменённые:**
- `backend/app/modules/portfolio/service.py` — `_PAID_LEGAL_BASES`, helper expressions, fixed aggregations, updated docstring + `_compute_avg_price` param rename
- `backend/app/modules/company_dashboard/service.py` — `_PAID_LEGAL_BASES`, fixed `_options_sold_sum` + `options_aggregate`, updated docstring
- `backend/tests/test_portfolio_installment.py` — **новый**, 3 регрессионных теста

**Тесты:** 368/368 зелёные (365 + 3 новых). VPS deploy log: `b9d1fee → 75168f0`. Production verified: investor `cd5db920...` portfolio теперь показывает `sale_units=1250, gift_units=0, avg_price=$0.95, invested=$1187.50` — арифметика согласована.

**Sprint 4.6 закрыт.**

---

### ✅ Sprint 4.5 prep (frontend wiring)

**Цель:** Подвести фронт под Sprint 4.5 endpoint и Phase F5 типы — без этого F5 development блокирован на отсутствующих type re-exports и API wrappers.

**Что сделано:**
- `frontend/src/api/companies.ts` — `+getMyCompany(): Promise<CompanyResponse>` для `GET /api/v1/companies/me`. Existing `listCompanies` / `getCompany` без изменений.
- `frontend/src/api/types.ts` — новая секция `Phase F5 -- Company UI` (между F4.1 и F4.2 блоками). Re-export'ит из `generated.ts`: `CompanyResponse`, `CompanyDashboardResponse`, `CompanyAnalyticsResponse`, `PoolEmbedResponse`, `CompanyTransactionResponse`, `SalesByMonthEntry`, `SalesByProductEntry`. Phase F5 компоненты теперь импортируют из `@/api/types`, не из `@/api/generated` напрямую.

**Файлы изменённые:**
- `frontend/src/api/companies.ts` — `+getMyCompany()` wrapper
- `frontend/src/api/types.ts` — `+Phase F5` re-export секция

**Тесты:** Frontend-only diff, бэкенд тесты 368/368 зелёные. VPS deploy log: `75168f0 → 0f11197`. `vue-tsc` прошёл, `Generated 116 types -> /opt/cbshome/repo/frontend/src/api/generated.ts`, `✓ Types are in sync, no commit needed`.

**Sprint 4.5 prep закрыт.**

---

**Phase 4 завершена.** 17 endpoints (7 staff companies + 2 public companies + 6 staff products + 2 public products), 22 теста Phase 4 (+93 Phase 0-3 = 115 total), 2 миграции (итого 6).

**Новые audit events:**
- `company.created` — создание компании
- `company.updated` — обновление профиля
- `company.price_updated` — изменение цены (+ products_updated count)
- `company.roadmap_item_created` — создание roadmap item
- `company.roadmap_item_updated` — обновление roadmap item
- `company.roadmap_item_deleted` — soft-delete roadmap item
- `company.roadmap_reordered` — изменение порядка
- `product.created` — создание продукта
- `product.updated` — обновление продукта
- `product.status_changed` — изменение статуса
- `product.installment_created` — создание installment template
- `product.installment_updated` — обновление installment template
- `product.installment_deleted` — soft-delete installment template

**Обновлённые файлы (Phase 4):**
- `staff/constants.py` — `+company_manage: True` в DEFAULT_STAFF_PERMISSIONS
- `staff/schemas.py` — `+company_manage: bool | None` в UpdatePermissionsRequest
- `main.py` — `+companies_router`, `+staff_companies_router`, `+products_router`, `+staff_products_router`
- `migrations/env.py` — раскомментированы импорты CompanyProfile, CompanyPriceHistory, CompanyRoadmapItem, Product, ProductInstallment
- `tests/helpers.py` — cleanup для company + product таблиц в `_cleanup_user_related_data()`

**Фиксы code review (Phase 4):**
- CR-P4-01: Публичные detail endpoints (`GET /companies/{id}`, `GET /products/{id}`) возвращали hidden/archived сущности по UUID → добавлена проверка `status != ACTIVE → NotFoundError` в роутерах (не в сервисах — staff endpoints не затронуты)
- CR-P4-02: `CreateCompanyRequest.email` — `str` → `EmailStr` (TD-030 закрыт)
- CR-P4-03: `CompanyStatus`, `RoadmapItemStatus` дублировались в `constants.py` и `models.py` → canonical source в `constants.py`, `models.py` импортирует (TD-029 закрыт). Аналогично `ProductStatus`
- CR-P4-04: `_require_financial_operations()` дублировалась в `companies/staff_router.py` и `products/staff_router.py` → вынесена в `staff/permissions.py` (`require_permission()`, `require_financial_operations()`)

**Файлы изменённые/созданные (code review Phase 4):**
- `staff/permissions.py` — **новый**: `require_permission()`, `require_financial_operations()`
- `companies/models.py` — энумы импортируются из `constants.py`
- `companies/schemas.py` — `email: EmailStr`
- `companies/router.py` — `+status check` в detail endpoint
- `companies/staff_router.py` — `_require_*` → `from staff.permissions import`
- `products/models.py` — `ProductStatus` импортируется из `constants.py`
- `products/router.py` — `+status check` в detail endpoint
- `products/staff_router.py` — `_require_*` → `from staff.permissions import`
- `tests/test_companies.py` — `test_delete_roadmap_item` активирует компанию перед публичной проверкой

---

## PHASE 5: Payments: Ledgers + Crypto

---

### ✅ Sprint 5.1: Ledger Service

**Цель:** Сервис работы с леджерами. Основа всей финансовой системы.

**Задачи:**
- [x] `app/modules/ledgers/service.py`:
  - `record_active_ledger()` — запись в active_ledger
  - `record_passive_ledger()` — запись в passive_ledger
  - `get_active_balance()` — confirmed + frozen отдельно
  - `get_passive_balance()` — confirmed + frozen отдельно
- [x] `app/modules/ledgers/validators.py` — `validate_route()` (Active -> Passive запрещено)
- [x] `tests/test_ledgers.py` — 17 тестов (включая AML-матрицу, status validation)

**Миграции:** не требуются — таблицы и CHECK-constraints из Phase 0.

**Решения реализации:**
- P5-01: `validate_route()` — **standalone** функция, НЕ вызывается внутри `record_*()`. Вызывается orchestrator-слоем (transfer service, Phase 6+). Purchase saga НЕ вызывает `validate_route()` — это контролируемая системная операция
- P5-02: `record_*()` — pure write, без AML-логики. Принимают `status: str`, но валидируют через `_validate_status()` с `_WRITABLE_STATUSES = frozenset({frozen, confirmed})`. Запись `reversed` напрямую запрещена — только через reversal process (Sprint 5.3)
- P5-03: `_VALID_LEDGER_TYPES = frozenset({"active", "passive"})` — whitelist в `validate_route()`. Неизвестные типы → `ValueError`
- P5-04: Balance queries: conditional SUM с CASE в одном запросе, `reversed` исключаются, `func.coalesce(..., 0)` для пустых результатов
- P5-05: `amount_cents=0` допустим — gift-записи используют нулевые суммы (семафор COUNT работает без исключений). Валидация amount — ответственность caller'а (processor)
- P5-06: Cleanup в `tests/helpers.py` расширен: `ActiveLedger` + `PassiveLedger` удаляются перед удалением пользователей (FK RESTRICT)

**Результат:**
```
backend/app/modules/ledgers/
├── __init__.py
├── models.py           -- ActiveLedger, PassiveLedger, LedgerStatus (Phase 0)
├── validators.py       -- validate_route() (standalone AML check)
└── service.py          -- record_active/passive_ledger, get_active/passive_balance

backend/tests/
└── test_ledgers.py     -- 17 tests
```

**Критерий готовности:** Ledger service работает. AML-матрица проверяется standalone. Status validation не пропускает невалидные значения. 132 теста зелёные.

---

### ✅ Sprint 5.2: Payment Module (закрытый модуль)

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
    amount_cents: int      -- BigInteger, в USD cents
    currency: str          -- String(10), default "USD"
    payment_type: enum     -- crypto | bank
    provider: str          -- String(100): "crypto_usdt_trc20", etc.
    status: enum           -- created | frozen | confirmed | reversed | failed
    expires_at: datetime   -- nullable, created -> failed если не оплачен
    frozen_until: datetime -- nullable, заполняется при created -> frozen
    provider_data: JSONB   -- схема зависит от payment_type (валидируется в сервисе)
    origin_payment_id: UUID -- FK payments.id, nullable (для reversal-цепочки)
    created_at: datetime
    updated_at: datetime

CryptoAddress:  -- внутренняя таблица модуля payments/
    id: UUID
    user_id: UUID   -- FK users.id
    network: str    -- TRC20 | ERC20 | BEP20 | PoS
    address: str    -- наш кошелёк для этого юзера и сети
    created_at: datetime
    -- UNIQUE (user_id, network)
```

**Задачи:**
- [x] `app/modules/payments/__init__.py`
- [x] `app/modules/payments/constants.py` — `PaymentType`, `PaymentStatus`, state machine transitions
- [x] `app/modules/payments/interface.py` — `PaymentServiceProtocol`, `DepositAddress` (frozen dataclass)
- [x] `app/modules/payments/models.py` — `Payment` (JSONBMixin), `CryptoAddress`
- [x] `app/modules/payments/schemas.py` — `CreateAddressRequest`, `DepositAddressResponse`, `PaymentResponse`, `PaymentHistoryResponse`, `CryptoWebhookRequest`
- [x] `app/modules/payments/service.py` — реализация protocol + webhook processing
- [x] `app/modules/payments/router.py`:
  - `POST /api/v1/payments/crypto-address` — получить/создать адрес (body: `{network}`)
  - `GET /api/v1/payments/history` — история платежей инвестора
- [x] `app/modules/payments/webhook_router.py`:
  - `POST /api/v1/payments/crypto/webhook` — blockchain webhook
- [x] Webhook: Payment `created -> frozen`, `provider_data` в конструкторе (single flush), запись в active_ledger
- [x] `frozen_until = now() + FREEZING_HOURS_CRYPTO`
- [x] `payment_confirmation_worker` — daemon skeleton (asyncio.Task в lifespan), полная логика в Sprint 5.3
- [x] `tests/test_crypto_deposits.py` — 10 тестов

**Миграции:**
- [x] `0007_payments` — таблицы `payments`, `crypto_addresses`, FK `origin_payment_id` на ledger-таблицах
- [x] `0008_payments_tx_hash_index` — partial unique index `uq_payments_tx_hash` на `provider_data->>'tx_hash'`

**Networks:** TRC20, ERC20, BEP20, PoS (из config)

**Config (новые настройки):**
```
crypto_webhook_secret: str = ""           -- required in production
confirmation_worker_interval_minutes: int = 5
```

**Решения реализации:**
- P5-07: Payment model расширена по CBSHOME-State-Machines.md: `+currency`, `+provider`, `+expires_at`, `+frozen_until`, `+origin_payment_id (FK payments.id)`. `payment_type` (не `method`) — избегает конфликта с HTTP-семантикой
- P5-08: `POST /api/v1/payments/crypto-address` (не GET) — endpoint создаёт ресурс, HTTP-семантика корректна. Body: `{"network": "TRC20"}`
- P5-09: Webhook auth — `hmac.compare_digest()` для timing-safe сравнения (SEC-1 fix). Shared secret из `CRYPTO_WEBHOOK_SECRET` config
- P5-10: tx_hash uniqueness — partial unique index на `(provider_data->>'tx_hash') WHERE NOT NULL`. Race condition обрабатывается через `begin_nested()` + `IntegrityError` catch на `uq_payments_tx_hash` (P-05)
- P5-11: `provider_data` заполняется в конструкторе Payment перед `session.add()` — один flush вместо двух. `set_jsonb()` не нужен для новых объектов
- P5-12: Daemon skeleton: пустой loop с `asyncio.sleep(interval)`. Proper `CancelledError` handling в shutdown. Ошибки не вызывают двойной sleep
- P5-13: `install_cbshome.sh` обновлён: генерация `CRYPTO_WEBHOOK_SECRET` в `.env`
- P5-14: Idempotent address creation через `begin_nested()` (P-05) на `uq_crypto_addresses_user_network`
- P5-15: Stub address generation: `CBS_{network}_{uuid4().hex[:16]}`. Реальная интеграция — Phase 2

**Попутные security-фиксы (применены в Sprint 5.2):**
- P5-SEC-1: `hmac.compare_digest()` для **обоих** webhook'ов (payments + KYC). KYC router обновлён
- P5-SEC-2: `process_webhook(user_id: str)` → `UUID` в `kyc/service.py`. Callers в `kyc/router.py` и `staff/admin_service.py` обновлены — убраны `str()` обёртки (CRIT-3)
- P5-SEC-3: Email auth rate limiting: `core/rate_limit.py` — ~~generic INCR+EXPIRE по IP~~ → атомарный Lua-скрипт (фикс code review). Применён к `POST /auth/email/register` и `/login`. Shared key `email_auth:{ip}` (SEC-5)
- P5-SEC-4: Failed login audit: `_audit_login_failure()` в `auth/service.py` — записывает в audit_log через **выделенную сессию** (основная rollback'ится при exception, P-01). Ошибки логируются через `logger.error()` (фикс code review). Записывается для wrong_password, platform_login_blocked, account_deactivated. User not found — только structlog (SEC-7)
- P5-SEC-5: `conftest.py` — autouse fixture `clear_rate_limit` + helpers `register_user`/`login_user` очищают rate limit key перед каждым вызовом (все тесты с 127.0.0.1)

**Endpoints:**
```
POST /api/v1/payments/crypto-address     -> DepositAddressResponse  (200)
GET  /api/v1/payments/history            -> PaymentHistoryResponse  (200)
POST /api/v1/payments/crypto/webhook     -> {"status": "ok", ...}   (200, X-Webhook-Secret)
```

**Результат:**
```
backend/app/modules/payments/
├── __init__.py
├── constants.py        -- PaymentType, PaymentStatus, state machine
├── models.py           -- Payment (JSONBMixin), CryptoAddress
├── interface.py        -- PaymentServiceProtocol, DepositAddress
├── schemas.py          -- CreateAddressRequest, DepositAddressResponse, CryptoWebhookRequest, etc.
├── service.py          -- get_or_create_deposit_address, process_crypto_webhook, list_payments, get_payment
├── router.py           -- POST /crypto-address, GET /history
└── webhook_router.py   -- POST /crypto/webhook (Depends auth, hmac.compare_digest)

backend/app/core/
└── rate_limit.py       -- check_rate_limit() atomic Lua script

backend/tests/
└── test_crypto_deposits.py  -- 10 tests
```

**Критерий готовности:** Инвестор получает крипто-адрес. Webhook создаёт Payment и запись в active_ledger. tx_hash уникален на уровне БД. Все webhook'ы timing-safe. Email auth rate-limited. Failed login audit записывается. 142 теста зелёные.

---

### ✅ Sprint 5.3: Payment Confirmation Daemon + Reversal

**Цель:** Автоматическое подтверждение платежей и механизм чарджбека.

**Задачи:**
- [x] `app/modules/payments/confirmation.py` — `run_confirmation_batch()`: batch UPDATE frozen -> confirmed для Payment, ActiveLedger, PassiveLedger при `frozen_until <= now()`
- [x] `main.py` — `_payment_confirmation_worker()` вызывает `run_confirmation_batch()` каждые `CONFIRMATION_WORKER_INTERVAL_MINUTES`
- [x] `app/modules/payments/reversal.py` — `reverse_payment()`: зеркальные ledger-записи, Payment -> reversed, audit
- [x] `app/modules/payments/staff_router.py` — `POST /api/v1/staff/payments/{id}/reverse` (permission: `payment_review`)
- [x] G2 fix: `GET /api/v1/staff/payments` — list all payments with filters (status, user_id), paginated. `StaffPaymentResponse` extends `PaymentResponse` + `user_id`. Permission: `payment_review`
- [x] `app/modules/payments/schemas.py` — `+ReversePaymentRequest`, `+ReversalResponse`
- [x] `tests/test_payment_confirmation.py` — 8 тестов
- [x] `tests/test_payment_reversal.py` — 6 тестов

**Миграции:** не требуются — все таблицы из Sprint 5.2.

**Endpoints:**
```
GET  /api/v1/staff/payments                -> StaffPaymentListResponse  (200, payment_review)
POST /api/v1/staff/payments/{id}/reverse   -> ReversalResponse         (200, payment_review)
```

**Решения реализации:**
- P5-16: Бизнес-логика confirmation вынесена в `payments/confirmation.py`, не в `main.py` — separation of concerns. `main.py` содержит только daemon loop
- P5-17: Bulk `update()` для Payment явно передаёт `updated_at=now` — ORM `onupdate=func.now()` не срабатывает при bulk operations
- P5-18: Каждая таблица (Payment, ActiveLedger, PassiveLedger) подтверждается независимо по своему `frozen_until`. Ledger entry не наследует `frozen_until` от parent Payment
- P5-19: Reversal создаёт зеркальные записи через `record_active/passive_ledger(status=confirmed, amount=-original)` — полный audit trail, баланс может уйти в минус (user owes platform)
- P5-20: Оригинальные entries помечаются `status=reversed` через direct ORM update — единственный authorized path обхода `_WRITABLE_STATUSES` guard
- P5-21: `reversal.py` — отдельный файл (не в `service.py`) — редкая операция, изолированный контракт, отдельные тесты
- P5-22: `staff_router.py` — в модуле `payments/` (не в `staff/`) — при распиле на микросервисы уходит целиком с модулем. Паттерн аналогичен `companies/staff_router.py`, `products/staff_router.py`
- P5-23: `ReversalResponse.affected_user_ids: list[UUID]` — Pydantic сериализует. Audit data в JSONB хранит `str(uuid)` (JSONB не сериализует UUID)
- P5-24: Daemon при ошибке логирует exception и продолжает — следующий tick через `CONFIRMATION_WORKER_INTERVAL_MINUTES` подберёт те же записи (они всё ещё frozen)

**Новые audit events:**
- `payment.chargeback` — Staff reversal с деталями: total_reversed_cents, entries counts, affected users, reason

**Результат:**
```
backend/app/modules/payments/
├── __init__.py
├── constants.py        -- PaymentType, PaymentStatus, state machine (Sprint 5.2)
├── models.py           -- Payment (JSONBMixin), CryptoAddress (Sprint 5.2)
├── interface.py        -- PaymentServiceProtocol, DepositAddress (Sprint 5.2)
├── schemas.py          -- +ReversePaymentRequest, +ReversalResponse (Sprint 5.3), +StaffPaymentResponse, +StaffPaymentListResponse (G2)
├── service.py          -- get_or_create_deposit_address, process_crypto_webhook, list_payments, list_all_payments (G2), get_payment (Sprint 5.2)
├── confirmation.py     -- run_confirmation_batch() (Sprint 5.3)
├── reversal.py         -- reverse_payment() (Sprint 5.3, +FOR UPDATE +total from entries: code review)
├── router.py           -- POST /crypto-address, GET /history (Sprint 5.2)
├── staff_router.py     -- GET /staff/payments (G2), POST /staff/payments/{id}/reverse (Sprint 5.3)
└── webhook_router.py   -- POST /crypto/webhook (Sprint 5.2)

backend/tests/
├── test_crypto_deposits.py      -- 10 tests (Sprint 5.2)
├── test_payment_confirmation.py -- 8 tests (Sprint 5.3)
└── test_payment_reversal.py     -- 6 tests (Sprint 5.3)
```

**Обновлённые файлы (Sprint 5.3):**
- `main.py` — `_payment_confirmation_worker()` вызывает `run_confirmation_batch()`, `+staff_payments_router`

**Критерий готовности:** Daemon подтверждает платежи по `frozen_until`. Staff делает chargeback с полным audit trail. 156 тестов зелёные.

---

**Phase 5 завершена.** 5 endpoints (2 investor payments + 1 webhook + 1 staff reversal + 1 staff list (G2)), 24 теста Phase 5 (+118 Phase 0-4 = 142 Sprint 5.2, 156 Sprint 5.3), 2 миграции (итого 8). AML-матрица standalone. Confirmation daemon. Chargeback reversal.

**Обновлённые файлы (Phase 5 total):**
- `core/constants.py` — `LedgerReason` registry
- `core/config.py` — `+crypto_webhook_secret`, `+confirmation_worker_interval_minutes`, `+crypto_networks`, `+freezing_hours_crypto`
- `core/rate_limit.py` — **новый**: ~~generic INCR+EXPIRE~~ → атомарный Lua-скрипт (фикс code review)
- `auth/service.py` — `+_audit_login_failure()` (SEC-7), `+logger.error` в except (фикс code review)
- `auth/router.py` — rate limiting на register/login (SEC-5)
- `kyc/service.py` — `process_webhook(user_id: UUID)` вместо `str` (CRIT-3)
- `kyc/router.py` — `hmac.compare_digest()` для webhook (SEC-1)
- `staff/admin_service.py` — убраны `str()` обёртки для KYC calls
- `main.py` — `+payments_router`, `+payments_webhook_router`, `+staff_payments_router`, confirmation daemon (batch-first, фикс code review)
- `install_cbshome.sh` — `+CRYPTO_WEBHOOK_SECRET` генерация
- `tests/helpers.py` — cleanup для Payment, CryptoAddress, ActiveLedger, PassiveLedger
- `tests/conftest.py` — `+clear_rate_limit` autouse fixture

**Фиксы code review (Phase 5):**
- CR-P5-01: `webhook_router.py` — `_verify_webhook_secret` переведён в `async def` + `dependencies=[Depends()]` на роуте → auth выполняется ДО парсинга body. Добавлен guard `not provided` против пустого `X-Webhook-Secret` header
- CR-P5-02: `rate_limit.py` — INCR+EXPIRE заменены на Lua-скрипт `_RATE_LIMIT_SCRIPT` → атомарное выполнение через `redis.eval()`. Если процесс падает — ключ не повисает без TTL
- CR-P5-03: `payments/router.py` — `create_crypto_address`: `get_current_user` → `get_current_user_write` → auth и endpoint используют одну write-сессию (TD-029 паттерн)
- CR-P5-04: `payments/schemas.py` — `amount_usd_cents`: добавлено `le=MAX_DEPOSIT_CENTS` ($10M = 1_000_000_000 cents). Sanity guard от ошибок провайдера
- CR-P5-05: `main.py` — confirmation worker: `run_confirmation_batch()` вызывается ДО `asyncio.sleep()` → frozen entries подтверждаются сразу при старте, не через 5 минут. `asyncio.sleep(interval)` добавлен в `except` блок для предотвращения tight error loop
- CR-P5-06: `payments/reversal.py` — `get_payment()` → `SELECT ... WITH FOR UPDATE` → сериализует concurrent reversals. `total_reversed_cents` считается из `sum(abs(entry.amount_cents))` по реальным entries, а не `payment.amount_cents` (TD-035 закрыт)

**Файлы изменённые (code review Phase 5):**
- `core/rate_limit.py` — Lua-скрипт
- `payments/webhook_router.py` — Depends auth + empty guard
- `payments/router.py` — `get_current_user_write`
- `payments/schemas.py` — `le=MAX_DEPOSIT_CENTS`
- `payments/reversal.py` — `FOR UPDATE` + total from entries
- `main.py` — worker batch-first
- `auth/service.py` — `logger.error` в `_audit_login_failure`
- `auth/telegram.py` — делегирует на `check_rate_limit()`, импорты на уровне модуля

---

## PHASE 6: Purchase + Installment

---

### ✅ Sprint 6.1: Distribution Engine (processors/) + Purchase

**Цель:** Самостоятельный модуль распределения денег. Не принадлежит ни Purchase, ни Agent —
владеет логикой того, как деньги распределяются в момент любой транзакции покупки.
В этом спринте закладывается фундамент и реализуются первые два процессора (Purchase, Gift).
ReferralProcessor и VolumeProcessor добавляются в Sprints 7.2 и 7.3 в ту же папку.

**Архитектурный принцип:** `processors/` получает `PurchaseContext`, возвращает список
`Transaction` с инвариантом `SUM(entries) = 0`. Не знает про HTTP, роутеры, сессии.
Не коммитит. Атомарная запись — ответственность `execute_purchase()` в `purchases/service.py`.
При рассрочке `PurchaseContext` получает данные конкретного транша из снапшота `plan_config`,
а не из `ProductInstallment` напрямую — изменение плана не влияет на активные рассрочки.

`PurchaseContext` содержит `agent_chain: list[UUID]` (resolved via `get_agent_chain()` в Sprint 7.2).
Если `agent_chain` пуст — покупка органическая, `ReferralProcessor` возвращает пустой список,
Platform получает полный остаток по `distribution_config`. Пустая цепочка — валидное состояние, не ошибка.

**Задачи:**
- [x] `app/modules/processors/base.py` — `ProcessorProtocol`, `PurchaseContext`, `Transaction`, `LedgerEntry`
- [x] `app/modules/processors/purchase.py` — `PurchaseProcessor`
- [x] `app/modules/processors/gift.py` — `GiftProcessor`
- [x] `app/modules/processors/registry.py` — `ProcessorRegistry` (расширяется в Phase 7)
- [x] `app/modules/processors/validators.py` — `validate_purchase_config()` (distribution + bonuses)
- [x] `app/modules/purchases/models.py` — `Purchase`
- [x] `app/modules/purchases/constants.py` — `PurchaseStatus`, `PurchaseLegalBasis`
- [x] `app/modules/purchases/schemas.py` — `CreatePurchaseRequest`, `PurchaseResponse`, `PurchaseListResponse`
- [x] `app/modules/purchases/service.py` — `execute_purchase()`, `get_sold_units_map()`, `get_investor_portfolio_cents()`
- [x] `app/modules/purchases/router.py` — `POST /api/v1/products/{id}/purchase` (role: investor or agent, G3 fix)
- [x] `app/modules/products/models.py` — `+purchase_config JSONB`, `-gift_units`, `+JSONBMixin`
- [x] `app/modules/products/schemas.py` — `purchase_config` вместо `gift_units` во всех схемах
- [x] `app/modules/products/service.py` — `purchase_config` в `create_product()`, `update_product()`
- [x] `app/modules/products/staff_router.py` — `financial_operations` для `purchase_config`
- [x] `app/modules/products/router.py` — `sold_units` из `get_sold_units_map()` (TD-031 закрыт)
- [x] `tests/test_purchases.py` — 15 тестов (7 юнит + 3 валидатор + 5 интеграционных)
- [x] `tests/test_products.py` — обновлён (`gift_units` → `purchase_config`)

**Миграции:**
- [x] `0009_purchases` — таблица `purchases` (CHECK constraints), `+purchase_config` JSONB на `products`, `-gift_units`

**Решения реализации:**
- P6-01: `purchase_config` — JSONB колонка на `Product`, nullable. Если `null` → fallback на `Company.distribution_config` + пустые bonuses в рантайме. Full override: если `purchase_config.distribution` задан — Company-level игнорируется
- P6-02: `purchase_config.distribution` — формат идентичен `Company.distribution_config`: `{"company_pct": float, "agent_levels": [float, ...]}`. Переиспользуется `validate_distribution_config()`
- P6-03: `purchase_config.bonuses[]` — массив бонусов. `bonus_units_percent` всегда процент от купленных юнитов, сумма всех ≤ 100%. `funded_by: "company" | "platform"` определяет источник списания
- P6-04: Старое поле `Product.gift_units` удалено, заменено записью `{"condition": "always", ...}` в `purchase_config.bonuses[]`. Единый механизм через `GiftProcessor`
- P6-05: `Purchase.document_id` убран из модели — документы о покупке генерируются по запросу с нуля, PDF хранить не нужно
- P6-06: `agent_chain` — заглушка (пустой список) в Sprint 6.1, ✅ реальный резолвинг через `get_agent_chain()` в Sprint 7.2
- P6-07: `{purchase_id}` placeholder в reason strings — процессоры не знают ID до записи в БД. `_write_transactions()` заменяет placeholder на реальный UUID после `flush()`
- P6-08: `pg_advisory_xact_lock(investor_id)` — сериализует покупки одного инвестора. Защита от TOCTOU race condition при параллельных запросах. Автоматически освобождается при commit/rollback
- P6-09: `_load_company()` проверяет `company.status == active` — защита от покупки продукта архивированной компании
- P6-10: `sold_units` реализован через прямой `COUNT` из purchases (`get_sold_units_map()` — батчевый запрос для всех продуктов на странице). Redis-кэш — при необходимости (TD-031 переформулирован)
- P6-11: Процессоры — чистые синхронные функции без I/O. `ProcessorProtocol.process()` → `list[Transaction]`. Инвариант SUM=0 проверяется в `ProcessorRegistry.run_all()`
- P6-12: `GiftProcessor` считает portfolio_size (`SUM(paid_cents)`) для условия `portfolio_size_gte`. Включает текущую покупку в расчёт. Извлечение в отдельный сервис — позже

**Модели:**
```python
Purchase:  -- иммутабельно, нет updated_at
    id: UUID
    investor_id: UUID        -- FK users.id
    product_id: UUID         -- FK products.id
    company_id: UUID         -- FK company_profiles.id (денормализовано)
    legal_basis: String(30)  -- CHECK: sale | gift | installment_tranche
    units: Integer
    paid_cents: BigInteger   -- 0 для gift
    price_per_unit_cents: BigInteger  -- снапшот цены на момент покупки
    status: String(20)       -- CHECK: active | reversed
    created_at: DateTime(tz)
    -- agent_id отсутствует: реферальная информация только в ReferralAttribution
    -- document_id отсутствует: PDF генерируется по запросу
```

**Структура `purchase_config` (на Product, nullable):**
```json
{
  "distribution": {
    "company_pct": 0.65,
    "agent_levels": [0.10, 0.03, 0.01]
  },
  "bonuses": [
    {
      "condition": "always",
      "bonus_units_percent": 10,
      "funded_by": "company"
    },
    {
      "condition": "portfolio_size_gte",
      "threshold_cents": 50000,
      "bonus_units_percent": 5,
      "funded_by": "platform"
    }
  ]
}
```

**Инвариант перед записью в БД:**
```python
for transaction in transactions:
    assert sum(e.amount_cents for e in transaction.entries) == 0
```

**Endpoints:**
```
POST /api/v1/products/{id}/purchase  -> list[PurchaseResponse]  (201)
```

**Новые audit events:**
- `purchase.created` — инстант-покупка (legal_basis=sale)
- `purchase.gift_created` — бонусное начисление (legal_basis=gift)

**Результат:**
```
backend/app/modules/processors/
├── __init__.py
├── base.py             -- ProcessorProtocol, PurchaseContext, Transaction, LedgerEntry
├── purchase.py         -- PurchaseProcessor (core distribution)
├── gift.py             -- GiftProcessor (bonus allocations)
├── referral.py         -- ReferralProcessor (agent commissions L1/L2/L3, Sprint 7.2)
├── volume.py           -- VolumeProcessor (volume bonus distribution, Sprint 7.3)
├── registry.py         -- ProcessorRegistry (run_all + SUM=0 invariant)
└── validators.py       -- validate_purchase_config()

backend/app/modules/purchases/
├── __init__.py
├── constants.py        -- PurchaseStatus, PurchaseLegalBasis
├── models.py           -- Purchase
├── schemas.py          -- CreatePurchaseRequest, PurchaseResponse, PurchaseListResponse
├── service.py          -- execute_purchase(), get_sold_units_map(), get_investor_portfolio_cents()
└── router.py           -- POST /products/{id}/purchase

backend/tests/
└── test_purchases.py   -- 15 tests
```

**Обновлённые файлы (Sprint 6.1):**
- `core/constants.py` — `+DISTRIBUTION_COMPANY`, `+PLATFORM_REMAINDER` в LedgerReason
- `products/models.py` — `+JSONBMixin`, `+purchase_config JSONB`, `-gift_units`
- `products/schemas.py` — `purchase_config` вместо `gift_units`
- `products/service.py` — `purchase_config` в `create_product()`, `update_product()` + `validate_purchase_config()`
- `products/staff_router.py` — `financial_operations` для `purchase_config`
- `products/router.py` — `sold_units` из `get_sold_units_map()`
- `main.py` — `+purchases_router`
- `migrations/env.py` — `+Purchase` import
- `tests/helpers.py` — `+Purchase` cleanup в `_cleanup_user_related_data()`
- `tests/test_products.py` — `gift_units` → `purchase_config`, `+_activate_company` в purchase тестах

**Критерий готовности:** Инвестор покупает продукт. PurchaseProcessor распределяет средства по `distribution_config` (product override или company fallback). GiftProcessor создаёт бонусные акции из `purchase_config.bonuses[]`. ProcessorRegistry готов к регистрации новых процессоров. Advisory lock защищает от двойной траты. Статус компании проверяется при покупке. `sold_units` считается из реальных покупок. 171 тест зелёный.

---

### ✅ Sprint 6.2: Installment Plans

**Цель:** Покупка продукта в рассрочку.

**Задачи:**
- [x] `app/modules/installments/constants.py` — `InstallmentPlanStatus`, `InstallmentTrancheStatus`, state machine transitions + validators
- [x] `app/modules/installments/models.py` — `InstallmentPlan`, `InstallmentTranche`
- [x] `app/modules/installments/scheduler.py` — `calculate_due_date()` (february rule)
- [x] `app/modules/installments/schemas.py` — `CreateInstallmentPlanRequest`, `InstallmentPlanResponse`, `InstallmentPlanDetailResponse`, `InstallmentTrancheResponse`, `InstallmentPlanListResponse`
- [x] `app/modules/installments/service.py` — `create_plan()`, `pay_tranche()`, `complete_plan()`, `default_plan()`, `get_investor_plans()`, `get_plan_detail()`
- [x] `app/modules/installments/router.py` — `POST /products/{id}/installment`, `GET /installments/me`, `GET /installments/{id}`
- [x] `app/modules/installments/worker.py` — `run_installment_batch()` (due tranche payment + overdue default)
- [x] `app/modules/purchases/engine.py` — **новый**: shared financial operation core (extracted from `purchases/service.py`)
- [x] `app/modules/purchases/service.py` — рефакторинг: `execute_purchase()` делегирует в `engine.execute()`, `compute_frozen_context()` публичный
- [x] `app/modules/products/constants.py` — `validate_plan_config()` расширен: `+units decomposition` check
- [x] `app/core/exceptions.py` — `+InsufficientBalanceError(BadRequestError)` с `available`/`required` полями
- [x] `_installment_payment_worker` — daemon (asyncio.Task в lifespan), daily at `INSTALLMENT_WORKER_HOUR`, batch-first
- [x] `tests/test_installments.py` — 20 тестов (5 scheduler + 2 validator + 4 create_plan + 4 endpoints + 2 pay + 2 complete/default)

**Миграции:**
- [x] `0010_installments` — таблицы `installment_plans`, `installment_tranches` (CHECK constraints, unique `plan_id+number`)

**Модель `InstallmentPlan`:**
```python
InstallmentPlan:
    id: UUID
    investor_id: UUID
    product_id: UUID
    product_installment_id: UUID
    company_id: UUID              -- денормализовано для быстрых запросов
    plan_config_snapshot: JSONB   -- полная копия plan_config на момент создания
    total_price_cents: int        -- денормализовано из снапшота
    total_units: int              -- денормализовано (product.units)
    price_per_unit_cents: int     -- снапшот цены на момент создания
    referral_link_id: UUID | None -- FK referral_links.id (resolved in Sprint 7.2)
    agent_id: UUID | None         -- Sprint 7.x stub (nullable, FK users.id)
    status: enum                  -- active | completed | defaulted | cancelled
    created_at, completed_at, defaulted_at
```

**Модель `InstallmentTranche`:**
```python
InstallmentTranche:
    id: UUID
    plan_id: UUID                 -- FK installment_plans.id
    number: int                   -- 1..N (unique per plan)
    due_date: date                -- с учётом february rule
    amount_cents: int             -- из snapshot tranches[N].amount_cents
    units_unlocked: int           -- pre-computed: units_percent * total_units // 100
    status: enum                  -- scheduled | paid | overdue | defaulted | cancelled
    paid_at: datetime | None
    purchase_id: UUID | None      -- FK purchases.id (NOT NULL после оплаты)
    created_at
```

**Решения реализации:**
- P6-13: **engine.py** — общее ядро финансовых операций, вынесено из `purchases/service.py`. `execute()` принимает готовый `PurchaseContext`, выполняет: advisory lock (если `amount_cents > 0`) → balance check → ProcessorRegistry → write transactions → audit. `write_transactions()` — публичная, используется `complete_plan()` для фиксированных бонусов
- P6-14: **Контекст immutable на входе** — engine никогда не вычисляет `frozen_until`, `distribution_config` и другие поля контекста. Вызывающий код (`execute_purchase()` или `pay_tranche()`) строит полный `PurchaseContext` самостоятельно
- P6-15: **Условная логика по amount_cents** — `amount_cents > 0`: advisory lock + balance check. `amount_cents == 0`: skip (gift/bonus scenario). Единственное условие, без флагов
- P6-16: **plan_config_snapshot** — полная копия `ProductInstallment.plan_config` + денормализованные `total_price_cents`, `total_units`, `price_per_unit_cents`. Изменение шаблона не влияет на active планы
- P6-17: **units_unlocked pre-computed** — вычисляется при создании плана (`units_percent * total_units // 100`), записывается в tranche. `validate_plan_config()` отклоняет конфигурации где `sum(units_unlocked) != total_units` (Sprint 6.2 addition)
- P6-18: **pay_tranche()** — загружает Product/Company без проверки status (plan переживает архивацию продукта). Distribution_config берётся из текущего состояния product/company, не из снапшота
- P6-19: **InsufficientBalanceError** — подкласс `BadRequestError` с `available`/`required` полями и `code="insufficient_balance"`. `engine.execute()` бросает, `pay_tranche()` ловит по типу (fix #35: вместо string match)
- P6-20: **Completion bonuses** — при закрытии плана (все tranches paid): `bonus_units` → investor gift Purchase, `agent_bonus_units` → agent L1 gift Purchase (если `agent_id is not None`). Транзакции строятся вручную (не через ProcessorRegistry) и записываются через `engine.write_transactions()`
- P6-21: **default_plan()** — overdue tranche → defaulted, remaining scheduled/overdue → cancelled, plan → defaulted. Инвестор сохраняет уже оплаченные акции. Бонусы не начисляются
- P6-22: **Daemon batch-first** — `run_installment_batch()` вызывается ДО `asyncio.sleep()` (fix #34: аналогично confirmation worker CR-P5-05). Sleep до следующего `INSTALLMENT_WORKER_HOUR`. `timedelta(days=1)` для границ месяцев
- P6-23: **Worker transaction isolation** — каждый tranche обрабатывается в отдельной DB-транзакции (`session.begin()`). Ошибка одного tranche не откатывает другие. Дедупликация defaults по `plan_id` через `seen_plans: set`
- P6-24: **Два роутера** — `create_router` (POST `/products/{id}/installment`) и `query_router` (GET `/installments/me`, GET `/installments/{id}`). Разные prefix'ы, оба требуют `role in (investor, agent)` (G4 fix: агенты тоже могут покупать)
- P6-25: **Дублирование планов разрешено** — инвестор может иметь несколько active планов по одному продукту (разные пакеты: 6 и 12 месяцев). By design, не баг

**Логика `create_plan()`:**
```
1. Загрузить Product (must be active) + Company (must be active)
2. Загрузить ProductInstallment -> скопировать plan_config в plan_config_snapshot
3. Создать InstallmentPlan (с referral_link_id: UUID | None из запроса)
4. Развернуть tranches из снапшота в записи InstallmentTranche:
   - tranches[0]: due_date = today, status = scheduled (daemon оплатит сразу)
   - tranches[1]: due_date = calculate_due_date(today, 1)
   - tranches[N]: due_date = calculate_due_date(today, N)
5. Daemon в ту же итерацию оплачивает tranches[0];
   referral_link_id передаётся в PurchaseContext каждого транша —
   если None, ReferralProcessor не вызывается
```

**Endpoints:**
```
POST /api/v1/products/{id}/installment  -> InstallmentPlanResponse  (201)
GET  /api/v1/installments/me            -> InstallmentPlanListResponse  (200)
GET  /api/v1/installments/{id}          -> InstallmentPlanDetailResponse  (200)
```

**Новые audit events:**
- `installment.plan_created` — создание плана с деталями template/tranches
- `installment.tranche_paid` — оплата транша с purchase_id
- `installment.tranche_overdue` — недостаточно средств
- `installment.plan_completed` — все транши оплачены, бонусы начислены
- `installment.plan_defaulted` — просрочка > INSTALLMENT_DEFAULT_DAYS
- `installment.bonus_awarded` — бонусные акции при завершении плана

**Результат:**
```
backend/app/modules/installments/
├── __init__.py
├── constants.py        -- InstallmentPlanStatus, InstallmentTrancheStatus, state machines
├── models.py           -- InstallmentPlan, InstallmentTranche
├── schemas.py          -- 1 request + 4 response
├── scheduler.py        -- calculate_due_date() (february rule)
├── service.py          -- create_plan, pay_tranche, complete_plan, default_plan, queries
├── router.py           -- create_router (1 endpoint) + query_router (2 endpoints)
└── worker.py           -- run_installment_batch() (due payments + defaults)

backend/app/modules/purchases/
├── engine.py           -- NEW: execute(), write_transactions() (shared core)
└── service.py          -- REFACTORED: execute_purchase() delegates to engine

backend/tests/
└── test_installments.py  -- 20 tests
```

**Обновлённые файлы (Sprint 6.2):**
- `core/exceptions.py` — `+InsufficientBalanceError(BadRequestError)` с `available`, `required`, `code="insufficient_balance"`
- `products/constants.py` — `validate_plan_config()` +units decomposition check: `sum(pct * units // 100) == units`
- `purchases/engine.py` — **новый**: `execute()` + `write_transactions()`, вынесены из service.py
- `purchases/service.py` — рефакторинг: `execute_purchase()` → context + `engine.execute()`, `_compute_frozen_context()` → `compute_frozen_context()` (публичный)
- `main.py` — `+_installment_payment_worker()` (batch-first, daily), `+installment_create_router`, `+installment_query_router`
- `migrations/env.py` — `+InstallmentPlan`, `+InstallmentTranche` import
- `tests/helpers.py` — `+InstallmentPlan`, `+InstallmentTranche` cleanup в `_cleanup_user_related_data()`

**Фиксы code review (Sprint 6.2):**
- CR-62-01: `main.py` — installment daemon: `run_installment_batch()` вызывается ДО `asyncio.sleep()` → просроченные транши обрабатываются сразу при старте, не ждут следующего target_hour (fix #34, аналогично CR-P5-05)
- CR-62-02: `installments/service.py` + `purchases/engine.py` — `InsufficientBalanceError` вместо `BadRequestError` + string match. Engine бросает типизированное исключение, service ловит по типу (fix #35)

**Закрыто code review (Sprint 6.2):**
- #36 (units_unlocked округление) — false positive: `validate_plan_config()` отклоняет конфигурации с неточным разложением
- #37 (дублирование планов) — by design: инвестор может иметь несколько планов (6 и 12 месяцев)

**Критерий готовности:** Инвестор выбирает план по `product_installment_id`. Снапшот фиксируется. Транши разворачиваются из снапшота. Daemon платит транши (batch-first). InsufficientBalance → overdue по типу исключения. Дефолт через 7 дней просрочки. Бонусы из снапшота при закрытии. Engine.py переиспользуется instant purchase и tranche payment. 191 тест зелёный.

---

### ✅ Sprint 6.3: Withdrawals

**Цель:** Вывод средств с passive_ledger.

**Задачи:**
- [x] `app/modules/withdrawals/__init__.py`
- [x] `app/modules/withdrawals/constants.py` — `WithdrawalStatus`, `ACTIVE_WITHDRAWAL_STATUSES`, state machine transitions + validator
- [x] `app/modules/withdrawals/models.py` — `Withdrawal` (partial unique index: one active per user)
- [x] `app/modules/withdrawals/schemas.py` — `CreateWithdrawalRequest`, `RejectWithdrawalRequest`, `WithdrawalResponse`, `WithdrawalListResponse`
- [x] `app/modules/withdrawals/service.py` — `create_withdrawal()`, `confirm_withdrawal()`, `reject_withdrawal()`, `complete_withdrawal()`, `fail_withdrawal()`, `get_my_withdrawals()`, `get_withdrawal()`
- [x] `app/modules/withdrawals/router.py` — `POST /api/v1/withdrawals`, `GET /api/v1/withdrawals/me`
- [x] `app/modules/withdrawals/staff_router.py` — `POST /api/v1/staff/withdrawals/{id}/confirm`, `POST /api/v1/staff/withdrawals/{id}/reject`
- [x] `app/modules/users/models.py` — `+payout_details: JSONB nullable`
- [x] `app/modules/users/schemas.py` — `+UpdatePayoutDetailsRequest`, `+PayoutDetailsResponse`, `+payout_details` в `UserResponse`
- [x] `app/modules/users/service.py` — `+update_payout_details()`
- [x] `app/modules/users/router.py` — `+GET /api/v1/users/me/payout-details`, `+PUT /api/v1/users/me/payout-details`
- [x] `tests/test_withdrawals.py` — 10 тестов

**Миграции:**
- [x] `0011_withdrawals` — таблица `withdrawals` (CHECK constraints, partial unique index `uq_withdrawals_user_active`), `+payout_details JSONB` на `users`

**Модель `Withdrawal`:**
```python
Withdrawal:
    id: UUID
    user_id: UUID                 -- FK users.id
    amount_cents: int             -- BigInteger, CHECK > 0
    status: enum                  -- pending | confirmed | processing | completed | rejected | failed
    payout_details_snapshot: JSONB -- snapshot User.payout_details на момент создания
    rejection_reason: str | None  -- обязательно при rejected
    created_at, confirmed_at, processing_at, completed_at, rejected_at, failed_at
```

**State machine (CBSHOME-State-Machines.md section 4, extended):**
```
pending    -> confirmed   (Staff: approved)
pending    -> rejected    (Staff: declined with reason)
confirmed  -> processing  (system: pushed to payment provider)
processing -> completed   (system/webhook: payout confirmed)
processing -> failed      (system/webhook: payout rejected)
```
Terminal: `completed`, `rejected`, `failed`.

**Решения реализации:**
- P6-26: **Instant debit** — при создании withdrawal passive_ledger дебетуется сразу (`record_passive_ledger(-amount, confirmed)`). При reject/fail — компенсирующая запись (`+amount, confirmed, reason + ":reversal"`). Предотвращает "размножение" денег при ожидании подтверждения
- P6-27: **Partial unique index** — `uq_withdrawals_user_active ON (user_id) WHERE status IN ('pending', 'confirmed', 'processing')`. DB-level гарантия: один активный withdrawal на пользователя. IntegrityError ловится по constraint name → `ConflictError`
- P6-28: **Advisory lock** — `pg_advisory_xact_lock(user.id.int & 0x7FFFFFFFFFFFFFFF)` перед проверкой баланса. Тот же lock_id что в `engine.py` — сериализует withdrawal с purchases одного пользователя. Предотвращает race condition при параллельной покупке и выводе (code review fix #38)
- P6-29: **SELECT FOR UPDATE** — `_load_withdrawal(..., for_update=True)` на всех мутирующих операциях (confirm, reject, complete, fail). Query-методы используют default `for_update=False`. Сериализует concurrent staff actions (code review fix)
- P6-30: **Payout details snapshot** — `User.payout_details` копируется в `Withdrawal.payout_details_snapshot` при создании. Изменение details после создания не влияет на pending withdrawal
- P6-31: **Payout details endpoint** — отдельный `PUT /users/me/payout-details` (не через `PATCH /users/me`). Финансовые реквизиты — чувствительные данные: отдельный audit event `user.payout_details_updated`, future: KYC required, rate limit, 2FA
- P6-32: **Payout details free-form JSONB** — без whitelist (в отличие от profile TD-024). Валидация конкретных методов при интеграции платёжного провайдера. Audit: `data={}` — financial details не логируются
- P6-33: **MVP confirm flow** — `pending → confirmed → processing` в одном действии. При интеграции реального провайдера: confirmed → processing будет отдельным шагом (push в API платёжки)
- P6-34: **Guards** — payout_details configured, MIN/MAX_WITHDRAWAL_CENTS, confirmed passive balance >= amount
- P6-35: **Permission** — `payment_review` для staff confirm/reject (аналогично `staff/payments/{id}/reverse`)

**Config (новые настройки):**
```
min_withdrawal_cents: int = 1000       -- $10.00
max_withdrawal_cents: int = 10000000   -- $100,000.00
```

**Endpoints:**
```
-- User endpoints:
POST /api/v1/withdrawals                          -> WithdrawalResponse      (201)
GET  /api/v1/withdrawals/me                        -> WithdrawalListResponse  (200)
GET  /api/v1/users/me/payout-details               -> PayoutDetailsResponse   (200)
PUT  /api/v1/users/me/payout-details               -> PayoutDetailsResponse   (200)

-- Staff endpoints:
POST /api/v1/staff/withdrawals/{id}/confirm        -> WithdrawalResponse      (200)
POST /api/v1/staff/withdrawals/{id}/reject         -> WithdrawalResponse      (200)
```

**Новые audit events:**
- `withdrawal.created` — запрос на вывод с amount_cents
- `withdrawal.confirmed` — Staff approve + amount + user_id
- `withdrawal.rejected` — Staff reject + reason + amount + user_id
- `withdrawal.completed` — system/webhook payout confirmed
- `withdrawal.failed` — system/webhook payout rejected
- `user.payout_details_updated` — обновление реквизитов выплат (data={} — sensitive)

**Результат:**
```
backend/app/modules/withdrawals/
├── __init__.py
├── constants.py        -- WithdrawalStatus, ACTIVE_WITHDRAWAL_STATUSES, state machine
├── models.py           -- Withdrawal (partial unique index)
├── schemas.py          -- 2 request + 2 response
├── service.py          -- create, confirm, reject, complete, fail, queries
├── router.py           -- 2 user endpoints
└── staff_router.py     -- 2 staff endpoints

backend/tests/
└── test_withdrawals.py -- 10 tests
```

**Обновлённые файлы (Sprint 6.3):**
- `core/config.py` — `+min_withdrawal_cents`, `+max_withdrawal_cents`
- `users/models.py` — `+payout_details: JSONB nullable`
- `users/schemas.py` — `+UpdatePayoutDetailsRequest`, `+PayoutDetailsResponse`, `+payout_details` в `UserResponse`
- `users/service.py` — `+update_payout_details()`
- `users/router.py` — `+GET/PUT /me/payout-details`
- `main.py` — `+withdrawals_router`, `+staff_withdrawals_router`
- `migrations/env.py` — `+Withdrawal` import
- `tests/helpers.py` — `+Withdrawal` cleanup в `_cleanup_user_related_data()`

**Фиксы code review (Sprint 6.3):**
- CR-63-01: `service.py` — advisory lock `pg_advisory_xact_lock(user.id.int & 0x7FFFFFFFFFFFFFFF)` перед проверкой баланса в `create_withdrawal()`. Тот же lock_id что в `engine.py` — сериализует withdrawal с purchases (fix #38)
- CR-63-02: `service.py` — `_load_withdrawal()` получил `for_update: bool = False`. Все 4 мутирующих метода используют `for_update=True`. Сериализует concurrent staff actions

**Критерий готовности:** Любой User с confirmed passive balance и payout_details запрашивает вывод. Staff подтверждает/отклоняет. Instant debit при создании + компенсация при reject/fail. Advisory lock сериализует с purchases. Partial unique index — один active withdrawal. 201 тест зелёный.

---

### ✅ Sprint 6.4: Transaction History + Semaphores

**Цель:** История операций и семафоры консистентности.

**Задачи:**
- [x] `app/modules/transactions/__init__.py`
- [x] `app/modules/transactions/constants.py` — `TransactionType` (14 типов, формат `{entity}:{event}`), `ReferenceType`
- [x] `app/modules/transactions/models.py` — `Transaction` (иммутабельная, BigInteger, JSONBMixin, индексы на user_created/reference/type)
- [x] `app/modules/transactions/schemas.py` — `TransactionResponse`, `TransactionListResponse`
- [x] `app/modules/transactions/service.py` — `record_transaction()`, `list_transactions()`, `get_transaction()`
- [x] `app/modules/transactions/router.py` — `GET /transactions`, `GET /transactions/{id}`
- [x] `app/modules/staff/consistency/__init__.py`
- [x] `app/modules/staff/consistency/schemas.py` — `SemaphoreResult`, `ConsistencyResponse`
- [x] `app/modules/staff/consistency/service.py` — 18 семафоров (S-01..S-13 без S-07 + IS-01..IS-06) + `run_all()` + `_safe_details()` (Decimal→int)
- [x] `app/modules/staff/consistency/router.py` — `GET /staff/consistency` (financial_operations)
- [x] Интеграция `record_transaction()` в payments/service, payments/confirmation, payments/reversal, purchases/engine, installments/service, withdrawals/service
- [x] `tests/test_transactions.py` — 8 тестов
- [x] `tests/test_consistency.py` — 10 тестов

**Миграции:**
- [x] `0012_transactions` — таблица `transactions` + CHECK constraints на type/reference_type

**Модель `Transaction`:**
```python
Transaction:  -- иммутабельная, нет updated_at
    id: UUID
    user_id: UUID         -- FK users.id
    type: String(50)      -- CHECK: 14 типов (deposit:received, purchase:completed, etc.)
    amount_cents: BigInteger
    reference_id: UUID | None   -- связанная сущность (payment_id, plan_id, etc.)
    reference_type: String(30) | None  -- CHECK: payment | purchase | installment_plan | withdrawal
    details: JSONB | None       -- дополнительные данные (network, tx_hash, etc.)
    created_at: DateTime(tz)
    -- Индексы: (user_id, created_at DESC), (reference_id, reference_type), (type)
```

**14 типов событий (TransactionType):**
```
deposit:received, deposit:confirmed, deposit:reversed
purchase:completed, purchase:gift
installment:tranche_paid, installment:completed, installment:defaulted
withdrawal:created, withdrawal:confirmed, withdrawal:rejected, withdrawal:completed, withdrawal:failed
reversal:completed
```

**18 семафоров:**
```
S-01: SUM(all ledger entries) = 0
S-02: COUNT(purchase ledger entries) = COUNT(purchases)
S-03: SUM(paid_cents) = ABS(SUM(active debits by purchases))
S-04: No active_ledger entries for company users
S-05: No users with negative confirmed active balance
S-06: No users with negative confirmed passive balance
S-08: No confirmed entries linked to reversed Payments
S-09: Reversal entry count matches reversed original count
S-10: SUM(tranches.amount_cents) = plan.total_price_cents per plan
S-11: Platform passive balance >= 0
S-12: All gift purchases have paid_cents = 0
S-13: SUM(purchase units) by company >= 0
IS-01: Alias of S-10
IS-02: SUM(units_unlocked of paid tranches) + bonus = total_units per completed plan
IS-03: No scheduled tranches for defaulted/cancelled plans
IS-04: Each paid tranche has purchase_id NOT NULL
IS-05: COUNT(paid tranches) = COUNT(installment_tranche purchases) per plan
IS-06: No active plans where all tranches are paid (should be completed)
```

**Решения реализации:**
- P6-36: **Transaction = иммутабельный event log.** Каждая строка = один факт, никаких UPDATE. Тип формата `{entity}:{event}`. Сумма всегда заполняется для удобства фронта. Группировка lifecycle по `reference_id + reference_type`
- P6-37: **Event-log таблица вместо UNION query** — простой SELECT с фильтрами vs монструозный UNION из 5 таблиц. Запись в той же DB-транзакции что и основная операция
- P6-38: **Семафоры в `staff/consistency/`** (не `admin/consistency/`), permission `financial_operations`. S-07 убран (документы генерируются по запросу, нет document_id на Purchase). S-14/S-15 убраны как дубли IS-01/IS-06
- P6-39: **`_safe_details()`** — конвертирует `Decimal → int` перед записью в audit JSONB (func.sum на BigInteger возвращает Decimal, не JSON-сериализуемый)
- P6-40: **Type prefix filter** — `GET /transactions?type=deposit:` фильтрует по `.startswith()`, `type=deposit:received` по `==`. SQLAlchemy, не raw SQL — безопасно
- P6-41: **IS-06 single query** — outerjoin + HAVING count(unpaid) == 0 вместо N+1 цикла по active plans. O(1) запросов
- P6-42: **IS-02 single query** — outerjoin + HAVING с JSONB `.as_integer()` для `bonus_units` из snapshot. O(1) запросов
- P6-43: **KYC guard (TD-038)** — `investor.kyc_status != KYCStatus.APPROVED` → `BadRequestError` в `execute_purchase()` и `create_plan()` перед step 1. Enum-based, не строковое сравнение. Worker `pay_tranche()` не проверяет — KYC валидирован при `create_plan()`
- P6-44: **Worker UTC date** — `date.today()` → `datetime.now(UTC).date()` в worker.py. Консистентность с `create_plan()` и `calculate_due_date()`
- P6-45: **Confirmation RETURNING** — bulk UPDATE в confirmation.py расширен: `RETURNING user_id, amount_cents` для записи Transaction без extra query

**Endpoints:**
```
GET  /api/v1/transactions          -> TransactionListResponse  (200, user-scoped)
GET  /api/v1/transactions/{id}     -> TransactionResponse      (200, ownership guard)
GET  /api/v1/staff/consistency     -> ConsistencyResponse      (200, financial_operations)
```

**Новые audit events:**
- `consistency.semaphore_failed` — семафор не прошёл (target_id=staff_id, severity + details в data)

**Результат:**
```
backend/app/modules/transactions/
├── __init__.py
├── constants.py        -- TransactionType (14 types), ReferenceType
├── models.py           -- Transaction (immutable event log)
├── schemas.py          -- TransactionResponse, TransactionListResponse
├── service.py          -- record_transaction, list_transactions, get_transaction
└── router.py           -- GET /transactions, GET /transactions/{id}

backend/app/modules/staff/consistency/
├── __init__.py
├── schemas.py          -- SemaphoreResult, ConsistencyResponse
├── service.py          -- 18 semaphores + run_all() + _safe_details()
└── router.py           -- GET /staff/consistency

backend/tests/
├── test_transactions.py    -- 8 tests
└── test_consistency.py     -- 10 tests
```

**Обновлённые файлы (Sprint 6.4):**
- `payments/service.py` — `+record_transaction()` (deposit:received)
- `payments/confirmation.py` — RETURNING расширен, `+record_transaction()` bulk (deposit:confirmed)
- `payments/reversal.py` — `+record_transaction()` (deposit:reversed, reversal:completed)
- `purchases/engine.py` — `+_LEGAL_BASIS_TO_TXN_TYPE` mapping, `+record_transaction()` (purchase:completed, purchase:gift)
- `purchases/service.py` — `+KYCStatus` import, `+KYC guard` в execute_purchase() (TD-038)
- `installments/service.py` — `+KYCStatus` import, `+KYC guard` в create_plan() (TD-038), `+record_transaction()` (tranche_paid, completed, defaulted)
- `installments/worker.py` — `date.today()` → `datetime.now(UTC).date()`
- `withdrawals/service.py` — `+record_transaction()` (created, confirmed, rejected, completed, failed)
- `main.py` — `+transactions_router`, `+consistency_router`
- `migrations/env.py` — `+Transaction` import
- `tests/helpers.py` — `+Transaction` cleanup в `_cleanup_user_related_data()`
- `tests/test_purchases.py` — `+kyc_status=approved` в helper, `+test_purchase_no_kyc` (16 тестов)
- `tests/test_installments.py` — `+kyc_status=approved` в helper, `+test_create_plan_no_kyc` (21 тест)

**Фиксы code review (Sprint 6.4):**
- CR-64-01: `consistency/service.py` — `_safe_details()` конвертирует Decimal→int для JSONB сериализации
- CR-64-02: `consistency/service.py` — `target_id=staff_id` вместо `None` в record_audit (audit_log.target_id NOT NULL)
- CR-64-03: `test_consistency.py` — `SET session_replication_role = 'replica'` для обхода FK constraints при инъекции тестовых нарушений
- CR-64-04: `test_consistency.py` — тесты не предполагают чистую БД, проверяют конкретный семафор
- CR-64-05: `test_transactions.py` — `strftime()` вместо `isoformat()` для date query params (timezone suffix)
- CR-64-06: IS-06 N+1 → single query с outerjoin + HAVING
- CR-64-07: IS-02 N+1 → single query с outerjoin + JSONB `.as_integer()`
- CR-64-08: worker.py — `date.today()` → `datetime.now(UTC).date()` (timezone consistency)

**Критерий готовности:** Инвестор видит историю операций с фильтрами. 18 семафоров работают. KYC guard на покупке и рассрочке. 221 тест зелёный.

---

**Phase 6 завершена.** 10 endpoints (1 purchase + 3 installments + 6 withdrawals/payout + 2 transactions + 1 consistency), 66 тестов Phase 6 (+156 Phase 0-5 = 221 total), 4 миграции (итого 12). Distribution Engine, installment plans, withdrawals, transaction history, 18 consistency semaphores. KYC guard на всех покупках.

---

## PHASE 7: Agent Module

---

### ✅ Sprint 7.1: Agent Application

**Цель:** Заявка на роль агента.

**Задачи:**
- [x] `app/modules/agent_applications/__init__.py`
- [x] `app/modules/agent_applications/models.py` — `AgentApplication`
- [x] `app/modules/agent_applications/constants.py` — `AgentApplicationStatus` (StrEnum), `VALID_TRANSITIONS`, `validate_transition()`
- [x] `app/modules/agent_applications/schemas.py` — `AgentApplicationResponse`, `AgentApplicationListResponse`, `RejectRequest`
- [x] `app/modules/agent_applications/service.py` — `submit_application()`, `get_my_applications()`
- [x] `app/modules/agent_applications/staff_service.py` — `agent_application_queue()`, `agent_application_approve()`, `agent_application_reject()`
- [x] `app/modules/agent_applications/router.py` — 2 investor endpoints
- [x] `app/modules/agent_applications/staff_router.py` — 3 staff endpoints
- [x] `POST /api/v1/agent-applications` — подать заявку (только investor)
- [x] `GET /api/v1/agent-applications/me` — история заявок
- [x] Staff: `GET /api/v1/staff/agent-applications` — очередь
- [x] Staff: `POST /api/v1/staff/agent-applications/{id}/approve`
- [x] Staff: `POST /api/v1/staff/agent-applications/{id}/reject`
- [x] При approve: `user.role = agent` (немедленно)
- [x] Cooldown: `cooldown_until = now() + AGENT_APPLICATION_COOLDOWN_DAYS`
- [x] `tests/test_agent_applications.py` — 14 тестов (12 base + 2 invalid transitions)

**Миграции:**
- [x] `0013_agent_applications` — таблица `agent_applications` (CHECK constraint на status, partial unique index `uq_agent_applications_user_pending`)

**Модель `AgentApplication`:**
```python
AgentApplication:
    id: UUID (UUIDMixin)
    user_id: UUID             -- FK users.id, indexed
    status: String(20)        -- CHECK: pending | approved | rejected
    rejection_reason: Text    -- nullable
    cooldown_until: DateTime(tz) -- nullable, set on rejection
    reviewed_at: DateTime(tz) -- nullable
    reviewed_by: UUID         -- FK users.id, nullable
    created_at, updated_at    -- TimestampMixin
```

**Решения реализации:**
- P7-01: `created_at` из `TimestampMixin` = момент подачи. Отдельного `submitted_at` нет — аналогично KYC
- P7-02: Staff endpoints в модуле `agent_applications/` (staff_service.py, staff_router.py), не в `staff/admin_*` — паттерн из documents, companies, products, payments
- P7-03: `begin_nested()` + `IntegrityError` catch по constraint `uq_agent_applications_user_pending` — защита от race condition при concurrent submission (P-05 паттерн)
- P7-04: `SELECT ... FOR UPDATE` в `_load_application()` — сериализует concurrent approve/reject двумя staff одновременно
- P7-05: Единый `datetime.now(UTC)` в approve и reject — `cooldown_until` и `reviewed_at` гарантированно совпадают
- P7-06: Rejected — терминальный per row. Повторная подача = новая строка AgentApplication после cooldown
- P7-07: Role guard в service: только `user.role == investor` может подать заявку
- P7-08: `rejection_reason` обязателен при reject (Pydantic `min_length=1`)

**Config (существующие настройки, добавлены ранее):**
```
agent_application_cooldown_days: int = 30
```

**Endpoints:**
```
-- Investor endpoints:
POST /api/v1/agent-applications     -> AgentApplicationResponse      (201)
GET  /api/v1/agent-applications/me  -> AgentApplicationListResponse  (200)

-- Staff endpoints:
GET  /api/v1/staff/agent-applications              -> list[AgentApplicationResponse]  (200)
POST /api/v1/staff/agent-applications/{id}/approve  -> 204
POST /api/v1/staff/agent-applications/{id}/reject   -> 204 (body: {reason})
```

**Новые audit events:**
- `agent_application.submitted` — инвестор подал заявку
- `agent_application.approved` — Staff одобрил, роль изменена на agent
- `agent_application.rejected` — Staff отклонил, cooldown установлен

**Результат:**
```
backend/app/modules/agent_applications/
├── __init__.py
├── constants.py        -- AgentApplicationStatus, VALID_TRANSITIONS, validate_transition()
├── models.py           -- AgentApplication
├── schemas.py          -- AgentApplicationResponse, AgentApplicationListResponse, RejectRequest
├── service.py          -- submit_application, get_my_applications
├── staff_service.py    -- agent_application_queue, approve, reject
├── router.py           -- 2 investor endpoints
└── staff_router.py     -- 3 staff endpoints

backend/tests/
└── test_agent_applications.py  -- 14 tests
```

**Обновлённые файлы (Sprint 7.1):**
- `main.py` — `+agent_applications_router`, `+staff_agent_applications_router`
- `migrations/env.py` — раскомментирован импорт `AgentApplication`
- `tests/helpers.py` — `+AgentApplication` cleanup в `_cleanup_user_related_data()`
- `installments/worker.py` — `+date` import, `+type annotations` restored, `+SELECT FOR UPDATE` (TD-042 fix)

**Фиксы code review (Sprint 7.1):**
- CR-71-01: `service.py` — `begin_nested()` + `IntegrityError` catch на `uq_agent_applications_user_pending` (race condition fix)
- CR-71-02: `staff_service.py` — `SELECT FOR UPDATE` в `_load_application()` (concurrent approve/reject serialization)
- CR-71-03: `staff_service.py` — единый `datetime.now(UTC)` в reject (было два вызова)
- CR-71-04: `installments/worker.py` — `session.get()` → `SELECT FOR UPDATE` через `_load_tranche_for_update()` / `_load_plan_for_update()` (TD-042 fix: double-payment / double-default race condition)
- CR-71-05: `installments/worker.py` — `from datetime import date` + type annotations `today: date` restored

**Критерий готовности:** Инвестор подаёт заявку. Staff одобряет/отклоняет. Роль меняется автоматически. 235 тестов зелёные.

---

### ✅ Sprint 7.2: Referral Links + Commissions

**Цель:** Реферальные ссылки и комиссионная цепочка L1/L2/L3.

**Задачи:**
- [x] `app/modules/referrals/models.py` — `ReferralLink`, `ReferralAttribution`
- [x] `app/modules/referrals/service.py` — `create_link()`, `resolve_referral_code()`, `get_agent_chain()`, `create_attribution()`, `validate_referral_link_id()`
- [x] `app/modules/referrals/schemas.py` — `ReferralLinkResponse`, `ReferralLinkListResponse`, `ReferralStatsResponse`
- [x] `app/modules/referrals/router.py` — 3 agent endpoints
- [x] `app/modules/processors/referral.py` — `ReferralProcessor` (расширение Distribution Engine из Sprint 6.1)
- [x] Зарегистрировать `ReferralProcessor` в `ProcessorRegistry`
- [x] STOP-механика: глубина цепочки ограничена `len(agent_levels)` из `distribution_config`
- [x] `POST /api/v1/referrals/links` — создать реферальную ссылку (только agent)
- [x] `GET /api/v1/referrals/links/me` — мои ссылки
- [x] `GET /api/v1/referrals/stats/me` — статистика по ссылкам
- [x] `tests/test_referrals.py` — 15 тестов (L1/L2/L3 цепочки, органический путь, stop-mechanic, атрибуция, permissions)

**Модели:**
```python
ReferralLink:
    id: UUID
    agent_id: UUID   -- FK users.id (role=agent)
    code: str        -- unique, 8 chars via secrets.token_urlsafe(6)
    is_active: bool  -- default True; деактивация отключает resolve
    created_at: datetime

ReferralAttribution:
    id: UUID
    purchase_id: UUID             -- FK purchases.id; UNIQUE (одна атрибуция на покупку)
    referral_link_id: UUID | None -- FK referral_links.id; NULL = органический трафик
    created_at: datetime
    -- Для инстант-покупок: создаётся для каждой покупки
    -- Для рассрочки: создаётся ТОЛЬКО для первого транша (одна на план)
```

**User.referred_by:**
```
User.referred_by: UUID -- FK users.id (self-ref, NOT NULL)
  - Устанавливается при регистрации (register_email / upsert_telegram_user)
  - referral_code в запросе → resolve → agent_id
  - Невалидный/отсутствующий код → fallback на platform_id (молча)
  - Иммутабельный после регистрации
  - Platform user: referred_by = self.id (self-ref)
```

**Логика комиссий:**
```
get_agent_chain(investor_id):
  Обход User.referred_by вверх с:
  - cycle detection (seen set)
  - stop при role=platform (root)
  - stop при role!=agent или is_active=False
  - stop при len(agent_levels) исчерпан
  Возвращает [L1_agent_id, L2_agent_id, L3_agent_id]

ReferralProcessor.process():
  zip(agent_chain, agent_levels) → одна Transaction на уровень
  Platform passive_ledger: -commission_cents
  Agent passive_ledger: +commission_cents
  commission_cents = round(pct * amount)  -- banker's rounding
```

**Endpoints:**
```
-- Agent endpoints:
POST /api/v1/referrals/links     -> ReferralLinkResponse      (201)
GET  /api/v1/referrals/links/me  -> ReferralLinkListResponse  (200)
GET  /api/v1/referrals/stats/me  -> ReferralStatsResponse     (200)
```

**Новые audit events:**
- `referral.link_created` — агент создал реферальную ссылку

**Результат:**
```
backend/app/modules/referrals/
├── __init__.py
├── models.py           -- ReferralLink, ReferralAttribution
├── service.py          -- resolve_referral_code, create_link, get_agent_chain, create_attribution, validate_referral_link_id, get_my_links, get_my_stats
├── schemas.py          -- ReferralLinkResponse, ReferralLinkListResponse, ReferralStatsResponse
└── router.py           -- 3 agent endpoints

backend/app/modules/processors/
└── referral.py         -- ReferralProcessor (agent commissions)

backend/tests/
└── test_referrals.py   -- 15 tests
```

**Обновлённые файлы (Sprint 7.2):**
- `core/constants.py` — `COMMISSION = "commission:l{level}:{agent_id}:{purchase_id}"` (параметрический, заменил L1/L2/L3)
- `users/models.py` — `+referred_by` (FK self, NOT NULL, ForeignKey import)
- `auth/schemas.py` — `+referral_code: str | None` на `EmailRegisterRequest`, `TelegramAuthRequest`
- `auth/service.py` — `+_resolve_referrer()`, `+get_platform_user_id()`, referral_code в register/upsert
- `auth/router.py` — passes `body.referral_code` to service
- `companies/service.py` — `+referred_by=platform_id` в create_company (User creation)
- `purchases/service.py` — `+get_agent_chain()`, `+create_attribution()`, `+validate_referral_link_id()`
- `installments/service.py` — `+agent_chain`, `+create_attribution` (tranche.number == 1 only)
- `processors/registry.py` — `+ReferralProcessor` в `run_all()`
- `scripts/seed_platform.py` — pre-generate UUID: `id=platform_id, referred_by=platform_id`
- `migrations/env.py` — `+ReferralLink`, `+ReferralAttribution` imports
- `main.py` — `+referrals_router`
- `tests/helpers.py` — `+ReferralAttribution/ReferralLink` cleanup (FK ordering)

**Решения реализации (Sprint 7.2):**
- P7-01: **Platform как Default Referrer** — каждый user имеет `referred_by` NOT NULL, дефолт = Platform user. Platform user self-references (`referred_by = self.id`). Устраняет NULL handling
- P7-02: **Referral resolved at registration** — `referral_code` добавлен в `EmailRegisterRequest` / `TelegramAuthRequest`. Резолвится ПЕРВЫМ в `register_email()` / `upsert_telegram_user()`. Невалидные коды молча fallback на Platform — никогда не блокируют регистрацию
- P7-03: **Параметрические комиссии** — одна константа `COMMISSION` с плейсхолдерами `{level}`, `{agent_id}`, `{purchase_id}`. `agent_levels` list в `distribution_config` управляет глубиной — добавление 4-го уровня = добавить процент в список
- P7-04: **Agent chain из User.referred_by** — не из ReferralAttribution. `get_agent_chain(investor_id)` обходит `referred_by` вверх, останавливается на Platform или `len(agent_levels)`. Cycle detection через `seen` set
- P7-05: **Атрибуция per plan, not per tranche** — для рассрочки `create_attribution()` только при `tranche.number == 1`. Статистика отражает бизнес-решения (конверсии), не финансовые транзакции
- P7-06: **N+1 оптимизация** — `current = referrer` reuse в `get_agent_chain()`. `max_depth + 1` запросов вместо `2 * max_depth`
- P7-07: **Banker's rounding** — `round()` вместо `int()` в `PurchaseProcessor` и `ReferralProcessor`. Стандарт для финансовых вычислений
- P7-08: **begin_nested в create_attribution** — SAVEPOINT для UNIQUE constraint на `purchase_id`. При дубликате (retry) — silent skip, outer transaction preserved

**Фиксы code review (Sprint 7.2):**
- CR-72-01: `processors/referral.py` — `round()` вместо `int()` в расчёте комиссий (float-truncation fix)
- CR-72-02: `processors/purchase.py` — `round()` вместо `int()` в расчёте доли компании (float-truncation fix)
- CR-72-03: `referrals/service.py` — cycle detection (`seen` set) в `get_agent_chain()` (double-commission prevention)
- CR-72-04: `referrals/models.py` — UNIQUE constraint на `referral_attributions.purchase_id` (migration 0015)
- CR-72-05: `referrals/service.py` — `validate_referral_link_id()` (analytics pollution prevention)
- CR-72-06: `referrals/models.py` — `is_active` flag на `ReferralLink` (link deactivation, migration 0015)
- CR-72-07: `referrals/service.py` — `begin_nested()` в `create_attribution()` (UNIQUE + P-01 compliant)
- CR-72-08: `installments/service.py` — атрибуция только для первого транша (`tranche.number == 1`)
- CR-72-09: `referrals/service.py` — N+1 fix: `current = referrer` reuse в `get_agent_chain()`

**Фиксы предупреждений (Sprint 7.2):**
- CR-72-10: `installments/service.py` — units truncation fix: последний транш = `total_units - sum(previous)` (TD-046)
- CR-72-11: `withdrawals/service.py` — `begin_nested()` в `create_withdrawal()` (TD-043)
- CR-72-12: `auth/service.py` — `ForbiddenError` → `UnauthorizedError` для деактивированных аккаунтов (TD-047, account leak)
- CR-72-13: `core/config.py` — production validation для `telegram_bot_token` (TD-044)
- CR-72-14: `pyproject.toml` — `filterwarnings` для pydantic-settings UserWarning

**Миграции (Sprint 7.2):**
- `2026_04_11_0014_referrals.py` — tables: referral_links, referral_attributions, users.referred_by (nullable → backfill → NOT NULL)
- `2026_04_11_0015_referrals_td.py` — UNIQUE на attribution.purchase_id, is_active на referral_links

**Критерий готовности:** Агент создаёт реферальные ссылки. При покупке по ссылке — комиссии L1/L2/L3 начисляются через ReferralProcessor. Органические покупки корректно обрабатываются. 250 тестов зелёные, 0 warnings, 0 критических issues, 0 предупреждений.

---

### ✅ Sprint 7.3: Leaderboard + Volume Bonuses

**Цель:** Рейтинг агентов и бонусные пулы.

**Задачи:**
- [x] `app/modules/commissions/__init__.py`
- [x] `app/modules/commissions/constants.py` — `PeriodType`, `current_month_start()`
- [x] `app/modules/commissions/models.py` — `LeaderboardSnapshot`, `VolumePayout`
- [x] `app/modules/commissions/schemas.py` — `LeaderboardEntry`, `LeaderboardResponse`, `CommissionEntry`, `CommissionListResponse`
- [x] `app/modules/commissions/service.py` — `get_leaderboard()`, `get_my_commissions()`
- [x] `app/modules/commissions/router.py` — 2 agent endpoints
- [x] `app/modules/commissions/worker.py` — `run_leaderboard_update()`, `run_monthly_payout()`, `run_quarterly_payout()`
- [x] `app/modules/processors/volume.py` — `VolumeProcessor` (чистая логика, не в ProcessorRegistry)
- [x] `leaderboard_worker` — asyncio.Task в `main.py` lifespan, интервал из конфига
- [x] `GET /api/v1/agent/leaderboard` — топ агентов (только agent)
- [x] `GET /api/v1/agent/commissions/me` — история комиссий + volume bonuses
- [x] Cron: месячный (top-20, 2%) + квартальный (top-10, 1%) бонусный пул
- [x] `tests/test_leaderboard.py` — 13 тестов

**Модели:**
```python
LeaderboardSnapshot:
    id: UUID
    agent_id: UUID         -- FK users.id
    rank: Integer          -- 1-based position
    volume_cents: BigInteger -- SUM(paid_cents) attributed purchases
    period_type: String(20)  -- "monthly" | "quarterly"
    period_start: Date       -- first day of period (e.g. 2026-04-01)
    snapshot_at: DateTime(tz) -- when computed
    is_final: Boolean        -- False=live (overwritten), True=frozen after payout
    created_at: DateTime(tz)

VolumePayout:
    id: UUID
    agent_id: UUID         -- FK users.id
    period_type: String(20)
    period_start: Date
    amount_cents: BigInteger -- bonus credited to agent
    rank: Integer           -- rank at payout time (denormalized)
    volume_cents: BigInteger -- volume at payout time (denormalized)
    pool_total_cents: BigInteger -- total pool for period
    created_at: DateTime(tz)
    -- UNIQUE(agent_id, period_type, period_start)
```

**VolumeProcessor (чистая логика, без I/O):**
```python
class VolumeProcessor:
    def distribute_pool(
        agents_ranked: list[AgentRank],
        pool_cents: int,
        platform_user_id: UUID,
        period_type: str,
    ) -> list[Transaction]:
        # Largest remainder method: sum(shares) == pool_cents exactly.
        # One Transaction per agent: Platform passive → Agent passive.
        # SUM=0 invariant per transaction.
```

Не зарегистрирован в `ProcessorRegistry` — триггерится worker'ом, не per-purchase. `AgentRank` — frozen dataclass (`agent_id`, `rank`, `volume_cents`).

**Worker (`commissions/worker.py`):**
- `run_leaderboard_update()`: каждые 60 мин → агрегирует объёмы из `Purchase JOIN ReferralAttribution`, DELETE+INSERT non-final snapshots (monthly + quarterly)
- `run_monthly_payout()`: при смене месяца → advisory lock → idempotency check → pool = `SUM(paid_cents) * bp // 10_000` → читает из snapshot (fallback на live) → `VolumeProcessor.distribute_pool()` → `VolumePayout` + `PassiveLedger`
- `run_quarterly_payout()`: аналогично, при смене квартала, top-10
- Platform balance check перед distribute — skip если `available < pool_cents`
- Deterministic tie-breaking: secondary sort by `agent_id`

**Endpoints:**
```
GET /api/v1/agent/leaderboard          -> LeaderboardResponse    (200, agent only)
GET /api/v1/agent/commissions/me       -> CommissionListResponse (200, agent only)
```

`GET /agent/commissions/me` читает из `PassiveLedger` по prefix `commission:` + `volume_bonus:`, обогащает JOIN'ами на `Purchase → Product + User` для display. Единый список комиссий и volume bonuses.

**Новые audit events:**
- `leaderboard.updated` — снапшот обновлён (actor_type: system)
- `volume_bonus.monthly_distributed` — месячный пул распределён
- `volume_bonus.quarterly_distributed` — квартальный пул распределён

**Config (новые настройки):**
```
volume_bonus_monthly_bp: int = 200           -- basis points (200 = 2.00%)
volume_bonus_quarterly_bp: int = 100         -- basis points (100 = 1.00%)
leaderboard_top_monthly: int = 20            -- top-N for monthly pool
leaderboard_top_quarterly: int = 10          -- top-N for quarterly pool
leaderboard_worker_interval_minutes: int = 60
```

**Миграции:**
- [x] `0016_commissions` — таблицы `leaderboard_snapshots` (2 индекса, FK), `volume_payouts` (UNIQUE constraint, FK)

**Результат:**
```
backend/app/modules/commissions/
├── __init__.py
├── constants.py        -- PeriodType, current_month_start()
├── models.py           -- LeaderboardSnapshot, VolumePayout
├── schemas.py          -- 2 response schemas
├── service.py          -- get_leaderboard, get_my_commissions
├── router.py           -- 2 agent endpoints
└── worker.py           -- leaderboard_update, monthly/quarterly payout

backend/app/modules/processors/
└── volume.py           -- VolumeProcessor (pure logic, largest remainder)

backend/tests/
└── test_leaderboard.py -- 13 tests
```

**Обновлённые файлы (Sprint 7.3):**
- `core/config.py` — `+volume_bonus_monthly_bp`, `+volume_bonus_quarterly_bp`, `+leaderboard_top_monthly`, `+leaderboard_top_quarterly`, `+leaderboard_worker_interval_minutes`
- `core/constants.py` — `+VOLUME_BONUS_MONTHLY`, `+VOLUME_BONUS_QUARTERLY` reason strings
- `main.py` — `+commissions_router`, `+_leaderboard_worker` asyncio.Task, `+leaderboard_task` cancel в shutdown
- `migrations/env.py` — `+LeaderboardSnapshot`, `+VolumePayout` imports
- `tests/helpers.py` — `+VolumePayout/LeaderboardSnapshot` cleanup в `_cleanup_user_related_data()`

**Решения реализации (Sprint 7.3):**
- P7-10: **VolumeProcessor ≠ ProcessorRegistry** — VolumeProcessor не зарегистрирован в ProcessorRegistry. Триггерится worker'ом (cron), не per-purchase. Чистая синхронная функция без I/O, тестируется без БД
- P7-11: **Largest remainder method** — `floor()` для всех долей, остаток раздаётся по 1 центу агентам с наибольшей дробной частью. Гарантирует `sum(shares) == pool_cents` (нет over-allocation)
- P7-12: **Advisory lock в `_distribute_pool`** — `pg_advisory_xact_lock(hash(period_type, period_start))` сериализует concurrent workers. Тот же паттерн что в `engine.py` и `withdrawals/service.py`
- P7-13: **Payout из snapshot, не re-aggregation** — `_distribute_pool` читает из `LeaderboardSnapshot`, fallback на live агрегацию только если снапшотов нет. Гарантирует совпадение отображаемого рейтинга и фактической выплаты
- P7-14: **Basis points вместо float** — `volume_bonus_monthly_bp: int = 200` (2%). Pool = `total * bp // 10_000` — чисто целочисленная арифметика, без float-ошибок
- P7-15: **Deterministic tie-breaking** — secondary sort by `agent_id` (UUID) при равном volume. Стабильно между запусками
- P7-16: **Platform balance check** — перед distribute проверяет `passive_balance >= pool_cents`. При нехватке — `logger.warning` + skip (не уходит в минус)
- P7-17: **No zip misalignment** — итерация по `transactions`, agent_id из `txn.entries[1].user_id` (credit entry), lookup через `agent_map` dict. Если агент пропущен процессором (share=0) — не смещает остальных
- P7-18: **Quarterly snapshots** — `run_leaderboard_update()` создаёт и monthly, и quarterly snapshots. `is_final=True` при выплате — архив
- P7-19: **volume_cents в leaderboard — by design** — агенты видят точные объёмы продаж друг друга (бизнес-решение, отражено в мокапах)

**Критерий готовности:** Лидерборд обновляется каждые 60 мин (monthly + quarterly). Бонусные пулы начисляются при смене месяца/квартала. Advisory lock защищает от двойной выплаты. Largest remainder гарантирует точное распределение пула. 263 теста зелёные, 0 warnings, 0 критических issues, 0 предупреждений.

---

## PHASE 8: Notifications

---

### ✅ Sprint 8.1: Notification Models + Processor

**Цель:** Двухуровневая архитектура уведомлений.

**Задачи:**
- [x] `app/modules/notifications/__init__.py`
- [x] `app/modules/notifications/constants.py` — `NotificationStatus`, `DeliveryStatus`, `DeliveryChannel`, `NotificationType`, `TargetType`
- [x] `app/modules/notifications/models.py` — `Notification`, `NotificationDelivery`
- [x] `app/modules/notifications/resolver.py` — `resolve_targets()` с registry по target_type
- [x] `app/modules/notifications/formatters.py` — `ChannelFormatter` Protocol + `StubFormatter`
- [x] `app/modules/notifications/service.py` — `create_notification()`, `resolve_notification()`, `deliver_notification()`, `rollup_notification()`
- [x] `app/modules/notifications/processor.py` — трёхстадийный pipeline (resolve -> deliver -> rollup), per-notification session, FOR UPDATE SKIP LOCKED
- [x] `app/modules/notifications/worker.py` — `run_notification_batch()`
- [x] Background worker `_notification_worker` в `main.py` lifespan
- [x] Cron очистка: `cleanup_expired_notifications()` удаляет `expiry_at < now()` у доставленных (hard-delete, CASCADE на deliveries)
- [x] `tests/test_notifications.py` — 18 тестов

**Модели:**
```python
Notification:  -- channel-agnostic, одна запись на событие
    id: UUID
    type: str          -- indexed; system | transaction | commission | news | installment
    title: str
    body: str
    target_type: str   -- user | role | all
    target_value: str  -- user:<uuid> | role:agent | *
    action_data: JSONB | None  -- {"action": "open_purchase", "params": {"id": "uuid"}, "_channels": ["in_app"]}
    priority: int      -- default 5 (1=highest)
    scheduled_at: datetime
    expiry_at: datetime | None
    status: enum       -- pending | processing | sent | partial_sent | failed | expired
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
    -- UNIQUE(notification_id, user_id, channel)
```

**Архитектура pipeline:**
```
resolve:  Notification -> N NotificationDelivery (по target_type/target_value)
deliver:  NotificationDelivery -> ChannelFormatter -> внешний сервис
rollup:   NotificationDelivery statuses -> Notification.status
```

**Resolver (`notifications/resolver.py`):**
- `resolve_targets(session, target_type, target_value)` -> `list[UUID]`
- Registry `_RESOLVERS`: `user` -> `_resolve_user()`, `role` -> `_resolve_role()`, `all` -> `_resolve_all()`
- Только `is_active=True`, исключая `role=platform`
- Расширяемый: новые target types добавляются в `_RESOLVERS` dict

**Formatters (`notifications/formatters.py`):**
- `ChannelFormatter` Protocol: `async deliver(notification, delivery) -> bool`
- `StubFormatter`: логирует и возвращает True (Sprint 8.2: TelegramFormatter, EmailFormatter)
- `get_formatter(channel)` — registry с fallback на StubFormatter

**Service (`notifications/service.py`):**
- `create_notification()` — валидация type/target_type/channels против enum frozenset, channels хранятся в `action_data["_channels"]`
- `resolve_notification()` — идемпотентен: если deliveries уже существуют (retry), пропускает resolve
- `deliver_notification()` — вызывает formatter для каждой pending delivery, increment attempts, max_attempts из config
- `rollup_notification()` — all sent -> sent, all failed -> failed, mix -> partial_sent, any pending -> stays processing

**Processor (`notifications/processor.py`):**
- `process_pending_notifications()` — выбирает PENDING + PROCESSING (retry), per-notification session, FOR UPDATE SKIP LOCKED
- `cleanup_expired_notifications()` — DELETE WHERE expiry_at < now AND status IN (sent, partial_sent, expired)
- Expire query ловит и PENDING, и PROCESSING (застрявшие не накапливаются)

**Worker (`notifications/worker.py`):**
- `run_notification_batch()` — orchestrator: process_pending + cleanup
- Processor управляет сессиями, worker просто вызывает

**Rollup статусы (расширение ТЗ):**
- `partial_sent` — добавлен для диагностики: mix sent + failed deliveries

**Endpoints:** Нет (Sprint 8.3)

**Config (новые настройки):**
```
notification_max_delivery_attempts: int = 3
notification_worker_interval_minutes: int = 1
```

**Миграции:**
- [x] `0017_notifications` — таблицы `notifications` (3 индекса), `notification_deliveries` (4 индекса, 2 FK CASCADE)
- [x] `0018_notifications_constraints` — fix JSON→JSONB (`action_data`, `channel_options`), CHECK constraints на status/type/channel, UNIQUE на `(notification_id, user_id, channel)`
- [x] `0019_notifications_target_type` — CHECK constraint на `target_type`

**Результат:**
```
backend/app/modules/notifications/
├── __init__.py
├── constants.py        -- NotificationStatus, DeliveryStatus, DeliveryChannel, NotificationType, TargetType
├── models.py           -- Notification, NotificationDelivery
├── resolver.py         -- resolve_targets (registry pattern)
├── formatters.py       -- ChannelFormatter Protocol, StubFormatter, get_formatter()
├── service.py          -- create, resolve (idempotent), deliver, rollup
├── processor.py        -- pipeline orchestrator (per-notification session, FOR UPDATE SKIP LOCKED)
└── worker.py           -- run_notification_batch (calls processor)

backend/tests/
└── test_notifications.py -- 18 tests
```

**Обновлённые файлы (Sprint 8.1):**
- `core/config.py` — `+notification_worker_interval_minutes` (секция Notifications обновлена)
- `main.py` — `+notification_worker` import, `+_notification_worker` asyncio.Task, `+notification_task` cancel в shutdown
- `migrations/env.py` — `+Notification`, `+NotificationDelivery` imports (раскомментированы)
- `tests/helpers.py` — `+NotificationDelivery` cleanup в `_cleanup_user_related_data()`

**Решения реализации (Sprint 8.1):**
- P8-01: **Channels в action_data** — `_channels` хранится в `action_data` JSONB вместо отдельной колонки. Channels immutable после создания, internal key контролируется только `create_notification()`. Отдельная колонка = миграция + ArrayType ради теоретической чистоты. Пересмотреть в Sprint 8.2 если понадобится (TD-053)
- P8-02: **Hard-delete в cleanup** — `DELETE FROM notifications` удаляет expired+delivered уведомления. Уведомления ≠ финансовые данные. Все события логируются через structlog. Soft-delete = `is_deleted` фильтр в каждом запросе + захламление таблицы (TD-054)
- P8-03: **Formatter timeouts** — StubFormatter мгновенный, таймаут бессмысленен. Sprint 8.2: `asyncio.wait_for(formatter.deliver(...), timeout=30)` при реальных TelegramFormatter/EmailFormatter (TD-055)
- P8-04: **Per-notification session** — каждое уведомление обрабатывается в своей сессии/транзакции. Сбой на #5 не откатывает #1-4. Паттерн из installment_worker (TD-042)
- P8-05: **FOR UPDATE SKIP LOCKED** — предотвращает double-processing при multi-worker. Второй worker пропускает заблокированные строки → `scalar_one_or_none()` = None → continue
- P8-06: **Retry через PENDING + PROCESSING** — processor выбирает оба статуса. PROCESSING = delivery с attempts < max ещё PENDING. `resolve_notification` идемпотентен (проверяет existing deliveries)
- P8-07: **Expiry ловит PROCESSING** — expire query фильтрует PENDING + PROCESSING. Застрявшие PROCESSING-уведомления протухнут, не накопятся
- P8-08: **Валидация в create_notification** — type, target_type, channels проверяются против frozenset из enum values. `BadRequestError` с информативным сообщением вместо IntegrityError (500)

**Критерий готовности:** Уведомления создаются, обрабатываются pipeline (resolve → deliver → rollup). Retry работает для PROCESSING. FOR UPDATE SKIP LOCKED защищает от double-delivery. Валидация на уровне сервиса + CHECK constraints на уровне БД. 281 тест зелёный, 0 warnings, 0 критических issues, 0 предупреждений.

---

### ✅ Sprint 8.2: Email + Telegram Formatters

**Цель:** Реальная доставка уведомлений.

**Задачи:**
- [x] `app/modules/notifications/templates/en.yaml` — шаблоны для 5 типов × 2 канала (telegram + email)
- [x] `app/modules/notifications/template_engine.py` — SafeDict, YAML loading, language fallback, path traversal protection
- [x] `app/modules/notifications/formatters.py` — `TelegramFormatter` (aiogram, send-only), `EmailFormatter` (SMTP primary + Mailgun fallback, high-secured domains)
- [x] Lazy init: real token/host -> real formatter, TEST/empty -> StubFormatter
- [x] Permanent failure handling (bot blocked -> immediate failed, attempts не растут)
- [x] Concurrent delivery: `asyncio.gather` + `Semaphore(20)` (broadcast safety)
- [x] `POST /api/v1/staff/notifications/templates/reload` — Staff reload templates (translation_edit permission)
- [x] `tests/test_notification_delivery.py` — 18 тестов
- [x] Mail server: Postfix + OpenDKIM в `install_cbshome.sh`
- [x] Config: EMAP удалён, SMTP + Mailgun fallback, `high_secured_domains`
- [x] Security: `_sanitize_error()`, `_mask_email()`, `lang.isalnum()` path traversal protection
- [x] Bug fix: `config.py` validator indentation (crypto/telegram/return вынесены на верхний уровень)

**Архитектура доставки:**
```
EmailFormatter:
  recipient domain in high_secured_domains → Mailgun only
  recipient domain NOT in list → SMTP → fallback Mailgun

TelegramFormatter:
  user.credentials["telegram"]["id"] → aiogram Bot.send_message()
  403 Forbidden / chat not found → PermanentDeliveryError (no retry)
```

**Template Engine:**
- `SafeDict` — `str.format_map()` без KeyError на отсутствующих переменных
- YAML-шаблоны: `{type}.{channel}.{field}` (e.g. `transaction.email.subject`)
- Language fallback: запрошенный → `en` → raw fallback string
- `lang.isalnum()` — защита от path traversal
- Module-level cache + staff reload endpoint

**Concurrent Delivery (review fix):**
- `asyncio.gather` + `Semaphore(20)` вместо sequential loop
- External API calls (aiogram, aiosmtplib, httpx) идут параллельно
- SQLAlchemy session не шарится между корутинами
- `_DeliveryOutcome` — результат применяется к delivery объектам последовательно после gather
- 1000 users × 30s timeout ÷ 20 concurrent = 25 мин worst case (vs 8.3 часов sequential)

**Mail Server (install_cbshome.sh):**
- Postfix: send-only, `inet_interfaces = all` (UFW блокирует 25 снаружи), Docker subnet `172.16.0.0/12` в mynetworks
- OpenDKIM: 2048-bit DKIM key, milter integration, автогенерация + вывод TXT-записи
- `DEBIAN_FRONTEND=noninteractive` + `debconf-set-selections` перед установкой
- Docker: `extra_hosts: host.docker.internal:host-gateway`, `SMTP_HOST=host.docker.internal`

**Config (изменения):**
```
# Удалено
emap_api_key (EMAP убран полностью)

# Добавлено
smtp_host: str = "host.docker.internal"
smtp_port: int = 25
smtp_user: str = ""
smtp_password: str = ""
smtp_from_email: str = "noreply@mail.cbshome.org"
smtp_use_tls: bool = False
high_secured_domains: str = ""  # comma-separated

# Изменено
mailgun_domain: str = "mail.cbshome.org"  # was ""
mailgun_api_url: str = "https://api.mailgun.net"  # v3.3: EU domains use https://api.eu.mailgun.net
```

**Endpoints:**
```
POST /api/v1/staff/notifications/templates/reload -> 204 (translation_edit permission)
```

**Результат:**
```
backend/app/modules/notifications/
├── __init__.py
├── constants.py        -- NotificationStatus, DeliveryStatus, DeliveryChannel, NotificationType, TargetType
├── models.py           -- Notification, NotificationDelivery
├── resolver.py         -- resolve_targets (registry pattern)
├── formatters.py       -- ChannelFormatter, StubFormatter, TelegramFormatter, EmailFormatter, _mask_email, _sanitize_error
├── template_engine.py  -- SafeDict, load/reload/render, YAML cache
├── service.py          -- create, resolve, deliver (gather+semaphore), rollup, _DeliveryOutcome
├── processor.py        -- pipeline orchestrator (per-notification session, FOR UPDATE SKIP LOCKED)
├── staff_router.py     -- POST /templates/reload
├── worker.py           -- run_notification_batch (calls processor)
└── templates/
    └── en.yaml         -- 5 types × 2 channels (telegram body, email subject+body)

backend/tests/
├── test_notifications.py          -- 18 tests (Sprint 8.1)
└── test_notification_delivery.py  -- 18 tests (Sprint 8.2)
```

**Обновлённые файлы (Sprint 8.2):**
- `core/config.py` — EMAP удалён, +SMTP settings, +high_secured_domains, +high_secured_domain_list property, validator indentation fix
- `main.py` — +staff_notifications_router import + include
- `pyproject.toml` — +aiosmtplib
- `.env.example` — EMAP удалён, +SMTP settings, +HIGH_SECURED_DOMAINS
- `docker-compose.yml` — +extra_hosts для app service (Docker→host Postfix)
- `scripts/install_cbshome.sh` — EMAP удалён, +MAIL_DOMAIN, +Postfix/OpenDKIM section, +SMTP .env template

**Решения реализации (Sprint 8.2):**
- P8-09: **Mailgun primary, SMTP fallback** (v3.3: inverted from original SMTP-primary). Mailgun HTTP API → primary (50K/month free, EU endpoint `api.eu.mailgun.net`). SMTP Postfix → fallback (own server, may be blocked by hosting provider). `send_email()` tries Mailgun first, falls back to SMTP on failure. `high_secured_domains` removed — Mailgun handles all domains. Config: `mailgun_api_url` setting for US/EU endpoint selection. `start_tls` explicitly set to `use_tls` value (prevents auto-negotiate with self-signed Postfix cert)
- P8-10: **Concurrent delivery** — `asyncio.gather` + `Semaphore(20)`. Formatter.deliver() не трогает SQLAlchemy session — только внешние API calls. Результаты применяются последовательно. TD-057 для dedicated delivery worker при 10K+ юзеров
- P8-11: **PermanentDeliveryError** — bot blocked (403), chat not found, no credentials → immediate FAILED, attempts не инкрементируются. Transient errors → retry до max_attempts
- P8-12: **Template engine** — `str.format_map(SafeDict)`, no SSTI risk. `yaml.safe_load()`. `lang.isalnum()` prevents path traversal
- P8-13: **Error sanitization** — `_sanitize_error()` обрезает после password/token/secret. `_mask_email()` маскирует PII в логах
- P8-14: **Config validator fix** — crypto_webhook_secret, telegram_bot_token, return self вынесены из `if not kyc_webhook_secret` на верхний уровень. Pydantic warning устранён

**Критерий готовности:** Уведомления приходят в Telegram и email. SMTP + Mailgun fallback. Postfix + OpenDKIM автоматически настраиваются при установке. 299 тестов зелёных, 0 warnings, 0 критических issues, 0 предупреждений.

---

### ✅ Sprint 8.3: Notification REST Endpoints

**Цель:** API для управления уведомлениями на фронте.

**Задачи:**
- [x] `GET /api/v1/notifications` — список доставок текущего юзера (пагинация 20, фильтры по type/channel)
- [x] `GET /api/v1/notifications/unread-count` — badge counter (deliveries где status=sent AND не прочитано)
- [x] `POST /api/v1/notifications/{delivery_id}/read` — отметить delivery прочитанной
- [x] `POST /api/v1/notifications/read-all` — отметить все delivery текущего юзера прочитанными
- [x] `tests/test_notification_endpoints.py` — 8 тестов

**Endpoints:**
```
GET  /api/v1/notifications                -> NotificationListResponse  (200)
GET  /api/v1/notifications/unread-count   -> UnreadCountResponse       (200)
POST /api/v1/notifications/{id}/read      -> 204
POST /api/v1/notifications/read-all       -> ReadAllResponse           (200)
```

**Миграции:**
- [x] `0020_delivery_read_at` — `read_at: DateTime(timezone=True)` на `notification_deliveries`
- [x] `0021_delivery_inbox_index` — partial composite index `ix_deliveries_user_inbox` на `(user_id, status, read_at, sent_at DESC) WHERE status = 'sent'`

**Результат:**
```
backend/app/modules/notifications/
├── schemas.py          -- NotificationDeliveryResponse, NotificationListResponse, UnreadCountResponse, ReadAllResponse (NEW)
├── router.py           -- 4 public endpoints (NEW)
├── service.py          -- +list_user_deliveries, get_unread_count, mark_delivery_read, mark_all_read
└── models.py           -- +read_at on NotificationDelivery

backend/tests/
└── test_notification_endpoints.py -- 8 tests (NEW)
```

**Обновлённые файлы (Sprint 8.3):**
- `main.py` — +notifications_router import + include
- `models.py` — +read_at field на NotificationDelivery

**Решения реализации (Sprint 8.3):**
- P8-15: **read_at для прочтения** — `DateTime(timezone=True), nullable=True`. NULL = unread. Нет отдельного `is_read` boolean — timestamp информативнее и однозначен
- P8-16: **JOIN для обогащения** — `list_user_deliveries` делает `select(NotificationDelivery, Notification).join()` для получения title/body/type/priority из parent Notification. Response собирается из dict, не из ORM напрямую
- P8-17: **`_channels` фильтрация** — `action_data` в ответе фильтрует ключи с `_` префиксом: `{k: v for k, v in items() if not k.startswith("_")} or None`. Предотвращает утечку internal routing metadata на фронт
- P8-18: **Partial inbox index** — `WHERE status = 'sent'` покрывает все три горячих паттерна: list, unread-count, mark-all-read. `sent_at DESC` для ORDER BY без дополнительного sort
- P8-19: **mark_all_read атомарный UPDATE** — `UPDATE ... WHERE user_id=? AND status='sent' AND read_at IS NULL`. Возвращает `rowcount` для фронта (badge обнуление без дополнительного запроса)
- P8-20: **mark_delivery_read идемпотентный** — 204 и для уже прочитанных, и для только что отмеченных. 404 если delivery не существует или чужая (IDOR guard: `WHERE id=? AND user_id=?`)

**Критерий готовности:** Фронт работает с `NotificationDelivery`, а не с `Notification` напрямую. 307 тестов зелёных, 0 warnings, 0 критических issues, 0 предупреждений.

---

## PHASE 9: Posts + Extras

---

### ✅ Sprint 9.1: Posts + Events

**Цель:** Единый модуль контента для платформы и компаний.

**Архитектурный принцип:** Платформенные новости и посты блога компаний — это одна и та же
сущность `Post` с разным `owner_type`. Единый модуль `posts/`, единый рендер на фронте,
единая лента с фильтрацией по владельцу. Staff создаёт посты как от имени платформы,
так и от имени конкретной компании.

**Задачи:**
- [x] `app/modules/posts/constants.py` — `OwnerType` (platform, company)
- [x] `app/modules/posts/models.py` — `Post`, `PostDismiss`, `Event`
- [x] `app/modules/posts/schemas.py` — 8 schemas (Create/Update/Response для Post и Event, List responses)
- [x] `app/modules/posts/service.py` — CRUD + баннерная логика + dismiss (11 функций)
- [x] Public endpoints:
  - `GET /api/v1/posts` — лента постов (фильтры: `owner_type`, `company_id`, `tag`)
  - `GET /api/v1/posts/{id}` — детали поста
  - `GET /api/v1/events` — список событий
  - `GET /api/v1/events/upcoming` — ближайшие 30 дней (limit 100)
  - `POST /api/v1/posts/{id}/dismiss` — закрыть баннер
- [x] Staff endpoints:
  - `POST /api/v1/staff/posts` — создать пост (платформа или от имени компании)
  - `PATCH /api/v1/staff/posts/{id}` — редактировать (partial update)
  - `DELETE /api/v1/staff/posts/{id}` — soft-delete
  - `POST /api/v1/staff/events` — создать событие
  - `PATCH /api/v1/staff/events/{id}` — редактировать (partial update)
  - `DELETE /api/v1/staff/events/{id}` — soft-delete
- [x] `staff/constants.py` — `+content_manage: True` permission
- [x] `tests/test_posts.py` — 12 тестов

**Модели:**
```python
Post:
    id: UUID
    owner_type: str          -- CHECK: platform | company
    owner_id: UUID | None    -- NULL если platform, FK company_profiles.id RESTRICT если company
    title: str(500)
    body: str(50000)         -- markdown или HTML
    cover_url: str | None    -- validated: http:// or https:// only
    tags: JSONB              -- ["investment", "growth"] -- массив строк, max 50 chars per tag
    is_banner: bool          -- показывать как баннер на главной
    is_published: bool
    published_at: datetime | None  -- set on publish transition
    created_by: UUID         -- FK users.id RESTRICT (staff_id)
    is_deleted: bool         -- soft delete
    created_at, updated_at

PostDismiss:                 -- факт закрытия баннера конкретным юзером
    id: UUID
    post_id: UUID            -- FK posts.id CASCADE
    user_id: UUID            -- FK users.id CASCADE
    dismissed_at: datetime
    UNIQUE(post_id, user_id)

Event:
    id: UUID
    title: str(500)
    description: str(5000) | None
    cover_url: str | None    -- validated: http:// or https://
    starts_at: datetime
    ends_at: datetime | None -- validated: ends_at > starts_at
    location: str(500) | None
    url: str(2000) | None    -- validated: http:// or https://
    is_published: bool
    created_by: UUID         -- FK users.id RESTRICT (staff_id)
    is_deleted: bool         -- soft delete
    created_at, updated_at
```

**Endpoints:**
```
-- Public (get_optional_user — anonymous allowed):
GET  /api/v1/posts                -> PostListResponse      (200)
GET  /api/v1/posts/{id}           -> PostResponse           (200)
GET  /api/v1/events               -> EventListResponse      (200)
GET  /api/v1/events/upcoming      -> list[EventResponse]    (200)

-- Public (auth required):
POST /api/v1/posts/{id}/dismiss   -> 204

-- Staff (content_manage permission):
POST   /api/v1/staff/posts        -> PostResponse           (201)
PATCH  /api/v1/staff/posts/{id}   -> PostResponse           (200)
DELETE /api/v1/staff/posts/{id}   -> 204
POST   /api/v1/staff/events       -> EventResponse          (201)
PATCH  /api/v1/staff/events/{id}  -> EventResponse          (200)
DELETE /api/v1/staff/events/{id}  -> 204
```

**Миграции:**
- [x] `0022_posts` — таблицы `posts` (3 индекса, CHECK owner_type, 2 FK RESTRICT), `post_dismissals` (UNIQUE, 2 FK CASCADE), `events` (1 индекс, 1 FK RESTRICT)

**Результат:**
```
backend/app/modules/posts/
├── __init__.py
├── constants.py        -- OwnerType (platform, company)
├── models.py           -- Post (JSONBMixin), PostDismiss, Event
├── schemas.py          -- 8 schemas (Literal owner_type, URL validators, tag constraints, date validator)
├── service.py          -- 11 functions (CRUD posts + events, dismiss, list, upcoming)
├── router.py           -- 5 public endpoints (posts_router + events_router)
└── staff_router.py     -- 6 staff endpoints (staff_posts_router + staff_events_router)

backend/tests/
└── test_posts.py       -- 12 tests
```

**Обновлённые файлы (Sprint 9.1):**
- `staff/constants.py` — `+content_manage: True` в DEFAULT_STAFF_PERMISSIONS
- `main.py` — +posts_router, events_router, staff_posts_router, staff_events_router
- `migrations/env.py` — +Post, PostDismiss, Event imports (раскомментированы)
- `tests/helpers.py` — +PostDismiss, Post, Event cleanup в `_cleanup_user_related_data()` (два места: по created_by + по owner_id в company block)

**Решения реализации (Sprint 9.1):**
- P9-01: **Soft delete** — `is_deleted: bool` вместо hard delete. Все запросы фильтруют `is_deleted.is_(False)`. Staff DELETE → `is_deleted = True`. Посты — user-facing content, удаление необратимо
- P9-02: **PATCH вместо PUT** — partial update с `exclude_unset=True`, единообразно с остальным проектом. Позволяет точечные операции: "опубликовать", "снять баннер", "поменять заголовок"
- P9-03: **get_optional_user на публичных endpoints** — анонимный доступ разрешён (незалогиненные видят новости). `is_dismissed` = False для анонимов, LEFT JOIN PostDismiss для авторизованных
- P9-04: **Dismiss SAVEPOINT** — `async with session.begin_nested()` + INSERT + flush. IntegrityError на UNIQUE → только savepoint откатывается, outer transaction intact. Паттерн из payments/withdrawals
- P9-05: **content_manage permission** — новый ключ в DEFAULT_STAFF_PERMISSIONS. Existing admins автоматически получают (get_effective_permissions мержит с дефолтами). Без миграции на StaffProfile
- P9-06: **Literal owner_type** — Pydantic `Literal["platform", "company"]` вместо str + service validation. 422 вместо 400 — стандартное Pydantic-поведение
- P9-07: **URL validation** — shared `_validate_url()` field_validator на cover_url и event.url. `startswith(("http://", "https://"))` — блокирует `javascript:`, `data:` XSS-векторы
- P9-08: **Tag constraints** — `Annotated[str, Field(max_length=50)]` per tag. Защита от oversized tags и `<script>` injection (длина ограничена)
- P9-09: **Date validation** — `model_validator(mode="after")`: `ends_at > starts_at` на Create. На Update — только если оба поля предоставлены (partial update может менять только одно)
- P9-10: **Tag filter** — JSONB `@>` operator: `Post.tags.op("@>")(json.dumps([tag]))`. Один тег — exact match в массиве
- P9-11: **published_at transition** — устанавливается при первом is_published=True (и в create, и в update). Не сбрасывается при unpublish
- P9-12: **list_upcoming_events limit(100)** — safety cap на unbounded query (30 дней). Prevents DoS через массовое создание событий

**Критерий готовности:** Staff создаёт посты платформы и постит от имени компаний. Инвесторы видят единую ленту с фильтрацией. Баннеры закрываются и не показываются повторно. Анонимные пользователи видят published посты. 319 тестов зелёных, 0 warnings, 0 критических issues, 0 предупреждений.

---

### ✅ Sprint 9.2: Dashboard + Portfolio + Certificates

**Цель:** Агрегированные данные для главного экрана + сертификаты покупок.

**Задачи:**
- [x] `app/modules/dashboard/` — модуль Dashboard (schemas, service, router)
- [x] `app/modules/portfolio/` — модуль Portfolio (schemas, service, router)
- [x] `app/modules/purchases/certificate_service.py` — генерация HTML/PDF сертификатов
- [x] `app/modules/purchases/certificate_router.py` — 2 endpoints (view + email)
- [x] `app/modules/purchases/templates/certificate.html` — Jinja2 шаблон
- [x] `app/core/email.py` — утилита отправки email (извлечено из formatters.py)
- [x] `tests/test_dashboard.py` — 11 тестов
- [x] Refactor: `notifications/formatters.py` — EmailFormatter делегирует в `core/email.py`
- [x] `pyproject.toml` — +jinja2, +xhtml2pdf
- [x] `Dockerfile` — +gcc/pkg-config/libcairo2-dev (builder), +libcairo2 (runtime)

**Dashboard endpoint:**
- `GET /api/v1/dashboard/summary` — active_balance (frozen/confirmed), passive_balance (frozen/confirmed), total_invested_cents, total_units, current_value_cents, companies_count, companies[] (company_id, company_name, logo_url, total_units, invested_cents, current_value_cents)

**Portfolio endpoints:**
- `GET /api/v1/portfolio/me` — позиции по компаниям (company_id, company_name, logo_url, total_units, sale_units, gift_units, total_paid_cents, avg_price_cents, current_price_cents, current_value_cents, purchases_count). Без пагинации (компаний мало), сортировка по current_value DESC
- `GET /api/v1/portfolio/me/company/{id}` — flat aggregate + пагинированный список purchases (id, product_id, legal_basis, units, paid_cents, price_per_unit_cents, status, created_at)

**Certificate endpoints:**
- `GET /api/v1/purchases/{id}/certificate` — HTML-страница сертификата (Content-Type: text/html). Фронт показывает в iframe, пользователь сохраняет как PDF через Ctrl+P
- `POST /api/v1/purchases/{id}/certificate/email` — генерирует PDF (xhtml2pdf), отправляет на email инвестора через SMTP/Mailgun. Rate-limited per user

**Endpoints:**
```
GET  /api/v1/dashboard/summary                  -> DashboardSummaryResponse  (200)
GET  /api/v1/portfolio/me                        -> PortfolioResponse         (200)
GET  /api/v1/portfolio/me/company/{id}           -> CompanyPositionDetailResponse (200)
GET  /api/v1/purchases/{id}/certificate          -> HTMLResponse              (200)
POST /api/v1/purchases/{id}/certificate/email    -> 204
```

**Результат:**
```
backend/app/core/
└── email.py                -- send_smtp, send_mailgun, build_message, send_email, mask_email

backend/app/modules/dashboard/
├── __init__.py
├── schemas.py              -- BalanceResponse, CompanySummaryResponse, DashboardSummaryResponse
├── service.py              -- get_dashboard_summary (ledger balances + purchase aggregation)
└── router.py               -- 1 endpoint (investor_dashboard_router)

backend/app/modules/portfolio/
├── __init__.py
├── schemas.py              -- CompanyPositionResponse, PortfolioResponse, PurchaseItemResponse, CompanyPositionDetailResponse
├── service.py              -- get_portfolio, get_company_position (conditional SUM, case expressions)
└── router.py               -- 2 endpoints (portfolio_router)

backend/app/modules/purchases/
├── certificate_service.py  -- load_certificate_data (single JOIN), render_certificate_html, generate_certificate_pdf, send_certificate_email
├── certificate_router.py   -- 2 endpoints (certificate_router)
└── templates/
    └── certificate.html    -- Jinja2 шаблон (A4 landscape, заглушки для seal/signature)

backend/tests/
└── test_dashboard.py       -- 11 tests
```

**Обновлённые файлы (Sprint 9.2):**
- `notifications/formatters.py` — рефакторинг: `_send_smtp`, `_send_mailgun`, `_mask_email` извлечены в `core/email.py`. EmailFormatter делегирует, сохраняя __init__ params (тесты не сломаны)
- `pyproject.toml` — +`jinja2>=3.1.0,<4.0`, +`xhtml2pdf>=0.2.13,<1.0`
- `Dockerfile` — builder: +gcc, pkg-config, libcairo2-dev (для pycairo). runtime: +libcairo2
- `main.py` — +investor_dashboard_router, +portfolio_router, +certificate_router

**Решения реализации (Sprint 9.2):**
- P9-20: **Два модуля** — dashboard и portfolio разделены (разные экраны на фронте, разная скорость изменений). Оба read-only, без миграций
- P9-21: **avg_price_cents** — `round(SUM(paid_cents) / SUM(units WHERE legal_basis='sale'))`. Gift units не участвуют. Если sale_units=0 → avg_price=0. Banker's rounding для точности
- P9-22: **current_value_cents** — `total_units × company.price_per_unit_cents` (текущая цена компании, не цена покупки). JOIN с CompanyProfile в каждом запросе
- P9-23: **Доступ без проверки роли** — `get_current_user` без role guard. Агенты тоже могут иметь покупки. Пустой портфель → пустой ответ, не 403
- P9-24: **Сертификат HTML** — Jinja2 с `autoescape=True` (XSS protection). xhtml2pdf для PDF (CSS 2.1, без системных зависимостей кроме libcairo2). Заглушки для печати/подписи компании (будут при доработке CompanyProfile)
- P9-25: **Два endpoint для сертификата** — GET возвращает HTML (браузер → Ctrl+P → PDF), POST отправляет PDF на email. Серверная генерация PDF только для email (не на каждый просмотр)
- P9-26: **core/email.py рефакторинг** — SMTP/Mailgun логика извлечена из EmailFormatter для переиспользования. `send_email()` — convenience wrapper читающий settings. EmailFormatter вызывает `send_smtp()`/`send_mailgun()` с явным конфигом (тесты сохранены)
- P9-27: **Certificate rate limit** — `check_rate_limit(f"cert_email:{user.id}")` на POST endpoint. Тот же Redis Lua script что и auth (5 req / 60s per user)
- P9-28: **Single JOIN в load_certificate_data** — `select(Purchase, User, CompanyProfile, Product).join(...).join(...).join(...)` вместо 4 последовательных SELECT
- P9-29: **CertificateData без User** — хранит `investor_name: str` и `investor_email: str | None` вместо полного User объекта. Credentials (password_hash) не задерживаются в памяти
- P9-30: **Avatar compatibility** — `get_current_user` возвращает target user в avatar mode. Проверка `purchase.investor_id == user_id` работает автоматически. Не нужен отдельный avatar guard

**Критерий готовности:** Фронт получает данные для Dashboard и портфеля. Инвестор просматривает сертификат в HTML и получает PDF на email. 330 тестов зелёных, 0 warnings, 0 критических issues, 0 предупреждений.

---

**Phase 9 завершена.** 16 endpoints (11 posts/events + 5 dashboard/portfolio/certificate), 23 теста Phase 9 (+307 Phase 0-8 = 330 total), 1 миграция (итого 22). CMS (posts/events), investor dashboard, portfolio, certificates (HTML+PDF+email), core/email.py refactor.

---

## PHASE 10: Розетки + Полировка

---

### ✅ Sprint 10.1: Розетки (Protocol-only)

**Цель:** Заглушки для будущих фич. Интерфейс определён, логика не реализована.

**Задачи:**
- [x] `app/modules/tokens/__init__.py` + `app/modules/tokens/interface.py` — `TokenServiceProtocol`, stub dataclasses `TokenIssuance`, `TokenHolding`
- [x] `app/modules/ai_trainer/__init__.py` + `app/modules/ai_trainer/interface.py` — `AITrainerProtocol`, stub dataclasses `TrainingQuestion`, `EvaluationResult`
- [x] `app/modules/payments/providers/__init__.py` + `app/modules/payments/providers/interface.py` — `PaymentProviderProtocol`, stub dataclasses `PaymentIntent`, `ProviderPaymentStatus`
- [x] `app/modules/auto_translate/__init__.py` + `app/modules/auto_translate/interface.py` — `AutoTranslateProtocol`
- [x] `GET /api/v1/transactions/export` — заглушка (501 Not Implemented)

**Решения реализации:**
- P10-01: **Stub dataclasses `frozen=True`** — по паттерну `DepositAddress` из `payments/interface.py`. Чистые type-контракты без I/O и state
- P10-02: **`ProviderPaymentStatus`** — намеренно НЕ `PaymentStatus`, чтобы не коллидировать с `payments/constants.py:PaymentStatus` (lifecycle states). Задокументировано в docstring
- P10-03: **`AutoTranslateProtocol`** — минимальная сигнатура `translate(text, source_lang, target_lang) -> str`. Расширится в Phase 2 при реальной интеграции
- P10-04: **Export endpoint перед `/{transaction_id}`** — иначе FastAPI матчит "export" как UUID path parameter. `response_model=None` + `raise HTTPException(501)` (не через `CBSError` — это инфраструктурный сигнал, не бизнес-ошибка)
- P10-05: **`main.py` не изменён** — новые модули не имеют роутеров, export endpoint живёт в уже подключённом `transactions_router`

**Endpoints:**
```
GET /api/v1/transactions/export  -> HTTPException(501, "Not Implemented")  (requires auth)
```

**Результат:**
```
backend/app/modules/tokens/
├── __init__.py
└── interface.py        -- TokenServiceProtocol, TokenIssuance, TokenHolding

backend/app/modules/ai_trainer/
├── __init__.py
└── interface.py        -- AITrainerProtocol, TrainingQuestion, EvaluationResult

backend/app/modules/payments/providers/
├── __init__.py
└── interface.py        -- PaymentProviderProtocol, PaymentIntent, ProviderPaymentStatus

backend/app/modules/auto_translate/
├── __init__.py
└── interface.py        -- AutoTranslateProtocol

backend/app/modules/transactions/
└── router.py           -- +GET /export (501 stub)
```

**Обновлённые файлы (Sprint 10.1):**
- `transactions/router.py` — `+HTTPException` import, `+GET /export` endpoint (перед `/{transaction_id}`)

**Критерий готовности:** Все интерфейсы определены. `GET /transactions/export` возвращает 501. 330 тестов зелёных, 0 warnings, 0 критических issues, 0 предупреждений.

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

## R1 + R2 Refactor — Backend artefacts (iter 2.1 — iter 2.7b)

Серия refactor-итераций R1 (Investor Market & Staff) + R2 (Company Attachments/Templates/Purchase docs) полностью закрыта. Этот раздел сводит backend артефакты в единую справку — то что добавилось к Phase 0-10, остаётся актуальным как backend контракт.

### Storage layer (iter 2.1, R2 §2)

`backend/app/core/storage.py` — `StorageBackend` abstraction. Production — MinIO через aiobotocore. CDN-стиль presigned URLs для read, multipart upload для write. Используется для:
- `CompanyAttachment` (R2 §3).
- `CompanyDocTemplate` (R2 §4).
- `CompanyRoadmapItem.cover_storage_key` (R1 §5.5).

### Company Attachments (iter 2.2, R2 §3)

- Модель `CompanyAttachment` с `language NOT NULL DEFAULT 'en'` (migration 0034, iter 2.4-attachments-lang).
- `order` unique per `(company_id, category)`, **не per-company** — see backend pattern "Bulk reorder per-category scope" ниже.
- Bulk reorder через `PATCH /staff/companies/{id}/attachments/reorder` с body `{category, item_ids}` (iter 2.6c).
- Public flow: `GET /api/v1/public/companies/{id}/attachments` (iter 2.2) + single attachment download (iter 2.2).
- Reconcile script: `cbshome storage reconcile <company_id>` — синхронизирует MinIO ↔ DB.

### Company Doc Templates (iter 2.3, R2 §4)

- Модель `CompanyDocTemplate` с 4-stage fallback: `(kind, language)` per-company active → `(kind, language='en')` per-company → `(kind, language)` platform-default → `(kind, language='en')` platform-default.
- Redis cache keyed by `(company_id, kind, language)` с TTL 5 min.
- Templates **read-only** в Staff UI (iter 2.7 Block C5) — editor вне MVP.
- Reconcile: `cbshome storage reconcile-templates <company_id>`.

### Purchase Documents (iter 2.4, R2 §5)

- `Agreement` (renamed from `Certificate`) + новый `OwnershipCertificate`.
- Endpoints: `POST /purchases/{id}/agreement`, `GET /purchases/{id}/agreement/download`, `POST /purchases/{id}/ownership-certificate`, etc.
- 4-stage fallback применяется при генерации (через templates module).

### Roadmap (iter 2.4 backend + iter 2.7 Block D frontend, R1 §5)

- `CompanyRoadmapItem` с полями: `kind` (milestone/event/announcement), `title`, `description`, `cover_storage_key`, `external_url`, `post_id` (FK, SET NULL), `linked_product_id` (FK same-company, SET NULL), `target_date`, `valid_until`, `status` (только для milestone), `order`.
- Per-kind Pydantic validation в `CreateRoadmapItemRequest._check_kind_rules`:
  - `milestone`: target_date опц., valid_until **запрещён**, status опц.
  - `event`: target_date + valid_until обязательны, valid_until > target_date.
  - `announcement`: target_date / valid_until / status **все запрещены**.
- `kind` immutable после create — `UpdateRoadmapItemRequest` не содержит `kind`.
- State machine (только milestone, R1 §5.6): `planned → in_progress → completed`. `completed → *` forbidden, 400 с сообщением `"Cannot move a completed milestone to another status. Soft-delete and recreate if the change is intentional."` (без машинного префикса — frontend ловит через generic error toast).
- Cover upload: `PUT /staff/companies/{id}/roadmap/{item_id}/cover` (multipart, mime PNG/JPEG/WEBP, 10MB, form field name `file`).
- Reorder: `PATCH /staff/companies/{id}/roadmap/reorder` body `{item_ids: [...]}` (per-company, **не per-category** в отличие от attachments). Error message `"Reorder mismatch: ..."` / `"Duplicate IDs in reorder list"` — без машинного префикса (frontend ловит любой 400 → toast + reload).

### Public Investor Flow (iter 2.6, R1 §1.6 + R2 §7.2)

- Префикс `/api/v1/public/*` для всех публичных эндпоинтов. Rate limit 60 req/min/IP (через `check_rate_limit_per_ip`).
- `PublicCompanyResponse`, `PublicProductResponse`, `PublicProductDetailResponse` — отдельные schemas с stripped полями (`agent_bonus_units` не leaked в public).
- `PublicCompanyDetailResponse.stats` — 5 метрик: `pool_total_options`, `options_sold`, `options_sold_percent`, `price_growth_90d_percent`, `founded_at`.
- Referral capture: `POST /api/v1/kyc/advance` (iter 2.7 mini #1) для idempotent advancement.

### Staff Platform endpoints (iter 2.6c + iter 2.7 mini #5)

Backend для Staff Platform Tab (R1 §4). Все под `company_manage` / `content_manage` permissions:

- `GET /staff/users?role=&kyc_status=&page=&per_page=` (iter 2.6c B1).
- `GET /staff/companies?status=&search=&page=&per_page=` (iter 2.6c B2). Status: `active / hidden / archived` (нет `draft` — companies create как `hidden`).
- `GET /staff/companies/{id}` → `CompanyDetailResponse` (iter 2.7 mini #5). Любой status (включая hidden/archived), не фильтрует на active.
- `GET /staff/companies/{id}/price-history?page=&per_page=` (iter 2.6c B3). Permission `company_manage` (не OR с financial_operations — см. backend pattern "OR-permission primitive" ниже).
- `GET /staff/posts?owner_type=&owner_id=&is_published=&search=&page=&per_page=` (iter 2.6c B4). Включает drafts (vs public `/posts` фильтр).
- `GET /staff/events?is_published=&upcoming=&search=&page=&per_page=` (iter 2.6c B4). Sort ASC для `upcoming=true`, DESC иначе.
- `PATCH /staff/companies/{id}/attachments/reorder` body `{category, item_ids}` → 204 (iter 2.6c B5).
- `UserResponse.staff_profile.permissions` — effective dict (defaults merged с overrides), приходит при `role=staff` через `/users/me` (iter 2.6c B6).

### Events public extension (iter 2.7b)

- `GET /api/v1/events?upcoming=true|false|null` — query param добавлен. Sort ASC для upcoming=true, DESC иначе. Backward-compat без параметра (DESC, all events).
- `GET /api/v1/events/upcoming?limit=N` — параметризован (раньше hardcode "next 30 days + LIMIT 100"). Default limit=3, clamp на 50 (`settings.events_upcoming_max_limit`). Sort ASC всегда (preview ближайших).
- **Не** меняли response shape — `/events` всегда `EventListResponse`, `/events/upcoming` всегда `list[EventResponse]`. Никаких union response models.

### Onboarding advance helper (iter 2.7 mini #1)

- `POST /api/v1/kyc/advance` — idempotent helper для onboarding-step advancement после KYC. 204 на happy-path (no-op если уже advanced).
- Закрывает deadlock при re-entry с `kyc_status=approved` + `onboarding_step=role_selected`.

---

## Backend patterns (зафиксированы по итогам R1+R2)

Эти patterns выявились по ходу iter 2.6c, iter 2.7, iter 2.7b. Применяются ко всем будущим backend задачам.

### Pattern 1: Bulk reorder — per-category scope, не per-company

Если ORM поле `order` unique per `(parent_id, category)` (a-la `CompanyAttachment`) — bulk reorder endpoint должен принимать `category` в body как часть scope:

```python
@router.patch("/companies/{id}/attachments/reorder", status_code=204)
async def reorder_attachments(
    id: UUID,
    body: ReorderAttachmentsRequest,  # {category, item_ids}
    ...
):
    # Validate: set(body.item_ids) == set(active attachments в (id, body.category))
    ...
```

Per-company reorder без category схлопнет уникальность по category (две категории с пересекающимися order values становятся неотличимы). Если хочется per-company reorder — нужна вторая `global_order` колонка с миграцией.

### Pattern 2: Validate-then-apply for bulk mutations

Bulk mutations с whole-set validation (reorder, mass-update, multi-delete) **обязаны** следовать схеме:

```
1. Load all affected rows
2. Validate (set match, value constraints)  ← if fails, return 400
3. Apply changes in-memory
4. Flush/commit
```

**Никогда** не начинать `apply` внутри validation loop — failure в середине оставляет DB в inconsistent state. Pattern зафиксирован в `reorder_roadmap` (iter 2.4) + `reorder_attachments` (iter 2.6c).

### Pattern 3: Route ordering — literal path before path-param

FastAPI matches routes in declaration order. Для `PATCH /resource/{id}/reorder` literal path **обязан** идти перед `PATCH /resource/{id}/{sub_id}` — иначе "reorder" попытается распарситься как UUID и упадёт 422.

```python
# CORRECT order
@router.patch("/resource/{id}/reorder")   # literal "reorder"
@router.patch("/resource/{id}/{sub_id}")  # generic {sub_id}
```

### Pattern 4: Query param name shadowing `fastapi.status`

Если Query param семантически называется `status` — Python arg name **не должен** совпадать с `from fastapi import status`. Use alias:

```python
async def endpoint(
    company_status: CompanyStatus | None = Query(default=None, alias="status"),
    ...,
) -> Response:
    return Response(status_code=status.HTTP_200_OK, ...)  # `status` module не shadowed
```

### Pattern 5: LIKE-metacharacter escape order

Для `?search=` фильтров с `ilike("%needle%")` — escape `\`, потом `%` и `_`. Backslash первый, иначе второй pass re-escape'ит escape-character из первого pass'а:

```python
escaped = needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
condition = Model.field.ilike(f"%{escaped}%", escape="\\")
```

### Pattern 6: Staff-list endpoints return ORM rows, validation in router

Public endpoints с per-user computation (e.g., `is_dismissed`) возвращают pre-validated `list[ResponseSchema]`. Staff endpoints **без** per-user computation возвращают `list[ORM]`, router валидирует через `ResponseSchema.model_validate(row)` в comprehension. Не pre-validate "для безопасности" — лишний pass без выигрыша.

### Pattern 7: Cross-module private import avoidance

Если модуль A нуждается в функциональности модуля B, упакованной в underscored helper (`_build_something`) — **не импортировать**. Re-implement 3-5 строк на A's side. Reasons:

1. Underscored = "module-internal, do not import" Python convention.
2. Изоляция от refactors внутри B (B's underscored helper может переродиться — A не должен страдать).
3. Public API B должна быть достаточной. Если её недостаточно — это сигнал что B нужен новый public export.

Pattern из iter 2.6c §2.3: `users.service::build_user_response` re-implements 3 lines from `staff/admin_service::_build_staff_profile_response`, **не** импортирует.

### Pattern 8: StrEnum binding for Query params

`role: UserRole | None = Query(...)`, потом `role.value if role else None` при передаче в service. Service signature остаётся `str | None`. FastAPI делает framework-edge validation (422 на garbage), service decoupled от enum:

```python
async def endpoint(
    role: UserRole | None = Query(default=None),
    ...,
):
    rows = await list_users_service(
        session,
        role=role.value if role else None,
    )
```

### Pattern 9: `{operation}_set_mismatch:` error message convention для bulk mutations

Для bulk mutations с set validation — error message **с машинным префиксом**:

```python
raise BadRequestError("attachments_reorder_set_mismatch: missing 2 ids, unknown 1 id")
```

Frontend ловит через `error.detail.startsWith("attachments_reorder_set_mismatch:")` → типизированный toast. Note из iter 2.7b: **не все existing endpoints** следуют этой convention (roadmap reorder использует "Reorder mismatch: ..." без префикса). Pattern применяется к **новым** endpoints; existing — at-discretion при touching.

---

## Open questions for future ТЗ revisions

Зафиксированы по итогам iter 2.6c — не блокеры MVP, но recur при росте.

### Q-BE-01: OR-permission primitive

Project не имеет `require_any_staff_permission([X, Y])`. Когда endpoint legitimately serves two staff roles (e.g., price-history — `company_manage` OR `financial_operations`) — текущее решение единичное permission на более permissive из двух. Это работает, но при росте usecases станет тесно. Suggested wording: "Перед expand'ом permission set'а для cross-role read endpoint — build OR-primitive".

### Q-BE-02: `_SELECTABLE_ROLES` SSOT

`users/schemas.py::_SELECTABLE_ROLES = {"investor", "agent", "company"}` — string set, не связан с `UserRole` enum. Если в `UserRole` добавится новая роль (staff-types и т.п.) — whitelist не подтянет автоматически. Refactor: `frozenset[UserRole]` вместо string set.

### Q-BE-03: Recovery flow для soft-deleted

Staff list endpoints (posts/events/attachments) скрывают `is_deleted=True` rows. **Нет UI** для восстановления — это deliberate cut в iter 2.6c. Если позже понадобится — нужны `?include_deleted=true` + `PATCH /undelete` + "trash" UI section.

### Q-BE-04: Search performance на large dev DB

`ilike("%needle%")` без GIN indexes — sequential scan. На сегодня (hundreds of rows per table) терпимо. При prod-scale (10k+) нужны `pg_trgm` trigram indexes.

### Q-BE-05: TD-REF-CLICKS-01 — click tracking endpoint

`/r/<code>` redirect handler уже работает (frontend), но backend не записывает click counts. Нужен `POST /api/v1/public/referral-click` endpoint + counter. **Обязательно перед F6** (Agent shell будет рендерить click stats).

### Q-BE-06: TD-PERMISSION-SSOT

`DEFAULT_STAFF_PERMISSIONS` (Python dict) + `UpdatePermissionsRequest` (Pydantic schema) — два источника truth для permission keys. iter 2.7 mini #3 закрыл текущий drift (9-vs-8), но архитектура остаётся хрупкой. Suggested refactor: `Literal[...]` enum как SSOT, оба места читают из enum.

### Q-BE-07: AUTH-HEADER-IN-302 leak

Auth-flow download endpoint делает 302 на presigned MinIO URL. Если client'ский HTTP library не strip'ит Authorization при cross-origin redirect — header утечёт на MinIO. MinIO ignores, но семантически утечка. Public flow обходит (no Authorization вообще, iter 2.6 design). Backend fix: возвращать JSON `{url}` вместо 302, client сам делает второй GET.

---

## Реестр технического долга

| ID | Файл | Проблема | Приоритет | Статус |
|----|------|----------|-----------|--------|
| TD-001 | `installments/` | Досрочное погашение | After MVP | ⬜ |
| TD-002 | `installments/` | Пауза/заморозка плана | After MVP | ⬜ |
| TD-003 | `kyc/` | Реальная SumSub интеграция | Phase 2 | ⬜ |
| TD-004 | `payments/` | Fiat on-ramp (Moonpay/Transak) | Phase 2 | ⬜ |
| TD-005 | `documents/` | DocuSign e-signature | Phase 2 | ⬜ |
| TD-006 | `notifications/` | ~~Cron для expiration waitlist~~ → `cleanup_expired_notifications()` в notification worker. Hard-delete expired+delivered, CASCADE на deliveries | After MVP | ✅ Sprint 8.1 |
| TD-007 | `tests/` | Cleanup fixtures через ORM вместо raw SQL | Backlog | ⬜ |
| TD-008 | Все роутеры | Rate limiting (slowapi) | Before Prod | ⬜ |
| TD-009 | `transactions/` | ~~Экспорт в CSV/XLSX~~ → `GET /transactions/export` stub (501 Not Implemented) создан в Sprint 10.1. Реальная реализация CSV/XLSX | Phase 2 | ⬜ |
| TD-010 | `purchases/` | ~~PDF генерация сертификатов~~ → HTML-просмотр + PDF-генерация (xhtml2pdf) + email отправка. `core/email.py` для SMTP/Mailgun, rate limit на email endpoint | Phase 2 | ✅ Sprint 9.2 |
| TD-011 | `app/core/database.py` | Lazy singleton race condition при concurrent startup — теоретический, asyncio single-threaded, но задокументировать | Backlog | ⬜ |
| TD-012 | `audit_log` | Партиционирование по `created_at` (range partitioning) для long-term performance | Before Prod | ⬜ |
| TD-013 | `app/modules/ledgers/models.py` | LedgerMixin: вынести общие поля ActiveLedger/PassiveLedger в `_LedgerBase` (Abstract) | Backlog | ⬜ |
| TD-014 | `app/core/constants.py` | LedgerReason: заменить `: str` аннотации на `Final[str]` из `typing` | Backlog | ⬜ |
| TD-015 | `app/core/mixins.py` | JSONBMixin.set_jsonb(): уточнить type hint `value: dict` -> `value: dict[str, Any]` | Backlog | ⬜ |
| TD-016 | `tests/` | Добавить тесты: модели (User, Ledger, Staff), middleware (TraceId), config validation, seed_platform.py идемпотентность | Sprint 1+ | ⬜ |
| TD-017 | `app/modules/auth/router.py` | Email enumeration: register возвращает 409 для дубликатов. Phase 8: всегда 201, уведомление на email | Phase 8 | ⬜ |
| TD-018 | `app/modules/auth/` | ~~Rate limiting на email auth endpoints (register + login). Отдельно от TD-008~~ | Before Prod | ✅ Sprint 5.2 (P5-SEC-3) |
| TD-019 | `app/modules/auth/schemas.py` | Password complexity: добавить требование цифры или mixed case | Before Prod | ⬜ |
| TD-020 | `app/core/middleware.py`, `app/core/audit.py` | ~~`_USER_AGENT_MAX_LEN = 500` в двух файлах. Вынести в `constants.py`~~ | Backlog | ✅ Phase 2 |
| TD-021 | `app/modules/auth/` | Password reset flow (forgot password -> email token -> reset) | After MVP | ⬜ |
| TD-022 | `app/modules/auth/telegram.py` | Generic error messages в production (сейчас details leakируют server time через "auth_date is in the future") | Before Prod | ⬜ |
| TD-023 | `scripts/seed_platform.py` | `seed --reset` flag не реализован, но присутствует в management script help | Backlog | ⬜ |
| TD-024 | `app/modules/users/service.py` | ~~Profile JSONB: whitelist допустимых ключей~~ → `_ALLOWED_PROFILE_KEYS = frozenset({first_name, last_name, country, phone, avatar_url})`. Неизвестные ключи → `BadRequestError`. XSS sanitization на фронте (SEC-8) — отдельно | Before Prod | ✅ Code review |
| TD-025 | `app/modules/documents/` | Проверка наличия подписей при смене роли. Структура готова, логика — при реализации role change (Phase 7) | Phase 7 | ⬜ |
| TD-026 | `app/modules/documents/` | Версионирование: переподписание при обновлении редакции. Поле `version` заложено, логика определения пользователей без актуальной подписи — после MVP | After MVP | ⬜ |
| TD-027 | `app/modules/staff/router.py` | Unblock endpoint (`PATCH /staff/users/{id}/unblock`). Сейчас разблокировка только через DB | After MVP | ⬜ |
| TD-028 | `app/modules/auth/avatar_guard.py` | Применить `@require_not_avatar` к остальным RESTRICTED_OPERATIONS endpoints по мере их создания (create_payment, create_withdrawal и т.д.) | Phase 5+ | ⬜ |
| TD-029 | `companies/`, `products/` | ~~Enum duplication: `CompanyStatus`, `ProductStatus`, `RoadmapItemStatus` определены и в `models.py`, и в `constants.py`~~ → canonical source в `constants.py`, `models.py` импортирует | Backlog | ✅ Code review |
| TD-030 | `companies/schemas.py` | ~~`CreateCompanyRequest.email` использует `str`, не `EmailStr`~~ → заменено на `EmailStr` | Backlog | ✅ Code review |
| TD-031 | `products/schemas.py` | ~~Social proof `sold_units: int = 0` — заглушка. Реализовать подсчёт из purchases с Redis кэшем~~ → Прямой COUNT реализован в Sprint 6.1 (`get_sold_units_map()`). Redis-кэш — при высокой нагрузке на витрину | Sprint 6.1 | ✅ Sprint 6.1 |
| TD-032 | `app/core/database.py` | Redis session создаётся ДО DB commit (CRIT-1). Orphan token живёт до TTL (30 дней). Приемлемо для MVP | After MVP | ⬜ |
| TD-033 | `companies/constants.py` | Float precision в `distribution_config` validation: `total > 1.0` может дать false positive. Рассмотреть `Decimal` или tolerance `1e-9` (MINOR-4) | Backlog | ⬜ |
| TD-034 | `payments/router.py` | `POST /crypto-address` — заглушка. При интеграции реального провайдера endpoint может измениться (адрес от API / pre-generated pool / hosted page redirect) | Phase 2 | ⬜ |
| TD-035 | `payments/reversal.py` | ~~`total_reversed_cents` = `payment.amount_cents`, не сумма ledger entries~~ → считается из `sum(abs(entry.amount_cents))` по реальным reversed entries. `SELECT FOR UPDATE` для concurrent reversal protection | Phase 6 | ✅ Code review |
| TD-036 | `payments/reversal.py` | N+1 flush в loop (каждый `record_*_ledger` делает flush). Приемлемо при 1-3 entries. Оптимизировать если saga создаёт >10 entries на payment | Phase 6 | ⬜ |
| TD-037 | `purchases/router.py` | Нет `idempotency_key` в `CreatePurchaseRequest`. Двойной клик или повторная отправка формы создаст две покупки. Advisory lock не защищает — второй запрос подождёт и выполнится | Backlog | ⬜ |
| TD-038 | `purchases/service.py`, `installments/service.py` | ~~Нет KYC-проверки перед покупкой~~ → KYC guard: `investor.kyc_status != KYCStatus.APPROVED` → `BadRequestError` в `execute_purchase()` и `create_plan()`. Worker `pay_tranche()` не проверяет — KYC валидирован при создании плана | Before Prod | ✅ Sprint 6.4 |
| TD-039 | `payments/`, `ledgers/` | Partial indexes на `(status, frozen_until) WHERE status='frozen'` для confirmation daemon. При росте данных `WHERE status='frozen' AND frozen_until <= now()` будет деградировать | Before Prod | ⬜ |
| TD-040 | `tests/conftest.py` | Тесты без транзакционной изоляции — `db_session` делает rollback в finally, но тесты с `commit()` оставляют данные. Нет SAVEPOINT-обёртки между тестами | Backlog | ⬜ |
| TD-041 | `main.py` | CORS `allow_methods=["*"]` — избыточно для финансовой платформы. Ограничить до `["GET", "POST", "PATCH", "DELETE", "OPTIONS"]` | Before Prod | ⬜ |
| TD-042 | `installments/worker.py` | ~~Worker race condition: `session.get()` без `FOR UPDATE`~~ → `_load_tranche_for_update()` / `_load_plan_for_update()` с `SELECT ... FOR UPDATE`. Сериализует concurrent worker instances | Before Scale | ✅ Sprint 7.1 |
| TD-043 | `withdrawals/service.py` | ~~Отсутствие `begin_nested()` в `create_withdrawal()`~~ → обёрнуто в `begin_nested()` + `IntegrityError` catch. Savepoint preserves outer transaction (P-01 compliant) | Backlog | ✅ Sprint 7.2 |
| TD-044 | `core/config.py` | ~~`telegram_bot_token` не имеет production enforcement~~ → `ValueError` при `telegram_bot_token in ("", "TEST")` в production, аналогично `secret_key` / `kyc_webhook_secret` | Before Prod | ✅ Sprint 7.2 |
| TD-045 | `processors/purchase.py` | ~~Float-truncation в доле компании: `int(pct * amount)`~~ → `round(pct * amount)` (banker's rounding). Аналогичный фикс в `processors/referral.py` | Backlog | ✅ Sprint 7.2 |
| TD-046 | `installments/service.py` | ~~Units truncation без компенсации в последнем транше~~ → последний транш = `total_units - sum(previous)`. Гарантирует `sum(units_unlocked) == total_units` даже если `validate_plan_config()` пропустит edge case | Backlog | ✅ Sprint 7.2 |
| TD-047 | `auth/service.py` | ~~Утечка существования аккаунта через 403 vs 401~~ → деактивированный аккаунт возвращает `UnauthorizedError("Invalid email or password")` (тот же код и сообщение что для неверного пароля). Timing-safe hash сохранён | Before Prod | ✅ Sprint 7.2 |
| TD-048 | `installments/service.py` | Двойная запись суммы в transaction log при завершении плана: `installment:completed` дублирует сумму уже записанную по отдельным `installment:tranche_paid`. Code review #10 | Backlog | ⬜ |
| TD-049 | `migrations/` | Отсутствующие CHECK-ограничения в некоторых миграциях, композитные индексы для оптимизации. Code review 🟢 | Backlog | ⬜ |
| TD-050 | `payments/webhook_router.py` | Webhook: 409 для дубликата → рассмотреть 200 (идемпотентность). `max_length` на полях вебхука. Code review 🟢 | Backlog | ⬜ |
| TD-051 | `payments/confirmation.py` | Лимит батча в confirmation worker — без LIMIT при большом объёме frozen entries может быть long-running transaction. Code review 🟢 | Before Scale | ⬜ |
| TD-052 | `referrals/service.py` | Self-referral prevention: агент теоретически может зарегистрировать второй аккаунт по своему реферальному коду и генерировать комиссии. Техническая проверка (email uniqueness) не покрывает — это антифрод бизнес-логика (multi-account detection). Code review 🟢 Sprint 7.2 | After MVP | ⬜ |
| TD-053 | `notifications/service.py` | Channels хранятся в `action_data["_channels"]` вместо отдельной колонки. Пересмотрено в Sprint 8.2 — проблем не создало, оставлено as-is. Нет DB-level валидации, но channels immutable и контролируются только `create_notification()` | Backlog | ⬜ |
| TD-054 | `notifications/processor.py` | Hard-delete в `cleanup_expired_notifications()`. Уведомления ≠ финансовые данные, structlog достаточен для audit. Рассмотреть soft-delete если потребуется аналитика по уведомлениям | Backlog | ⬜ |
| TD-055 | `notifications/formatters.py` | ~~Нет таймаутов для `formatter.deliver()`~~ → `asyncio.wait_for(..., timeout=30)` в `deliver_notification()`. Concurrent delivery через `asyncio.gather` + `Semaphore(20)` | Sprint 8.2 | ✅ Sprint 8.2 |
| TD-056 | `notifications/formatters.py` | Email обязательность: юзер без email в credentials → delivery FAILED + `PermanentDeliveryError`. Enforcement на уровне onboarding (запрет продолжения без email) — отдельный спринт | Phase 9 | ⬜ |
| TD-057 | `notifications/service.py` | Dedicated delivery worker для масштабирования broadcast. Текущий `asyncio.gather` + `Semaphore(20)` — 25 мин worst case на 1000 юзеров. При 10K+ нужен отдельный worker с `FOR UPDATE SKIP LOCKED` на deliveries | Before Scale | ⬜ |
| TD-058 | `commissions/worker.py` | Leaderboard `run_leaderboard_update()` без advisory lock. При multi-instance deployment возможна двойная обработка. Monthly/quarterly payout имеют advisory lock, update — нет | Before Scale | ⬜ |
| TD-059 | `purchases/router.py`, `installments/router.py` | ~~Agent purchase/installment blocked (`role != investor` → 403)~~ → `_BUYER_ROLES = {INVESTOR, AGENT}`. Агенты — тоже инвесторы по бизнес-логике | G3/G4 | ✅ G3/G4 fix |
| TD-060 | `staff/admin_router.py`, `admin_schemas.py`, `admin_service.py` | ~~KYC reject без reason~~ → `KYCRejectRequest {reason?: str, max_length=2000}`. Reason записывается в `audit_log.data`, не в модель KYCApplication | G5 | ✅ G5 fix |
| TD-061 | `auth/router.py`, `auth/service.py`, `auth/schemas.py` | ~~Email verification endpoint отсутствует~~ → 6-значный код, TTL 10 мин, max 5 попыток, `secrets.compare_digest`, resend с rate limit. Email через `core/email.py` | G1 | ✅ G1 fix |
| TD-062 | `payments/staff_router.py`, `payments/service.py`, `payments/schemas.py` | ~~Staff не может видеть список всех платежей~~ → `GET /staff/payments` с фильтрами (status, user_id), `StaffPaymentResponse` (+user_id), permission `payment_review` | G2 | ✅ G2 fix |
| TD-063 | `tests/conftest.py` | ~~`_send_verification_email()` вызывается в тестах~~ → SMTP timeout (Postfix → example.com) + Mailgun timeout (placeholder key) = ~60с на каждую регистрацию. Фикс: `mock_email` autouse fixture, `monkeypatch` на noop. Продакшен-код не тронут | F1 | ✅ F1 fix |
| TD-064 | `tests/test_staff_admin.py` | ~~`test_kyc_reject` не отправляет JSON body~~ → G5 добавил `KYCRejectRequest` (обязательный body), тест не обновлён. 422 вместо 204. Фикс: `json={}` | F1 | ✅ F1 fix |
| TD-065 | `scripts/install_cbshome.sh` | ~~`docker compose build --no-cache` в `case_update()`~~ → каждый `cbshome update` пересобирал все слои с нуля (~105с + 17GB мусора). Фикс: убран `--no-cache` из update (оставлен только при первичной установке) | F1 | ✅ F1 fix |
| TD-066 | `frontend/public/legal/**/*.html` | 20 legal-болванок с Lorem ipsum вместо реального текста. Pre-launch blocker (не код-блокер): юрист должен заменить тексты до production. CI-гейта намеренно нет — проверяется в release-checklist | Pre-launch | ⬜ |
| TD-067 | `backend/tests/test_documents.py`, `test_onboarding.py` | `_cleanup_documents` fixture делает `DELETE FROM document_signings; DELETE FROM documents` перед/после каждого теста. Чтобы тесты могли создавать `(type, version, language)` без конфликта с seed-записями. На общей БД (TEST = PROD) снесёт реальные seed и подписания — но тесты против production и не запускаются. Правильный фикс — изолированная test-DB (TD-068) | Backlog | ⬜ |
| TD-068 | `docker-compose.yml`, `backend/tests/conftest.py` | Нет изолированной тестовой БД: тесты гоняются по тому же `postgres` сервису что и приложение. Нужен `test-postgres` service + `TEST_DATABASE_URL`. Снимет TD-067 и вернёт тестам нормальные fixtures-scoped cleanups | Before Scale | ⬜ |
| TD-069 | `backend/tests/test_dashboard.py::test_certificate_email` | Исходный мок был на `aiosmtplib.send` — `core/email.py` реально ходит Mailgun primary, SMTP только как fallback. Тест случайно проходил только потому что Mailgun placeholder-key давал ошибку и падало в SMTP, который мок ловил. Фикс: мок на `send_certificate_email` router-level. Настоящий долг — явный sender-contract (protocol), mock на который не ломается от ротации primary/fallback | Backlog | ⬜ |
| TD-070 | `backend/app/modules/documents/service.py` | `list_documents_for_role` делает два запроса (candidates + distinct types) чтобы отличить "юзер в миноритарной локали" от "платформа сломана". Можно сократить до одного запроса с `GROUP BY type` + агрегатом по наличию en/user_lang, но читаемость пострадает. Приемлемо при <20 типов | Backlog | ⬜ |
| TD-071 | `companies/models.py`, `products/models.py`, `purchases/service.py`, `processors/base.py`, `tests/` | ~~**Share Pool & Product Inventory refactor.** `Product.units` ошибочно трактуется как «инвентарь пакета», `sold_units = COUNT(Purchase)` не отражает акции~~ → Реализован полностью в Sprint 4.3 + 4.4: новая модель `OptionPool`, `Product.package_size`, `available_packages` через pool. Code review hardening (Sprint 4.4): `POOL_STATUS_ACTIVE` централизован, dead copies в purchases/service удалены, ORM mutation antipattern заменён explicit constructor, schema cleanup (no defaults on populated fields). 362/362 тестов зелёные. Детальная спецификация — `CBSHOME-Share-Pool-Refactor.md` (v2.4) | Sprint 4.3 + 4.4 | ✅ Sprint 4.4 |
| TD-072 | `withdrawals/service.py` | 🔴 **Sign error в transaction log.** `reject_withdrawal` и `fail_withdrawal` пишут `amount_cents=-withdrawal.amount_cents` в `record_transaction`, тогда как ledger пишется с `+amount_cents` (compensation credit). История транзакций показывает -2X для rejected withdrawal вместо 0 (CREATED -X + REJECTED -X). Реальный баланс корректен (ledger source of truth), но отображаемая история ломает доверие пользователя. Фикс: `amount_cents=withdrawal.amount_cents` в обоих местах (lines 348, 493). Code review CRITICAL. | Before Prod | ⬜ |
| TD-073 | `transactions/constants.py`, `withdrawals/service.py`, `payments/reversal.py` | Sign convention в `TransactionType` inconsistent. Проаудитить все `record_transaction` вызовы и зафиксировать конвенцию `positive=in / negative=out` в комментариях к каждому enum-значению. Также проверить `WITHDRAWAL_COMPLETED` — может быть избыточная transaction (после CREATED ledger движения нет, только статус-переход — тогда транзакция дублирует знак или должна иметь `amount=0`). После фикса TD-072 — связанная задача. | Before Prod | ⬜ |
| TD-074 | `withdrawals/router.py`, `auth/router.py` | Rate limiting + docstring rectification. (1) `POST /withdrawals` — нет slowapi guard (уникальный индекс `uq_withdrawals_user_active` ограничивает одним активным выводом, но каждый запрос бьёт в БД advisory lock + balance query). Добавить `check_rate_limit("withdrawal_create:{user.id}")`. (2) `/verify-email/resend` docstring: «1 per 60s» vs реализация 5/60s (auth default). Либо добавить отдельный конфиг `resend_rate_limit_max_requests=1`, либо синхронизировать docstring. | Before Prod | ⬜ |
| TD-075 | `commissions/service.py::get_my_commissions` | N+1 запросы. Цикл из 50 ledger entries делает отдельный JOIN на каждую (Purchase × Product × User по `purchase_id`). До 51 запроса на вызов; при истории на 1000+ позиций — критично. Фикс: собрать `purchase_ids` заранее регексом, один JOIN с `Purchase.id.in_(purchase_ids)`, потом dict-lookup. То же для `payout_id` JOIN в volume_bonus блоке. | Before Scale | ⬜ |
| TD-076 | `kyc/router.py` | 🔴 **KYC webhook security.** Сейчас проверяется только `X-Webhook-Secret` (shared secret). SumSub в production использует `X-Payload-Digest` — HMAC-SHA1 подпись тела запроса. Без неё: компрометация секрета через TLS-терминатор/логи позволяет подделать KYC approval; payload не привязан к запросу — возможен replay. **Production blocker.** Stub-комментарий «In production, replace with SumSub signature validation» требует трекинга. Фикс: `hmac.new(secret, body_bytes, sha1).hexdigest()` против `X-Payload-Digest` header. | Before Prod | ⬜ |
| TD-077 | `auth/service.py::verify_email_code` | `stored_code = onboarding.get("email_token", "")` возвращает `None` если ключ присутствует со значением `null` (после успешной верификации token обнуляется в `updated_creds["onboarding"]["email_token"] = None`). `dict.get(key, default)` возвращает `default` только при отсутствии ключа; для `None`-значения вернёт `None`. `secrets.compare_digest(code, None)` → `TypeError` → 500. Edge case (защищён через `if email_creds.get("verified")`), но fragile. Фикс: `onboarding.get("email_token") or ""`. | Backlog | ⬜ |
| TD-078 | `core/config.py` | `secret_key` присутствует в Settings и обязателен в production, но не используется в видимом коде (JWT не используется, sessions в Redis). Либо убрать до момента реального использования, либо задокументировать назначение (готовность к JWT-flow / signed cookies / другой crypto-related feature). Code review SUGGESTION. | Backlog | ⬜ |
| TD-079 | `ledgers/validators.py` | AML matrix (Active→Passive запрещено) проверяется только в `validate_route()`; не вызывается автоматически в `record_active_ledger`/`record_passive_ledger`. Любой новый сервис который не вызовет `validate_route()` явно — может нарушить AML-ограничение незаметно. Фикс: добавить defensive assertion в `record_*_ledger` (на каждом write вызывать validator), либо документировать как convention + покрыть тестами на все пути записи. | Backlog | ⬜ |

---

**Конец документа**

---

*Version 3.7 | 2026-05-13 | R1 + R2 рефакторинг полностью закрыт (iter 2.1 — iter 2.7b). Новый раздел "R1 + R2 Refactor — Backend artefacts" суммирует все backend артефакты: storage layer, attachments, templates (4-stage fallback + Redis cache), purchase docs (agreement/ownership), roadmap (per-kind validation + state machine + cover upload), public investor flow (rate-limited /public/*), 7 staff endpoints из iter 2.6c + GET /staff/companies/{id} + POST /kyc/advance + UserResponse.staff_profile, events public extension (?upcoming + /events/upcoming?limit). Добавлен раздел "Backend patterns" из 9 паттернов: per-category reorder scope, validate-then-apply, route ordering literal-before-param, Query alias shadowing fastapi.status, LIKE escape order, ORM rows vs validated responses, cross-module private import avoidance, StrEnum binding, {operation}_set_mismatch error message convention. 7 open questions для будущих revisions: OR-permission primitive, _SELECTABLE_ROLES SSOT, recovery flow, search performance, click tracking (TD-REF-CLICKS-01 — обязательно до F6), permission keys SSOT, AUTH-HEADER-IN-302 leak. Pytest 247 → 254 после iter 2.7b. R1+R2 documents переведены в final / fully implemented.*

*Version 3.7-F5 | 2026-05-05 | Phase F5 (Company UI) closed: F5.1 dashboard + F5.2 products / analytics / balance / settings deployed. F5.2 B4 forms (POST /withdrawals, PUT payout-details) wired and verified. Code review TD batch landed: TD-072..079 — sign error в WITHDRAWAL_REJECTED/FAILED transaction log (CRITICAL), KYC webhook без HMAC (production blocker), N+1 в get_my_commissions, rate limit на /withdrawals, sign convention аудит, mini-fixes (None-safe email_token compare, unused secret_key, AML defensive assertion). Все TD-72..79 — Before Prod / Backlog, не блокируют F5.*

*Version 3.6 | 2026-05-03 | Sprint 4.5: GET /companies/me canonical path для company-роли (CompanyResponse staff-side schema). Sprint 4.6 hotfix: portfolio + company_dashboard installment regression — installment_tranche purchases теперь корректно классифицируются как paid acquisitions (был silent fall-through в gift bucket из-за `!= SALE` else-branch, оставшегося с pre-Sprint-6.2 кода). Sprint 4.5 frontend prep: `getMyCompany()` wrapper + Phase F5 re-exports в types.ts. 368 tests, all green. Deploys: b539ee8 → b9d1fee (4.5) → 75168f0 (4.6) → 0f11197 (prep).*

*Version 3.5 | 2026-05-03 | Sprint 4.3 + 4.4 закрыты. Share Pool refactor (TD-071) deployed: `OptionPool` модель, `Product.package_size` rename, `available_packages` через pool, `price_per_pack_cents` в public response, gift overflow в owner supply. Sprint 4.4: VELO Migration (frontend types pipeline), pack-pricing UX, code review hardening (POOL_STATUS_ACTIVE centralisation, dead-copies removal, explicit Pydantic constructors, ProductDetailResponse cleanup). 362 tests, all green.*

*Version 3.4 | 2026-04-17 | Sprint 2.2 UPDATE: `content_url` dropped, Document body moved to static HTML in `frontend/public/legal/<lang>/<type>.html`, `required_for_roles` JSONB replaces `ROLE_REQUIRED_DOCUMENT_TYPES` dict, localisation (en/ru/de/ar) via `Document.language` + `UNIQUE (type, version, language)`, seed_documents.py syncs hash-based. 336 tests, all green.*

*Version 3.3 | 2026-04-17 | Email: Mailgun primary + SMTP fallback (inverted), EU endpoint support, start_tls fix. KYC non-blocking onboarding. install_cbshome.sh: UFW Docker SMTP, /dev/tty reads, docker stdin fix, test-email command. 336 tests, all green*
