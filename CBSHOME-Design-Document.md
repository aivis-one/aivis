# cbshome — Дизайн-документ (Конституция)

**Версия:** 1.6
**Дата:** 12 мая 2026
**Статус:** Active
**Репозиторий:** https://github.com/aivis-one/aivis

---

## 1. Что такое cbshome

### 1.1. Миссия

> **AIVIS.ONE -- единая инвестиционная платформа CBS Home. Инвесторы покупают продукты, агенты продают и зарабатывают комиссии, компании размещают продукты и получают выручку, система управляет всем автоматически.**

cbshome -- платформа для четырёх аудиторий, объединённая под одним доменом `cbshome.org`:

| Аудитория | Что получает |
|-----------|-------------|
| **Investor** | Кабинет, портфель, покупка продуктов, рассрочка, активный баланс, пакет документов |
| **Agent** | Всё инвесторское + Agent Hub: реферальные ссылки, L1/L2/L3 комиссии, лидерборд, сертификация, пассивный баланс, расширенный пакет документов |
| **Company** | Кабинет компании: размещение продуктов, аналитика продаж, управление документами, пассивный баланс (выручка) |
| **Staff** | Управление всеми пользователями, KYC-очередь, платёжный ревью, одобрение заявок агентов, аватаринг. Права определяются permission matrix в конфиге |

### 1.2. Продукты платформы

| Продукт | Компания | Запуск |
|---------|---------|--------|
| **Product A** -- IPI AG | DubaiCo-1 (BVI BC) | Март 2026 |
| **Product B** -- Immo-Pro-Invest | DubaiCo-2 | Май 2026 |
| **Product C** -- CBS Home franchise | DubaiCo-3 | Октябрь 2026 |

Каждый продукт маршрутизирует выручку на Passive balance соответствующей Компании. Добавление новых продуктов и компаний -- через кабинет или Staff, без рефакторинга кода.

### 1.3. Глоссарий

| Термин | Определение |
|--------|-------------|
| **Продукт** | Инвестиционный инструмент, размещённый Компанией на витрине платформы |
| **Портфель** | Пакет продуктов от €200 до €100K+; тип определяет бонус |
| **Рассрочка 6м** | 10% × 5 платежей + 50% финальный |
| **Рассрочка 12м** | 5% × 11 платежей + 45% финальный |
| **Цена фиксируется** | На момент создания плана рассрочки (при первом платеже) |
| **Active balance** | Баланс для покупок. Пополняется внешними деньгами (крипта/фиат). Шлюз "снаружи внутрь" |
| **Passive balance** | Баланс для вывода и начислений. Пополняется системными операциями (комиссии, выручка, бонусы). Шлюз "изнутри наружу" |
| **User-роль** | Investor, Agent, Company, Staff, Platform -- всё это роли единой User-сущности |
| **Platform (системный юзер)** | Специальная роль: `is_system=true`. Принимает все входящие платежи, распределяет по ролям. Не логинится |
| **Staff** | Сотрудник платформы (Admin или Support). Роль `staff` + сущность `StaffProfile` с permission matrix |
| **Аватаринг** | Механизм входа Staff под любым пользователем для техподдержки. Полный audit trail, оверлей "Вернуться в свой аккаунт" |
| **AvatarSession** | Запись сессии аватаринга: кто вошёл, под кем, когда, с какого IP |
| **Сага распределения** | Атомарная цепочка ledger-записей при покупке: Investor Active -> Platform Passive -> Company/Agent Passive |
| **distribution_config** | JSONB в Product: процент компании, агентские комиссии. Дефолты -- в `config` |
| **L1/L2/L3** | Уровни агентских комиссий: 10% / 3% / 1%. Строго для агентов |
| **STOP-механика** | 4-е звено цепочки становится корневым (новая независимая ветка) |
| **Лидерборд** | Рейтинг агентов по объёму, обновляется каждые 60 минут. Строго для агентов |
| **Бонусный пул** | 2% месячного объёма (top-20) + 1% квартального (top-10) |
| **Cooling-off** | 14-дневная задержка выплаты комиссии (EU fiat) -- защита от chargeback |
| **KYC** | Know Your Customer -- верификация через SumSub |
| **Sub-contract** | Отдельный контракт на каждый транш рассрочки |
| **Розетка** | Заготовка под будущую функцию: интерфейс определён, логика не реализована |
| **Конституция** | Этот документ. Описывает что строим и почему. Не меняется без весомой причины |
| **Кодекс** | Backend.md / Frontend.md. Описывает как строим. Живёт в рамках Конституции |

---

## 2. Технологический стек

### 2.1. Backend

| Компонент | Технология | Версия |
|-----------|------------|--------|
| Язык | Python | 3.12 |
| Фреймворк | FastAPI | latest |
| ORM | SQLAlchemy | 2.0 (async) |
| Валидация | Pydantic | v2 |
| Миграции | Alembic | latest |
| Тестирование | pytest + pytest-asyncio | latest |
| Логирование | structlog | latest |
| Type checker | mypy (strict) | latest |
| Formatter/Linter | ruff | latest |

**Абсолютный запрет:** raw SQL (`text(...)`). Только и исключительно ORM.

### 2.2. База данных и кэш

| Компонент | Технология | Назначение |
|-----------|------------|------------|
| Primary DB | PostgreSQL 16 | Все данные |
| Cache / Sessions | Redis 7 | Сессии, очереди задач, кэш |

### 2.3. Frontend

| Компонент | Технология | Версия |
|-----------|------------|--------|
| Фреймворк | Vue 3 | latest |
| Язык | TypeScript | 5.x |
| Сборка | Vite | latest |
| Роутинг | Vue Router | 4.x |
| Стейт | Pinia | latest |
| HTTP | Fetch (обёртка `client.ts`) | native |
| i18n | vue-i18n | v10 |
| Стили | Свой CSS (дизайн-токены) | -- |
| Линтинг | ESLint + Prettier | latest |

### 2.4. Внешние сервисы

| Сервис | Назначение | Фаза |
|--------|------------|------|
| SumSub | KYC верификация (220+ стран) | MVP |
| Telegram Bot API | Уведомления (aiogram), Telegram mini-app | MVP |
| EMAP (primary) + Mailgun (fallback) | Transactional email + email verification | MVP |
| Moonpay / Transak | Fiat on-ramp EUR -> USDT | Розетка (Phase 2) |
| DocuSign | Формальная e-signature | Розетка (Phase 2) |

### 2.5. Инфраструктура

| Компонент | Технология |
|-----------|------------|
| Контейнеризация | Docker + Docker Compose |
| Хостинг | VPS (Ubuntu 22.04+) |
| Reverse proxy | Nginx (на хосте) |
| SSL | Let's Encrypt (certbot) |
| Деплой | `cbshome update` (git pull + rebuild + migrate + restart) |

---

## 3. Архитектура

### 3.1. Модульный монолит сейчас -- микросервисы потом

MVP -- один сервис, разбитый на изолированные модули. Каждый модуль самодостаточен и спроектирован так, чтобы в будущем стать отдельным микросервисом без переписывания бизнес-логики. Граница модуля = граница будущего сервиса.

```
backend/app/modules/
├── auth/               -- Email+password, Telegram WebApp, сессии Redis
├── users/              -- Профили, роли, credentials JSONB, is_system flag
├── kyc/                -- SumSub интеграция, статусы, webhook
├── documents/          -- Документы, версии, факты подписания (checkbox + DocuSign)
├── agent_applications/ -- Заявки на роль агента, история, кулдаун
├── companies/          -- Профили компаний, настройки, аналитика
├── products/           -- Продукты, цены, distribution_config JSONB
├── payments/           -- Крипто-адреса per-payment, блокчейн-трекинг, сага распределения
├── installments/       -- Планы рассрочки, sub-contracts, расписания, PDF
├── commissions/        -- L1/L2/L3 расчёт, leaderboard, бонусные пулы (только агенты)
├── referrals/          -- Реферальные ссылки, attribution, аналитика per-link (только агенты)
├── notifications/      -- Email, in-app, Telegram bot
├── staff/              -- StaffProfile, AvatarSession, KYC-очередь, платёжный ревью
├── ai_trainer/         -- Розетка: квиз-сертификация агентов (Phase 2)
└── tokens/             -- Розетка: токенизация Solana (Q3 2027)
```

### 3.2. Структура модуля

Каждый модуль содержит:

```
module/
├── models.py       -- SQLAlchemy ORM models
├── schemas.py      -- Pydantic request/response schemas
├── service.py      -- Business logic (единственное место для логики)
├── router.py       -- FastAPI endpoints (только маршрутизация)
└── exceptions.py   -- Module-specific exceptions (опционально)
```

**Правило:** router не содержит бизнес-логики. service не знает об HTTP.

### 3.3. Будущий распил на микросервисы

Таблицы БД уже сгруппированы по будущим сервисам:

```
Auth Service:         sessions
User Service:         users, active_ledger, passive_ledger
KYC Service:          kyc_applications
Document Service:     documents, document_versions, document_signings
Agent Service:        agent_applications, agent_quiz_sessions
Company Service:      company_profiles
Product Service:      products, product_prices
Payment Service:      payments, crypto_addresses, transfers
Installment Service:  installment_plans, installment_tranches, contracts
Commission Service:   commission_rules, leaderboard_snapshots, payouts
Referral Service:     referral_links, referral_attributions
Notification Service: notifications, notification_deliveries
Staff Service:        staff_profiles, avatar_sessions, audit_log
```

`trace_id` пробрасывается в каждом запросе -- готова основа для distributed tracing.

### 3.4. Два леджера и финансовые инварианты

Все роли (Investor, Agent, Company, Staff, Platform) -- это роли единой User-сущности. У каждого пользователя два независимых леджера. Double-entry: каждая операция -- две записи, сумма всех записей обоих леджеров вместе = 0 всегда.

#### Системный пользователь Platform

Специальная запись в таблице `users` с флагом `is_system=true` и ролью `platform`. Создаётся при инициализации БД (seed). Не логинится, не появляется в списках пользователей, управляется только автоматическими операциями системы. Принимает все входящие платежи Инвесторов на свой Passive balance и распределяет их сагой.

#### Два леджера -- два однонаправленных шлюза

**active_ledger** -- шлюз "снаружи внутрь":
- Пополняется только внешними деньгами пользователя (крипта, фиат)
- Тратится только на покупки продуктов с витрины

**passive_ledger** -- шлюз "изнутри наружу":
- Пополняется только системными операциями (комиссии, выручка, бонусы, сага распределения)
- Выводится во внешний мир (крипта, фиат)

#### Матрица маршрутов

| Перевод | Разрешён | Примечание |
|---------|----------|------------|
| Active -> свой Active | YES | Не имеет смысла, но не запрещён |
| Active -> чужой Active | YES | Легитимные p2p переводы |
| Active -> свой Passive | NO | Layering: внешние деньги попадают в канал вывода без бизнес-основания |
| Active -> чужой Passive | NO | То же + mixing: источник выведенных средств неотслеживаем |
| Passive -> свой Active | YES | Перевод заработанного на покупки |
| Passive -> чужой Active | YES | Штатная операция: бонусы, промо от Компании и др. |
| Passive -> свой Passive | YES | Не имеет смысла, но не запрещён |
| Passive -> чужой Passive | YES | Штатные переводы между пассивными балансами |

**Единственный запрет:** Active не может попасть в Passive ни через какой маршрут.

**Инвариант системы:** деньги, которые можно вывести из платформы, могут иметь только одно происхождение -- реальная бизнес-активность внутри системы (Passive). Внешние пополнения (Active) выводу не подлежат -- только трате на продукты.

#### Промо-операции Компании

Компания инициирует промо-начисление через запрос к Platform. Platform исполняет как системную операцию (`Passive -> чужой Active`) с обязательной записью `reason` и audit log. Прямого доступа к нестандартным операциям у бизнес-ролей нет -- все исключения только через системный аккаунт.

#### Сага распределения (атомарная)

При покупке Инвестором продукта за 100$:

```
active_ledger:   user=Investor,  amount=-100   -- списание с покупателя
passive_ledger:  user=Platform,  amount=+100   -- приход на платформу

passive_ledger:  user=Platform,  amount=-80    -- распределение компании
passive_ledger:  user=Company,   amount=+80    -- (80% из distribution_config)

passive_ledger:  user=Platform,  amount=-10    -- комиссия L1
passive_ledger:  user=Agent_L1,  amount=+10

passive_ledger:  user=Platform,  amount=-3     -- комиссия L2
passive_ledger:  user=Agent_L2,  amount=+3

passive_ledger:  user=Platform,  amount=-1     -- комиссия L3
passive_ledger:  user=Agent_L3,  amount=+1
                                               -- остаток 6$ остаётся у Platform
```

Вся цепочка -- одна транзакция БД. Либо все шаги, либо ни одного. Промежуточное состояние недопустимо.

Проценты берутся из `product.distribution_config` (JSONB). Если не заданы -- из `config` (дефолты). Компания переопределяет для конкретного продукта при создании или редактировании.

#### Passive balance у чистого инвестора

Пассивный леджер существует технически для всех пользователей, но у инвестора без агентской роли системные начисления в него не поступают. В интерфейсе инвестора пассивный баланс не отображается.

### 3.5. Модуль документов

Документы -- отдельный модуль с полным трекингом в БД. Две сущности:

**Document** -- шаблон документа:
```
id, type (enum), version, title, content_url, is_active, created_at
```

**DocumentSigning** -- факт подписания пользователем:
```
id, user_id, document_id, signed_at, ip_address, user_agent
-- будущее (Phase 2):
docusign_envelope_id, docusign_signed_at
```

Пакеты документов по роли:
- **Investor**: базовый набор (Privacy Policy, Terms, Investment Agreement и др.)
- **Agent**: инвесторский пакет + агентское соглашение (комиссионная политика, MLM terms и др.)
- **Company**: корпоративный пакет (партнёрское соглашение, условия размещения продуктов)

MVP: checkbox consent + факт записывается в `DocumentSigning`. Phase 2: DocuSign envelope -- только поле `docusign_envelope_id` добавляется к существующей записи, структура модуля не меняется.

Версионирование (переподписание при обновлении редакции) -- за пределами MVP, заложено через поле `version`. Система умеет определить, есть ли у пользователя подпись актуальной версии.

### 3.6. Модуль заявок на роль агента

Инвестор подаёт заявку на получение роли агента через настройки кабинета. Отдельная сущность, не флаг на пользователе.

```
AgentApplication:
  id, user_id
  status (enum): pending | approved | rejected
  submitted_at, reviewed_at, reviewed_by (staff_id)
  rejection_reason
  cooldown_until          -- now() + AGENT_APPLICATION_COOLDOWN_DAYS (из config)
  -- будущее (Phase 2):
  quiz_session_id         -- ссылка на сессию AI-тренажёра
  quiz_score
```

Правила:
- У пользователя одновременно только одна активная заявка (pending или approved). Остальные -- история
- При одобрении: `user.role` автоматически меняется на `agent`, пользователь получает агентский пакет документов для подписания
- При отказе: `cooldown_until = now() + AGENT_APPLICATION_COOLDOWN_DAYS` (из config, по умолчанию 30 дней). Новая заявка невозможна до истечения кулдауна
- История всех заявок хранится -- нужна для compliance и будущего AI-тренажёра

### 3.7. Авторизация и каналы входа

Пользователь -- единая сущность (`users`). К ней привязаны один или несколько провайдеров авторизации через `credentials` JSONB:

```json
{
  "email": {"email": "user@example.com", "verified": true},
  "telegram": {"id": 123456789}
}
```

Два канала -- оба полноценные, не первичный/вторичный:

| Канал | Endpoint | Платформа |
|-------|----------|-----------|
| Email + password | `POST /api/v1/auth/email` | Web SPA |
| Telegram WebApp | `POST /api/v1/auth/telegram` | Telegram mini-app |

Личные данные пользователя (имя, страна, телефон) добиваются на ходу в диалогах верификации -- по мере прохождения KYC и других этапов онбординга. Регистрация не требует полного профиля сразу.

### 3.8. Frontend: роли и Shell'ы

Единое SPA с ролевым роутингом. Роль определяется из `GET /api/v1/users/me` после авторизации.

| Роль | Shell | Доступ |
|------|-------|--------|
| `investor` | `InvestorShell` | Кабинет, портфель, рассрочка, активный баланс, документы |
| `agent` | `AgentShell` | Всё инвесторское + Agent Hub (реферальные ссылки, комиссии L1/L2/L3, лидерборд, сертификация, пассивный баланс) |
| `company` | `CompanyShell` | Управление продуктами, аналитика продаж, документы, пассивный баланс (выручка) |
| `staff` | `StaffShell` | Управление всеми пользователями, KYC-очередь, аватаринг. Доступные функции определяются permission matrix |

`AgentShell` включает полный инвесторский интерфейс -- агент видит своё портфолио внутри агентского кабинета без переключения.

Системный пользователь `platform` (`is_system=true`) Shell'а не имеет -- вход в интерфейс невозможен.

### 3.9. Платформенная абстракция (Frontend)

Приложение работает в двух средах. Различия инкапсулированы в `src/platform/`:

| Файл | Назначение |
|------|------------|
| `platform/types.ts` | Интерфейс `Platform` (общий контракт) |
| `platform/web.ts` | Реализация для браузера (Web SPA) |
| `platform/telegram.ts` | Реализация для Telegram WebApp SDK |
| `platform/index.ts` | Автодетект: `window.Telegram?.WebApp` -> telegram, иначе web |

```typescript
interface Platform {
  name: 'web' | 'telegram'
  init(): Promise<void>
  getInitData(): string | null
  getTheme(): 'light' | 'dark'
  hapticFeedback(type: string): void
  showBackButton(cb: () => void): void
  hideBackButton(): void
  close(): void
}
```

Обе реализации полноценные. Нет понятия "заглушка" -- web и telegram равнозначны.

### 3.10. Модуль Staff и аватаринг

Сотрудники платформы -- отдельная сущность `StaffProfile`, привязанная к User.

```
StaffProfile:
  id, user_id
  permissions (JSONB)    -- permission matrix из config или переопределённая
  created_at, is_active
```

Конфигурация по умолчанию (`config`):

```yaml
staff_permissions:
  avatar_mode: true
  kyc_approve: true
  payment_review: true
  user_block: true
  financial_operations: true   # false для Support
  agent_application_review: true
```

"Admin" -- Staff с полными правами. "Support" -- Staff с `financial_operations: false` и другими ограничениями. Градации определяются конфигурацией, не отдельными ролями в коде.

#### Аватаринг

Staff вводит ID пользователя в специальном поле `StaffShell` и переходит в его интерфейс. Создаётся запись `AvatarSession`:

```
AvatarSession:
  id, staff_id, target_user_id
  created_at, ended_at
  ip_address
```

Механика:
- Сессия Staff не уничтожается -- создаётся дочерняя `AvatarSession`
- JWT/сессия содержит `avatar_session_id`; бэкенд знает, что операция выполняется от имени Staff
- Все мутирующие операции в режиме аватара пишутся в `audit_log` с `performed_by=staff_id, on_behalf_of=target_user_id`
- Фронт показывает оверлей: "Avatar mode: {user_name} — Return to your account"
- Кнопка возврата завершает `AvatarSession`, восстанавливает оригинальную сессию Staff
- Реальная сессия целевого пользователя не затрагивается -- два независимых клиента

---

## 4. Принципы и правила

### 4.1. Инварианты (нельзя нарушать никогда)

| Инвариант | Почему |
|-----------|--------|
| **Только ORM** -- никакого raw SQL | Единообразие, типобезопасность, будущий распил |
| **Два леджера** -- active и passive, баланс только через записи | Финансовая целостность |
| **Сага атомарна** -- распределение платежа либо целиком, либо никак | Нет зависших денег на Platform |
| **Маршруты балансов** -- Active никогда не попадает в Passive (раздел 3.4) | AML-защита |
| **Бизнес-логика только в service** | Тестируемость, переносимость |
| **Статусные переходы только через явные функции** | State machine с валидацией |
| **commit() только через get_db_session()** | Нет двойных коммитов |
| **Только structlog** -- никакого `import logging` | Единый формат логов |
| **Только i18n-ключи на фронте** -- никаких строковых литералов | Мультиязычность без рефакторинга |
| **Реферальные ссылки и Agent Hub** -- строго только для агентов | Бизнес-логика ролей |
| **Platform (`is_system=true`)** -- только автоматические операции, вход невозможен | Безопасность системного аккаунта |
| **Аватаринг** -- все операции логируются с `performed_by` + `on_behalf_of` | Audit trail, compliance |

### 4.2. Запреты (бэкенд)

```python
# ЗАПРЕЩЕНО:
await session.commit()            # в роутерах -- двойной коммит
raw_sql = text("SELECT ...")      # только ORM
profile.data["key"] = value       # JSONB мутация без set_jsonb()
ledger.balance += amount          # прямое изменение баланса
payment.status = "confirmed"      # статус без валидации перехода
import logging                    # только structlog
```

### 4.3. Запреты (фронтенд)

```css
/* ЗАПРЕЩЕНО -- хардкод цветов: */
color: #334D6E;

/* ПРАВИЛЬНО -- CSS-переменные: */
color: var(--cbs-primary);
```

```typescript
// ЗАПРЕЩЕНО -- строковые литералы:
title="Investment Portfolio"

// ПРАВИЛЬНО -- i18n ключи:
:title="t('portfolio.title')"

// ЗАПРЕЩЕНО -- локальные дубли маппингов:
const STATUS_LABEL = { pending: 'Pending', ... }

// ПРАВИЛЬНО -- единый источник:
import { PAYMENT_STATUS_LABEL } from '@/utils/displayHelpers'
```

### 4.4. Соглашения по коду

| Правило | Значение |
|---------|---------|
| Комментарии в коде | Только английский |
| Общение / документация | Русский |
| Стрелка в коде | Только ASCII `->` (не Unicode) |
| Тире в коде | Только `--` двойной дефис (не Unicode) |
| Unicode-символы | Допустимы только в документации вне кода |
| Backend formatter | ruff |
| Backend type checker | mypy (strict) |
| Frontend formatter | Prettier |
| Frontend linter | ESLint (flat config) |

### 4.5. i18n -- обязательно с первого коммита

**Основной язык: EN.** Дополнительные (Phase 2+): RU, DE, AR.

Правила:
- `vue-i18n v10` подключается при инициализации проекта, до первого компонента
- Все строки -- в `src/locales/en.json` (и будущих `ru.json`, `de.json`, `ar.json`)
- Ни одного строкового литерала в `.vue` и `.ts` -- только `t('key')`
- Бэкенд чист: только коды ошибок в ответах API
- Notification templates -- в `en.yaml` (и будущих `ru.yaml` etc.)

Нарушение этого правила с первого дня создаёт технический долг в 9-14 дней рефакторинга (опыт VELO: 486 литералов в 54 файлах).

### 4.6. KYC и онбординг

Верификация -- обязательна для совершения любой покупки и активации агентского модуля. Данные пользователя добираются на ходу в верификационных диалогах:

- Этап 1: email + password (или Telegram)
- Этап 2: email verification
- Этап 3: выбор роли + подписание базового пакета документов
- Этап 4: KYC (SumSub) -- имя, страна, документ, селфи
- Этап 5 (агенты): заявка -> одобрение Staff -> подписание агентского пакета документов

Платформа не блокирует регистрацию из-за неполного профиля. Блокирует только покупку -- до `kyc_status = approved`.

### 4.7. Принципы проверяются на каждом решении

Любое архитектурное предложение, которое выглядит как "разумный компромисс", обязано быть явно прокатано через принципы своего домена. Принципы домена -- это:

- Инварианты и запреты этой Конституции (§4.1-§4.4).
- Принципы документа, в рамках которого принимается решение (например, P-OBS-1...P-OBS-5 в `CBSHOME-Observability-Frontend.md`, или другие, появляющиеся в специализированных документах по мере их написания).

Если у документа-домена нет явно сформулированных принципов -- решение всё равно проверяется на принципах Конституции, как минимальной базе.

**Механика:**

1. Тот, кто предлагает решение (координатор, исполнитель, заказчик), при формулировке решения **обязан явно перечислить**, какие принципы домена релевантны и почему предложение их не нарушает. Молчание о принципах = недопустимое решение, оно отправляется на переоценку.
2. Тот, кто принимает решение, имеет право требовать такой проверки и отклонять решения без неё.
3. Если решение явно нарушает принцип, оно либо отклоняется, либо принимается с **явным обоснованием исключения** в changelog'е документа.

**Почему этот принцип нужен:** опыт показал, что без явной обязательной проверки разумно звучащие предложения проскальзывают мимо принципов. Пример (родивший правило): в `CBSHOME-Observability-Frontend.md` v0.1 было предложено `withTrace(callback)` -- обёртка для per-action trace_id, выглядевшая как разумный компромисс между route-level и full automation. Принцип P-OBS-3 ("новый разработчик не помнит дисциплину") был нарушен, потому что обёртка как раз и требует от разработчика дисциплины. Без явной проверки решение прошло бы в реализацию. С явной проверкой -- остановились, переоценили, отклонили.

**Где это видно в работе:**

- В чате координации архитектурных решений -- предложение содержит секцию "проверка по принципам: ...".
- В changelog'ах документов при принятии нетривиальных решений -- ссылка на затронутые принципы и явное обоснование, если есть исключения.
- В промптах для исполнительных чатов -- ссылка на этот §4.7 для решений, которые могут возникнуть по ходу реализации.

---

## 5. Структура репозитория

```
cbshome/                           -- GitHub: aivis-one/aivis
├── backend/
│   ├── app/
│   │   ├── main.py                -- FastAPI app + lifespan
│   │   ├── core/                  -- DB, Redis, config, exceptions, mixins
│   │   └── modules/               -- Бизнес-модули (см. раздел 3.1)
│   ├── migrations/                -- Alembic migrations
│   ├── tests/                     -- pytest
│   ├── scripts/                   -- seed.py и прочие утилиты
│   ├── Dockerfile
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── api/                   -- HTTP-клиент + методы по модулям
│   │   ├── components/            -- ui/, layout/, shared/
│   │   ├── composables/           -- useAuth, usePagination и др.
│   │   ├── locales/               -- en.json, ru.json, de.json, ar.json
│   │   ├── platform/              -- Web / Telegram абстракция
│   │   ├── router/                -- Vue Router + guards
│   │   ├── stores/                -- Pinia stores
│   │   ├── styles/                -- variables.css (дизайн-токены), global.css
│   │   ├── utils/                 -- format.ts, displayHelpers.ts, staffHelpers.ts
│   │   └── views/                 -- investor/, agent/, company/, staff/, auth/, shells/
│   ├── public/                    -- manifest.json, иконки
│   ├── Dockerfile
│   └── package.json
├── docker-compose.yml             -- Весь стек: app + frontend + postgres + redis
├── scripts/
│   └── install_cbshome.sh         -- Целевой артефакт поставки заказчику
├── notifications/
│   └── templates/                 -- en.yaml, ru.yaml (notification templates)
├── diagrams/                      -- Mermaid-схемы (не источник правды)
└── CBSHOME-Design-Document.md     -- Этот файл
```

**Источник правды по схеме БД:** `backend/app/modules/*/models.py`

### 5.1. install_cbshome.sh -- главный артефакт поставки

`scripts/install_cbshome.sh` -- это то, что передаётся заказчику. Скрипт запускается на чистом Ubuntu 22.04+ сервере и разворачивает полностью рабочую платформу "из коробки":

1. Preflight: OS, RAM, disk, DNS
2. System deps: Docker, Nginx, Certbot, UFW
3. Deploy user `cbshome` (non-root, в docker group)
4. SSH deploy key -> GitHub (`aivis-one/aivis`) -> clone repo
5. Генерация `.env` с рандомными паролями + запрос чувствительных переменных
6. Nginx reverse proxy (`api.cbshome.org`, `cbshome.org`) + SSL
7. `docker compose up` -> healthcheck -> миграции Alembic -> seed системного пользователя Platform
8. Создание management script -> symlink `/usr/local/bin/cbshome`
9. Cron для ежедневного backup

После установки заказчик заполняет `.env` (SumSub API key, blockchain nodes, wallet addresses, Mailgun API key) и получает рабочий стек.

**Разработка и тестирование ведётся на VPS, идентичном проду.** Нет понятия "локальная разработка". Все изменения -- через `cbshome update` (git pull + rebuild + migrate + restart).

### 5.2. Management commands

```
cbshome status              -- Health check + Docker status
cbshome logs [app|db|redis] -- View logs
cbshome update              -- Pull, build, migrate, test, restart
cbshome test                -- Run all tests
cbshome lint                -- Run linters (ruff)
cbshome restart [app]       -- Restart services
cbshome db connect          -- Open psql session
cbshome db migrate          -- Run Alembic migrations
cbshome backup              -- Backup DB + .env
cbshome seed                -- Populate DB with test data
cbshome seed --reset        -- Clean seed data & re-seed
cbshome ssl renew           -- Renew SSL certificate
cbshome version             -- Show version info
```

---

## 6. Дорожная карта за MVP

### 6.1. Мультиязычность полная (i18n Phase 2)

MVP запускается на EN. После MVP добавляются RU, DE, AR -- только через файлы локалей, без изменения компонентов. Возможно только если i18n встроен с первого дня (см. раздел 4.5).

### 6.2. Fiat payments (EUR)

Провайдер TBD (Moonpay / Transak / Banxa). Разблокируется после регистрации DubaiCo-1 BVI. Архитектурно: интерфейс `PaymentProviderProtocol` определён в MVP, fiat -- вторая реализация.

### 6.3. AI-тренажёр для агентов

Квиз-игра, квалифицирующая пользователя на роль агента. Результат прикрепляется к `AgentApplication`. Финальное решение остаётся за Staff (см. розетку 7.5).

### 6.4. Версионирование документов

При обновлении редакции документа система определяет пользователей без актуальной подписи и запрашивает переподписание. Структура уже заложена через поле `version` в `Document`.

### 6.5. Микросервисы

Таблицы уже сгруппированы по будущим сервисам (раздел 3.3). `trace_id` в каждом запросе. Распил не требует переписывания бизнес-логики.

---

## 7. Розетки

Заготовки, которые намеренно не реализованы в MVP. Интерфейсы определены, чтобы будущая реализация не ломала архитектуру.

### 7.1. Токенизация (Q3 2027)

Solana utility tokens -- конвертация в security tokens. Модуль `tokens`, таблица `token_holdings`. Интерфейс `TokenServiceProtocol` определён, реализация -- заглушка.

```python
class TokenServiceProtocol(Protocol):
    async def issue_tokens(
        self, investor_id: UUID, amount: int, product_id: UUID
    ) -> TokenIssuance: ...

    async def get_holdings(
        self, investor_id: UUID
    ) -> list[TokenHolding]: ...
```

### 7.2. Вторичный рынок / OTC

Торговля продуктами между инвесторами. Таблицы `offers`, `trades` спроектированы, логика не реализована. TODO-комментарии в `payments/models.py`.

### 7.3. Fiat on-ramp

Интерфейс `PaymentProviderProtocol` определён в `payments/providers/interface.py`. MVP реализует `CryptoProvider`. Fiat (`MoonpayProvider`) -- Phase 2.

```python
class PaymentProviderProtocol(Protocol):
    async def create_payment(
        self, amount_usd: Decimal, investor_id: UUID
    ) -> PaymentIntent: ...

    async def verify_payment(
        self, payment_id: str
    ) -> PaymentStatus: ...
```

### 7.4. SMS 2FA

`User.credentials` JSONB уже содержит поле `phone` в структуре. Логика отправки OTP не реализована. Разблокируется в Phase 2.

### 7.5. AI Trainer (сертификация агентов)

Адаптивный квиз для квалификации пользователя на роль агента. Интерфейс `AITrainerProtocol` в `ai_trainer/interface.py`. MVP: заявка подаётся без квиза, Staff решает вручную. Phase 2: квиз перед заявкой, результат прикрепляется к `AgentApplication`.

```python
class AITrainerProtocol(Protocol):
    async def generate_question(
        self, agent_id: UUID, topic: str
    ) -> TrainingQuestion: ...

    async def evaluate_answer(
        self, question_id: UUID, answer: str
    ) -> EvaluationResult: ...
```

### 7.6. DocuSign (e-signature)

Phase 2 -- формальная e-signature контрактов. MVP: checkbox consent, факт записывается в `DocumentSigning`. Phase 2: `docusign_envelope_id` добавляется к существующей записи -- структура модуля `documents` не меняется.

---

## 8. Артефакты

| Артефакт | Путь | Статус |
|----------|------|--------|
| Конституция (этот документ) | `CBSHOME-Design-Document.md` | Актуален |
| Бэковый Кодекс | `CBSHOME-Backend.md` | Создаётся |
| Фронтовый Кодекс | `CBSHOME-Frontend.md` | Создаётся |
| Install script | `scripts/install_cbshome.sh` | Целевой артефакт |
| Notification templates | `notifications/templates/en.yaml` | MVP |
| Схема БД (правда) | `backend/app/modules/*/models.py` | Актуальна |

---

**Конец документа**

---

*Version 1.5 | 2026-03-27 | aivis-one/aivis*
