# CBSHOME -- State Machines

**Версия:** 1.4
**Дата:** 28 марта 2026
**Статус:** В работе
**Контекст:** Допустимые переходы между статусами для всех сущностей с жизненным циклом.
Читается перед работой над любым модулем, содержащим статусную модель.
Нарушение переходов -- архитектурная ошибка, не баг.

---

## Правила 

- Переход возможен ТОЛЬКО если он указан в этом документе
- Статус меняется ТОЛЬКО через явную функцию в service-слое, не через прямое присвоение
- Терминальные статусы помечены (*). Выход из них невозможен
- Инициатор перехода указан для каждой стрелки

---

## 1. Payment

### Статусы

| Статус | Описание |
|--------|----------|
| `created` | Инвойс выписан, ожидаем платёж от юзера |
| `frozen` | Платёж получен, на cooling-off периоде |
| `confirmed` | Cooling-off прошёл, деньги подтверждены |
| `failed` * | Платёж не прошёл или истёк `expires_at` |
| `reversed` * | Chargeback обработан, зеркальные ledger-записи добавлены |

### Переходы

```
created   -> frozen    (webhook: провайдер подтвердил получение)
created   -> failed    (webhook: отклонён / daemon: expires_at <= now())
frozen    -> confirmed (daemon: frozen_until <= now())
frozen    -> reversed  (Staff: chargeback в период cooling-off)
confirmed -> reversed  (Staff: fraud dispute после подтверждения)
```

### Инициаторы

| Переход | Инициатор |
|---------|-----------|
| `created -> frozen` | Webhook от провайдера |
| `created -> failed` | Webhook (отклонён) или daemon (expired) |
| `frozen -> confirmed` | Daemon (`payment_confirmation_worker`) |
| `frozen -> reversed` | Staff (ручной триггер) |
| `confirmed -> reversed` | Staff (ручной триггер, fraud dispute) |

### Модель

```python
Payment:
    id
    user_id
    amount_cents: int
    currency: str          -- "USD"
    method: enum           -- "crypto" | "bank" | "card"
    status: enum           -- "created" | "frozen" | "confirmed" | "failed" | "reversed"
    provider: str          -- "crypto_usdt_trc20" | "moonpay" | "stripe" | ...
    expires_at: datetime   -- created -> failed если не оплачен
    frozen_until: datetime -- заполняется при created -> frozen
    provider_data: JSONB   -- провайдер-специфичное: tx_hash, checkout_url, session_id, ...
    origin_payment_id: UUID -- для reversal цепочки (nullable)
    created_at: datetime
```

---

## 2. AgentApplication

### Статусы

| Статус | Описание |
|--------|----------|
| `pending` | Заявка подана, ожидает решения Staff |
| `approved` * | Заявка одобрена, роль `agent` выдана автоматически |
| `rejected` | Заявка отклонена, cooldown до повторной подачи |

### Переходы

```
pending  -> approved  (Staff)
pending  -> rejected  (Staff)
rejected -> pending   (юзер, после cooldown_until <= now())
```

### Инициаторы

| Переход | Инициатор |
|---------|-----------|
| `pending -> approved` | Staff (ручное решение) |
| `pending -> rejected` | Staff (ручное решение) |
| `rejected -> pending` | Юзер (новая заявка после cooldown) |

### Примечания

- `approved` -- терминальный: роль уже выдана, история заявки сохраняется
- При `approved`: `user.role = "agent"` автоматически, агентский пакет документов на подпись
- При `rejected`: `cooldown_until = now() + AGENT_APPLICATION_COOLDOWN_DAYS`
- У юзера одновременно только одна активная заявка (`pending`). Остальные -- история

---


---

## 3. Purchase

### Статусы

| Статус | Описание |
|--------|----------|
| `created` | Покупка создана, ledger-записи зафиксированы |
| `completed` | Продукт поставлен, документ доступен |
| `refunded` * | Возврат выполнен, зеркальные ledger-записи добавлены |
| `reversed` * | Chargeback родительского Payment, автоматический откат |

### Переходы

```
created   -> completed  (система: все условия поставки выполнены)
created   -> refunded   (Staff или система: возврат по заявке)
created   -> reversed   (система: reversal родительского Payment)
completed -> refunded   (Staff: возврат после поставки, исключительный случай)
```

### Примечания

- `reversed` инициируется автоматически при `Payment -> reversed`
- Для gift purchases (`paid_cents=0`): `refunded` невозможен, только `reversed`

### legal_basis enum

| Значение | Описание |
|----------|----------|
| `sale` | Обычная платная покупка |
| `gift` | Любое бесплатное начисление (bundle_bonus, airdrop, welcome, campaign) |
| `installment_tranche` | Транш рассрочки |

---

## 4. Withdrawal

### Статусы

| Статус | Описание |
|--------|----------|
| `pending` | Запрос создан, ожидает подтверждения Staff |
| `confirmed` * | Staff подтвердил, перевод выполнен вручную |
| `rejected` * | Staff отклонил запрос |

### Переходы

```
pending -> confirmed  (Staff: ручное подтверждение + перевод)
pending -> rejected   (Staff: отклонение с причиной)
```

### Примечания

- Автоматических выплат нет в MVP
- При `rejected`: средства остаются на `passive_ledger` (запись уже создана при подаче заявки -- нужна компенсирующая запись возврата)
- `rejection_reason` -- обязательное поле при `rejected`

---

## 5. Document

### Статусы

| Статус | Описание |
|--------|----------|
| `draft` | Документ создан, не опубликован |
| `active` | Документ активен, доступен для подписания |
| `archived` * | Документ выведен из обращения (новая версия или устарел) |

### Переходы

```
draft  -> active    (Staff: публикация)
active -> draft     (Staff: возврат на доработку)
active -> archived  (Staff: архивирование)
draft  -> archived  (Staff: отмена черновика)
```

### Примечания

- При появлении новой версии документа: старая `active -> archived`, новая `draft -> active`
- `DocumentSigning` привязывается к конкретной версии документа
- Архивированный документ остаётся доступен для просмотра истории подписаний

---

## 6. AvatarSession

### Статусы

| Статус | Описание |
|--------|----------|
| `active` | Staff работает под целевым пользователем |
| `ended` * | Сессия завершена, Staff вернулся в свой аккаунт |

### Переходы

```
active -> ended  (Staff: явный выход / истечение таймаута / logout целевого юзера)
```

### Примечания

- Реальная сессия целевого пользователя не затрагивается
- Все мутирующие операции в `active` режиме пишутся в `audit_log` с `performed_by=staff_id`
- Таймаут: `AVATAR_SESSION_TIMEOUT_MINUTES` из конфига
- При `ended`: JWT/сессия Staff восстанавливается автоматически

---

## 7. KYC (заглушка MVP)

В MVP `kyc_status` -- простое поле на `User` без валидации переходов.
Полноценная state machine реализуется при подключении SumSub (Phase 2+).

```python
kyc_status: enum  -- "not_started" | "submitted" | "approved" | "rejected"
```

---

## 8. InstallmentPlan

### Статусы

| Статус | Описание |
|--------|----------|
| `active` | План активен, транши оплачиваются |
| `completed` * | Все транши оплачены, бонусы начислены |
| `defaulted` * | Просрочка > INSTALLMENT_DEFAULT_DAYS, план прекращён |
| `cancelled` * | Принудительное расторжение Staff |

### Переходы

```
active -> completed  (система: последний транш оплачен)
active -> defaulted  (daemon: overdue > INSTALLMENT_DEFAULT_DAYS)
active -> cancelled  (Staff: принудительное расторжение)
```

### Инициаторы

| Переход | Инициатор |
|---------|-----------|
| `active -> completed` | Система (после оплаты последнего транша) |
| `active -> defaulted` | Daemon (`installment_payment_worker`) |
| `active -> cancelled` | Staff |

### Примечания

- При `defaulted`: оплаченные акции остаются у инвестора, бонус не начисляется
- При `completed`: бонус акциями инвестору + агенту L1 через gift_processor

---

## 9. InstallmentTranche

### Статусы

| Статус | Описание |
|--------|----------|
| `scheduled` | Транш ожидает своей даты |
| `paid` * | Транш оплачен, акции начислены |
| `overdue` | Дата прошла, средств не хватило |
| `defaulted` * | Просрочка превысила лимит, транш закрыт без оплаты |
| `cancelled` * | Отменён вместе с планом |

### Переходы

```
scheduled -> paid       (daemon: due_date <= today И средств достаточно)
scheduled -> overdue    (daemon: due_date <= today И средств недостаточно)
scheduled -> cancelled  (план -> cancelled или defaulted)
overdue   -> paid       (daemon: средства появились до INSTALLMENT_DEFAULT_DAYS)
overdue   -> defaulted  (daemon: просрочка > INSTALLMENT_DEFAULT_DAYS)
overdue   -> cancelled  (план -> cancelled)
```

### Инициаторы

| Переход | Инициатор |
|---------|-----------|
| `scheduled -> paid` | Daemon (`installment_payment_worker`) |
| `scheduled -> overdue` | Daemon |
| `scheduled/overdue -> cancelled` | Система (каскад от плана) |
| `overdue -> paid` | Daemon (при появлении средств) |
| `overdue -> defaulted` | Daemon |
| `overdue -> cancelled` | Система (каскад от плана) |

### Примечания

- `paid` транш всегда имеет `purchase_id NOT NULL`
- Акции разблокируются (`gift_processor`) одновременно с оплатой транша
- Детальная механика: CBSHOME-Installment.md

---

*Version 1.4 | 2026-03-28 | cbshome State Machines Codex*
