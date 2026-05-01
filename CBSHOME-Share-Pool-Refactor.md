# CBSHOME — Option Pool & Product Inventory Refactor

**Tracking ID (Backend):** TD-071
**Tracking ID (Frontend):** TD-F07
**Sprint:** 4.3 (Phase 4)
**Статус:** In Progress / 🔴 Blocker before Frontend Phase F5
**Версия:** 2.0
**Дата создания:** 17 апреля 2026
**Дата обновления:** 30 апреля 2026

**Зависимости:**
- `CBSHOME-Backend.md` — Phase 4, реестр техдолга (TD-071)
- `CBSHOME-Frontend.md` — PHASE F5, реестр техдолга (TD-F07)
- `CBSHOME-Financial-System.md` — `Purchase.units`, `Purchase.paid_cents`, pricing

---

## 1. Summary

Текущая модель `Product` конфликтует с бизнес-реальностью выпуска опционов и будущей токенизацией.

**Одна фраза:** компания имеет фиксированный `total_supply` опционов (покрывающий 100% акций), часть из них выделяет в `OptionPool` для продажи через платформу, а продукты — это лишь **правила деноминации** (упаковки) пула на пакеты разных размеров.

**Ключевые архитектурные решения v2.0:**

1. **Три уровня владения:**
   - **Акции** — юридическая реальность, вне системы.
   - **Total Supply** — все опционы компании, покрывающие 100% акций. `total_supply = total_shares / shares_per_option`. При токенизации — полный mint контракта.
   - **Option Pool** — доля Total Supply, выделенная на продажу через платформу. Owners компании держат оставшиеся опционы вне платформы.

2. **`OptionPool` — отдельная модель**, не поле на CompanyProfile. Имеет свой lifecycle (`active` / `archived`), хранит `equity_percent` и `total_options`.

3. **Product привязан к Pool** (`pool_id`), не к Company напрямую.

4. **Цена живёт на Company**, не на Pool. Цена меняется чаще, чем пул (переоценка компании не требует нового пула). При токенизации цена будет жить в внешнем оракуле.

5. **Gift/bonus опционы расходуют пул**, overflow идёт из owner supply (Total Supply за пределами пула).

6. **Сплит** — архитектурно заложен (новый Pool, миграционные Products, двойная запись), реализация — future scope.

7. **Допэмиссия** — редактирование `total_options` на существующем Pool (деноминация не меняется → покупки не мигрируются).

---

## 2. Проблема — детально

### 2.1. Текущая модель (broken)

```python
class CompanyProfile:
    price_per_unit_cents: BigInteger      # $ per share
    # нет total_supply, нет shares_per_option, нет Pool

class Product:
    company_id: FK -> CompanyProfile      # прямая привязка к компании
    units: Integer                         # иммутабельно
    # трактуется одновременно как:
    #   (a) размер пакета (смысл в name: "Starter — 100 Shares")
    #   (b) инвентарь этого продукта (исчерпывается при покупке)
```

**Функция подсчёта проданного:**

```python
async def get_sold_units_map(...) -> dict[UUID, int]:
    # COUNT(*), НЕ SUM(units) — считает пакеты, не акции
    # Продукты одной компании не связаны между собой
```

### 2.2. Конкретный баг

Продукт «IPI AG Sold Tranche» с `units=500`. Один инвестор купил пакет целиком → создаётся **одна** `Purchase` с `units=500`.

- На бэке: `get_sold_units_map()` возвращает `{product_id: 1}` (одна строка).
- На фронте: `available = product.units - product.sold_units = 500 − 1 = 499`.
- В UI пишется «499 available», хотя фактически пакет куплен целиком.

### 2.3. Бизнес-реальность

Компания IPI AG готова продать 10% своих акций. Если у компании 100 000 000 акций и `shares_per_option = 10`, то `total_supply = 10 000 000` опционов. Из них в Pool выделено 10% = `1 000 000` опционов.

Эти опционы предложены инвесторам через три одновременно активных пакета:
- Продукт «Starter» — 100 опционов за пакет.
- Продукт «Investor» — 1 000 опционов за пакет.
- Продукт «Whale» — 10 000 опционов за пакет.

Покупка пакета у **любого** продукта уменьшает `pool_remaining` для **всех** продуктов этой компании (каждый продукт по-своему, исходя из своего `package_size`).

### 2.4. Правовой аспект и токенизация

Юридически все опционы одной компании стоят одинаково. Цена фиксируется на уровне Company и каскадируется на Products.

**Будущее (за пределами MVP):** при получении лицензии опционы конвертируются в токены на блокчейне. Отсюда архитектурные требования:
- Pool = будущий смарт-контракт. Фиксированный supply.
- Опцион = будущий токен.
- Сплит = новый контракт + swap старых токенов на новые.
- Нельзя мутировать количество токенов после создания контракта, но можно выпустить новые и сделать swap.
- Двойная запись (списание + выпуск) — точная модель того, что произойдёт on-chain.

---

## 3. Правильная модель

### 3.1. CompanyProfile — новые поля

```python
class CompanyProfile(JSONBMixin, UUIDMixin, TimestampMixin, Base):
    # ... все существующие поля без изменений ...
    price_per_unit_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # NEW: tokenization parameters
    total_supply: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    # total_supply = all options covering 100% of company shares
    # Formula: total_shares / shares_per_option
    # At tokenization: this becomes the total mint of the contract

    shares_per_option: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    # shares_per_option = how many shares one option represents
    # Example: shares_per_option=10 means 1 option = 10 shares
    # Determines denomination. Changes only on split (new Pool).
```

### 3.2. OptionPool — новая модель

```python
class OptionPool(UUIDMixin, TimestampMixin, Base):
    """Pool of options allocated for sale on the platform.

    One active pool per company at any time.
    Enforced by partial unique index: UNIQUE(company_id) WHERE status='active'.
    """
    __tablename__ = "option_pools"

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("company_profiles.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    equity_percent: Mapped[Decimal] = mapped_column(
        Numeric(7, 4),
        nullable=False,
    )
    # equity_percent = share of company allocated for sale
    # Example: 10.0000 = 10% of total_supply

    total_options: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    # total_options = number of options in this pool
    # At creation: computed from total_supply * equity_percent / 100
    # At edit (допэмиссия): staff sets total_options, equity_percent recomputed

    status: Mapped[str] = mapped_column(
        String(20),
        default="active",
        server_default="active",
        nullable=False,
        index=True,
    )
    # Statuses: active, archived
    # archived = pool frozen (e.g. after split)
```

**Partial unique index (DB-level guarantee):**

```sql
CREATE UNIQUE INDEX uq_one_active_pool_per_company
ON option_pools (company_id)
WHERE status = 'active';
```

**Source of truth rules:**

| Operation | Source | Computed |
|-----------|--------|----------|
| Pool creation | `equity_percent` (staff sets) | `total_options = total_supply * equity_percent / 100` |
| Pool edit (допэмиссия) | `total_options` (staff sets) | `equity_percent = total_options / total_supply * 100` |
| Split | `equity_percent` inherits from old pool | `total_options` recomputed from new `total_supply` and new `shares_per_option` |

### 3.3. Product — привязка к Pool

```python
class Product(JSONBMixin, UUIDMixin, TimestampMixin, Base):
    # CHANGED: pool_id instead of company_id
    pool_id: Mapped[UUID] = mapped_column(
        ForeignKey("option_pools.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Denormalized for fast queries (populated on creation, immutable)
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("company_profiles.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # RENAMED from `units`
    package_size: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    # package_size = how many options in one package of this product
    # Immutable after creation.

    # ... all other existing fields unchanged ...
```

**`company_id` на Product сохраняется** как денормализация — нужен для быстрых запросов (dashboard, portfolio) без JOIN через Pool. Заполняется при создании из `pool.company_id`, иммутабелен.

### 3.4. Purchase — без структурных изменений

```python
class Purchase:
    product_id: FK -> Product         # без изменений
    company_id: FK -> CompanyProfile  # без изменений (денормализация)
    units: int                        # snapshot of product.package_size at purchase time
    # Поле НЕ переименовывается — это «сколько опционов получил инвестор»
```

### 3.5. Вычисляемая доступность

Не колонка в БД, а runtime-функция:

```python
async def get_available_packages_map(
    session: AsyncSession,
    company_ids: list[UUID],
    product_ids: list[UUID],
) -> dict[UUID, int]:
    """For each product, compute how many packs are still available.

    available_packages[product_id] = max(0, floor(
        pool_remaining / product.package_size
    ))

    pool_remaining = pool.total_options - SUM(Purchase.units
        WHERE company_id = product.company_id
        AND status = 'active')

    ALL purchases (including gifts) consume the pool.
    If pool_remaining < 0, gifts have overflowed into owner supply.
    Available packages = 0 in that case.
    """
```

**IMPORTANT:** В отличие от v1.0 спеки, gift purchases **учитываются** в расходе пула. Gift-опционы расходуют пул в первую очередь; если пул исчерпан, overflow берётся из owner supply (`total_supply` за пределами пула).

### 3.6. Валидация покупки

В `execute_purchase()` добавляется проверка **перед** списанием денег:

```python
# Inside execute_purchase(), after loading Product and Company:
# -- 1.5. Find active pool, validate availability --
pool = await _get_active_pool(company.id, session)
pool_remaining = await _get_pool_remaining(pool, session)
if pool_remaining < product.package_size:
    raise BadRequestError("sold out")
```

```python
async def _get_active_pool(company_id: UUID, session: AsyncSession) -> OptionPool:
    """Load the single active pool for a company."""
    stmt = select(OptionPool).where(
        OptionPool.company_id == company_id,
        OptionPool.status == "active",
    )
    result = await session.execute(stmt)
    pools = list(result.scalars().all())

    if len(pools) == 0:
        raise BadRequestError("Company has no active pool")
    if len(pools) > 1:
        raise RuntimeError(f"Data integrity: multiple active pools for company {company_id}")

    return pools[0]


async def _get_pool_remaining(pool: OptionPool, session: AsyncSession) -> int:
    """Options remaining in pool: total - all consumed (including gifts)."""
    consumed_stmt = (
        select(func.coalesce(func.sum(Purchase.units), 0))
        .where(
            Purchase.company_id == pool.company_id,
            Purchase.status == PurchaseStatus.ACTIVE,
        )
    )
    consumed = (await session.execute(consumed_stmt)).scalar_one()
    return pool.total_options - int(consumed)
```

**Race condition:** Нет advisory lock на `pool_id` / `company_id`. Два параллельных запроса теоретически могут пройти валидацию одновременно, и пул уйдёт в минус. Это **осознанный бизнес-риск**: компании предупреждены, что фактически проданный пул может незначительно превысить заявленный. Решается потом оперативным снятием с продажи. Для MVP с малым трафиком — не проблема.

### 3.7. Gift / bonus shares — семантика

Bonus shares, создаваемые `GiftProcessor`, расходуют пул наравне с обычными покупками.

**Приоритет расхода:**
1. Сначала пул (`pool.total_options`)
2. Если пул исчерпан — overflow из owner supply (`total_supply - pool.total_options`)

Gift **всегда выдаётся** — даже если пул кончился. Система знает об overflow: `pool_remaining < 0` означает, что `abs(pool_remaining)` опционов «одолжено» у owners.

Для **availability продуктов** (можно ли КУПИТЬ):
- `available_packages = max(0, floor(pool_remaining / package_size))`
- Когда `pool_remaining < package_size` → sold out, купить нельзя
- Но gift всё равно создаётся (пишется Purchase с `legal_basis='gift'`)

### 3.8. Installments

`InstallmentPlan.total_units` — снапшот `product.package_size` на момент создания плана. Переименование поля не ломает снапшоты.

**Единственное изменение:** в `installments/service.py:create_plan()`:
`total_units = product.units` → `total_units = product.package_size`.

Активные планы в БД продолжают работать по снапшотам.

### 3.9. Installment Calculator (NEW)

Staff endpoint для расчёта `plan_config` с мотивационным распределением опционов.

**Суть:** суммы траншей — примерно равные и «красивые» (кратные шагу округления). Опционы — перекос к последнему траншу (30-50%), мотивирующий инвестора закрыть план до конца.

**Endpoint:** `POST /api/v1/staff/products/{id}/installments/preview`

**Параметры:**

| Параметр | Тип | Описание |
|----------|-----|----------|
| `num_tranches` | int | Из списка `ALLOWED_TRANCHES` (конфиг): `[3, 6, 12, 24, 36]` |
| `last_tranche_percent` | int | % опционов в последнем транше (30-50, staff задаёт) |
| `amount_rounding_cents` | int | Шаг округления суммы (500, 1000, 5000, 10000 cents) |

`total_amount_cents` и `package_size` берутся из Product автоматически.

**Алгоритм:**

```python
# Amounts — equal and "pretty", remainder to last
regular_amount = (total_amount_cents // num_tranches // amount_rounding) * amount_rounding
last_amount = total_amount_cents - regular_amount * (num_tranches - 1)

# Options — skew to last, remainder to last
last_options_base = package_size * last_tranche_percent // 100
remaining = package_size - last_options_base
regular_options = remaining // (num_tranches - 1)
last_options = package_size - regular_options * (num_tranches - 1)
```

**Инварианты (всегда true):**
- `regular_amount * (N-1) + last_amount == total_amount_cents`
- `regular_options * (N-1) + last_options == package_size`
- `regular_amount % amount_rounding == 0`
- `last_amount > 0` (иначе шаг округления слишком грубый → 400 error)

**Пример:** пакет 10000 опционов, $1000, 6 траншей, last_tranche_percent=50, округление $5:
- 5 × ($165, 1000 опционов) + 1 × ($175, 5000 опционов)

**Response:** готовый `plan_config` + summary. Staff смотрит, жмёт «Создать» → стандартный `POST /products/{id}/installments` с тем же `plan_config`. Один алгоритм, один язык, DRY.

---

## 4. Сплит — архитектура (future scope)

Реализация сплита НЕ входит в Sprint 4.3, но архитектура моделей спроектирована так, чтобы сплит был возможен без ломающих миграций.

### 4.1. Когда нужен сплит

Сплит = изменение `shares_per_option` (деноминации). Одна старая акция = N новых → старый опцион ≠ новый опцион → нужна полная миграция.

**Граница:** если `shares_per_option` не изменился — редактируем Pool (допэмиссия). Если изменился — новый Pool + миграция.

### 4.2. Механика сплита

1. **Новый Pool** создаётся с новой деноминацией. Старый Pool → `status = 'archived'`.

2. **Миграционные Products:** для каждого старого Product создаётся «миграционный» Product в новом Pool. `package_size` пересчитан по коэффициенту сплита. `status = 'pool_migration'` — скрыт, купить нельзя, но FK сохранён.

3. **Двойная запись покупок:** для каждой старой Purchase:
   - Reversal: `legal_basis = 'pool_migration'`, отрицательная / `status = 'migrated_out'`, FK → старый Product
   - Новая: `legal_basis = 'pool_migration'`, `paid_cents = 0`, `units = старые * коэффициент`, FK → миграционный Product нового Pool

4. **Installment plans:** НЕ закрываются / пересоздаются. Обновляются in-place:
   - `total_units *= коэффициент`
   - `product_id` → переключить на миграционный Product нового Pool
   - `plan_config_snapshot.tranches[].amount_cents` — **не трогать** (деньги не меняются)
   - `plan_config_snapshot.tranches[].units_percent` — **не трогать** (проценты от деноминации не зависят)
   - Уже оплаченные транши → их Purchase мигрируются двойной записью

### 4.3. ProductStatus расширяется

```python
class ProductStatus(str, Enum):
    ACTIVE = "active"
    HIDDEN = "hidden"
    ARCHIVED = "archived"
    POOL_MIGRATION = "pool_migration"  # NEW: invisible, for FK integrity at split
```

### 4.4. Допэмиссия — НЕ сплит

Допэмиссия (увеличение/уменьшение количества опционов без изменения деноминации) — редактирование `total_options` на существующем Pool. Покупки не мигрируются. Products не трогаются. Availability пересчитывается динамически.

**Валидация при уменьшении:**
```python
consumed = SUM(Purchase.units WHERE company_id = X AND status = active)
if new_total_options < consumed:
    raise BadRequestError("Cannot reduce pool below already sold")
```

---

## 5. Staff endpoints — новые и изменённые

### 5.1. Pool endpoints (NEW, staff-only)

Все под permissions: `company_manage` + `financial_operations`.

**`POST /api/v1/staff/companies/{id}/pool`** — создать Pool.

Body:
```json
{
  "equity_percent": 10.0
}
```
- `total_options` вычисляется: `company.total_supply * equity_percent / 100`
- Валидация: у компании нет другого активного Pool
- Создаёт Pool со статусом `active`

**`PATCH /api/v1/staff/companies/{id}/pool`** — редактировать Pool (допэмиссия).

Body:
```json
{
  "total_options": 1500000
}
```
- `equity_percent` пересчитывается: `total_options / company.total_supply * 100`
- Валидация: `total_options >= consumed` (нельзя уменьшить ниже проданного)
- Audit event: `pool.updated`

### 5.2. Product creation — изменения

**`POST /api/v1/staff/products`** — body по-прежнему содержит `company_id`.

Внутри сервиса:
1. По `company_id` находим единственный активный Pool
2. Если Pool'ов 0 → `BadRequestError("Company has no active pool")`
3. Если Pool'ов > 1 → `RuntimeError("Data integrity: multiple active pools")`
4. Создаём Product с `pool_id = pool.id`, `company_id = pool.company_id` (денормализация)
5. Валидация: `package_size <= pool.total_options` (защита от дурака)

### 5.3. Installment Calculator (NEW)

**`POST /api/v1/staff/products/{id}/installments/preview`**

Permissions: `company_manage` + `financial_operations`.

Body:
```json
{
  "num_tranches": 6,
  "last_tranche_percent": 50,
  "amount_rounding_cents": 500
}
```

Response:
```json
{
  "plan_config": {
    "tranches": [
      {"amount_cents": 16500, "units_percent": 10},
      ...
    ],
    "bonus_units": 0,
    "agent_bonus_units": 0
  },
  "summary": {
    "regular_amount_cents": 16500,
    "last_amount_cents": 17500,
    "regular_options": 1000,
    "last_options": 5000,
    "num_tranches": 6
  }
}
```

Validation:
- `num_tranches` must be in `ALLOWED_TRANCHES` config → `[3, 6, 12, 24, 36]`
- `last_tranche_percent` must be 1-99 (reasonable: 30-50)
- `last_amount > 0` after rounding, else 400

---

## 6. Company Dashboard — новый модуль (NEW)

### 6.1. Обоснование

Investor dashboard (`dashboard/`) и Company dashboard — разные аудитории, разные запросы, разные schemas, разные permissions. Объединять бессмысленно.

### 6.2. Структура

```
backend/app/modules/company_dashboard/
    __init__.py
    router.py
    service.py
    schemas.py
```

### 6.3. Dependency — `get_current_company_profile()`

Новый dependency в `companies/dependencies.py`:

```python
async def get_current_company_profile(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_reader),
) -> CompanyProfile:
    """Load CompanyProfile for authenticated company user."""
    stmt = select(CompanyProfile).where(CompanyProfile.user_id == user.id)
    result = await session.execute(stmt)
    company = result.scalar_one_or_none()
    if company is None:
        raise ForbiddenError("User is not linked to a company")
    return company
```

### 6.4. Endpoints (read-only)

**`GET /api/v1/company/dashboard`**

Response:
```json
{
  "passive_balance": {"frozen": 0, "confirmed": 50000},
  "total_revenue_cents": 1000000,
  "total_options_sold": 7000,
  "products_count": 3,
  "pool": {
    "total_options": 1000000,
    "equity_percent": 10.0,
    "consumed": 7000,
    "remaining": 993000,
    "status": "active"
  },
  "recent_transactions": [...]
}
```

**`GET /api/v1/company/analytics`**

Response:
```json
{
  "total_revenue_cents": 1000000,
  "revenue_this_month_cents": 150000,
  "total_options_sold": 7000,
  "sales_by_month": [
    {"month": "2026-01", "revenue_cents": 200000, "options_sold": 1400},
    ...
  ],
  "sales_by_product": [
    {"product_id": "...", "product_name": "Starter", "revenue_cents": 300000, "options_sold": 3000},
    ...
  ]
}
```

**`GET /api/v1/company/pool`**

Pool info для company dashboard — можно сделать частью `/company/dashboard` response, либо отдельным endpoint.

---

## 7. Миграция (Alembic)

### 7.1. Стратегия

Одна ревизия `0027_option_pool_refactor`. Порядок:
1. Создать таблицу `option_pools`
2. Добавить `total_supply`, `shares_per_option` на `company_profiles`
3. Data migration: создать Pool для каждой компании
4. Добавить `pool_id` на `products` (nullable → populate → NOT NULL)
5. Rename `products.units` → `products.package_size`
6. Добавить partial unique index на `option_pools`

### 7.2. Upgrade

```python
"""option pool refactor -- Sprint 4.3

Revision ID: 0027_option_pool_refactor
Revises: 0026_products_cover_url

Changes:
  - NEW TABLE: option_pools
  - companies: +total_supply, +shares_per_option
  - products: +pool_id (FK), rename units → package_size
  - partial unique index on option_pools(company_id) WHERE status='active'
"""

def upgrade() -> None:
    # -- 1. Create option_pools table --
    op.create_table(
        "option_pools",
        sa.Column("id", sa.UUID(), nullable=False, default=uuid4),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("equity_percent", sa.Numeric(7, 4), nullable=False),
        sa.Column("total_options", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(20), server_default="active", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["company_id"], ["company_profiles.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_option_pools_company_id", "option_pools", ["company_id"])
    op.create_index("ix_option_pools_status", "option_pools", ["status"])

    # -- 2. Add company fields (nullable first) --
    op.add_column("company_profiles", sa.Column("total_supply", sa.BigInteger(), nullable=True))
    op.add_column("company_profiles", sa.Column("shares_per_option", sa.Integer(), nullable=True))

    # -- 3. Data migration: populate company fields --
    # Default: shares_per_option=1, total_supply = SUM(products.units) per company
    op.execute("""
        UPDATE company_profiles SET shares_per_option = 1
    """)
    op.execute("""
        UPDATE company_profiles
        SET total_supply = COALESCE(
            (SELECT SUM(units) FROM products WHERE company_id = company_profiles.id),
            0
        )
    """)

    # -- 4. Lock company fields as NOT NULL --
    op.alter_column("company_profiles", "total_supply", nullable=False)
    op.alter_column("company_profiles", "shares_per_option", nullable=False)

    # -- 5. Create a Pool for each existing company --
    op.execute("""
        INSERT INTO option_pools (id, company_id, equity_percent, total_options, status)
        SELECT
            gen_random_uuid(),
            cp.id,
            100.0000,
            cp.total_supply,
            'active'
        FROM company_profiles cp
    """)

    # -- 6. Add pool_id to products (nullable first) --
    op.add_column("products", sa.Column("pool_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_products_pool_id", "products", "option_pools",
        ["pool_id"], ["id"], ondelete="RESTRICT"
    )

    # -- 7. Populate pool_id from company_id --
    op.execute("""
        UPDATE products p
        SET pool_id = (
            SELECT op.id FROM option_pools op
            WHERE op.company_id = p.company_id
            AND op.status = 'active'
        )
    """)

    # -- 8. Lock pool_id as NOT NULL, add index --
    op.alter_column("products", "pool_id", nullable=False)
    op.create_index("ix_products_pool_id", "products", ["pool_id"])

    # -- 9. Rename products.units → products.package_size --
    op.alter_column("products", "units", new_column_name="package_size")

    # -- 10. Partial unique index: one active pool per company --
    op.execute("""
        CREATE UNIQUE INDEX uq_one_active_pool_per_company
        ON option_pools (company_id)
        WHERE status = 'active'
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_one_active_pool_per_company")
    op.alter_column("products", "package_size", new_column_name="units")
    op.drop_index("ix_products_pool_id", "products")
    op.drop_constraint("fk_products_pool_id", "products", type_="foreignkey")
    op.drop_column("products", "pool_id")
    op.execute("DELETE FROM option_pools")
    op.drop_index("ix_option_pools_status", "option_pools")
    op.drop_index("ix_option_pools_company_id", "option_pools")
    op.drop_table("option_pools")
    op.drop_column("company_profiles", "shares_per_option")
    op.drop_column("company_profiles", "total_supply")
```

---

## 8. Backend changes — полный чек-лист

### 8.1. Модели

| Файл | Правка |
|------|--------|
| `companies/models.py` | +`total_supply: BigInteger`, +`shares_per_option: Integer`. Обновить docstring, `__repr__` |
| `companies/constants.py` | Без изменений |
| `products/models.py` | `units` → `package_size`. +`pool_id: FK -> option_pools`. Обновить docstring, `__repr__` |
| **NEW:** `pools/models.py` | Новая модель `OptionPool` (§3.2) |
| **NEW:** `pools/__init__.py` | — |

### 8.2. Схемы

| Файл | Правка |
|------|--------|
| `companies/schemas.py` | +`total_supply`, +`shares_per_option` в Response/Create/Update |
| `products/schemas.py` | `units` → `package_size` в Create/Response/Public. `sold_units` → `available_packages` в Public |
| **NEW:** `pools/schemas.py` | `CreatePoolRequest`, `UpdatePoolRequest`, `PoolResponse` |

### 8.3. Сервисы и роутеры

| Файл | Правка |
|------|--------|
| `companies/service.py` | `create_company()`: +`total_supply`, +`shares_per_option`. `update_company()`: handle new fields |
| **NEW:** `pools/service.py` | `create_pool()`, `update_pool()`, `get_active_pool()` |
| **NEW:** `pools/router.py` | Staff endpoints: POST/PATCH `/staff/companies/{id}/pool` |
| `products/service.py` | `create_product()`: `units` → `package_size`, lookup active Pool, set `pool_id`. Валидация `package_size <= pool.total_options` |
| `products/constants.py` | `validate_plan_config()`: `product_units` → `product_package_size` |
| `purchases/service.py` | `get_sold_units_map()` → `get_available_packages_map()`. `execute_purchase()`: +pool validation (§3.6). `amount_cents = product.package_size * ...`. +`_get_active_pool()`, +`_get_pool_remaining()` |
| `products/router.py` (public) | `get_sold_units_map` → `get_available_packages_map`, `resp.sold_units =` → `resp.available_packages =`. Import: `get_sold_units_map` → `get_available_packages_map` |
| `processors/base.py` | `PurchaseContext.units` — comment update only. Field name stays `units` |
| `installments/service.py` | `product.units` → `product.package_size` (one line) |
| **NEW:** `company_dashboard/` | Новый модуль (§6) |
| **NEW:** `companies/dependencies.py` | `get_current_company_profile()` |

### 8.4. Installment Calculator

| Файл | Правка |
|------|--------|
| `products/staff_router.py` | +`POST /staff/products/{id}/installments/preview` |
| `products/service.py` (или `products/calculator.py`) | `calculate_installment_preview()` — алгоритм из §3.9 |
| `products/schemas.py` | +`InstallmentPreviewRequest`, +`InstallmentPreviewResponse` |
| `products/constants.py` | +`ALLOWED_TRANCHES = [3, 6, 12, 24, 36]` (config) |

### 8.5. Seed script

`backend/scripts/seed_storefront.py`:

| Место | Правка |
|-------|--------|
| `COMPANIES` list | +`total_supply`, +`shares_per_option` для каждой компании |
| `PRODUCTS` list | `units` → `package_size` |
| Seed logic | Создать Pool для каждой компании после создания CompanyProfile |

### 8.6. Тесты

#### Обновление существующих:

| Файл | Правка |
|------|--------|
| `test_products.py` | Хелперы: +`total_supply`, +`shares_per_option` в company, `units` → `package_size`, +создание Pool. Ассёрты: `sold_units` → `available_packages` |
| `test_purchases.py` | Хелперы: аналогично. `product["units"]` → `product["package_size"]` |
| `test_installments.py` | Хелперы: аналогично |
| `test_dashboard.py` | Хелперы: +`total_supply`, +`shares_per_option`, +Pool |
| `test_companies.py` | +`total_supply`, +`shares_per_option` в Create/Response assertions |

#### Новые тесты:

| Тест | Описание |
|------|----------|
| `test_create_pool` | POST pool → 201, equity_percent + total_options correct |
| `test_one_active_pool_per_company` | Второй POST pool → 400 или DB constraint error |
| `test_update_pool_total_options` | PATCH → equity_percent recomputed |
| `test_update_pool_below_consumed` | PATCH total_options below sold → 400 |
| `test_product_requires_active_pool` | Create product without pool → 400 |
| `test_available_packages_decreases` | Buy → availability decreases for ALL products of company |
| `test_purchase_sold_out` | pool_remaining < package_size → 400 |
| `test_gift_consumes_pool` | Gift purchase reduces pool_remaining |
| `test_gift_overflow_allowed` | Gift when pool_remaining=0 → succeeds, pool goes negative |
| `test_installment_preview` | Calculator returns correct plan_config |
| `test_installment_preview_invariants` | Amounts sum, options sum, rounding correct |

---

## 9. Frontend changes — полный чек-лист (TD-F07)

Механическое переименование после backend merge. Не отдельный спринт.

### 9.1. Types

`frontend/src/api/types.ts`:

```typescript
// PublicProductResponse: units → package_size, sold_units → available_packages
// PublicCompanyResponse: +total_supply, +shares_per_option
// NEW: PoolResponse (for company dashboard)
```

### 9.2. Components

| Файл | Правка |
|------|--------|
| `ProductCard.vue` | `p.units - p.sold_units` → `p.available_packages` |
| `ProductDetailView.vue` | Аналогично + sold-out state |
| `stores/products.ts` | Проверить passthrough |

### 9.3. i18n

4 локали: `+inv.market.packsAvailable`, `+inv.product.packsAvailability`, `+inv.product.soldOut`

---

## 10. Price cascade — без изменений

Цена живёт на Company, не на Pool. Price cascade работает как раньше: `Company.price_per_unit_cents` → каскад на все active/hidden Products → soft-delete всех installment templates. Pool не участвует.

---

## 11. Edge cases и риски

### 11.1. `pool.total_options` = 0
Все продукты компании: `available_packages = 0`. Покупка → `BadRequestError`. Корректное поведение.

### 11.2. `package_size` > `pool.total_options`
`available_packages = 0` с самого начала. Mitigation: валидация при `create_product()`.

### 11.3. Параллельные покупки (race condition)
Без lock'а на pool. Два инвестора могут купить одновременно → пул уходит в минус. Бизнес-приемлемо для MVP.

### 11.4. Gift overflow
`pool_remaining < 0` после gift → overflow из owner supply. Вычисляется динамически, не хранится.

### 11.5. Installment calculator: шаг округления слишком грубый
`regular_amount * (N-1) >= total_amount` → `last_amount <= 0` → 400 error.

---

## 12. Out of scope

- Split реализация (§4 — архитектура заложена)
- Advisory lock на pool при покупке
- Staff UI для Pool management (F3 админка)
- Multi-currency
- Partial-pack покупки
- Blockchain integration / smart contracts
- Lock periods для owner tokens

---

## 13. Acceptance criteria

### Backend

- [ ] Миграция `0027_option_pool_refactor` применена, БД консистентна
- [ ] Таблица `option_pools` создана, partial unique index работает
- [ ] `CompanyProfile` имеет `total_supply` и `shares_per_option`
- [ ] `Product` имеет `pool_id` (FK) и `package_size` (renamed from `units`)
- [ ] Pool CRUD endpoints работают (staff-only)
- [ ] `get_available_packages_map()` — корректный расчёт через pool
- [ ] `execute_purchase()` — валидация `pool_remaining >= package_size`
- [ ] Gift purchases учитываются в расходе пула
- [ ] Installment calculator endpoint возвращает корректный preview
- [ ] Company dashboard endpoints возвращают данные
- [ ] Все существующие тесты зелёные
- [ ] Все новые тесты зелёные

### Frontend (TD-F07)

- [ ] Types обновлены: `package_size`, `available_packages`
- [ ] Components используют `available_packages` напрямую
- [ ] i18n ключи во всех 4 локалях
- [ ] `npm run typecheck` — без ошибок

### Data / seed

- [ ] Seed создаёт Pool для каждой компании
- [ ] Availability показывает реалистичные числа

---

## 14. Changelog

- **v1.0 (2026-04-17):** первая версия. Простое переименование + total_shares_issued.
- **v2.0 (2026-04-30):** полная переработка архитектуры:
  - `OptionPool` как отдельная модель
  - `total_supply` + `shares_per_option` на Company
  - Product привязан к Pool (`pool_id`), не к Company
  - Gift shares расходуют пул (overflow → owner supply)
  - Installment Calculator (preview endpoint)
  - Company Dashboard — отдельный модуль
  - Сплит — архитектура заложена (future scope)
  - Допэмиссия — редактирование Pool (без миграции покупок)
- **v2.1 (2026-04-30):** Impact analysis от Claude Code:
  - Номер миграции: 0028 → 0027 (после 0026_products_cover_url)
  - Точный перечень файлов/строк для правок (Appendix A)
  - Зафиксированы Risk Areas
  - `generate_ts_types.py` — в scope Sprint 4.3

---

## Appendix A: Impact Analysis Report (Claude Code)

Generated: 2026-04-30
Repository: cbshome @ 31b5e28f671c3a98c5762de942b68ea981427a74
Spec: CBSHOME-Share-Pool-Refactor.md v2.0

> **Report revision v2:** corrected OptionPool field set, CompanyProfile field placement,
> removed `consumed` column, `is_active→status`, fixed gift semantics, added
> `products/router.py` to Files to Modify.

### Summary

| Metric | Count |
|--------|-------|
| Backend source files to modify | 9 + 1 script |
| Frontend files to modify | 5 |
| Test files to modify | 6 |
| New files to create | 11 |
| Latest migration | 0026_products_cover_url |
| Next migration | **0027** |

### Backend: Files to Modify (exact lines)

**`products/models.py`**
- Line 6: docstring — update `units` → `package_size`
- Line 75: `units: Mapped[int]` → rename column to `package_size`; add `pool_id` FK
- Line 114: `__repr__` — `units=` → `package_size=`

**`products/schemas.py`**
- Line 40: `units: int = Field(gt=0)` → `package_size` in `CreateProductRequest`
- Line 49: docstring `units and company_id are immutable` → update
- Line 112: `units: int` → `package_size` in `StaffProductResponse`
- Line 150: `units: int` → `package_size` in `PublicProductResponse`
- Line 153: `sold_units: int = 0` → `available_packages: int = 0` (semantics change: now floor(pool_remaining / package_size) across whole company)

**`products/router.py` (public)**
- Line 53: import `get_sold_units_map` → `get_available_packages_map`
- Lines 77–79: `sold_map = await get_sold_units_map(session, product_ids)` → `available_map = await get_available_packages_map(session, company_ids, product_ids)`; ⚠️ `company_ids` collected on line 83 must be moved **before** this call
- Line 96: `resp.sold_units = sold_map.get(p.id, 0)` → `resp.available_packages = available_map.get(p.id, 0)`
- Line 137: `sold_map = await get_sold_units_map(session, [product.id])` → `available_map = await get_available_packages_map(session, [product.company_id], [product.id])`
- Line 155: `response.sold_units = sold_map.get(product.id, 0)` → `response.available_packages = available_map.get(product.id, 0)`

**`products/staff_router.py`**
- Line 90: `body.units,` → `body.package_size,`

**`products/service.py`**
- Line 72: param `units: int` → `package_size: int`
- Line 99: `units=units,` → `package_size=package_size,`
- Line 120: audit dict `"units"` → `"package_size"`
- Lines 347, 403: `product.units` → `product.package_size` (call sites to `validate_plan_config`)

**`products/constants.py`**
- Lines 22, 115, 132–143: comments referencing `product.units` → `product.package_size`
- Line 52: param `product_units: int` — name can stay; Line 69 comment update

**`purchases/service.py`**
- Line 320: `product.units * product.price_per_unit_cents` → `product.package_size`
- Line 329: `units=product.units` → `units=product.package_size` (populates `PurchaseContext.units`, NOT renamed)
- **New function:** `get_available_packages_map(session, company_ids, product_ids)` — replaces `get_sold_units_map`; formula: `floor(pool_remaining / product.package_size)`; gift purchases **included** in consumed (v2.0 decision)
- **New function:** `_get_shares_remaining(company_id, session)` — SUM excludes nothing (all active purchases count against pool)
- **`execute_purchase()`** — add pool validation after `_load_company`, before `PurchaseContext`; raise `BadRequestError` if `shares_remaining < product.package_size`

**`installments/service.py`**
- Line 150: `total_units = product.units` → `product.package_size`

**`processors/base.py`**
- Line 81: comment `# product.units` → `# product.package_size` (field name `units` stays)

### Frontend: Files to Modify (exact lines)

**`api/types.ts`**
- Line 388: `units: number` → `package_size: number`
- Line 391: `sold_units: number` → `available_packages: number` (no frontend subtraction needed — pre-computed by backend)
- Add `pool_id: string | null` to `PublicProductResponse`
- Add `total_supply: number`, `shares_per_option: number` to Company responses

**`components/shared/ProductCard.vue`**
- Line 45: `props.product.units - props.product.sold_units` → `props.product.available_packages` (no subtraction; pre-computed)
- Line 73: update class name / label to reflect `packsAvailable` i18n key

**`views/investor/ProductDetailView.vue`**
- Line 90: `p.units - p.sold_units` → `p.available_packages`
- `<CButton :disabled="...">` guard — update to `p.available_packages === 0`

**`views/investor/PurchaseView.vue`**
- Line 89: `p.units * p.price_per_unit_cents` → `p.package_size * p.price_per_unit_cents`
- Line 94: `p.units - p.sold_units` → `p.available_packages`
- Line 277: `product.units` → `product.package_size`

**`views/investor/InstallmentView.vue`**
- Line 180: `product.value.units` → `product.value.package_size`

### Tests: Files to Modify (exact lines)

**`test_products.py`**
- Line 111: helper param `units: int = 100` → `package_size`
- Line 120: `"units": units` → `"package_size": package_size`
- `_create_company()` helper: add `"total_supply": 10_000_000`
- Line 169: `product["units"]` → `product["package_size"]`
- Line 224: `"units": 50` → `"package_size": 50`
- Line 563: `body["sold_units"]` → `body["available_packages"]`

**`test_purchases.py`**
- Line 113: `"units": units` → `"package_size": units` in helper
- `_create_company()` helper: add `"total_supply": 10_000_000`
- Line 427: ⚠️ MIXED — `data[0]["units"]` is `Purchase.units` (stays), `product["units"]` → `product["package_size"]`
- Line 428: `product["units"]` → `product["package_size"]`
- Lines 577, 579: `Purchase.units` — stays

**`test_installments.py`**
- Line 146: `"units": units` → `"package_size": units`
- `_create_company()` helper: add `"total_supply"`

**`test_dashboard.py`**
- Line 108: `"units": units` → `"package_size": units`
- Line 436: ⚠️ AMBIGUOUS — verify if `p["units"]` is Purchase (stays) or Product (rename)

**`test_leaderboard.py`**
- Line 214: `"units": 100` → `"package_size": 100`

**`test_referrals.py`**
- Line 132: `"units": 10` → `"package_size": 10`

### New Test Cases Needed

- `test_pools.py` — Pool CRUD, one-active-per-company constraint, archive with remaining active purchases
- `test_products.py` — `available_packages_decreases_on_purchase`, `purchase_fails_when_pool_exhausted`
- `test_purchases.py` — `gift_consumes_pool`, `pool_exhausted_blocks_sale`
- `test_installment_calculator.py` — preview endpoint roundtrip, tranche invariants
- `test_company_dashboard.py` — auth, data shape, pool remaining

### Seed Script (`seed_storefront.py`)

- 20 occurrences: `"units": <value>` → `"package_size": <value>`
- Add `"total_supply"`, `"shares_per_option"` to COMPANIES (IPI AG → 10M, Immo-Pro-Invest → 5M, CBS Home → 100K, Nordic → 50K, Tesla → 2M, Stealth → 100)
- `_ensure_company()`: pass new fields to `CompanyProfile` constructor
- `_ensure_product()`: `units=` → `package_size=`; pass `pool_id`
- Add pool seeding: upsert `OptionPool(status='active')` per company

### Migration Notes

- Previous: `2026_04_17_0026_products_cover_url`
- New: `0027_share_pool_refactor` (`down_revision = "0026_products_cover_url"`)
- New table: `option_pools` (id, company_id FK, equity_percent NUMERIC, total_options BIGINT, status VARCHAR(20) DEFAULT 'active', timestamps). **No `consumed` column.**
- Altered: `company_profiles` (+total_supply BIGINT, +shares_per_option INTEGER), `products` (rename units→package_size, +pool_id UUID FK)
- New index: `uq_one_active_pool_per_company` — partial unique on `option_pools(company_id)` WHERE `status='active'`
- Data migration: `shares_per_option=1`, `total_supply=SUM(package_size)` per company; create Pool per company

### Risk Areas

1. **`products/router.py` line ordering** — `company_ids` collected on line 83 must be moved **before** the `get_available_packages_map` call (currently after `get_sold_units_map`). Two separate call sites (list endpoint line 79, detail endpoint line 137).
2. **`products/constants.py` + `service.py`** — `validate_plan_config(product_units=product.units)` → all 3 points (param def + 2 call sites) must change atomically.
3. **`processors/base.py:81`** — `PurchaseContext.units` shares the word "units" with renamed `Product.units`. Only comment changes. Risk: auto-replace catches it.
4. **`test_purchases.py:427`** — mixed assertion: `data[0]["units"]` (Purchase, stays) vs `product["units"]` (Product, rename). Risk: rename both by accident.
5. **`test_dashboard.py:436`** — `p["units"]` context ambiguous without fixture check.
6. **Gift purchases consume pool (v2.0)** — `_get_shares_remaining()` must NOT filter out `legal_basis='gift'`. The v1.0 spec on disk says the opposite — **do not follow v1.0**.
7. **Pool enforcement in `execute_purchase()`** — validation inserted between `_load_company` and `PurchaseContext` construction, inside same DB transaction. No advisory lock on pool (decided: business-acceptable race condition for MVP).
8. **`pool_id` FK nullable** — existing products have no pool. `create_product()` must require active pool; migration populates pool_id for existing products.
9. **`InstallmentView.vue:180`** — `getTrancheUnits` in `utils/installmentPlans.ts` may have own tests needing update.

---

**Конец документа**
