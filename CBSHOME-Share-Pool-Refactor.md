# CBSHOME — Share Pool & Product Inventory Refactor

**Tracking ID (Backend):** TD-071
**Tracking ID (Frontend):** TD-F07
**Sprint:** 4.3 (planned, Phase 4)
**Статус:** Planned / 🔴 Blocker before Frontend Phase F5
**Дата создания:** 17 апреля 2026

**Зависимости:**
- `CBSHOME-Backend.md` — раздел Phase 4, реестр техдолга (TD-071)
- `CBSHOME-Frontend.md` — раздел PHASE F5, реестр техдолга (TD-F07)
- `CBSHOME-Financial-System.md` — ссылки на `Purchase.units`, `Purchase.paid_cents`, `Product.price_per_unit_cents`

---

## 1. Summary

Текущая модель `Product` конфликтует с бизнес-реальностью выпуска акций.

**Одна фраза:** компания выпускает фиксированный пул акций на продажу, а продукты — это лишь **правила деноминации** пула на пакеты разных размеров. Покупка одного пакета любого размера у любого продукта **уменьшает общий пул** компании — и одновременно меняет доступность **всех** продуктов этой компании (каждый продукт по-своему, исходя из своего размера пакета).

Текущий код этого не моделирует. `Product.units` трактуется как «инвентарь этого конкретного продукта», `sold_units = COUNT(Purchase)` считает пакеты, а не акции. Продукты одной компании не связаны между собой.

Рефактор должен: (1) ввести эмиссию на уровне компании, (2) переименовать `Product.units` → `Product.package_size` для ясности семантики, (3) вычислять availability динамически как производную от остатка пула компании и размера пакета конкретного продукта, (4) валидировать покупку против остатка пула.

---

## 2. Проблема — детально

### 2.1. Текущая модель (broken)

```python
class CompanyProfile:
    price_per_unit_cents: BigInteger      # $ per share
    # нет total_shares_issued — эмиссия не моделируется

class Product:
    units: Integer                         # иммутабельно
    # трактуется одновременно как:
    #   (a) размер пакета (смысл в name: "Starter — 100 Shares")
    #   (b) инвентарь этого продукта (исчерпывается при покупке)
```

**Функция подсчёта проданного:**

```python
# backend/app/modules/purchases/service.py
async def get_sold_units_map(
    session: AsyncSession,
    product_ids: list[UUID],
) -> dict[UUID, int]:
    stmt = (
        select(
            Purchase.product_id,
            func.count().label("cnt"),              # ← COUNT(*), НЕ SUM(units)
        )
        .where(
            Purchase.product_id.in_(product_ids),
            Purchase.status == PurchaseStatus.ACTIVE,
            Purchase.legal_basis == PurchaseLegalBasis.SALE,
        )
        .group_by(Purchase.product_id)
    )
    result = await session.execute(stmt)
    return {row.product_id: row.cnt for row in result.all()}
```

**Публичная схема:**

```python
# backend/app/modules/products/schemas.py
class PublicProductResponse(BaseModel):
    units: int                             # размер пакета (миксуется со смыслом "доступно")
    sold_units: int = 0                    # COUNT покупок этого продукта
```

### 2.2. Конкретный баг

Продукт «IPI AG Sold Tranche» с `units=500`. Один инвестор купил пакет целиком → создаётся **одна** `Purchase` с `units=500`.

- На бэке: `get_sold_units_map()` возвращает `{product_id: 1}` (одна строка).
- На фронте: `available = product.units - product.sold_units = 500 − 1 = 499`.
- В UI пишется «499 available», хотя фактически пакет куплен целиком.

Баг проявился при первой же проверке seed-данных — см. транскрипт B5.

### 2.3. Бизнес-реальность

Компания IPI AG готова продать суммарно 1 000 000 акций. Эти акции предложены инвесторам через два одновременно активных пакета:

- Продукт A: «Starter» — 100 акций за пакет.
- Продукт B: «Pro» — 5 000 акций за пакет.

В начале доступно: **10 000 Starter'ов ИЛИ 200 Pro**, или любое сочетание (их сумма в пересчёте на акции не должна превысить 1 000 000).

Инвесторы покупают 198 Pro → продано 990 000 акций. Остаётся 10 000 акций в пуле компании. Теперь:
- Pro пакетов доступно: `floor(10 000 / 5 000) = 2`.
- Starter пакетов доступно: `floor(10 000 / 100) = 100`.

Ещё один инвестор покупает 1 Starter → продано 990 100 акций, остаток 9 900:
- Pro пакетов доступно: `floor(9 900 / 5 000) = 1`.
- Starter пакетов доступно: `floor(9 900 / 100) = 99`.

**Ключевой инвариант:** availability продукта A **зависит от покупок продукта B** в рамках одной компании.

### 2.4. Правовой аспект

Юридически все акции одной компании должны стоить одинаково. Продукты НЕ могут иметь разную цену за акцию у одной компании — это фиксируется уже сейчас (`Product.price_per_unit_cents` денормализован из `Company` и каскадом обновляется).

Но стимулировать большие пакеты можно через **gift shares** — дополнительные акции «в подарок», оформленные как отдельная `Purchase` с `legal_basis='gift'` и `paid_cents=0`. Это уже работает через `purchase_config.bonuses` и `GiftProcessor`. Семантика рефакторинга их не меняет.

---

## 3. Правильная модель

### 3.1. CompanyProfile

Добавляется колонка `total_shares_issued: BigInteger` (NOT NULL, эмиссия — общее число акций, которые компания готова продать через платформу).

```python
class CompanyProfile(JSONBMixin, UUIDMixin, TimestampMixin, Base):
    # ... все существующие поля без изменений ...
    price_per_unit_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    total_shares_issued: Mapped[int] = mapped_column(     # NEW
        BigInteger,
        nullable=False,
    )
```

### 3.2. Product

Переименование `units` → `package_size`. Семантика меняется кардинально, но тип и иммутабельность остаются.

```python
class Product(JSONBMixin, UUIDMixin, TimestampMixin, Base):
    # ... все существующие поля без изменений, кроме:
    package_size: Mapped[int] = mapped_column(            # RENAMED from `units`
        Integer,
        nullable=False,
    )
    # package_size = сколько акций в одном пакете этого продукта
    # Immutable after creation (как и раньше).
```

### 3.3. Вычисляемая доступность

Не колонка в БД, а runtime-функция:

```python
# backend/app/modules/purchases/service.py
async def get_available_packages_map(
    session: AsyncSession,
    company_ids: list[UUID],
    product_ids: list[UUID],
) -> dict[UUID, int]:
    """For each product, compute how many packs are still available.

    available_packages[product_id] = floor(
        (company.total_shares_issued
         - SUM(Purchase.units WHERE company_id = product.company_id
                              AND status = 'active'
                              AND legal_basis != 'gift'))
        / product.package_size
    )

    Gift purchases are excluded from the sold count -- they are free
    shares given out of bonuses, not consumption of the issued pool.
    If the company has zero shares remaining, all its products show 0.
    """
```

**Параметры расчёта:**

- В знаменателе — `package_size` конкретного продукта.
- В числителе — остаток по эмиссии **компании** (общий для всех её продуктов).
- `legal_basis != 'gift'` исключает бонусные акции из подсчёта потреблённого пула (bonus shares — это дополнительная эмиссия сверх пула, см. §3.5).

**Возвращает:** `{product_id: available_packages}`. Если компания распродана — `0` для всех её продуктов.

### 3.4. Валидация покупки

В `execute_purchase()` добавляется проверка **перед** списанием денег:

```python
# backend/app/modules/purchases/service.py, inside execute_purchase()
# -- 1.5. Validate share pool has enough --
shares_remaining = await _get_shares_remaining(company.id, session)
if shares_remaining < product.package_size:
    raise BadRequestError(
        f"Company has only {shares_remaining} shares left in issuance, "
        f"package requires {product.package_size}"
    )
```

Вспомогательная функция:

```python
async def _get_shares_remaining(
    company_id: UUID,
    session: AsyncSession,
) -> int:
    """Total shares remaining for a company: issued − consumed."""
    company = await _load_company(company_id, session)
    consumed_stmt = (
        select(func.coalesce(func.sum(Purchase.units), 0))
        .where(
            Purchase.company_id == company_id,
            Purchase.status == PurchaseStatus.ACTIVE,
            Purchase.legal_basis != PurchaseLegalBasis.GIFT,
        )
    )
    consumed = (await session.execute(consumed_stmt)).scalar_one()
    return company.total_shares_issued - int(consumed)
```

### 3.5. Gift shares — семантика

Bonus shares, создаваемые `GiftProcessor`, — это **дополнительные** акции сверх объявленной эмиссии. Они предназначены как стимул, юридически оформлены как подарок, не уменьшают пул:

- `Purchase.legal_basis = 'gift'`, `paid_cents = 0`.
- В подсчёте `shares_remaining` НЕ учитываются.
- `PurchaseProcessor` не создаёт gift-акции; их создаёт `GiftProcessor` на основе `purchase_config.bonuses[]`.
- `total_shares_issued` компании их не лимитирует — теоретически компания может раздать сколь угодно подарочных акций в зависимости от `bonuses` конфигурации продуктов.

Это **правильная** семантика: пул — про продаваемые акции; подарки — отдельный финансовый жест компании без лимита сверху.

### 3.6. Installments

`InstallmentPlan.total_units` денормализован как `product.package_size` на момент создания плана. Переименование поля не ломает снапшоты — `plan_config_snapshot` в JSONB не содержит ключа `units`, только `tranches`, `bonus_units`, `agent_bonus_units`. Плюс `total_units` уже отдельная колонка, заполняется при создании плана.

**Что надо:** в `installments/service.py:create_plan` строка `total_units = product.units` становится `total_units = product.package_size`. Одна точка правки.

**Что не надо:** миграция JSONB-снапшотов. Старые активные планы в БД продолжат работать — они смотрят на свой снапшот, не на актуальное состояние Product.

---

## 4. Миграция (Alembic)

### 4.1. Стратегия — двухшаговая внутри одной ревизии

Колонка `total_shares_issued` появляется как `nullable=True` → data-migration выставляет значения → `ALTER COLUMN ... SET NOT NULL`. Это позволяет обработать существующие записи без server_default-заглушки.

Ревизия: **`0028_share_pool_refactor`** (номер — следующий свободный после последней revision в проекте; проверить `backend/migrations/versions/` перед созданием).

### 4.2. Upgrade

```python
"""share pool refactor -- Sprint 4.3

Revision ID: 0028_share_pool_refactor
Revises: 0027_<previous>
Create Date: 2026-04-XX XX:XX:XX.XXXXXX

Changes:
  - companies: +total_shares_issued (BigInteger, NOT NULL, computed for
    existing rows as SUM(products.units) per company)
  - products: rename column `units` → `package_size`
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0028_share_pool_refactor"
down_revision: Union[str, None] = "0027_<previous>"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -- 1. Add total_shares_issued as nullable --
    op.add_column(
        "company_profiles",
        sa.Column("total_shares_issued", sa.BigInteger(), nullable=True),
    )

    # -- 2. Data migration: compute value for existing rows --
    # For each company, set total_shares_issued to SUM(products.units).
    # This preserves current availability levels at migration time:
    # a company with 3 products (100+500+2000 units) becomes an issuance
    # of 2600 shares, and every existing pack becomes buyable exactly once.
    # Staff will revise these values later via UI (out of scope for this
    # sprint) or via direct DB write on dev server.
    op.execute("""
        UPDATE company_profiles
        SET total_shares_issued = COALESCE(
            (SELECT SUM(units) FROM products WHERE company_id = company_profiles.id),
            0
        )
    """)

    # -- 3. Lock column as NOT NULL --
    op.alter_column(
        "company_profiles",
        "total_shares_issued",
        nullable=False,
    )

    # -- 4. Rename products.units → products.package_size --
    op.alter_column(
        "products",
        "units",
        new_column_name="package_size",
    )


def downgrade() -> None:
    op.alter_column(
        "products",
        "package_size",
        new_column_name="units",
    )
    op.drop_column("company_profiles", "total_shares_issued")
```

### 4.3. Миграционный контракт

- **Data integrity:** после миграции для каждой существующей компании `total_shares_issued >= SUM(active Purchase.units for this company)`. Условие вытекает из формулы: если до миграции продукты продавались, `SUM(products.units) >= SUM(purchases.units)` не гарантировано формально, но на практике — инвенторь продуктов подстраивался через стафа в админке. Для dev-сервера (единственное место где есть purchase-данные) условие выполняется.
- **Idempotent:** повторный `alembic upgrade head` — no-op.
- **Reversible:** `downgrade()` корректен для отката, но теряет information (колонка `total_shares_issued` удаляется).
- **Нулевой даунтайм:** миграция INSERT-only по данным, не блокирует reads. `ALTER COLUMN RENAME` в Postgres — O(1) metadata-операция.

### 4.4. Production readiness (позже, не этот sprint)

- Перед production-миграцией — запустить проверочный SELECT: `SELECT company_id, SUM(units) FROM products GROUP BY company_id` → сравнить с ожидаемой эмиссией от бизнеса. Если расходится — staff-доводка через API.
- Добавить staff-endpoint `PATCH /api/v1/staff/companies/{id}/shares-issued` для ручной корректировки. **Out of scope для этого спринта** (dev-сервер достаточно).

---

## 5. Backend changes — полный чек-лист

### 5.1. Модели и схемы

| Файл | Правка |
|------|--------|
| `app/modules/companies/models.py` | `CompanyProfile`: +`total_shares_issued: Mapped[int] = mapped_column(BigInteger, nullable=False)`. Обновить docstring класса. |
| `app/modules/companies/schemas.py` | `CompanyResponse`, `CompanyDetailResponse`: +`total_shares_issued: int`. `CreateCompanyRequest`: +`total_shares_issued: int = Field(gt=0)`. `UpdateCompanyRequest`: +`total_shares_issued: int \| None = None`. `PublicCompanyResponse`, `PublicCompanyDetailResponse`: +`total_shares_issued: int` (публичная информация — сколько всего акций компания выпустила; НЕ `shares_remaining`, чтобы не раскрывать динамику продаж инвесторам раньше staff). Либо оставить только staff-view — решается в ходе ревью, рекомендация: **публично показывать** как social-proof «emisson: 1M». |
| `app/modules/products/models.py` | `Product`: `units` → `package_size`. Обновить docstring класса. |
| `app/modules/products/schemas.py` | `ProductResponse`, `PublicProductResponse`: `units` → `package_size`. **`sold_units` → `available_packages`** (семантика меняется, имя тоже, чтоб избежать confusion). `CreateProductRequest`: `units` → `package_size`. |

### 5.2. Сервисы и роутеры

| Файл | Правка |
|------|--------|
| `app/modules/companies/service.py` | `create_company()`: принимать `total_shares_issued`, записывать в модель. `update_company()`: обработать `total_shares_issued` в `body.model_dump(exclude_unset=True)`. Audit event `company.shares_issued_updated` при изменении. |
| `app/modules/products/service.py` | `create_product()`: параметр `units` → `package_size`. `cascade_price()` без изменений (не трогает `package_size`). Audit event `product.created` — `data={"package_size": ...}` вместо `"units"`. |
| `app/modules/products/constants.py` | `validate_plan_config()` принимает `product_units` → `product_package_size`. Инварианты остаются те же, просто переменная переименована. Все места использования обновить. |
| `app/modules/purchases/service.py` | **`get_sold_units_map()` → `get_available_packages_map()`**. Полная переписка по формуле из §3.3. `execute_purchase()`: добавить валидацию §3.4 сразу после загрузки product/company. `amount_cents = product.package_size * product.price_per_unit_cents` (одна строка переименования). +функция `_get_shares_remaining()` (приватная). |
| `app/modules/purchases/router.py` | В `list_products_endpoint` и `get_product_detail_endpoint`: вместо `get_sold_units_map()` вызвать `get_available_packages_map()`, заполнять `resp.available_packages`. Убрать `resp.sold_units = ...`. |
| `app/modules/processors/base.py` | `PurchaseContext.units` — комментарий обновить: `product.units` → `product.package_size`. Имя поля в dataclass оставить `units` (это **купленные акции** в данном покупочном контексте, не `package_size` продукта). |
| `app/modules/installments/service.py` | `create_plan()`: `total_units = product.units` → `total_units = product.package_size`. В остальных местах `plan.total_units` не трогать — это снапшот. |

### 5.3. Миграция

- Создать `backend/migrations/versions/0028_share_pool_refactor.py` по шаблону §4.2.

### 5.4. Тесты

Backend тесты, которые ссылаются на `Product.units` или `sold_units` — нужно обновить. Ниже — исчерпывающий список.

#### 5.4.1. `tests/test_products.py`

| Тест | Правка |
|------|--------|
| `_create_product()` helper | `"units": units` → `"package_size": units` в JSON body. |
| `_create_company()` helper | +`"total_shares_issued": 10_000_000` (или запас под все тесты) в CreateCompanyRequest. |
| `test_create_product` | `assert product["units"] == 100` → `assert product["package_size"] == 100`. |
| `test_public_list_active_only` | Проверяет `PublicProductResponse` — поле `sold_units` → `available_packages`. Значение: `10_000_000 / 100 = 100000`. Либо переписать assertion на `>= 0`. |
| `test_price_cascade_deletes_installments` | Без изменений, не трогает `units`/`sold_units`. |
| Новый тест `test_create_company_requires_total_shares_issued` | POST без `total_shares_issued` → 422. |
| Новый тест `test_product_available_packages_decreases_on_purchase` | Создать company (issuance=1000), product (package_size=100). Проверить `GET /products` → `available_packages=10`. Купить один пакет. Снова `GET /products` → `available_packages=9`. |
| Новый тест `test_purchase_fails_when_company_exhausted` | issuance=100, package_size=200 → `execute_purchase` кидает BadRequestError. |

#### 5.4.2. `tests/test_purchases.py`

| Тест | Правка |
|------|--------|
| `_make_context()` helper | Комментарий: `units = product.package_size`. Значение параметра не меняется. |
| `_create_product()` helper | Как в `test_products.py`. |
| `_create_company()` helper | Как в `test_products.py`. |
| `test_purchase_instant_buy` | `data[0]["units"] == product["units"]` → `data[0]["units"] == product["package_size"]`. `paid_cents == product["units"] * ...` → `paid_cents == product["package_size"] * ...`. |
| Все тесты `test_purchase_*` и `test_gift_*` | Автоматически проходят, если `_create_company()` / `_create_product()` хелперы правильны. |

#### 5.4.3. `tests/test_installments.py`

| Тест | Правка |
|------|--------|
| Все тесты где создаётся product | Хелперы обновить (см. выше). |
| `test_create_plan_snapshots_units` | Проверка что `plan.total_units == product.package_size`. |

#### 5.4.4. `tests/test_dashboard.py`, `tests/test_companies.py`

Косметические правки: `units` → `package_size` в test body, проверка `total_shares_issued` в Company responses.

### 5.5. Seed script

`backend/scripts/seed_storefront.py` — уже в /outputs/b5_backend. Правки:

| Место | Правка |
|-------|--------|
| `COMPANIES` list | Каждая компания: +`"total_shares_issued": N`. Разумные значения: IPI AG — 10_000_000, Immo-Pro-Invest — 5_000_000, CBS Home — 100_000, Nordic — 50_000, Tesla — 2_000_000, Stealth — 100. |
| `PRODUCTS` list | Ключ `"units"` → `"package_size"`. Значения НЕ меняются. |
| `_ensure_company()` функция | При создании `CompanyProfile` — добавить `total_shares_issued=spec["total_shares_issued"]`. |
| `_ensure_product()` функция | `units=spec["units"]` → `package_size=spec["package_size"]`. |

Проверить итог: для каждой компании `SUM(product.package_size)` меньше `total_shares_issued` с запасом (чтоб availability не была 1-2 пакета сразу после сида).

### 5.6. Audit / documentation

| Файл | Правка |
|------|--------|
| `CBSHOME-Backend.md` | Добавить Sprint 4.3 в Phase 4 раздел (уже сделано в patch этого батча). Обновить модель `CompanyProfile` / `Product` в описаниях. |
| `CBSHOME-Financial-System.md` | Где упоминается `Product.units` — переименовать в `Product.package_size`. Добавить упоминание `Company.total_shares_issued`. |
| Новые audit events | `company.shares_issued_updated` (при изменении total_shares_issued staff-endpoint'ом). Регистрировать в Sprint 4.3 summary. |

---

## 6. Frontend changes — полный чек-лист

Переименование двух полей в API + текстов. Всё — в рамках `TD-F07` (не отдельный спринт).

### 6.1. Types

**Файл:** `frontend/src/api/types.ts`

```typescript
// BEFORE
export interface PublicProductResponse {
  id: string
  company_id: string
  name: string
  description: string | null
  units: number                    // package size
  price_per_unit_cents: number
  sold_units: number               // COUNT(Purchase) -- broken
  company_name: string
  logo_url: string | null
  cover_url: string | null
  currency?: string
}

// AFTER
export interface PublicProductResponse {
  id: string
  company_id: string
  name: string
  description: string | null
  package_size: number             // RENAMED from `units`
  price_per_unit_cents: number
  available_packages: number       // RENAMED + semantics fixed
  company_name: string
  logo_url: string | null
  cover_url: string | null
  currency?: string
}

// PublicCompanyResponse: +total_shares_issued
export interface PublicCompanyResponse {
  // ... existing fields ...
  total_shares_issued: number      // NEW: эмиссия компании
}
```

TypeScript тут же укажет все сломанные места через type-error.

### 6.2. Utils / helpers

**Файл:** `frontend/src/utils/format.ts`

Проверить — есть ли там функции форматирования availability. Судя по прошлому F4, вероятно нет (availability считался инлайн в компонентах). Если появится нужда — добавить:

```typescript
export function formatPacksAvailable(count: number, locale: string): string {
  return formatNumber(count, locale)
}
```

### 6.3. Components

**Файл:** `frontend/src/components/shared/ProductCard.vue`

```vue
<!-- BEFORE -->
<script setup lang="ts">
const available = computed(() => props.product.units - props.product.sold_units)
</script>

<template>
  <span>{{ available }} {{ t('inv.market.available') }}</span>
</template>

<!-- AFTER -->
<script setup lang="ts">
// available_packages приходит уже вычисленным с бэка
</script>

<template>
  <span>
    {{ product.available_packages }} {{ t('inv.market.packsAvailable') }}
  </span>
</template>
```

**Файл:** `frontend/src/views/investor/ProductDetailView.vue`

```vue
<!-- BEFORE -->
<CStat>
  <template #label>{{ t('inv.product.availability') }}</template>
  <template #value>{{ product.units - product.sold_units }}</template>
  <template #hint>{{ t('inv.market.available') }}</template>
</CStat>
<CButton :disabled="product.units - product.sold_units === 0">
  {{ t('inv.product.buy') }}
</CButton>

<!-- AFTER -->
<CStat>
  <template #label>{{ t('inv.product.packsAvailability') }}</template>
  <template #value>{{ product.available_packages }}</template>
  <template #hint>{{ t('inv.market.packsAvailable') }}</template>
</CStat>
<CButton :disabled="product.available_packages === 0">
  {{ product.available_packages > 0 ? t('inv.product.buy') : t('inv.product.soldOut') }}
</CButton>
```

### 6.4. Stores

**Файл:** `frontend/src/stores/products.ts`

Проверить — store может просто передавать API-ответ, без трансформаций. Если есть маппинг (`const mapped = raw.map(...)`) — убедиться что передаются новые имена полей. Прозрачная правка при правильном типе `PublicProductResponse`.

### 6.5. i18n locales

**Файлы:** `frontend/src/i18n/locales/{en,ru,de,ar}.json`

Добавить ключ в раздел `inv.market`:

```json
// en.json
{
  "inv": {
    "market": {
      "packsAvailable": "packs available"
    },
    "product": {
      "packsAvailability": "PACKS AVAILABLE",
      "soldOut": "Sold out"
    }
  }
}
```

```json
// ru.json
{
  "inv": {
    "market": {
      "packsAvailable": "пакетов доступно"
    },
    "product": {
      "packsAvailability": "ДОСТУПНО ПАКЕТОВ",
      "soldOut": "Распродано"
    }
  }
}
```

```json
// de.json
{
  "inv": {
    "market": {
      "packsAvailable": "Pakete verfügbar"
    },
    "product": {
      "packsAvailability": "PAKETE VERFÜGBAR",
      "soldOut": "Ausverkauft"
    }
  }
}
```

```json
// ar.json
{
  "inv": {
    "market": {
      "packsAvailable": "حزمة متاحة"
    },
    "product": {
      "packsAvailability": "حزم متاحة",
      "soldOut": "نفذ"
    }
  }
}
```

Старый ключ `inv.market.available` — проверить grep'ом `rg "inv.market.available" frontend/src`. Если нигде не используется — удалить. Если используется где-то ещё (агент-шелл? компани-шелл?) — оставить пока.

### 6.6. Company profile display

Если где-то показывается `PublicCompanyResponse` (в F4.1 это `CompanyFilterSheet`) — решить, показывать ли там `total_shares_issued`. Рекомендация: нет, это детальная информация для компани-экрана (F5), не для фильтра.

---

## 7. Порядок выкатки

### 7.1. Последовательность commits

1. **Backend batch (Sprint 4.3):**
   a. Миграция `0028_share_pool_refactor.py`.
   b. Models (Company + Product).
   c. Schemas (Company + Product + Public*).
   d. Services (Company + Product + Purchase + Installment).
   e. Routers (public product router, staff company router).
   f. Processors (validators).
   g. Tests (`test_products.py`, `test_purchases.py`, `test_installments.py`).
   h. Seed script (`seed_storefront.py`).
   i. Документация: `CBSHOME-Backend.md` обновить раздел моделей Phase 4.

   **Merge criterion:** все существующие backend тесты зелёные (340+ тестов). +новые тесты share-pool.

2. **Frontend batch (TD-F07, сразу после backend merge):**
   a. `api/types.ts` — переименование.
   b. `utils/format.ts` — если что-то добавляется.
   c. `components/shared/ProductCard.vue`.
   d. `views/investor/ProductDetailView.vue`.
   e. `stores/products.ts` — проверка.
   f. `i18n/locales/*.json` — 4 файла.

   **Merge criterion:** `npm run typecheck` без ошибок, ручная проверка на dev-сервере: витрина показывает «packs available», правильные числа по seed-данным.

3. **Seed re-run:**
   ```bash
   docker compose exec app python scripts/seed_storefront.py --reset
   ```
   Проверить: все 18 видимых продуктов показывают реалистичные числа. Для IPI AG Starter (package_size=100, company issuance=10_000_000): `available_packages=100_000`.

### 7.2. Breaking API contract

Между backend merge и frontend merge — контракт сломан (фронт ожидает `units`, бэк отдаёт `package_size`). На dev-сервере это приемлемо. Если потребуется — можно временно оставить оба поля в response с одним значением, выпилить старое после фронт-merge. Для нашего случая — нет необходимости.

### 7.3. Rollback plan

- Если обнаружится bug на стадии smoke-test: `alembic downgrade -1` → revert backend commit → revert frontend commit → сид перезапустить.
- Данные не теряются: `total_shares_issued` колонка снимается, данные в БД переживут rollback только через `pg_dump` перед миграцией (которое рекомендуется делать всегда на dev).

---

## 8. Acceptance criteria

Для закрытия TD-071 / Sprint 4.3 / TD-F07 должны выполняться:

### Backend

- [ ] Миграция `0028_share_pool_refactor` применена, БД консистентна: каждая компания имеет `total_shares_issued > 0`.
- [ ] `products.units` переименована в `products.package_size` на уровне БД.
- [ ] `get_sold_units_map` удалена, `get_available_packages_map` работает.
- [ ] `execute_purchase` отклоняет покупку при исчерпании пула с `BadRequestError`.
- [ ] `PublicProductResponse` возвращает `package_size` и `available_packages`.
- [ ] `PublicCompanyResponse` возвращает `total_shares_issued`.
- [ ] Все существующие backend тесты зелёные.
- [ ] Новые тесты (`test_product_available_packages_decreases_on_purchase`, `test_purchase_fails_when_company_exhausted`) зелёные.

### Frontend

- [ ] `api/types.ts` содержит `package_size` и `available_packages` вместо `units` и `sold_units`.
- [ ] `ProductCard.vue` и `ProductDetailView.vue` используют `product.available_packages`.
- [ ] Новые i18n ключи `inv.market.packsAvailable`, `inv.product.packsAvailability`, `inv.product.soldOut` присутствуют во всех 4 локалях.
- [ ] `npm run typecheck` — без ошибок.
- [ ] Ручная проверка: купить один пакет на dev-сервере → в витрине availability уменьшается **у всех продуктов той же компании** с соответствующим пересчётом.

### Data / seed

- [ ] `docker compose exec app python scripts/seed_storefront.py --reset` — зелёный.
- [ ] В UI после сида: «IPI AG Starter» показывает `100_000 packs available` (если issuance=10M, package_size=100).
- [ ] В UI «IPI AG Whale» (package_size=10_000) показывает `1_000 packs available` у той же компании — **те же 10M акций, разная гранулярность**.

---

## 9. Edge cases и риски

### 9.1. Edge case: `total_shares_issued` = 0

Нулевая эмиссия → все продукты компании показывают `available_packages=0`, витрина их прячет. Покупка кидает `BadRequestError`. Корректное поведение.

**Risk:** если staff случайно выставит 0 — компания пропадёт с витрины. Mitigation: валидация на staff-endpoint `PATCH /staff/companies/{id}` — `total_shares_issued > 0` (плюс `>= SUM(active purchases)`, чтобы не «раскулачить» уже проданные акции).

### 9.2. Edge case: `package_size` > `total_shares_issued`

Создан продукт с пакетом больше чем вся эмиссия. `available_packages = 0` с самого начала — никто не купит.

**Risk:** бизнес-ошибка при создании. Mitigation: валидация в `create_product()` — `package_size <= company.total_shares_issued`.

### 9.3. Edge case: одновременные покупки разных продуктов одной компании

Два инвестора одновременно кликают Buy на разных продуктах одной компании. Какой-то из них может «съесть» последние акции. Второй получит `BadRequestError`.

**Текущая защита:** advisory lock в `engine.execute()` берётся на `investor_id`, не на `company_id`. Двум разным инвесторам блокировка не мешает делать покупки параллельно.

**Risk:** race condition — оба прошли pre-check «есть 500 акций», но суммарно они покупают 700 → последний в транзакции получит constraint failure.

**Mitigation:** добавить advisory lock на `company_id` в `execute_purchase` перед `_get_shares_remaining()` проверкой. Это сериализует покупки у одной компании, но позволяет параллельные покупки разных компаний. Добавить в §5.2 как TODO-note.

### 9.4. Edge case: gift shares потенциально могут создать «отрицательный» inventory если их считать в consumed

Разобрано в §3.5: `legal_basis != 'gift'` в WHERE фильтре. Gift shares НЕ расходуют пул. Consistent с бизнес-логикой.

### 9.5. Risk: тесты с hardcoded `units=100` в JSON body

Тесты могут забыть обновить — pydantic validation на стороне API кинет 422. Mitigation: сквозной grep + code review.

### 9.6. Risk: snapshots в installment plans не трогаются

`InstallmentPlan.total_units` — снапшот, колонка в БД. `plan_config_snapshot` — JSONB, не содержит ключа `units`. После миграции активные планы продолжают работать по снапшотам. Новые планы создаются из `product.package_size`. Проверено: нет breakage.

---

## 10. Out of scope

Не входит в Sprint 4.3, откладывается:

- Staff UI для редактирования `total_shares_issued` (админка в Phase F3 этого не поддерживает — нужен новый endpoint + UI).
- Проверка в `execute_purchase` с advisory lock на `company_id` — добавить в TD после merge, чтобы не раздувать спринт.
- Показ `shares_remaining` (динамический, не `total_shares_issued`) на публичной company detail странице — UX-решение, согласовывается в Phase F5.
- Analytics для компании: сколько % эмиссии продано, динамика продаж — Phase F5.2 CompanyAnalyticsView.
- Partial-pack покупки («купить 50 акций из пакета 100») — архитектурно сложно, не MVP.

---

## 11. Changelog

- **v1.0 (2026-04-17):** первая версия. Создан после обсуждения в ходе B5 (seed script) — см. транскрипт.

---

**Конец документа**
