# CBSHOME -- Рассрочка (Installment)

**Версия:** 1.1
**Дата:** 28 марта 2026
**Статус:** Утверждено
**Контекст:** Механика рассрочки. Читается перед работой над модулем `installments`.
Зависимости: CBSHOME-Financial-System.md, CBSHOME-State-Machines.md

---

## 1. Зачем рассрочка

Инструмент продаж для Агентов. Позволяет предложить инвестору с $200 пакет на $1000
(первый транш $165 ему по силам). Создаёт стабильный кэшфлоу для платформы.
Юридически чистый механизм: инвестор получает акции пропорционально оплаченным
траншам, бонусные акции -- только при полном исполнении обязательств.

---

## 2. Модели

### Company (distribution_config)

```python
Company:
    price_per_unit_cents: int     -- текущая цена акции
    distribution_config: JSONB    -- L1/L2/L3 денежные комиссии
    # {
    #   "company_percent": 75,
    #   "l1_percent": 10,
    #   "l2_percent": 3,
    #   "l3_percent": 1
    # }
```

### Product

```python
Product:
    company_id: UUID
    name: str
    units: int                    -- размер пакета акций
    gift_units: int               -- бонус акциями при инстант-покупке (0 если нет)
    status: enum                  -- active | hidden | archived
    price_per_unit_cents: int     -- денормализовано с Company, обновляется каскадно
```

### ProductInstallment

```python
ProductInstallment:
    id: UUID
    product_id: UUID
    duration_months: int          -- 6 | 12 (розетка: 24)
    schedule_cents: JSONB         -- [16500, 16500, 16500, 16500, 16500, 17500]
                                  -- сумма должна = units * price_per_unit_cents
    units_schedule_percent: JSONB -- [10, 10, 10, 10, 10, 50]
                                  -- сумма должна = 100
    bonus_units: int              -- бонус акциями инвестору за закрытие плана
    agent_bonus_units: int        -- бонус акциями агенту L1 за закрытие плана
    status: enum                  -- active | archived
```

**Инварианты (валидируются при сохранении Staff-ом):**
```
SUM(schedule_cents) == product.units * product.price_per_unit_cents
SUM(units_schedule_percent) == 100
len(schedule_cents) == len(units_schedule_percent) == duration_months
```

### InstallmentPlan (активный план инвестора)

```python
InstallmentPlan:
    id: UUID
    investor_id: UUID
    product_id: UUID
    product_installment_id: UUID  -- шаблон (ProductInstallment)
    agent_id: UUID                -- прямой агент L1 (для бонуса акциями)
    price_per_unit_cents: int     -- SNAPSHOT цены на момент оформления
    total_units: int              -- полный пакет акций
    total_price_cents: int        -- зафиксировано при оформлении
    status: enum                  -- active | completed | defaulted | cancelled
    created_at: datetime
    completed_at: datetime | None
    defaulted_at: datetime | None
```

### InstallmentTranche

```python
InstallmentTranche:
    id: UUID
    plan_id: UUID
    number: int                   -- 1..N
    due_date: date                -- дата платежа (с учётом february rule)
    amount_cents: int             -- из schedule_cents[number-1]
    units_unlocked: int           -- из units_schedule_percent[number-1] * total_units // 100
    status: enum                  -- scheduled | paid | overdue | defaulted
    paid_at: datetime | None
    purchase_id: UUID | None      -- ссылка на Purchase после оплаты
```

---

## 3. Февральское правило

При создании `InstallmentPlan` вычисляем `due_date` для каждого транша:

```python
def calculate_due_date(start_date: date, month_offset: int) -> date:
    """
    start_date: дата оформления инсталлмента
    month_offset: номер транша (1..N)
    """
    target_month = start_date.month + month_offset
    target_year = start_date.year + (target_month - 1) // 12
    target_month = ((target_month - 1) % 12) + 1

    # last_day_of_month rule:
    last_day = calendar.monthrange(target_year, target_month)[1]
    target_day = min(start_date.day, last_day)

    return date(target_year, target_month, target_day)
```

**Примеры:**
```
Оформлен 31 декабря:
  Транш 1: 31 января
  Транш 2: 28 февраля (last_day_of_month)
  Транш 3: 31 марта
  Транш 4: 30 апреля (last_day_of_month)

Оформлен 28 января:
  Транш 1: 28 февраля
  Транш 2: 28 марта
```

---

## 4. Жизненный цикл плана

### 4.1. Оформление

```
1. Инвестор выбирает Product + ProductInstallment на витрине
2. Проверка: active_ledger[investor] >= schedule_cents[0] (первый транш)
3. Создание InstallmentPlan (status=active)
4. Создание всех InstallmentTranche (status=scheduled) с due_date
5. Немедленная оплата первого транша (см. 4.2)
```

### 4.2. Оплата транша

```
1. Daemon или ручной триггер: due_date <= today
2. Проверка: active_ledger[investor] (confirmed + frozen) >= amount_cents
3. Если достаточно:
   a. purchase_processor: списание + распределение комиссий L1/L2/L3
      Purchase: units=units_unlocked, paid_cents=amount_cents,
                legal_basis="installment_tranche"
      (юниты за транш -- это ОПЛАЧЕННЫЕ юниты, не подарок)
   b. InstallmentTranche -> status=paid, paid_at=now()
   c. Уведомления инвестору и агенту: транш оплачен
   d. Если это последний транш -> см. 4.3 (закрытие)
4. Если недостаточно:
   a. InstallmentTranche -> status=overdue
   b. Уведомление инвестору + агенту: недостаточно средств
   c. Ежедневные уведомления о просрочке
   d. Через INSTALLMENT_DEFAULT_DAYS -> см. 4.4 (дефолт)
```

### 4.3. Закрытие плана (все транши оплачены)

```
1. InstallmentPlan -> status=completed, completed_at=now()
2. gift_processor: бонусные акции инвестору
   units = ProductInstallment.bonus_units
   reason = "gift:installment_completion:{plan_id}"
3. gift_processor: бонусные акции агенту L1
   units = ProductInstallment.agent_bonus_units
   reason = "gift:installment_completion_agent:{plan_id}"
   recipient = InstallmentPlan.agent_id
4. Документ: сводный сертификат плана
5. Уведомления: инвестору + агенту
```

### 4.4. Дефолт (просрочка > INSTALLMENT_DEFAULT_DAYS)

```
1. InstallmentTranche (текущий) -> status=defaulted
2. Все оставшиеся InstallmentTranche -> status=cancelled
3. InstallmentPlan -> status=defaulted, defaulted_at=now()
4. Инвестор СОХРАНЯЕТ уже полученные акции (оплаченные транши)
5. Инвестор НЕ получает:
   - Оставшиеся акции (будущие транши)
   - bonus_units (бонус за закрытие)
6. Агент НЕ получает agent_bonus_units
7. Уведомления: инвестору + агенту
8. audit_log: installment_defaulted
```

**Важно:** акции из оплаченных траншей остаются у инвестора навсегда.
Они просто обошлись ему дороже (оплатил часть, получил часть).

---

## 5. Daemon: `installment_payment_worker`

Фоновая задача (asyncio.Task в lifespan). Запускается ежедневно в `INSTALLMENT_WORKER_HOUR`.

```
Алгоритм:
1. SELECT tranches WHERE status=scheduled AND due_date <= today
   ORDER BY plan_id, number ASC
2. Для каждого транша: попытка оплаты (см. 4.2)
3. SELECT tranches WHERE status=overdue
   AND due_date + INSTALLMENT_DEFAULT_DAYS <= today
4. Для каждого: дефолт (см. 4.4)
```

---

## 6. Уведомления

| Триггер | Получатели | Тип |
|---------|------------|-----|
| За 7 дней до due_date | Инвестор | `installment_reminder_7d` |
| За 1 день до due_date | Инвестор | `installment_reminder_1d` |
| В день due_date (при нехватке средств) | Инвестор + Агент | `installment_due_insufficient` |
| Каждый день просрочки | Инвестор + Агент | `installment_overdue_day_N` |
| Транш оплачен | Инвестор | `installment_tranche_paid` |
| План закрыт | Инвестор + Агент | `installment_completed` |
| Дефолт | Инвестор + Агент | `installment_defaulted` |

**Reminder daemon** запускается ежедневно:
```
SELECT tranches WHERE status=scheduled
  AND due_date = today + 7  -> installment_reminder_7d
  AND due_date = today + 1  -> installment_reminder_1d
```

---

## 7. Финансовые записи

### Транш (платная часть)

```
-- purchase_processor:
active_ledger[investor]      -amount_cents  frozen  "installment:tranche:{tranche_id}"
passive_ledger[platform]     +amount_cents  frozen  "installment:tranche:{tranche_id}"

passive_ledger[platform]     -company_share frozen  "distribution:company:{id}:{tranche_id}"
passive_ledger[company]      +company_share frozen  "distribution:company:{id}:{tranche_id}"

passive_ledger[platform]     -l1_share      frozen  "commission:l1:{agent_id}:{tranche_id}"
passive_ledger[agent_l1]     +l1_share      frozen  "commission:l1:{agent_id}:{tranche_id}"
...

Purchase: units=units_unlocked, paid_cents=amount_cents,
          legal_basis="installment_tranche",
          price_per_unit_cents=plan.price_per_unit_cents  -- snapshot
Σ = 0 ✓
```

### Бонус инвестору при закрытии

```
-- gift_processor:
active_ledger[investor]      0  confirmed  "gift:installment_completion:{plan_id}"
passive_ledger[company]      0  confirmed  "gift:installment_completion:{plan_id}"

Purchase: units=bonus_units, paid_cents=0, legal_basis="gift"
Σ = 0 ✓
```

### Бонус агенту L1 при закрытии

```
-- gift_processor:
active_ledger[agent_l1]      0  confirmed  "gift:installment_completion_agent:{plan_id}"
passive_ledger[company]      0  confirmed  "gift:installment_completion_agent:{plan_id}"

Purchase: units=agent_bonus_units, paid_cents=0, legal_basis="gift",
          investor_id=agent_l1_id
Σ = 0 ✓
```

---

## 8. Семафоры консистентности (Installment)

| # | Семафор | Критичность |
|---|---------|-------------|
| IS-01 | `SUM(tranches.amount_cents) = plan.total_price_cents` для каждого плана | CRITICAL |
| IS-02 | `SUM(units_unlocked по paid траншам) + bonus_units` = total_units при completed плане | CRITICAL |
| IS-03 | Нет `status=scheduled` траншей у `status=defaulted/cancelled` планов | CRITICAL |
| IS-04 | Каждый `status=paid` транш имеет `purchase_id NOT NULL` | CRITICAL |
| IS-05 | `COUNT(paid tranches)` совпадает с `COUNT(purchases WHERE legal_basis=installment_tranche)` для плана | HIGH |
| IS-06 | Нет планов `status=active` где все транши `status=paid` (должны быть completed) | HIGH |

---

## 9. Принятые решения

| # | Решение | Обоснование |
|---|---------|-------------|
| 1 | Каждый транш = отдельная Purchase | Юридический документ на каждый платёж |
| 2 | Акции разблокируются пропорционально траншам | Инвестор получает актив по мере оплаты |
| 3 | Бонус акциями только при полном закрытии | Мотивация исполнять обязательства |
| 4 | Дефолт через INSTALLMENT_DEFAULT_DAYS | Настраивается, не хардкод |
| 5 | Оплаченные акции не отзываются при дефолте | Юридическая чистота |
| 6 | Денежный бонус агенту с каждого транша | Мотивация помогать клиенту платить |
| 7 | Бонус акциями агенту только L1 и только при закрытии | Он довёл клиента до конца |
| 8 | february rule: last_day_of_month | Предсказуемость дат для инвестора |
| 9 | Цена фиксируется при оформлении плана | Защита инвестора от роста цены |
| 10 | ProductInstallment отдельная сущность | Продукт может иметь несколько вариантов рассрочки |
| 11 | Денежные и акционные бонусы разделены | Разные механизмы, разные записи, разная логика |

---

## 10. Настраиваемые переменные

| Переменная | Описание | Дефолт |
|------------|----------|--------|
| `INSTALLMENT_DEFAULT_DAYS` | Дней просрочки до дефолта | 7 |
| `INSTALLMENT_WORKER_HOUR` | Час запуска daemon (UTC) | 9 |
| `INSTALLMENT_REMINDER_DAYS` | За сколько дней напоминание | [7, 1] |

---

## 11. Розетки

| Фича | Статус | Что заложено |
|------|--------|--------------|
| Рассрочка 24 месяца | Розетка | `duration_months=24` в ProductInstallment |
| Досрочное погашение | Розетка | `early_repayment` в InstallmentPlan |
| Пауза плана (заморозка) | Розетка | `status=paused` в InstallmentPlan |
| Реструктуризация долга | Розетка | Staff может изменить schedule при согласии инвестора |

---

**Конец документа**

---

*Version 1.1 | 2026-03-28 | cbshome Installment Codex*
