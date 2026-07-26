# AIVIS.ONE -- Финансовая система

**Версия:** 1.5
**Дата:** 28 марта 2026
**Статус:** Утверждено
**Контекст:** Финансовая логика платформы. Не ТЗ и не ДизДок -- отраслевой Кодекс.
Читается перед работой над модулями: `payments`, `installments`, `commissions`, `referrals`.

---

## 1. Архитектура: как устроены деньги в системе

### Принцип: Double-Entry (Двойная запись)

> **Каждый цент отслеживается. Сумма всех записей в системе ВСЕГДА = 0.**

Это бухгалтерский стандарт. Исключает "потерянные" деньги, делает аудит тривиальным,
позволяет семафорам консистентности работать как автоматические тесты.

### Все участники -- это User

В системе нет отдельных сущностей "инвестор", "агент", "компания". Все -- роли единой
сущности `User`. У каждого `User` без исключения -- ровно два леджера.

```
User (любая роль)
├── active_ledger   -- шлюз "снаружи внутрь"
└── passive_ledger  -- шлюз "изнутри наружу"
```

### Два леджера -- два однонаправленных шлюза

| Леджер | Пополняется | Тратится | Вывод наружу |
|--------|-------------|----------|--------------|
| **active_ledger** | Внешние деньги (крипта, фиат) | Покупка продуктов | Нет |
| **passive_ledger** | Системные операции (комиссии, выручка, бонусы) | Вывод наружу | Да (только confirmed) |

---

## 2. Системный юзер Platform

`Platform` -- специальная запись в таблице `users` с флагом `is_system=true` и ролью `platform`.

**Правила:**
- Создаётся один раз при инициализации БД (seed), никогда не удаляется
- Не логинится, не появляется в списках пользователей
- Принимает ВСЕ входящие платежи инвесторов на свой `passive_ledger`
- Немедленно распределяет их сагой по получателям
- Остаток после распределения остаётся на `passive_ledger` Platform

---

## 3. Матрица маршрутов (AML-защита)

| Перевод | Разрешён | Причина запрета |
|---------|----------|-----------------|
| Active -> свой Active | YES | Бессмысленно, но не опасно |
| Active -> чужой Active | YES | Легитимные p2p переводы |
| Active -> свой Passive | **NO** | Layering: внешние деньги попадают в канал вывода |
| Active -> чужой Passive | **NO** | Mixing: источник выведенных средств неотслеживаем |
| Passive -> свой Active | YES | Перевод заработанного на покупки |
| Passive -> чужой Active | YES | Штатная операция: бонусы, промо от Компании |
| Passive -> свой Passive | YES | Бессмысленно, но не опасно |
| Passive -> чужой Passive | YES | Штатные переводы между пассивными балансами |

> **Единственный запрет:** Active не может попасть в Passive ни через какой маршрут.
> Проверяется в коде при каждой записи в леджер -- не только в purchase_processor.

---

## 4. Модель ledger-записи

Каждая запись в `active_ledger` и `passive_ledger` содержит:

```python
class LedgerEntry:
    id: UUID
    user_id: UUID
    ledger_type: enum        -- "active" | "passive"
    amount_cents: int        -- отрицательные для списаний
    status: enum             -- "frozen" | "confirmed" | "reversed"
    frozen_until: datetime   -- NULL если сразу confirmed (crypto после N блоков)
    origin_payment_id: UUID  -- ссылка на исходный Payment (для reversal-цепочки)
    reason: str              -- из LedgerReason
    created_at: datetime
```

**Правила статусов:**
- `frozen` -- деньги существуют. С `active_ledger` **можно** тратить на покупки. С `passive_ledger` **нельзя** выводить
- `confirmed` -- cooling-off прошёл, вывод с passive_ledger разрешён
- `reversed` -- чарджбек обработан, зеркальная запись добавлена

**Записи никогда не удаляются** -- только `reversed` через добавление зеркальной записи.

---

## 5. Механика freezing и chargeback

### 5.1. Freezing по типу платежа

| Метод | `frozen_until` | Обоснование |
|-------|---------------|-------------|
| Крипта (USDT) | `created_at + FREEZING_HOURS_CRYPTO` | Blockchain finality, чарджбэков нет |
| Банковский перевод | `created_at + FREEZING_HOURS_BANK` | Chargeback window |

`frozen_until` считается от момента создания КАЖДОЙ записи в леджере, включая
производные записи в `passive_ledger` после purchase_processor.

**Пример:** инвестор закинул $100 банковским переводом, подождал 10 дней, сделал покупку.
Записи в `passive_ledger` агентов создаются в момент покупки -- их `frozen_until`
считается от этого момента (ещё 14 дней), а не 4 оставшихся от депозита.

Это упрощает reversal: не нужно отслеживать цепочку источников -- достаточно
`origin_payment_id` и `created_at` каждой записи.

### 5.2. Смешанный баланс (несколько источников)

Инвестор может иметь на `active_ledger` несколько записей с разными `frozen_until`:

```
Пример:
  +100000  frozen_until=now()+1h    (крипта)
  +100000  frozen_until=now()+336h  (банковский перевод)
  Покупка на $150 использует оба источника.
```

**Правило: MAX frozen_until.**

`payment_service` при создании `PurchaseContext` вычисляет:

```python
frozen_until = max(
    entry.frozen_until
    for entry in investor_active_ledger_entries
    if entry.status == "frozen"
) or now() + timedelta(hours=FREEZING_HOURS_CRYPTO)
```

Все порождённые passive_ledger записи получают этот MAX.

**Обоснование:** чарджбэки редки. Агент ждёт чуть дольше в редком случае
смешанного баланса -- приемлемый компромисс против сложности FIFO-сплита.
Сплит потребовал бы разбивки purchase_processor на N транзакций по источникам.

### 5.3. State machine ledger-записи

```
frozen -> confirmed   (daemon: frozen_until <= now())
frozen -> reversed    (явный reversal триггер от Staff)
confirmed -> reversed (чарджбек после подтверждения -- fraud dispute)
```

### 5.4. Daemon: `payment_confirmation_worker`

Фоновая задача (asyncio.Task в lifespan). Запускается каждые `CONFIRMATION_WORKER_INTERVAL_MINUTES`.

```
Алгоритм:
1. SELECT ledger_entries WHERE status=frozen AND frozen_until <= now()
   FOR UPDATE (batch)
2. UPDATE status=confirmed
3. Уведомление владельцам разблокированных passive_ledger записей
```

### 5.5. Reversal при чарджбеке

Явный триггер от Staff через платёжный модуль:

```
POST /api/v1/admin/payments/{payment_id}/reverse

1. Payment -> status=reversed
2. SELECT ledger_entries
   WHERE origin_payment_id=X AND status IN (frozen, confirmed)
3. Для каждой записи:
   INSERT зеркальную запись:
     amount_cents = -original.amount_cents
     reason       = original.reason + ":reversal"
     status       = confirmed   -- reversal немедленно действует
     origin_payment_id = X
   UPDATE original -> status=reversed
4. audit_log: chargeback_reversal, staff_id, payment_id, total_reversed_cents
5. Уведомления всем затронутым пользователям
```

---

## 6. Канонические reasons (LedgerReason)

Все `reason` -- строки формата `{операция}:{детали}`.
Единый реестр в `app/core/constants.py`:

```python
class LedgerReason:
    # Deposits
    DEPOSIT_CRYPTO       = "deposit:crypto:{tx_hash}"
    DEPOSIT_BANK         = "deposit:bank:{payment_id}"

    # Purchases
    PURCHASE             = "purchase:{purchase_id}"

    # Gifts (all free unit allocations -- bundle bonus, airdrop, welcome, campaign)
    # type: bundle_bonus | airdrop | welcome | campaign | ...
    # reference_id: purchase_id | campaign_id | user_id | ...
    GIFT                 = "gift:{type}:{reference_id}"

    # Distribution saga
    DISTRIBUTION_COMPANY = "distribution:company:{company_id}:{purchase_id}"
    COMMISSION_L1        = "commission:l1:{agent_id}:{purchase_id}"
    COMMISSION_L2        = "commission:l2:{agent_id}:{purchase_id}"
    COMMISSION_L3        = "commission:l3:{agent_id}:{purchase_id}"
    PLATFORM_REMAINDER   = "platform:remainder:{purchase_id}"

    # Bonuses
    BONUS_REFERRAL       = "bonus:referral:{referral_id}:{purchase_id}"
    BONUS_VOLUME         = "bonus:volume:{period}:{agent_id}"
    BONUS_PROMO          = "bonus:promo:{promo_code}:{purchase_id}"

    # Installments
    INSTALLMENT_TRANCHE  = "installment:tranche:{tranche_id}"

    # Gifts -- extended types
    # bundle_bonus: бонус за размер пакета при инстант-покупке
    # airdrop: маркетинговый аирдроп
    # welcome: велком-бонус при онбординге
    # campaign: маркетинговая акция
    # installment_tranche: акции за оплаченный транш
    # installment_completion: бонус инвестору за закрытие плана
    # installment_completion_agent: бонус агенту L1 за закрытие плана

    # Withdrawals
    WITHDRAWAL           = "withdrawal:{withdrawal_id}"

    # Refunds
    REFUND               = "refund:{purchase_id}"

    # Transfers
    TRANSFER_INTERNAL    = "transfer:internal:{from_ledger}:{to_ledger}"

    # Reversals: суффикс добавляется к оригинальному reason
    # Пример: "deposit:bank:{payment_id}:reversal"
    REVERSAL_SUFFIX      = ":reversal"
```

**Правило:** `reason.split(":")[0]` -- тип операции. Семафоры фильтруют по префиксу.
Reversal-записи идентифицируются по суффиксу `:reversal`.

---

## 7. Purchase Processor

### Концепция

`purchase_processor` -- изолированный модуль, отвечающий за финансовую логику покупки.
Не знает про HTTP, роутеры, сессии. Берёт `PurchaseContext`, возвращает список
`Transaction`, каждая из которых имеет `SUM(entries) = 0`.

```python
class ProcessorProtocol(Protocol):
    async def process(
        self, context: PurchaseContext
    ) -> list[Transaction]: ...

    async def validate_config(
        self, config: dict
    ) -> None: ...
```

### PurchaseContext

```python
@dataclass
class PurchaseContext:
    investor: User
    product: Product
    company: Company           -- для чтения distribution_config
    amount_cents: int          -- сумма покупки
    origin_payment_id: UUID    -- исходный Payment (для freezing цепочки)
    frozen_until: datetime     -- вычисляется в payment_service по Payment.method
    agent_chain: list[User]    -- [L1, L2, L3], может быть пустым
    triggered_at: datetime
```

### LedgerEntry в контексте процессора

```python
@dataclass
class LedgerEntry:
    user_id: UUID
    ledger_type: str           -- "active" | "passive"
    amount_cents: int
    reason: str
    origin_payment_id: UUID    -- транслируется из PurchaseContext
    frozen_until: datetime     -- транслируется из PurchaseContext
```

`frozen_until` вычисляется в `payment_service` на основе `Payment.method` и конфига,
передаётся в `PurchaseContext`. Процессор транслирует его на все порождённые записи.
`company.distribution_config` читается процессором для определения долей распределения.

### Transaction -- юридическая единица

```python
@dataclass
class Transaction:
    reason: str                -- из LedgerReason
    legal_basis: str           -- "sale" | "gift" | "installment_tranche"
    entries: list[LedgerEntry] -- SUM(amount_cents) = 0 ОБЯЗАТЕЛЬНО
    units: int                 -- количество акций (0 для не-юнитовых операций)
```

### Инвариант семафора

```python
# Проверяется ПЕРЕД записью в БД:
for transaction in transactions:
    assert sum(e.amount_cents for e in transaction.entries) == 0

# Семафор консистентности:
# COUNT(active_ledger по purchase_id) == COUNT(Purchase по purchase_id)
```

Включая нулевые транзакции (gift, бонусы). Каждый `Purchase` -- ровно одна
запись в `active_ledger`, пусть с `amount_cents=0`.

### Product.purchase_config JSONB

```json
{
    "distribution": {
        "company_percent": 75,
        "l1_percent": 10,
        "l2_percent": 3,
        "l3_percent": 1
    },
    "bonuses": [
        {
            "type": "gift_units",
            "condition": "portfolio_size_gte",
            "threshold_cents": 50000,
            "bonus_units_percent": 10,
            "funded_by": "company",
            "legal_basis": "gift"
        }
    ]
}
```

Если `distribution` не задан -- берутся дефолты из `config.py`.
При сохранении продукта конфиг валидируется `PurchaseConfigValidator`.

---

## 8. Все финансовые операции

### 8.1. Пополнение Active Balance (крипто-депозит)

```
active_ledger: user=investor, amount=+100000, status=frozen,
               frozen_until=created_at+1h,
               reason="deposit:crypto:{tx_hash}"
────────────────────────────────────────────────────────
Σ = +100000 (деньги вошли в систему извне)
Доступно для трат сразу. Вывод с passive -- после daemon подтверждения.
```

### 8.2. Пополнение Active Balance (банковский перевод)

```
active_ledger: user=investor, amount=+100000, status=frozen,
               frozen_until=created_at+336h,
               reason="deposit:bank:{payment_id}"
────────────────────────────────────────────────────────
Σ = +100000
Инвестор сразу может тратить на покупки.
Вывод с passive для получателей -- только после frozen_until.
```

### 8.3. Простая покупка продукта

Инвестор покупает 1000 акций за $1000 (банковский перевод).
Агентская цепочка: L1, L2, L3. Distribution: company 75%, L1 10%, L2 3%, L3 1%.
Все записи наследуют `frozen_until` из PurchaseContext.

```
Transaction 1 (sale, units=1000):
  active_ledger[investor]    -100000  frozen  "purchase:{id}"
  passive_ledger[platform]   +100000  frozen  "purchase:{id}"
  Σ = 0 ✓

  passive_ledger[platform]   -75000   frozen  "distribution:company:{id}"
  passive_ledger[company]    +75000   frozen  "distribution:company:{id}"
  Σ = 0 ✓

  passive_ledger[platform]   -10000   frozen  "commission:l1:{agent_id}:{id}"
  passive_ledger[agent_l1]   +10000   frozen  "commission:l1:{agent_id}:{id}"
  Σ = 0 ✓

  passive_ledger[platform]   -3000    frozen  "commission:l2:{agent_id}:{id}"
  passive_ledger[agent_l2]   +3000    frozen  "commission:l2:{agent_id}:{id}"
  Σ = 0 ✓

  passive_ledger[platform]   -1000    frozen  "commission:l3:{agent_id}:{id}"
  passive_ledger[agent_l3]   +1000    frozen  "commission:l3:{agent_id}:{id}"
  Σ = 0 ✓

  passive_ledger[platform]   остаток = 11000 cents (frozen)

purchases: id, investor_id, product_id, units=1000,
           paid_cents=100000, legal_basis="sale"
```

### 8.4. Покупка с бонусными единицами (gift_processor)

Инвестор покупает пакет за $5000 -- получает 5000 акций + 500 в подарок.

`purchase_processor` выполняет платную покупку, затем вызывает `gift_processor`
с `type="bundle_bonus"` и `reference_id=purchase_id`. Два изолированных механизма.

```
Transaction 1 (sale, units=5000) -- purchase_processor:
  ... (распределение аналогично 8.3, суммы пропорциональны)
  Σ = 0 ✓

Transaction 2 (gift, units=500) -- gift_processor:
  active_ledger[investor]    0  frozen  "gift:bundle_bonus:{purchase_id}"
  passive_ledger[company]    0  frozen  "gift:bundle_bonus:{purchase_id}"
  Σ = 0 ✓

purchases:
  id_1: units=5000, paid_cents=500000, legal_basis="sale"
  id_2: units=500,  paid_cents=0,      legal_basis="gift"
```

> Нулевые записи обязательны. Семафор S-02: COUNT(active_ledger) = COUNT(purchases) = 2.
> Механизм одинаков для всех gift-типов: bundle_bonus, airdrop, welcome, campaign.

### 8.5. Рассрочка

Каждый транш -- отдельная транзакция с отдельным `Purchase`.
Цена фиксируется в `installment_plan.price_per_unit_cents` при оформлении плана.

```
Транш 1 (10% = $600):
  active_ledger[investor]   -60000  frozen  "installment:tranche:{tranche_1_id}"
  passive_ledger[platform]  +60000  frozen  "installment:tranche:{tranche_1_id}"
  ... (распределение по конфигу продукта)
  Σ = 0 ✓

purchases: units=пропорционально, paid_cents=60000,
           legal_basis="installment_tranche"
```

### 8.6. Вывод средств (Withdrawal)

Вывод только из `passive_ledger` со статусом `confirmed`.

```
passive_ledger[agent]   -100000  confirmed  "withdrawal:{id}"
────────────────────────────────────────────────────
Σ = -100000 (деньги покинули систему)
Withdrawal: status=pending -> Staff confirm -> status=confirmed
```

### 8.7. Перевод Passive -> Active

Агент переводит подтверждённые комиссии для покупки продукта:

```
passive_ledger[agent]   -50000  confirmed  "transfer:internal:passive:active"
active_ledger[agent]    +50000  confirmed  "transfer:internal:passive:active"
Σ = 0 ✓
```

---

## 9. Семейство процессоров

```
app/modules/processors/
├── base.py       -- ProcessorProtocol, PurchaseContext, Transaction, LedgerEntry
├── purchase.py   -- PurchaseProcessor (MVP)
├── gift.py       -- GiftProcessor (все бесплатные начисления акций)
├── volume.py     -- VolumeProcessor (бонус агенту за объём за период)
├── referral.py   -- ReferralProcessor (комиссии L1/L2/L3)
├── promocode.py  -- PromocodeProcessor (скидки и бонусы по промокоду)
└── registry.py   -- ProcessorRegistry (маппинг trigger -> processor)
```

| Процессор | Триггер | Что делает |
|-----------|---------|------------|
| `PurchaseProcessor` | Любая покупка | Распределение по конфигу продукта |
| `GiftProcessor` | bundle_bonus / airdrop / welcome / campaign | Бесплатные начисления акций (paid_cents=0) |
| `ReferralProcessor` | Покупка через реферальную ссылку | Комиссии по цепочке |
| `VolumeProcessor` | Cron (конец периода) | Бонус агентам за объём |
| `PromocodeProcessor` | Покупка с промокодом | Скидка или бонусные единицы |

`payment_service` не знает про бонусы и промокоды. Он:
1. Вычисляет `frozen_until` на основе `Payment.method` и конфига
2. Получает список `Transaction` от процессора
3. Проверяет `SUM = 0` для каждой транзакции
4. Атомарно записывает все записи в БД

---

## 10. Модель Product и ценообразование

### Структура

```
Company
├── price_per_unit_cents      -- текущая цена акции (обновляется Staff вручную)
├── distribution_config: JSONB -- L1/L2/L3 денежные комиссии (для всех продуктов компании)
└── CompanyPriceHistory[]     -- история изменений цены

Product (принадлежит Company)
├── company_id
├── units: int                -- размер пакета (неизменен)
├── gift_units: int           -- бонус акциями при инстант-покупке (0 если нет)
├── price_per_unit_cents      -- денормализованная копия с Company
├── status: enum              -- active | hidden | archived
└── ProductInstallment[]      -- варианты рассрочки (опционально, может быть несколько)
    ├── duration_months: int  -- 6 | 12 (розетка: 24)
    ├── schedule_cents: JSONB -- [16500, 16500, ..., 17500]
    ├── units_schedule_percent: JSONB -- [10, 10, ..., 50]
    ├── bonus_units: int      -- бонус акциями инвестору за закрытие
    └── agent_bonus_units: int -- бонус акциями агенту L1 за закрытие
```

> Детальная механика рассрочки: AIVIS-Installment.md

### Изменение цены акции

Staff меняет цену компании -- каскадное обновление:

```
1. UPDATE company SET price_per_unit_cents = X WHERE id = Y
2. UPDATE product SET price_per_unit_cents = X
   WHERE company_id = Y AND status IN ('active', 'hidden')
3. INSERT company_price_history (company_id, old_price, new_price, changed_by, changed_at)
```

Архивные продукты (`status=archived`) цену не обновляют -- они закрыты.

### Snapshot в Purchase

`Purchase` хранит `price_per_unit_cents` на момент покупки -- иммутабельно.
При изменении цены компании старые Purchase не меняются.
История покупок инвестора показывает реальную цену покупки, не текущую.

### Портфель инвестора по компании

```sql
-- Все акции инвестора X в компании Y:
SELECT SUM(units) FROM purchases
WHERE investor_id = X
  AND company_id = Y        -- через JOIN product
  AND status != 'reversed'
-- Включает и sale и gift акции
```

### Средняя цена акции в портфеле

```
AVG = SUM(paid_cents) / SUM(units WHERE legal_basis='sale')
```

Gift акции не участвуют в средней цене -- они бесплатны по определению.

---

## 11. Документ на каждую покупку

Каждая `Purchase` -- юридический документ. `document_id` NOT NULL на `purchases`.

| `legal_basis` | Тип документа | Генерируется |
|---------------|---------------|--------------|
| `sale` | Investment Agreement | По запросу: `GET /purchases/{id}/document` |
| `gift` | Gift Certificate / Airdrop / Bonus | По запросу: `GET /purchases/{id}/document` |
| `installment_tranche` | Sub-contract | По запросу: `GET /purchases/{id}/document` |

PDF генерируется на лету из данных БД. Нет S3 в MVP.
Сертификат инвестора -- агрегат всех `Purchase` по продукту, генерируется из БД.

---

## 12. Семафоры консистентности

`GET /api/v1/admin/consistency` -- ALERT пишется в audit_log и structlog.

| # | Семафор | Критичность |
|---|---------|-------------|
| S-01 | `SUM(все ledger записи включая reversed) = 0` | CRITICAL |
| S-02 | `COUNT(active_ledger по purchase_id) = COUNT(purchases по purchase_id)` | CRITICAL |
| S-03 | `SUM(paid_cents в purchases) = ABS(SUM(active_ledger дебеты по покупкам))` | CRITICAL |
| S-04 | Нет `active_ledger` записей где получатель -- passive | CRITICAL |
| S-05 | Нет юзеров с `confirmed_active_balance < 0` | CRITICAL |
| S-06 | Нет юзеров с `confirmed_passive_balance < 0` | CRITICAL |
| S-07 | Все `Purchase` имеют `document_id NOT NULL` | CRITICAL |
| S-08 | Нет `confirmed` записей с `origin_payment_id` у которого `Payment.status=reversed` | CRITICAL |
| S-09 | Каждой `:reversal` записи соответствует оригинал со статусом `reversed` | HIGH |
| S-10 | Все `installment_plan` имеют сумму траншей = `total_price_cents` | HIGH |
| S-11 | Platform `passive_ledger (confirmed)` остаток >= 0 | HIGH |
| S-12 | Все `Purchase(legal_basis=gift)` имеют `paid_cents = 0` | HIGH |
| S-13 | `SUM(purchases.units)` по компании совпадает с суммой всех sale+gift записей | HIGH |
| S-14 | `SUM(installment_tranches.amount_cents)` = `plan.total_price_cents` для каждого плана | CRITICAL |
| S-15 | Нет `status=active` планов где все транши `status=paid` (должны быть completed) | HIGH |

---

## 13. Принятые решения

| # | Решение | Обоснование |
|---|---------|-------------|
| 1 | Все суммы в Integer cents (USD) | USDT -> cents на входе, без float в системе |
| 2 | Два леджера у каждого User | Чёткое разделение: внешние деньги vs заработок |
| 3 | Platform как системный юзер | Double-entry на границе с внешним миром |
| 4 | Active -> Passive запрещён | AML: внешние деньги не могут стать выводимыми |
| 5 | Нулевые транзакции для gift | Семафор COUNT работает без исключений |
| 6 | Purchase = юридический документ | Compliance, audit trail |
| 7 | PDF генерируется по запросу | Нет S3 в MVP, данные всегда актуальны |
| 8 | purchase_processor изолирован | Маркетинговая логика не трогает финансовую |
| 9 | Конфиг продукта валидируется при сохранении | Ошибки не попадают в транзакции |
| 10 | LedgerReason -- канонические литералы | Читаемо в psql, семафоры фильтруют по префиксу |
| 11 | Цена фиксируется при первом транше рассрочки | Защита инвестора от роста цены |
| 12 | Вывод только из passive_ledger (confirmed) | AML + защита от chargeback |
| 13 | `frozen_until` на каждой ledger-записи | Простой daemon, не нужно отслеживать цепочки |
| 14 | `frozen_until` считается от создания записи | Упрощает reversal: только origin_payment_id |
| 15 | Reversal -- зеркальные записи, не удаление | Иммутабельность леджера, полный audit trail |
| 16 | `active(frozen)` доступен для трат | Оптимистичный подход -- удобство инвестора |
| 17 | `passive(frozen)` недоступен для вывода | Защита до подтверждения платежа |
| 18 | Смешанный баланс: MAX frozen_until | Чарджбэки редки, простота важнее точности FIFO |
| 19 | Цена акции на Company, денормализована на Product | Витрина без JOIN, каскадное обновление при смене цены |
| 20 | GiftProcessor изолирован от PurchaseProcessor | DRY: все бесплатные начисления через один механизм |
| 21 | `legal_basis=gift` вместо `goodwill` | Единый тип для всех бесплатных начислений |

---

## 14. Настраиваемые переменные

| Переменная | Описание | Дефолт |
|------------|----------|--------|
| `DISTRIBUTION_COMPANY_PERCENT` | Доля компании по умолчанию | 75 |
| `DISTRIBUTION_L1_PERCENT` | Комиссия L1 по умолчанию | 10 |
| `DISTRIBUTION_L2_PERCENT` | Комиссия L2 по умолчанию | 3 |
| `DISTRIBUTION_L3_PERCENT` | Комиссия L3 по умолчанию | 1 |
| `MIN_DEPOSIT_CENTS` | Минимальный депозит | 1000 (= $10) |
| `MIN_WITHDRAWAL_CENTS` | Минимальная сумма вывода | 5000 (= $50) |
| `FREEZING_HOURS_CRYPTO` | Cooling-off для крипто-депозитов | 1 |
| `FREEZING_HOURS_BANK` | Cooling-off для банковских переводов | 336 (= 14 дней) |
| `CONFIRMATION_WORKER_INTERVAL_MINUTES` | Интервал запуска daemon | 10 |
| `INSTALLMENT_6M_SCHEDULE` | Дефолтная схема % разблокировки 6м (шаблон для Staff) | [10,10,10,10,10,50] |
| `INSTALLMENT_12M_SCHEDULE` | Дефолтная схема % разблокировки 12м (шаблон для Staff) | [5,5,5,5,5,5,5,5,5,5,5,45] |
| `VOLUME_BONUS_MONTHLY_PERCENT` | Бонусный пул агентам (месяц, top-20) | 2 |
| `VOLUME_BONUS_QUARTERLY_PERCENT` | Бонусный пул агентам (квартал, top-10) | 1 |

---

## 15. Розетки

| Фича | Статус | Что заложено |
|------|--------|--------------|
| Fiat on-ramp (Moonpay/Transak) | Розетка | `PaymentProviderProtocol` в `payments/providers/interface.py` |
| Вторичный рынок / OTC | Розетка | Таблицы `offers`, `trades` спроектированы |
| Рассрочка 24 месяца | Розетка | Параметрический конфиг, добавление = новая запись в INSTALLMENT_SCHEDULE |
| Экспорт истории (CSV/XLSX) | Розетка | `GET /transactions/export` -- заглушка |
| Антифрод промокодов | Розетка | TODO в promocode_processor |
| Автоматический chargeback (webhook) | Розетка | Сейчас только ручной триггер через Staff |

---

**Конец документа**

---

*Version 1.5 | 2026-03-28 | AIVIS.ONE Financial System Codex*
