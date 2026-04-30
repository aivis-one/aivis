# Sprint 4.3 Impact Analysis Report

Generated: 2026-04-30
Repository: cbshome @ 31b5e28f671c3a98c5762de942b68ea981427a74
Spec: CBSHOME-Share-Pool-Refactor.md v2.0 (file in repo is v1.0 — owner to update)

> **Revision notes (v2):** corrected OptionPool field set, CompanyProfile field placement,
> removed `consumed` column, `is_active→status`, fixed gift semantics, added
> `products/router.py` to Files to Modify.

---

## Summary

- Total backend files affected: 9 (source) + 1 script
- Total frontend files affected: 5
- Total test files affected: 6
- New files to create: 11
- Latest migration: 0026 (`2026_04_17_0026_products_cover_url`)
- Next migration: **0027** (spec file says 0028 — that is a typo; actual latest is 0026)

---

## Backend: Files to Modify

### `backend/app/modules/products/models.py`
- Line 6: `# Investment package belonging to a Company. Contains units (package` — update docstring to reflect rename to `package_size`
- Line 75: `units: Mapped[int] = mapped_column(` — rename to `package_size`; add `pool_id: Mapped[uuid | None] = mapped_column(ForeignKey("option_pools.id"), nullable=True)` FK column
- Line 114: `f"units={self.units} status={self.status}>"` — update `__repr__` to `package_size=self.package_size`

### `backend/app/modules/products/schemas.py`
- Line 40: `units: int = Field(gt=0)` — rename to `package_size: int = Field(gt=0)` in `CreateProductRequest`
- Line 49: docstring `units and company_id are immutable` — update to `package_size and company_id are immutable`
- Line 112: `units: int` — rename to `package_size: int` in `StaffProductResponse`
- Line 150: `units: int` — rename to `package_size: int` in `PublicProductResponse`
- Line 153: `sold_units: int = 0` — rename to `available_packages: int = 0`; semantics change from COUNT(Purchase) per product to floor(pool_remaining / package_size) across whole company

### `backend/app/modules/products/router.py`  ← **was missing from v1 report**
- Line 53: `from app.modules.purchases.service import get_sold_units_map` — change import to `get_available_packages_map`
- Line 77–79: `sold_map = await get_sold_units_map(session, product_ids)` — replace with `available_map = await get_available_packages_map(session, company_ids, product_ids)`; note `company_ids` is already collected on line 83 but must now be computed **before** this call, not after
- Line 96: `resp.sold_units = sold_map.get(p.id, 0)` — rename to `resp.available_packages = available_map.get(p.id, 0)`
- Line 137: `sold_map = await get_sold_units_map(session, [product.id])` — replace with `available_map = await get_available_packages_map(session, [product.company_id], [product.id])`
- Line 155: `response.sold_units = sold_map.get(product.id, 0)` — rename to `response.available_packages = available_map.get(product.id, 0)`

### `backend/app/modules/products/staff_router.py`
- Line 90: `body.units,` — update to `body.package_size,` (argument passed to `create_product`)

### `backend/app/modules/products/service.py`
- Line 72: `units: int,` — rename parameter to `package_size: int`
- Line 99: `units=units,` — rename kwarg to `package_size=package_size`
- Line 120: `"units": units,` — rename key to `"package_size": package_size` in the audit/log dict
- Line 347: `product_units=product.units,` — rename to `product_units=product.package_size,` (call to `validate_plan_config`)
- Line 403: `product_units=product.units,` — rename to `product_units=product.package_size,`

### `backend/app/modules/products/constants.py`
- Line 22: comment `sum(amount_cents) == product.units * company.price_per_unit_cents` — update to `product.package_size`
- Line 52: `product_units: int,` — parameter name stays (internal value); comment on line 69 `product_units: Product.units (package size)` — update to `Product.package_size`
- Line 115: comment `sum(amount_cents) == product.units * price_per_unit_cents` — update
- Lines 132–143: all comments referencing `product_units == product.units` — update to `Product.package_size`

### `backend/app/modules/purchases/service.py`
- Line 320: `amount_cents = product.units * product.price_per_unit_cents` — rename to `product.package_size`
- Line 329: `units=product.units,` — rename to `units=product.package_size,` (populates `PurchaseContext.units` which is NOT renamed)
- **New function** `get_available_packages_map(session, company_ids, product_ids)` — replaces `get_sold_units_map`; formula: `floor((company.total_supply - SUM(Purchase.units WHERE company_id=... AND status='active')) / product.package_size)`; gift purchases **are included** in consumed count (v2.0 decision)
- **New function** `_get_shares_remaining(company_id, session)` — internal helper; SUM excludes nothing (all active purchases count against the pool)
- **`execute_purchase()`** — add pool availability validation immediately after `_load_company` and before `PurchaseContext` construction; raise `BadRequestError` if `shares_remaining < product.package_size`

### `backend/app/modules/installments/service.py`
- Line 150: `total_units = product.units` — rename to `total_units = product.package_size`

### `backend/app/modules/processors/base.py`
- Line 81: `units: int  # product.units` — update comment to `# product.package_size`

---

## Backend: New Files to Create

- `app/modules/pools/__init__.py`
- `app/modules/pools/models.py` — `OptionPool` model: `id`, `company_id` FK → `company_profiles.id`, `equity_percent: Numeric`, `total_options: BigInteger`, `status: String(20)` (values: `'active'` / `'archived'`), timestamps. **No `consumed` column** — availability is computed dynamically via SUM(Purchase.units).
- `app/modules/pools/schemas.py` — `CreatePoolRequest`, `UpdatePoolRequest`, `PoolResponse`
- `app/modules/pools/service.py` — Pool CRUD: create, get active, archive; enforce one-active-per-company constraint
- `app/modules/pools/router.py` — Staff Pool endpoints: `POST /staff/companies/{id}/pool`, `PATCH /staff/companies/{id}/pool`
- `app/modules/company_dashboard/__init__.py`
- `app/modules/company_dashboard/router.py` — Company-facing dashboard endpoints
- `app/modules/company_dashboard/service.py` — Company dashboard data queries
- `app/modules/company_dashboard/schemas.py` — Company dashboard response schemas
- `app/modules/companies/dependencies.py` — `get_current_company_profile()` FastAPI dependency
- `backend/migrations/versions/2026_04_30_0027_share_pool_refactor.py` — next after 0026

---

## Frontend: Files to Modify

### `frontend/src/api/types.ts`
- Line 388: `units: number` — rename to `package_size: number` in `PublicProductResponse`
- Line 391: `sold_units: number` — rename to `available_packages: number`; semantics change (now pre-computed by backend, no frontend subtraction needed)
- Add `pool_id: string | null` to `PublicProductResponse` (new FK field)
- `PublicCompanyResponse` / `PublicCompanyDetailResponse`: add `total_supply: number`, `shares_per_option: number`

### `frontend/src/components/shared/ProductCard.vue`
- Line 45: `() => props.product.units - props.product.sold_units,` — replace entire computed with `props.product.available_packages` (no subtraction; value pre-computed on backend)
- Line 73: `<span class="product-card__units">` — update class name and/or label text to reflect `packsAvailable` i18n key

### `frontend/src/views/investor/ProductDetailView.vue`
- Line 90: `return p ? p.units - p.sold_units : 0` — replace with `return p ? p.available_packages : 0`
- `<CButton :disabled="...">` guard — update condition from `p.units - p.sold_units === 0` to `p.available_packages === 0`

### `frontend/src/views/investor/PurchaseView.vue`
- Line 89: `return p ? p.units * p.price_per_unit_cents : 0` — rename `.units` to `.package_size`
- Line 94: `return p ? Math.max(p.units - p.sold_units, 0) : 0` — replace with `return p ? p.available_packages : 0`
- Line 277: `{{ formatNumber(product.units, locale) }}` — rename `.units` to `.package_size`

### `frontend/src/views/investor/InstallmentView.vue`
- Line 180: `return getTrancheUnits(planConfig.value, product.value.units, index)` — rename `product.value.units` to `product.value.package_size`

---

## Frontend: New Files to Create

- `frontend/scripts/generate_ts_types.py` — script to auto-generate TS types from backend OpenAPI schema
- `frontend/src/api/generated.ts` — auto-generated types output

---

## Tests: Files to Modify

### `backend/tests/test_products.py`
- Line 111: `units: int = 100,` — rename helper param to `package_size: int = 100`
- Line 120: `"units": units,` — rename to `"package_size": package_size`
- `_create_company()` helper — add `"total_supply": 10_000_000` to request body
- Line 169: `assert product["units"] == 100` — rename to `product["package_size"]`
- Line 224: `"units": 50,` — rename to `"package_size": 50`
- Line 563: `assert body["sold_units"] == 0` — rename to `body["available_packages"]`

### `backend/tests/test_purchases.py`
- Line 113: `"units": units,` — rename to `"package_size": units` in `_create_product` helper
- `_create_company()` helper — add `"total_supply": 10_000_000`
- Line 427: `assert data[0]["units"] == product["units"]` — right-hand `product["units"]` → `product["package_size"]`; left-hand `data[0]["units"]` is `Purchase.units` — NOT renamed
- Line 428: `assert data[0]["paid_cents"] == product["units"] * ...` — rename `product["units"]` to `product["package_size"]`
- Line 577: `assert sale["units"] == 100` — `Purchase.units`, stays
- Line 579: `assert gift["units"] == 10` — `Purchase.units`, stays

### `backend/tests/test_installments.py`
- Line 146: `"units": units,` — rename to `"package_size": units` in `_create_product` helper
- `_create_company()` helper — add `"total_supply"` field

### `backend/tests/test_dashboard.py`
- Line 108: `"units": units,` — rename to `"package_size": units`
- Line 436: `assert p["units"] == 50` — verify context: if `p` is a Purchase row, this stays; if it is a product dict, rename to `package_size`

### `backend/tests/test_leaderboard.py`
- Line 214: `"units": 100` — rename to `"package_size": 100`

### `backend/tests/test_referrals.py`
- Line 132: `"units": 10,` — rename to `"package_size": 10`

---

## Tests: New Test Cases Needed

- `test_pools.py` — Pool CRUD (create, read, archive), one-active-per-company constraint, archive attempt with remaining active purchases
- `test_products.py` — `test_available_packages_decreases_on_purchase` (buy one → available_packages drops across all company products), `test_purchase_fails_when_pool_exhausted` (total_supply=100, package_size=200 → 409/400)
- `test_purchases.py` — `test_gift_consumes_pool` (gift purchase IS deducted from pool remaining; v2.0 decision), `test_pool_exhausted_blocks_sale`
- `test_installment_calculator.py` — `POST /staff/products/{id}/installments/preview` roundtrip, tranche invariants
- `test_company_dashboard.py` — company dashboard endpoints: auth, data shape, pool remaining

---

## Migration Notes

- Previous migration: `2026_04_17_0026_products_cover_url`
- `down_revision`: `"0025_documents_language"`
- New file: `backend/migrations/versions/2026_04_30_0027_share_pool_refactor.py`
- `revision`: `"0027_share_pool_refactor"`
- `down_revision`: `"0026_products_cover_url"`
- **Spec file says revision 0028 — that is incorrect; actual next free number is 0027.**
- New tables:
  - `option_pools` (`id UUID PK`, `company_id UUID FK→company_profiles.id`, `equity_percent NUMERIC`, `total_options BIGINT`, `status VARCHAR(20) DEFAULT 'active'`, `created_at`, `updated_at`)
  - **No `consumed` column.** Pool consumption is always `SUM(Purchase.units WHERE company_id=... AND status='active')`.
- Altered tables:
  - `company_profiles`: add `total_supply BIGINT NOT NULL` (two-step: nullable → data-migration → NOT NULL), add `shares_per_option INTEGER NOT NULL`
  - `products`: rename column `units` → `package_size`, add `pool_id UUID NULL FK→option_pools.id`
- New index: `uq_one_active_pool_per_company` — partial unique index on `option_pools(company_id)` WHERE `status = 'active'`
- Data migration for `company_profiles.total_supply`: `UPDATE company_profiles SET total_supply = COALESCE((SELECT SUM(package_size) FROM products WHERE company_id = company_profiles.id), 0)`

---

## Seed Script Changes (`backend/scripts/seed_storefront.py`)

- Lines 234–445: rename all `"units": <value>` keys in the `PRODUCTS` list to `"package_size": <value>` (values unchanged)
- Add `"total_supply"` and `"shares_per_option"` to each entry in the `COMPANIES` list (e.g. IPI AG → `total_supply=10_000_000`, Immo-Pro-Invest → `5_000_000`, CBS Home → `100_000`, Nordic → `50_000`, Tesla → `2_000_000`, Stealth → `100`)
- `_ensure_company()`: pass `total_supply=spec["total_supply"]`, `shares_per_option=spec["shares_per_option"]` to `CompanyProfile` constructor
- `_ensure_product()`: `units=spec["units"]` → `package_size=spec["package_size"]`; also pass `pool_id` once active pool is seeded
- Add pool seeding: after each company is created/ensured, upsert one `OptionPool` with `status='active'`; set `equity_percent` and `total_options` to spec values

---

## Risk Areas

- **`backend/app/modules/products/router.py`** — two separate call sites for `get_sold_units_map` (list endpoint line 79, detail endpoint line 137). The new `get_available_packages_map` signature takes `company_ids` as well as `product_ids`. In the list endpoint `company_ids` is already collected on line 83, but it must be moved **before** the map call. In the detail endpoint a single-element list `[product.company_id]` suffices.
- **`backend/app/modules/products/constants.py`** — `validate_plan_config()` receives `product_units` as a parameter name; all three locations (function definition + two call sites in `service.py`) must change atomically.
- **`backend/app/modules/processors/base.py:81`** — `PurchaseContext.units` field shares the word "units" with the renamed `Product.units`. Only the comment changes; the field itself is `Purchase.units` semantics — do NOT rename.
- **`backend/tests/test_purchases.py:427`** — mixed assertion: left-hand `data[0]["units"]` is `Purchase.units` (stays), right-hand `product["units"]` becomes `product["package_size"]`. Risk of renaming both sides by accident.
- **`backend/tests/test_dashboard.py:436`** — `p["units"]` context is ambiguous without surrounding fixture; verify whether `p` is a Purchase row or a product dict before deciding.
- **Gift purchases consume pool (v2.0)** — `_get_shares_remaining()` and `get_available_packages_map()` must NOT filter out `legal_basis='gift'` from the SUM. The v1.0 spec excluded gifts; v2.0 reverses this. All WHERE clauses and any comments referencing gift exclusion must be updated accordingly. The spec file on disk (v1.0) still says the opposite — do not follow it.
- **Pool enforcement insertion point** — `execute_purchase()` in `purchases/service.py` calls `_load_product` then `_load_company` before building `PurchaseContext`. Pool validation and the consumed-SUM query must be inserted between those calls and `PurchaseContext` construction, inside the same DB transaction. Consider a `SELECT ... FOR UPDATE` on the company_profiles row to serialise concurrent purchases from the same company (race condition: two investors both pass pre-check, collectively over-consume pool).
- **`frontend/src/views/investor/InstallmentView.vue:180`** — `getTrancheUnits` receives `product.value.units`; if `frontend/src/utils/installmentPlans.ts` has its own tests, those fixtures also need updating.
- **`pool_id` FK on Product is nullable at creation** — `Product.pool_id` is nullable (existing products have no pool). Consider validation in `create_product()` to require an active pool exists for the company before allowing product creation. Decided in Sprint 4.3 or deferred? Clarify before implementation.
