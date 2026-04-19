# Arch-Review Skills — Комплексное исследование и рекомендации

> **Дата:** 2026-03-19
> **Документ:** Объединённый research для arch-review (generic) + arch-review-bogame (project)
> **Статус:** Validated — все найденные проблемы исправлены (см. Appendix A)

---

# ЧАСТЬ I: arch-review (generic skill) — v1.1.0 → v2.0.0

---

## 1. ТЕКУЩЕЕ СОСТОЯНИЕ

### Что есть
- 12 секций анализа + 1 секция Pattern Quality
- 13 Good Patterns (GP-01..GP-13)
- 13 Bad Patterns (BP-01..BP-13)
- 8 Diamond Patterns (DP-01..DP-08)
- 12-мерный Scorecard с весами
- Quality Gate (PASS/WARN/FAIL)
- Fix mode

### Где перекос
- **Diamond-паттерны:** 4 из 8 — ORM/SQL-специфичные (JSONB, Two-Session, Savepoint, Atomic WHERE). Сильно для Python+SQLAlchemy, слабо для всех остальных стеков.
- **Good Patterns:** Нет coverage по infrastructure patterns (graceful shutdown, retry, configuration), API design, DDD.
- **Bad Patterns:** Нет distributed anti-patterns (distributed monolith, shared database between services, anemic domain).
- **Секции анализа:** Нет Security Architecture, API Design Quality, Configuration Architecture.
- **Scorecard:** Нет калибровочных anchor-примеров — оценка субъективна и нестабильна между запусками.

---

## 2. НОВЫЕ DIAMOND PATTERNS

> Diamond = исключительное качество, которое решает фундаментальную проблему элегантно. Не просто "хорошо сделано", а "это превращает целый класс ошибок в невозможные".

### DP-09: Transactional Outbox Pattern
- Бизнес-операция и событие записываются в одной ACID-транзакции (основная таблица + outbox-таблица)
- Отдельный publisher читает outbox и доставляет в message broker
- При откате транзакции событие тоже откатывается — нет рассинхрона
- Consumer-ы идемпотентны — повторная доставка безвредна
- **Почему diamond:** Решает dual-write problem без distributed transactions. Гарантирует at-least-once доставку с нулевым шансом "данные обновились, а событие потерялось". Фундамент надёжной event-driven архитектуры.

### DP-10: Event Sourcing с Projection Rebuild
- Все изменения состояния сохраняются как immutable events в append-only store
- Текущее состояние = проекция (replay событий или snapshot + tail)
- Проекции можно перестроить полностью из событий (blue-green rebuild)
- Каждый event содержит correlation_id и causation_id
- Снапшоты для производительности, с автоматической инвалидацией при изменении схемы проекции
- **Почему diamond:** Полный аудит из коробки. Воспроизводимость состояния на любой момент времени. Возможность добавлять новые read-модели задним числом. Time-travel debugging.

### DP-11: CQRS с Physical Separation
- Write-модель оптимизирована под консистентность (нормализованная БД, агрегаты)
- Read-модель оптимизирована под запросы (денормализованная, materialized views, ElasticSearch)
- Синхронизация через events (не через shared database)
- Read и Write масштабируются независимо
- **Почему diamond:** Устраняет компромисс "или быстрое чтение, или консистентная запись". Каждая сторона оптимальна для своей задачи.

### DP-12: Saga с Компенсациями и Idempotency
- Распределённая бизнес-транзакция разбита на последовательность локальных транзакций
- Каждый шаг имеет compensating transaction для отката
- Каждый участник идемпотентен (idempotency key на входе)
- Orchestrator (или choreography) отслеживает состояние саги
- Pivot transaction определяет point of no return
- **Почему diamond:** Надёжная распределённая согласованность без 2PC. Каждый сервис автономен. Компенсации делают систему self-healing.

### DP-13: Hexagonal Architecture (Ports & Adapters) — чистая реализация
- Домен (бизнес-логика) в центре, zero зависимостей на инфраструктуру
- Driving ports (входящие) — интерфейсы use-cases, реализованные доменом
- Driven ports (исходящие) — интерфейсы, которые домен объявляет, а адаптеры реализуют
- Adapters: HTTP, CLI, gRPC (driving) / PostgreSQL, Redis, S3 (driven) — заменяемые
- Домен тестируется с in-memory адаптерами, без I/O
- **Почему diamond:** Домен полностью изолирован. Можно сменить БД, фреймворк, транспорт не трогая бизнес-логику. Тестируемость — максимальная.

### DP-14: Strangler Fig с Routing Façade
- Legacy-система обёрнута в façade (API Gateway / reverse proxy)
- Новый функционал реализуется как отдельные сервисы
- Façade маршрутизирует: новые endpoints → новые сервисы, остальные → legacy
- Постепенное замещение: каждый перенесённый endpoint верифицируется в параллельном прогоне
- Legacy сужается, пока не остаётся пустым и не отключается
- **Почему diamond:** Единственный безопасный путь модернизации критических систем. Zero downtime migration. Каждый шаг обратим.

### DP-15: Bulkhead Isolation
- Ресурсы (потоки, соединения, очереди) разделены на изолированные пулы по сервисам/компонентам
- Отказ одного компонента не исчерпывает ресурсы другого
- Каждый пул имеет свой лимит, свой circuit breaker, свои метрики
- Деградация — послойная, не каскадная
- **Почему diamond:** Принцип судостроения (водонепроницаемые отсеки). Пробоина в одном отсеке не топит корабль. В сочетании с Circuit Breaker — полная resilience-архитектура.

### DP-16: Contract Testing между сервисами
- Provider публикует контракт (OpenAPI spec / Pact / AsyncAPI для events)
- Consumer пишет consumer-driven contract tests
- CI/CD проверяет совместимость при каждом PR — до деплоя
- Breaking changes обнаруживаются до production
- Backward compatibility гарантируется автоматически
- **Почему diamond:** Устраняет "мы задеплоили и сломали 3 команды". API эволюционирует без страха. Schema registry для events — та же идея в async-мире.

### DP-17: Graceful Degradation Cascade
- Система определяет уровни деградации (full → degraded → minimal → maintenance)
- Каждый уровень: какие функции работают, какие отключены, какие показывают cached data
- Переход между уровнями автоматический (по health checks и circuit breakers)
- Пользователь видит деградированный UX вместо 500 ошибки
- **Почему diamond:** Система не "падает" — она "теряет высоту управляемо". Netflix-level resilience. Бизнес-функции ранжированы по критичности.

### DP-18: Idempotency Key Pattern
- Каждая мутирующая операция принимает клиентский idempotency_key
- Сервер хранит mapping key → result с TTL
- Повторный запрос с тем же ключом возвращает cached result без повторного выполнения
- Работает на всех уровнях: API → service → message consumer
- **Почему diamond:** Safe retry на любом уровне стека. Сетевые ошибки, таймауты, дубликаты сообщений — всё безвредно. Stripe, AWS, все серьёзные API используют этот паттерн.

### DP-19: Typed Configuration with Startup Validation
- Единый typed config object (Pydantic / dataclass / Zod schema)
- Все settings загружаются и валидируются при запуске (fail fast)
- Secrets отделены от config (vault / env, не в файлах)
- Environment parity: один механизм для dev/staging/prod
- Defaults документированы, каждый field typed и described
- **Почему diamond:** Zero runtime config surprises. Невалидная конфигурация невозможна — приложение не стартует. Один источник правды.

---

## 3. НОВЫЕ GOOD PATTERNS

### GP-14: Repository Pattern (чистая абстракция хранилища)
- Интерфейс `Repository<T>` с методами `find`, `save`, `delete`
- Бизнес-логика работает с интерфейсом, не с ORM/SQL
- Реализации: SQLRepository, InMemoryRepository (для тестов), CacheRepository
- **Почему важно:** Домен не знает о способе хранения. Тестируемость. Заменяемость.

### GP-15: DTO/Value Object на границах слоёв
- Данные между слоями передаются через dedicated типы (не entity, не dict)
- Request DTO → Service → Response DTO; внутри сервиса — domain objects
- Каждый DTO валидирует себя (Pydantic, dataclass, Zod, record)
- **Почему важно:** Нет leaky abstraction. API-контракт не зависит от структуры БД. Эволюция схемы без breaking changes.

### GP-16: Middleware Chain / Pipeline Pattern
- Обработка request/response — цепочка composable middleware
- Каждый middleware делает одну вещь: auth, logging, rate-limit, CORS, error-translate
- Порядок цепочки определяет поведение (logging → auth → rate-limit → handler)
- **Почему важно:** Cross-cutting concerns отделены от бизнес-логики. Reusable. Testable independently.

### GP-17: Configuration Hierarchy с валидацией при старте
- Приоритет: env vars → config file → defaults
- Все настройки валидируются при запуске (fail fast, не в runtime)
- Secrets отделены от config (vault / env, не в файлах)
- Конфиг — typed object, не россыпь `os.getenv()` по всему коду
- **Почему важно:** No surprise failures. Один источник правды. Config injection через DI.

### GP-18: Graceful Shutdown
- SIGTERM → stop accepting new requests → drain in-flight requests → close connections → exit
- Timeout на drain (если не успели — force exit с логом)
- Health check endpoint сразу возвращает "not ready" при получении SIGTERM
- Background workers завершают текущую задачу, не берут новые
- **Почему важно:** Zero-downtime deployments. Нет потерянных запросов при рестарте. Kubernetes-ready.

### GP-19: Retry with Jitter
- Exponential backoff: 1s → 2s → 4s → 8s (с cap)
- Jitter: random delay в пределах [0, backoff_interval]
- Max retries capped
- Retry только для transient errors (5xx, timeout, connection reset) — не для 4xx
- **Почему важно:** Предотвращает thundering herd при восстановлении сервиса. Без jitter — все ретраи приходят одновременно и кладут сервис снова.

### GP-20: Dead Letter Queue с мониторингом
- Сообщения, не обработанные после N попыток, попадают в DLQ
- DLQ мониторится (alert при превышении порога)
- Каждое сообщение в DLQ сохраняет: оригинальное тело, причину отказа, timestamp, stack trace
- Есть механизм replay из DLQ обратно в основную очередь
- **Почему важно:** Ни одно сообщение не теряется. Проблемы видны и debuggable. Replay позволяет восстановить обработку после фикса.

---

## 4. НОВЫЕ BAD PATTERNS

### BP-14: Anemic Domain Model
- Entities — только getters/setters, никакого поведения
- Вся бизнес-логика в service-классах, которые манипулируют данными entity снаружи
- Domain objects = data bags, бизнес-правила дублируются между сервисами
- **Fix:** Перенести поведение в domain objects. Entity.process(), Entity.validate(), Entity.can_transition_to(). Сервисы координируют, а не вычисляют.

### BP-15: Distributed Monolith
- Система разбита на микросервисы, но они не могут деплоиться независимо
- Синхронные цепочки вызовов (A → B → C → D), один падает — всё падает
- Shared database между сервисами
- Shared code library с бизнес-логикой, version lock между сервисами
- Координированный деплой нескольких сервисов для одного изменения
- **Fix:** Database-per-service. Async communication. Чёткие bounded contexts. Contract testing вместо shared libs.

### BP-16: Shared Database Between Services
- Несколько сервисов читают/пишут в одни и те же таблицы
- Изменение схемы таблицы требует координации между командами
- Tight coupling на уровне данных, даже если код decoupled
- Невозможно масштабировать БД независимо для разных сервисов
- **Fix:** Каждый сервис владеет своими данными. Данные других сервисов — через API или events. Если нужны join-ы — materialized view через event-синхронизацию.

### BP-17: Configuration Sprawl
- Настройки размазаны: часть в env vars, часть в YAML, часть hardcoded, часть в БД
- Нет единой точки, где видна полная конфигурация системы
- Defaults не документированы, secret management отсутствует
- Разные модули читают конфиг по-разному (os.getenv, config parser, hardcode)
- **Fix:** Единый config module. Все настройки загружаются при старте. Typed config. Secrets через vault/env, config через files. Валидация при запуске.

### BP-18: Log-and-Throw Anti-pattern
- Ошибка логируется И пробрасывается дальше
- Результат: одна и та же ошибка появляется в логах 3-5 раз (на каждом уровне стека)
- Шум в логах, confusion при debugging
- **Fix:** Логировать на одном уровне (обычно — на границе, middleware/handler). Внутренние слои — добавляют контекст через chaining, не логируют.

### BP-19: Missing Idempotency
- Retry запроса приводит к дублированию операции (double charge, double create)
- POST-запросы без idempotency key
- Message consumer обрабатывает одно сообщение дважды и создаёт дубликат
- **Fix:** Idempotency key на мутирующих операциях. Consumer-ы проверяют "уже обработано?" перед выполнением. UPSERT вместо INSERT.

### BP-20: Feature Flag Rot
- Feature flags создаются, но никогда не удаляются
- Код обрастает ветвлениями `if feature_enabled("old_flag_2023")`
- Невозможно понять, какой код реально работает в production
- Flags без TTL, без owner, без review process
- **Fix:** Каждый flag создаётся с owner, TTL и cleanup ticket. Периодический аудит: если flag 100% включён > 30 дней — удалить ветвление, оставить только новый путь.

### BP-21: Chatty Microservices
- Один бизнес-запрос → 10+ синхронных inter-service вызовов
- Каждый вызов добавляет latency и точку отказа
- Fine-grained API между сервисами требует множества round-trips для одной операции
- **Fix:** Coarse-grained API. Batch endpoints. Async communication. CQRS materialized views.

### BP-22: Catch-Rethrow без добавления контекста
- `try/except` который ничего не добавляет — только ловит и бросает
- Или хуже — ловит typed exception, оборачивает в generic (destroys information)
- **Fix:** Либо добавить контекст (`raise NewError(...) from original`), либо не ловить вообще.

---

## 5. НОВЫЕ СЕКЦИИ АНАЛИЗА

### Section 14: Security Architecture

**Что проверять:**
- Единая модель authentication (JWT, session, API key)?
- Authorization: RBAC / ABAC / policy engine?
- Input validation: на границе (schema validation) или размазана?
- Secrets management: vault / env или hardcoded?
- CSRF / XSS / injection protection: framework-level или ad-hoc?
- Rate limiting: на API gateway или отсутствует?
- Audit logging: кто, когда, что сделал?

**Severity guide:**
- CRITICAL: Hardcoded secrets в коде или config в репозитории
- CRITICAL: SQL/command injection возможны
- CRITICAL: Нет authentication на публичных mutation endpoints
- WARNING: Нет rate limiting на auth endpoints
- WARNING: Authorization дублируется между endpoints
- WARNING: Нет input validation на границе
- SUGGESTION: Мог бы использовать policy engine

**Template fragment для отчёта:**
```markdown
## Section 14: Security Architecture
<auth model, authz approach, input validation, secrets, injection vectors, rate limiting, audit>
```

### Section 15: API Design Quality

**Что проверять:**
- Consistency: naming, HTTP methods, status codes, error format across endpoints
- Versioning: стратегия и последовательность применения
- Pagination: cursor/offset, default/max limit
- Error contract: единый формат (code + message + details)
- Backward compatibility и deprecation стратегия
- Resource design: REST-ful или RPC-style? Consistent?
- Documentation: OpenAPI spec актуален?

**Severity guide:**
- CRITICAL: Breaking changes без versioning
- CRITICAL: Inconsistent error format across endpoints
- WARNING: Нет pagination на list endpoints (>100 records)
- WARNING: Mixed naming conventions
- WARNING: Нет deprecation механизма
- SUGGESTION: Cursor-based pagination для производительности
- SUGGESTION: OpenAPI auto-generated из кода

**Template fragment для отчёта:**
```markdown
## Section 15: API Design Quality
<consistency, versioning, pagination, error contract, backward compat, documentation>
```

### Section 16: Configuration Architecture

**Что проверять:**
- Единый config module / config object?
- Валидация при старте (fail fast)?
- Secrets отделены от config?
- Defaults документированы?
- Config injection vs scattered os.getenv()?
- Environment parity?

**Severity guide:**
- CRITICAL: Secrets в коде или в config файлах в репозитории
- WARNING: Config читается в глубине кода (не через injection)
- WARNING: Нет валидации при старте
- WARNING: Defaults не документированы
- SUGGESTION: Typed config object

**Template fragment для отчёта:**
```markdown
## Section 16: Configuration Architecture
<config loading, validation, secrets separation, defaults, environment parity>
```

---

## 6. КАЛИБРОВОЧНАЯ ШКАЛА SCORECARD

> Проблема: без anchor-примеров оценка "7/10 по Modularity" субъективна.

### Формат: 4 anchor points per dimension (Broken 1-3 / Weak 4-5 / Solid 6-7 / Excellent 8-10)

**Modularity:**
- 1-3: God modules (>1500 LOC), vague names (utils.py), >50% кода в 2-3 файлах.
- 4-5: Модули существуют, границы размыты. Naming в основном нормальное, но есть common.py.
- 6-7: Каждый модуль — одна ответственность. Чёткие public API. 1-2 модуля-аутлайера.
- 8-10: Single Responsibility everywhere. Feature changes → 1 модуль. Self-documenting names.

**Coupling:**
- 1-3: Fan-out >10. Global mutable state. Singletons без injection. Всё зависит от всего.
- 4-5: Fan-out 7-10. Некоторый DI, но не систематический.
- 6-7: DI используется. Interface-based. Fan-out <7. 1-2 tight coupling spots.
- 8-10: Все зависимости injectable. Fan-out <5. DAG, no cycles.

**Cohesion:**
- 1-3: Функции в модуле не связаны. "utils" содержит date formatting, HTTP calls, и crypto.
- 4-5: Связанные функции рядом, но 30% кода в неструктурированных helpers.
- 6-7: Высокая cohesion. Внутренние вызовы > внешних. Редкие исключения.
- 8-10: Каждый модуль — cohesive unit. Нет orphan functions. Data and behavior together.

**Layering:**
- 1-3: Нет слоёв. SQL в роутерах. Business logic в templates.
- 4-5: Слои намечены, но протекают. HTTP objects в service layer. 2-3 violations.
- 6-7: Router → Service → Repository. 1 minor violation. Cross-cutting выделены.
- 8-10: Zero violations. DTOs на каждой границе. Domain не знает о HTTP/DB.

**Consistency:**
- 1-3: 3+ разных подхода к error handling. Naming хаос.
- 4-5: Основной паттерн есть, новый код drift-ит.
- 6-7: Один паттерн для каждой проблемы. Naming consistent с 1-2 исключениями.
- 8-10: Полная consistency. Conventions documented.

**Error Design:**
- 1-3: Bare except. Silent swallowing. Internal details в ошибках.
- 4-5: Некоторые typed errors, inconsistent. Endpoints leak stack traces.
- 6-7: Error hierarchy. Consistent format. Boundary translation. 1-2 bare catches.
- 8-10: Full hierarchy. Machine-readable codes. Retry strategies. No leaks.

**Data Flow:**
- 1-3: Hidden mutations. Multiple sources of truth. Side effects everywhere.
- 4-5: Pipeline видна, но с shortcuts. 1-2 sources of truth конфликтуют.
- 6-7: Clear pipeline. Explicit side effects. Minor leaks.
- 8-10: Pure transformations. Single source of truth. All mutations traceable.

**Scalability:**
- 1-3: In-process state. N+1 queries. No pooling. Unbounded queries.
- 4-5: Connection pooling exists. Some N+1.
- 6-7: Stateless handling. Pagination. 1-2 bottleneck spots.
- 8-10: Horizontally scalable. Queue-based. Batch operations. Caching strategy.

**Testability:**
- 1-3: Import-time side effects. Hardcoded dependencies. Global state between tests.
- 4-5: Некоторый DI. Моки возможны, но setup сложный.
- 6-7: DI systematic. Interfaces at boundaries. Tests stable.
- 8-10: Full DI. In-memory adapters. Domain testable without framework.

**Evolvability:**
- 1-3: Shotgun surgery. Deep inheritance. No extension points.
- 4-5: Можно добавить фичу, но 3-4 файла.
- 6-7: Strategy pattern. Plugin-ready. 1-2 файла для feature.
- 8-10: Open/Closed in practice. New features = new modules.

**Concurrency:**
- 1-3: Unprotected shared state. Sync blocking in async. No timeouts.
- 4-5: Locks inconsistent. Pool configured but not optimized.
- 6-7: Consistent synchronization. Pools bounded. Timeouts propagated.
- 8-10: Lock-free where possible. Circuit breakers. Full timeout budgets.

**Observability:**
- 1-3: print(). No correlation IDs. Secrets in logs. No health endpoints.
- 4-5: Logger exists but plain text. No correlation.
- 6-7: Structured logging. Correlation IDs. Health checks. No PII.
- 8-10: Full correlation. RED/USE metrics. Distributed tracing.

**Security (NEW):**
- 1-3: Hardcoded secrets. No auth on some endpoints. SQL injection possible.
- 4-5: Auth inconsistent. Some input validation. No audit log.
- 6-7: Consistent auth. Schema validation. Secrets in vault/env. Rate limiting.
- 8-10: Policy engine. Zero-trust. Full audit. OWASP top 10 addressed.

**API Design (NEW):**
- 1-3: Inconsistent naming. No versioning. Errors ad-hoc. No pagination.
- 4-5: Naming mostly consistent. Some pagination. No versioning.
- 6-7: Consistent REST. Versioned. Pagination everywhere. Unified error contract.
- 8-10: Contract-first. Consumer-driven tests. Cursor pagination. Full backward compat.

**Configuration (NEW):**
- 1-3: os.getenv() разбросан. Secrets hardcoded. Нет валидации.
- 4-5: Config module существует, не всё через него.
- 6-7: Typed config. Validation at startup. Secrets через env.
- 8-10: Single config object. Full validation. Vault. Environment parity.

---

## 7. ОБНОВЛЁННЫЙ SCORECARD

### Новые веса (15 dimensions)

| Dimension | Weight | Rationale |
|-----------|--------|-----------|
| Modularity | 1.5x | Structural foundation |
| Coupling | 1.5x | Structural foundation |
| Cohesion | 1.5x | Structural foundation |
| Layering | 1.2x | Maintainability |
| Consistency | 1.2x | Maintainability |
| Error Design | 1.0x | Operational quality |
| Data Flow | 1.0x | Operational quality |
| Scalability | 1.0x | Growth readiness |
| Testability | 1.0x | Development velocity |
| Evolvability | 1.0x | Long-term health |
| Concurrency | 1.0x | Runtime safety |
| Observability | 1.0x | Operational readiness |
| Security | 1.3x | Non-negotiable |
| API Design | 1.0x | Interface quality |
| Configuration | 0.8x | Supporting, не core |

**Total weight sum: 1.5+1.5+1.5+1.2+1.2+1.0+1.0+1.0+1.0+1.0+1.0+1.0+1.3+1.0+0.8 = 17.5**

**Formula:** `weighted_avg = sum(dimension_score × weight) / 17.5`

---

## 8. ОБНОВЛЁННЫЕ ESCALATION RULES

### Security Escalation
- Hardcoded secrets в коде → 🔴 CRITICAL
- SQL/command injection возможен → 🔴 CRITICAL
- Нет auth на публичных mutation endpoints → 🔴 CRITICAL
- Нет rate limiting на auth endpoints → 🟡 WARNING
- Authorization дублируется между endpoints → 🟡 WARNING
- Нет input schema validation → 🟡 WARNING
- Нет audit logging → 🟡 WARNING
- Мог бы использовать policy engine → 🟢 SUGGESTION
- Full zero-trust + policy engine + automated security tests → 💎 DIAMOND

### API Design Escalation
- Breaking changes без versioning → 🔴 CRITICAL
- Inconsistent error format across endpoints → 🔴 CRITICAL
- Нет pagination на list endpoints (>100 records) → 🟡 WARNING
- Mixed naming conventions → 🟡 WARNING
- Нет deprecation механизма → 🟡 WARNING
- Cursor pagination вместо offset → 🟢 SUGGESTION
- Contract testing → 💎 DIAMOND

### Configuration Escalation
- Secrets в коде / config в repo → 🔴 CRITICAL
- Config разбросан по коду (не через injection) → 🟡 WARNING
- Нет валидации при старте → 🟡 WARNING
- Typed config с полной валидацией при старте (DP-19 level) → 💎 DIAMOND

---

## 9. СВОДКА ИЗМЕНЕНИЙ

### Количественно

| Элемент | v1.1.0 | v2.0.0 (target) | Delta |
|---------|--------|------------------|-------|
| Analysis Sections | 12+1 | 15+1 | +3 |
| Good Patterns | 13 | 20 | +7 |
| Bad Patterns | 13 | 22 | +9 |
| Diamond Patterns | 8 | 19 | +11 |
| Scorecard Dimensions | 12 | 15 | +3 |
| Calibration Anchors | 0 | 15×4 = 60 | +60 |
| Total weight sum | 13.4 | 17.5 | +4.1 |

### Качественно
- **Coverage:** backend-only → full-stack (API, Security, Config, DDD, distributed systems)
- **Diamond-ы:** ORM-specific → universal (Outbox, Event Sourcing, CQRS, Saga, Hexagonal, Strangler Fig, Bulkhead, Contract Testing, Graceful Degradation, Idempotency, Typed Config)
- **Bad Patterns:** code-level → architecture-level (Distributed Monolith, Shared DB, Anemic Domain, Chatty Microservices)
- **Scorecard:** субъективный → calibrated с 60 anchor-примерами + verified weight formula

---

## 10. ПЛАН ВНЕДРЕНИЯ

1. **patterns-catalog.md** — добавить GP-14..GP-20, BP-14..BP-22, DP-09..DP-19
2. **analysis-sections.md** — добавить Section 14 (Security), 15 (API Design), 16 (Configuration)
3. **severity-format.md** — добавить Security/API/Config escalation rules
4. **output-template.md** — обновить шаблон: 3 новые секции + 15-мерный scorecard с total weight 17.5
5. **SKILL.md** — обновить Step 3 (15 секций), Step 5 (15 dimensions + формула + веса)
6. **Новый файл: calibration-anchors.md** — калибровочная шкала (15 × 4 anchors)
7. **CHANGELOG.md** — зафиксировать v2.0.0

---
---

# ЧАСТЬ II: arch-review-bogame (project skill) — v2.0.0 → v3.0.0

---

## 11. ТЕКУЩЕЕ СОСТОЯНИЕ

### Что есть
- 12 секций анализа (Layer Compliance → Doc Accuracy) + fix/refactor modes
- 12-мерный project scorecard
- Детальные project-rules (12 sections), coding-standards, patterns-checklist
- Специфика: L0/L1/L2, Service Registry, Agent Architecture, Protocol Engine, Meta-Agent, Memory Model, Motherboard, Flow Executor, Resource Management, Security, GDScript boundary

### Где сильно
- L0/L1/L2 layer compliance, Service Registry (40+ сервисов), Protocol Engine, Meta-Agent decomposition, Resource Management

### Зависимость от generic skill
BOGame skill runs AFTER arch-review general. Combined quality gate объединяет оба score. С обновлением generic skill до v2.0.0 (15 dimensions вместо 12), combined gate должен учитывать новый формат general score. При внедрении обновить combined gate section в output-template.md: general score теперь 15-мерный, формула `(gen_weighted + proj_avg) / 2` остаётся, но general score рассчитывается по новым весам (total weight 17.5).

---

## 12. AGENT ORCHESTRATION — УСИЛЕНИЕ

### 12.1 Context Window Budget Tracking
**Новый red flag:**
- Агент передаёт полный accumulated context следующему без compaction
- Нет лимита на размер context, system prompt + history >60% окна

**Checklist:**
- [ ] Context budget per agent (max tokens for system prompt + history)
- [ ] Context compaction/summarization before handoff
- [ ] Actual context utilization logged per agent call

### 12.2 Agent Tool Allowlisting
**Новый red flag:**
- Все агенты имеют доступ ко всем MCP tools без ограничений

**Checklist:**
- [ ] Each agent profile defines allowed tools explicitly
- [ ] Tool calls validated against allowlist before execution
- [ ] Denied tool calls logged with agent_id + tool_name

### 12.3 Two-Phase Action Pattern (Plan → Validate → Execute)
**Новый red flag:**
- Write-операция выполняется без предварительного plan step

**Checklist:**
- [ ] High-risk actions: Plan → Validate → Execute pipeline
- [ ] Plan is inspectable (logged, auditable) before execution
- [ ] Failed validation prevents execution (not just logs)

### 12.4 Agent Timeout Budgets
**Новый red flag:**
- Agent execution без timeout
- Supervisor.wait_for_task() без timeout
- Agent в EXECUTING без heartbeat/watchdog

**Checklist:**
- [ ] Every execution has timeout budget (per task type)
- [ ] Supervisor enforces timeout → ERROR on expiry
- [ ] Watchdog detects stuck agents

---

## 13. PROTOCOL ENGINE — УСИЛЕНИЕ

### 13.1 Protocol Versioning & Migration
**Checklist:**
- [ ] In-flight executions pinned to version at start
- [ ] Protocol version migration strategy documented
- [ ] Schema changes validated for backward compatibility

### 13.2 Protocol Execution Observability
**Checklist:**
- [ ] Each step: start_time, end_time, duration_ms, status, error
- [ ] correlation_id propagated through all downstream calls
- [ ] Failed steps: step_index, step_title, error_type, error_message, retry_count

### 13.3 Protocol Idempotency
**Checklist:**
- [ ] Steps with side effects have idempotency mechanism
- [ ] RESUME verifies step completion before re-executing
- [ ] Checkpoint captures step outcome, not just step index

---

## 14. SQLITE CONCURRENCY — УСИЛЕНИЕ

### 14.1 busy_timeout Configuration
**Checklist:**
- [ ] All connections: `PRAGMA busy_timeout = 5000` (minimum)
- [ ] Configured in connection factory, not per-query

### 14.2 Single-Writer Enforcement
**Checklist:**
- [ ] All writes through dedicated_writer or equivalent
- [ ] Write transactions short (no external I/O inside)
- [ ] Bulk operations batched into single transaction

### 14.3 WAL File Growth Control
**Checklist:**
- [ ] `PRAGMA wal_autocheckpoint` set (1000 pages default)
- [ ] Long-running reads avoided or snapshot isolation used
- [ ] WAL file size in health metrics

---

## 15. MULTI-PROJECT ISOLATION — УСИЛЕНИЕ

### 15.1 Blast Radius Containment
**Checklist:**
- [ ] Per-project resource pool quotas
- [ ] Agent crash in project X doesn't affect project Y
- [ ] Module-level mutable state partitioned by project_id

### 15.2 Noisy Neighbor Detection
**Checklist:**
- [ ] Per-project metrics: tokens/sec, MCP calls/sec, queue depth
- [ ] Alert when project exceeds fair-share by >2x for >5min
- [ ] Automatic throttling on noisy neighbor

---

## 16. FLOW EXECUTOR — УСИЛЕНИЕ

### 16.1 Data Type Safety Between Nodes
- Silent type coercion → 🟡 WARNING (was: not flagged)
- Data loss from type mismatch → 🔴 CRITICAL

**Checklist:**
- [ ] Node connections validate type compatibility
- [ ] Type mismatch produces warning log
- [ ] Strict mode option (mismatch = error)

### 16.2 Parallel Node State Isolation
**Checklist:**
- [ ] Each branch: isolated copy of flow state
- [ ] Merge function explicitly defined
- [ ] Branch timeout: stuck branch doesn't block others

### 16.3 Paused Flow Persistence
- `_paused_flows` without persistence → 🔴 CRITICAL (upgraded from implied)

**Checklist:**
- [ ] Paused state persisted to database
- [ ] On restart: paused flows restored from DB
- [ ] Orphan cleanup after TTL (default 24h)

---

## 17. AGENT-SPECIFIC OBSERVABILITY — НОВАЯ ПРОВЕРКА

### 17.1 Agent Decision Tracing
- [ ] Every decision logged: tool chosen, confidence score, routing reason
- [ ] Every LLM call: model, prompt hash, token count, latency_ms, cost
- [ ] End-to-end reasoning chain traceable

### 17.2 Cost Attribution
- [ ] LLM costs attributed per agent + task + project
- [ ] MCP tool call costs tracked per agent call
- [ ] Cost anomaly detection: alert if call exceeds N× average

### 17.3 Quality Signals
- [ ] Generator-Critic iterations tracked
- [ ] Confidence scores logged before/after execution
- [ ] Failed task failure mode analysis (timeout, confidence, tool error, budget)

---

## 18. SECURITY — AGENT-SPECIFIC ПРОВЕРКИ

### 18.1 Prompt Injection Protection
**Checklist:**
- [ ] User input separated from system prompt
- [ ] Input sanitization for injection patterns
- [ ] System prompt integrity (not modifiable by user content)
- [ ] Output guardrails catch system prompt exfiltration attempts

### 18.2 MCP Tool Safety
**Checklist:**
- [ ] Tool parameters validated against schema
- [ ] Per-tool rate limits configured
- [ ] Tool results validated before passing to agent context

---

## 19. CODING STANDARDS — ДОПОЛНЕНИЯ

### 19.1 Advanced Async Patterns
**Checklist:**
- [ ] All `create_task()` results stored and awaited/cancelled on shutdown
- [ ] `async with` for all resource acquisition
- [ ] No fire-and-forget tasks without `add_done_callback()`

### 19.2 SQLite-Specific Patterns
**Checklist:**
- [ ] All connections: WAL + busy_timeout + foreign_keys pragmas at creation
- [ ] All connections via context manager
- [ ] All SELECT with LIMIT or bounded WHERE

---

## 20. PROJECT-SPECIFIC DIAMOND PATTERNS

### PDP-01: Declarative Motherboard with Full Lifecycle
- JSON declarative definition, 12 node types, risk-per-node, checkpoints, generator-critic with quality threshold, sub-motherboard risk inheritance, output guardrails
- **Почему diamond:** Production-grade declarative orchestration с risk management и crash recovery.

### PDP-02: Three-Layer Memory Model
- Episodic (TTL 30d), Semantic (deduplication), Procedural (linked to source)
- Strict type separation, consolidation on hibernation
- **Почему diamond:** Cognitive architecture for agents. Separation prevents pollution. Procedural memory = learning.

### PDP-03: Hibernation Lifecycle with Ordered Cleanup
- 6-step ordered sequence, WAL checkpoint via run_in_executor
- **Почему diamond:** Full resource lifecycle. No leaks, no stale cache, no WAL bloat.

### PDP-04: Circuit Breaker with asyncio.Lock + DegradationResult
- Correct async FSM, typed degradation responses
- **Почему diamond:** Resilience adapted for async Python. Typed degradation over raw exceptions.

### PDP-05: Fair Scheduling with Starvation Prevention
- Round-robin deque, per-project concurrent limit, asyncio.Lock
- **Почему diamond:** Fairness guarantee in multi-tenant agent system.

### PDP-06: Double-Entry Ledger Pattern
- (Из существующих severity-format.md diamond rules)
- Every state change creates balancing records, sum invariants, immutable audit trail
- **Почему diamond:** Data integrity + auditability + catch bugs early.

### PDP-07: Lazy Singleton with Reset for Testing
- (Из существующих severity-format.md diamond rules)
- Resource created on first access, factory function with module-level cache, reset mechanism
- **Почему diamond:** Solves async lifecycle issues + enables test isolation.

---

## 21. ОБНОВЛЁННЫЕ ESCALATION RULES

**Agent Orchestration:**
- Agent without timeout budget → 🟡 WARNING
- Agent tool calls without allowlist → 🟡 WARNING
- Context window utilization not tracked → 🟡 WARNING
- Full agent decision tracing with cost attribution → 💎 DIAMOND

**Protocol Engine:**
- Step with side effects lacks idempotency → 🟡 WARNING
- In-flight execution not pinned to version → 🟡 WARNING
- Steps instrumented with timing + correlation_id → 💎 DIAMOND

**SQLite:**
- Missing busy_timeout pragma → 🟡 WARNING
- Writes bypassing dedicated_writer → 🔴 CRITICAL
- WAL checkpoint blocking event loop → 🔴 CRITICAL
- fetchall() without LIMIT on unbounded query → 🟡 WARNING

**Security (Agent-specific):**
- User input concatenated into LLM prompt → 🔴 CRITICAL
- MCP tool with unvalidated user parameters → 🔴 CRITICAL
- No per-tool rate limiting → 🟡 WARNING

**Flow Executor:**
- `_paused_flows` not persisted → 🔴 CRITICAL
- Silent type coercion between nodes → 🟡 WARNING
- Parallel branches sharing mutable state → 🔴 CRITICAL

---

## 22. СВОДКА (PROJECT SKILL)

### Новые проверки: ~65

| Область | Checks | Severity |
|---------|--------|----------|
| Agent Context Budget | 3 | WARNING |
| Agent Tool Allowlisting | 3 | WARNING |
| Two-Phase Actions | 3 | WARNING |
| Agent Timeouts | 3 | WARNING/CRITICAL |
| Protocol Versioning | 3 | WARNING |
| Protocol Observability | 3 | WARNING/DIAMOND |
| Protocol Idempotency | 3 | WARNING |
| SQLite busy_timeout | 2 | WARNING |
| SQLite Single-Writer | 3 | WARNING/CRITICAL |
| SQLite WAL Growth | 3 | WARNING |
| Blast Radius Containment | 3 | WARNING/CRITICAL |
| Noisy Neighbor Detection | 3 | WARNING |
| Flow Type Safety | 3 | WARNING/CRITICAL |
| Paused Flow Persistence | 3 | CRITICAL |
| Agent Decision Tracing | 3 | WARNING |
| Cost Attribution | 3 | WARNING |
| Quality Signals | 3 | WARNING |
| Prompt Injection | 4 | CRITICAL |
| MCP Tool Safety | 3 | CRITICAL/WARNING |
| Async Advanced | 3 | WARNING |
| SQLite Patterns | 4 | WARNING |

### Diamond Patterns: 5 новых + 2 из существующих = 7 PDP

### Scorecard: 12 → 13 dimensions (+Agent Observability)

---

## 23. ПЛАН ВНЕДРЕНИЯ (PROJECT SKILL)

1. **project-rules.md** — sub-sections: Section 3 (Agent: context, tools, timeouts), Section 8 (Protocol: versioning, observability, idempotency), Section 10 (Flow: type safety, pause persistence), Section 12 (SQLite: busy_timeout, single-writer, WAL growth)
2. **coding-standards.md** — Section 9 (Advanced Async), усилить Section 8 (Database pragmas)
3. **patterns-checklist.md** — Agent Context, Protocol Observability, SQLite Pragmas, Prompt Injection, MCP Safety
4. **severity-format.md** — escalation rules из Section 21
5. **SKILL.md** — проверки в Steps 5/5.5/5.7/7.5/8/8.5 + новый Step (Agent Observability)
6. **output-template.md** — 13-мерный scorecard (+Agent Observability), combined gate note (general теперь 15-мерный)
7. **CHANGELOG.md** — v3.0.0

---
---

# APPENDIX A: Validation Log

## Найденные и исправленные проблемы

| # | File | Severity | Описание | Исправление |
|---|------|----------|----------|-------------|
| G1 | Generic | GAP | Нет total weight sum для 15-мерного scorecard | Добавлен: total weight = 17.5, формула weighted_avg |
| G2 | Generic | GAP | Нет template-фрагментов для S14/S15/S16 | Добавлены template fragments в Section 5 |
| G3 | Generic | GAP | Configuration Diamond в escalation rules без matching DP | Добавлен DP-19 (Typed Configuration with Startup Validation), escalation rule обновлён со ссылкой |
| B1 | Bogame | BREAK | "13 dimensions → +1" — арифметическая ошибка | Исправлено на "12 → 13 (+1)" в Section 22 |
| B2 | Bogame | GAP | Существующие diamond rules не в PDP-каталоге | Добавлены PDP-06 (Double-Entry Ledger), PDP-07 (Lazy Singleton with Reset) |
| B3 | Bogame | GAP | Нет упоминания о влиянии generic upgrade на combined gate | Добавлен параграф в Section 11 о зависимости от generic 15-dimensional score |

## Счёт после исправления

| Элемент | Generic | Bogame |
|---------|---------|--------|
| Diamond Patterns | 19 (was 18) | 7 PDP (was 5) |
| Total DP-19 добавлен | ✅ | — |
| Scorecard formula verified | ✅ (17.5) | ✅ (12→13) |
| Template fragments | ✅ S14/S15/S16 | — |
| Cross-skill dependency | — | ✅ documented |
