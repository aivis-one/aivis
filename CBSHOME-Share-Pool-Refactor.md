# CBSHOME — Option Pool & Product Inventory Model

**Tracking ID (Backend):** TD-071 (✅ Closed Sprint 4.4)
**Tracking ID (Frontend):** TD-F07 (✅ Closed Sprint 4.4)
**Sprints:** 4.3 + 4.4 — deployed on `b539ee8`
**Версия:** 2.4-trimmed
**Дата закрытия:** 3 мая 2026

> **Status: Closed.** This is the **architectural reference** for the option pool model that powers product inventory.
> Process artifacts (acceptance checklists, batch progress, impact analysis, file-by-file change lists) have been removed.
> What remains: the model itself, the migration shape, edge cases, and what's intentionally left out of MVP scope.
> If you need the implementation history, the git log on `b539ee8` and Backend.md / Frontend.md changelogs are the source of truth.

**Зависимости:**
- `CBSHOME-Backend.md` — Phase 4, актуальный код модулей `pools/`, `products/`, `purchases/`, `company_dashboard/`
- `CBSHOME-Frontend.md` — `types.ts` (VELO Migration), pack-pricing UX, типизированный auth store
- `CBSHOME-Financial-System.md` — `Purchase.units`, `Purchase.paid_cents`, pricing

---

## 1. Проблема — детально

### 1.1. Текущая модель (broken)

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

### 1.2. Конкретный баг

Продукт «IPI AG Sold Tranche» с `units=500`. Один инвестор купил пакет целиком → создаётся **одна** `Purchase` с `units=500`.

- На бэке: `get_sold_units_map()` возвращает `{product_id: 1}` (одна строка).
- На фронте: `available = product.units - product.sold_units = 500 − 1 = 499`.
- В UI пишется «499 available», хотя фактически пакет куплен целиком.

### 1.3. Бизнес-реальность

Компания IPI AG готова продать 10% своих акций. Если у компании 100 000 000 акций и `shares_per_option = 10`, то `total_supply = 10 000 000` опционов. Из них в Pool выделено 10% = `1 000 000` опционов.

Эти опционы предложены инвесторам через три одновременно активных пакета:
- Продукт «Starter» — 100 опционов за пакет.
- Продукт «Investor» — 1 000 опционов за пакет.
- Продукт «Whale» — 10 000 опционов за пакет.

Покупка пакета у **любого** продукта уменьшает `pool_remaining` для **всех** продуктов этой компании (каждый продукт по-своему, исходя из своего `package_size`).

### 1.4. Правовой аспект и токенизация

Юридически все опционы одной компании стоят одинаково. Цена фиксируется на уровне Company и каскадируется на Products.

**Будущее (за пределами MVP):** при получении лицензии опционы конвертируются в токены на блокчейне. Отсюда архитектурные требования:
- Pool = будущий смарт-контракт. Фиксированный supply.
- Опцион = будущий токен.
- Сплит = новый контракт + swap старых токенов на новые.
- Нельзя мутировать количество токенов после создания контракта, но можно выпустить новые и сделать swap.
- Двойная запись (списание + выпуск) — точная модель того, что произойдёт on-chain.

---

## 2. Правильная модель

### 2.1. CompanyProfile — новые поля

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

### 2.2. OptionPool — новая модель

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

### 2.3. Product — привязка к Pool

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

### 2.4. Purchase — без структурных изменений

```python
class Purchase:
    product_id: FK -> Product         # без изменений
    company_id: FK -> CompanyProfile  # без изменений (денормализация)
    units: int                        # snapshot of product.package_size at purchase time
    # Поле НЕ переименовывается — это «сколько опционов получил инвестор»
```

### 2.5. Вычисляемая доступность

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

### 2.6. Валидация покупки

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

### 2.7. Gift / bonus shares — семантика

Bonus shares, создаваемые `GiftProcessor`, расходуют пул наравне с обычными покупками.

**Приоритет расхода:**
1. Сначала пул (`pool.total_options`)
2. Если пул исчерпан — overflow из owner supply (`total_supply - pool.total_options`)

Gift **всегда выдаётся** — даже если пул кончился. Система знает об overflow: `pool_remaining < 0` означает, что `abs(pool_remaining)` опционов «одолжено» у owners.

Для **availability продуктов** (можно ли КУПИТЬ):
- `available_packages = max(0, floor(pool_remaining / package_size))`
- Когда `pool_remaining < package_size` → sold out, купить нельзя
- Но gift всё равно создаётся (пишется Purchase с `legal_basis='gift'`)

### 2.8. Installments

`InstallmentPlan.total_units` — снапшот `product.package_size` на момент создания плана. Переименование поля не ломает снапшоты.

**Единственное изменение:** в `installments/service.py:create_plan()`:
`total_units = product.units` → `total_units = product.package_size`.

Активные планы в БД продолжают работать по снапшотам.

### 2.9. Installment Calculator (NEW)

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

## 3. Сплит — архитектура (future scope)

Реализация сплита НЕ входит в Sprint 4.3, но архитектура моделей спроектирована так, чтобы сплит был возможен без ломающих миграций.

### 3.1. Когда нужен сплит

Сплит = изменение `shares_per_option` (деноминации). Одна старая акция = N новых → старый опцион ≠ новый опцион → нужна полная миграция.

**Граница:** если `shares_per_option` не изменился — редактируем Pool (допэмиссия). Если изменился — новый Pool + миграция.

### 3.2. Механика сплита

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

### 3.3. ProductStatus расширяется

```python
class ProductStatus(str, Enum):
    ACTIVE = "active"
    HIDDEN = "hidden"
    ARCHIVED = "archived"
    POOL_MIGRATION = "pool_migration"  # NEW: invisible, for FK integrity at split
```

### 3.4. Допэмиссия — НЕ сплит

Допэмиссия (увеличение/уменьшение количества опционов без изменения деноминации) — редактирование `total_options` на существующем Pool. Покупки не мигрируются. Products не трогаются. Availability пересчитывается динамически.

**Валидация при уменьшении:**
```python
consumed = SUM(Purchase.units WHERE company_id = X AND status = active)
if new_total_options < consumed:
    raise BadRequestError("Cannot reduce pool below already sold")
```

---

## 4. Staff endpoints — новые и изменённые

### 4.1. Pool endpoints (NEW, staff-only)

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

### 4.2. Product creation — изменения

**`POST /api/v1/staff/products`** — body по-прежнему содержит `company_id`.

Внутри сервиса:
1. По `company_id` находим единственный активный Pool
2. Если Pool'ов 0 → `BadRequestError("Company has no active pool")`
3. Если Pool'ов > 1 → `RuntimeError("Data integrity: multiple active pools")`
4. Создаём Product с `pool_id = pool.id`, `company_id = pool.company_id` (денормализация)
5. Валидация: `package_size <= pool.total_options` (защита от дурака)

### 4.3. Installment Calculator (NEW)

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

## 5. Company Dashboard — новый модуль (NEW)

### 5.1. Обоснование

Investor dashboard (`dashboard/`) и Company dashboard — разные аудитории, разные запросы, разные schemas, разные permissions. Объединять бессмысленно.

### 5.2. Структура

```
backend/app/modules/company_dashboard/
    __init__.py
    router.py
    service.py
    schemas.py
```

### 5.3. Dependency — `get_current_company_profile()`

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

### 5.4. Endpoints (read-only)

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

## 6. Миграция (Alembic)

### 6.1. Стратегия

Одна ревизия `0027_option_pool_refactor`. Порядок:
1. Создать таблицу `option_pools`
2. Добавить `total_supply`, `shares_per_option` на `company_profiles`
3. Data migration: создать Pool для каждой компании
4. Добавить `pool_id` на `products` (nullable → populate → NOT NULL)
5. Rename `products.units` → `products.package_size`
6. Добавить partial unique index на `option_pools`

### 6.2. Upgrade

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

## 7. Price cascade — без изменений

Цена живёт на Company, не на Pool. Price cascade работает как раньше: `Company.price_per_unit_cents` → каскад на все active/hidden Products → soft-delete всех installment templates. Pool не участвует.

---

## 8. Edge cases и риски

### 8.1. `pool.total_options` = 0
Все продукты компании: `available_packages = 0`. Покупка → `BadRequestError`. Корректное поведение.

### 8.2. `package_size` > `pool.total_options`
`available_packages = 0` с самого начала. Mitigation: валидация при `create_product()`.

### 8.3. Параллельные покупки (race condition)
Без lock'а на pool. Два инвестора могут купить одновременно → пул уходит в минус. Бизнес-приемлемо для MVP.

### 8.4. Gift overflow
`pool_remaining < 0` после gift → overflow из owner supply. Вычисляется динамически, не хранится.

### 8.5. Installment calculator: шаг округления слишком грубый
`regular_amount * (N-1) >= total_amount` → `last_amount <= 0` → 400 error.

---

## 9. Out of scope

- Split реализация (§3 — архитектура заложена)
- Advisory lock на pool при покупке
- Staff UI для Pool management (F3 админка)
- Multi-currency
- Partial-pack покупки
- Blockchain integration / smart contracts
- Lock periods для owner tokens

---

## 10. Changelog

- **v1.0 (2026-04-17):** initial draft — simple rename + total_shares_issued.
- **v2.0 (2026-04-30):** full architecture redesign. The model documented above is this version: `OptionPool` as a separate entity, `total_supply` + `shares_per_option` on Company, Product → Pool via FK, gift overflow into owner supply, installment calculator preview, company dashboard module, split as future scope, допэмиссия = pool resize without purchase migration.
- **v2.1–v2.3 (2026-04-30 → 2026-05-02):** implementation rounds B0–B8 — model deployed, tests grew 322 → 360. Process detail (per-batch deploy notes, impact analysis, acceptance checklists) lived here and was removed when the doc was trimmed to a reference. The git log on `main` between `0c2a4d1` and `d9071ef` is the source of truth for what landed when.
- **v2.4 (2026-05-03):** Sprint 4.4 closed. VELO Migration (frontend types pipeline → single source of truth = `generated.ts`), B7 pack-pricing UX (`price_per_pack_cents` server-computed, two-line price block), schema cleanup (`available_packages` / `company_name` / `installments` required, no defaults), pool architecture hardening (`POOL_STATUS_ACTIVE` centralised, dead copies in `purchases/service` removed, `update_pool` returns tuple, `with_consumed_remaining` requires `consumed`, `_compute_equity_percent` guards `total_supply <= 0`, ORM mutation antipattern → explicit Pydantic constructors, `ProductDetailResponse` dead class removed). Frontend type narrowing (`UserRole` / `KycStatus` runtime guards with compile-time exhaustiveness, `auth.ts` typed `role` + `kycStatus`). Final score 9.5/10. 362/362 tests green on `b539ee8`. Open: only TD-066 legal stubs, **not a code blocker**.
- **v2.4-trimmed (2026-05-03):** doc trimmed from 1370 → ~780 lines. Removed: §1 summary (became stale), §8 backend changes checklist, §9 frontend changes checklist, §13 acceptance criteria, Appendix A impact analysis, §15 implementation progress. Renumbered §2–§14 → §1–§10. Cross-reference §4 → §3 fixed. Doc is now an architectural reference for the option pool model, not a project tracker.

---

**End of architectural reference.** Implementation is deployed and stable; this document captures the *why* and *what* of the model, not the *how it got built*.
