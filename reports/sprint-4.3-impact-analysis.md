# Sprint 4.3 Impact Analysis Report

Generated: 2026-04-30
Repository: cbshome @ 31b5e28f671c3a98c5762de942b68ea981427a74

## Summary

- Total backend files affected: 8 (source) + 1 script
- Total frontend files affected: 5
- Total test files affected: 6
- New files to create: 11
- Latest migration: 0026_products_cover_url

---

## Backend: Files to Modify

### `backend/app/modules/products/models.py`
- Line 6: `# Investment package belonging to a Company. Contains units (package` — update docstring to reflect rename to `package_size`
- Line 75: `units: Mapped[int] = mapped_column(` — rename column/attribute to `package_size`; add `pool_id: Mapped[uuid | None]` FK column pointing to `option_pools.id`
- Line 114: `f"units={self.units} status={self.status}>"` — update `__repr__` string to `package_size=`

### `backend/app/modules/products/schemas.py`
- Line 40: `units: int = Field(gt=0)` — rename to `package_size: int = Field(gt=0)` in `CreateProductRequest`
- Line 49: docstring `units and company_id are immutable` — update to `package_size and company_id are immutable`
- Line 112: `units: int` — rename to `package_size: int` in `StaffProductResponse`
- Line 150: `units: int` — rename to `package_size: int` in `PublicProductResponse`
- Line 153: `sold_units: int = 0  # Populated by router from Purchase count (TD-031)` — field name stays; verify `sold_units` computation logic now uses pool-based availability instead of raw `package_size - sold_units`

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
- Line 52: `product_units: int,` — parameter name unchanged (internal, refers to the value); comment on line 69 `product_units: Product.units (package size)` — update to `Product.package_size`
- Line 115: comment `sum(amount_cents) == product.units * price_per_unit_cents` — update
- Lines 132–143: all comments referencing `product_units == product.units` — update references to `Product.package_size` in comments

### `backend/app/modules/purchases/service.py`
- Line 320: `amount_cents = product.units * product.price_per_unit_cents` — rename to `product.package_size`
- Line 329: `units=product.units,` — rename to `units=product.package_size,` (this is populating `PurchaseContext.units`, which is NOT renamed)

### `backend/app/modules/installments/service.py`
- Line 150: `total_units = product.units` — rename to `product.package_size` (the local variable `total_units` and `InstallmentPlan.total_units` are NOT renamed)

### `backend/app/modules/processors/base.py`
- Line 81: `units: int  # product.units` — update comment to `# product.package_size`

---

## Backend: New Files to Create

- `app/modules/pools/__init__.py`
- `app/modules/pools/models.py` — `OptionPool` model (`id`, `company_id` FK, `total_supply`, `shares_per_option`, `consumed`, `is_active`, timestamps)
- `app/modules/pools/schemas.py` — Pool request/response schemas (`CreatePoolRequest`, `PoolResponse`)
- `app/modules/pools/service.py` — Pool CRUD: create, get active, update consumed, enforce one-active-per-company
- `app/modules/pools/router.py` — Staff Pool endpoints (`POST /staff/pools`, `GET /staff/pools/{company_id}`, `PATCH /staff/pools/{id}`)
- `app/modules/company_dashboard/__init__.py`
- `app/modules/company_dashboard/router.py` — Company-facing dashboard endpoints
- `app/modules/company_dashboard/service.py` — Company dashboard data queries
- `app/modules/company_dashboard/schemas.py` — Company dashboard response schemas
- `app/modules/companies/dependencies.py` — `get_current_company_profile` dependency
- `backend/migrations/versions/2026_04_30_0027_option_pool_refactor.py` — next migration number after 0026; new table `option_pools`; alter `company_profiles` (+`total_supply`, +`shares_per_option`); alter `products` (+`pool_id` FK, rename `units` → `package_size`); partial unique index `uq_one_active_pool_per_company`

---

## Frontend: Files to Modify

### `frontend/src/api/types.ts`
- Line 388: `units: number` — rename to `package_size: number` in `PublicProductResponse`
- Line 391: `sold_units: number` — field stays; verify computed availability logic is `package_size - sold_units` after rename
- Line 496: `units: number` — rename to `package_size: number` in `StaffProductResponse` (if staff types are included in this file)

### `frontend/src/components/shared/ProductCard.vue`
- Line 45: `() => props.product.units - props.product.sold_units,` — rename `.units` to `.package_size`
- Line 73: `<span class="product-card__units">` — consider renaming CSS class if visible label changes; at minimum update computed expression

### `frontend/src/views/investor/ProductDetailView.vue`
- Line 90: `return p ? p.units - p.sold_units : 0` — rename `.units` to `.package_size`

### `frontend/src/views/investor/PurchaseView.vue`
- Line 89: `return p ? p.units * p.price_per_unit_cents : 0` — rename `.units` to `.package_size`
- Line 94: `return p ? Math.max(p.units - p.sold_units, 0) : 0` — rename `.units` to `.package_size`
- Line 277: `{{ formatNumber(product.units, locale) }}` — rename `.units` to `.package_size`

### `frontend/src/views/investor/InstallmentView.vue`
- Line 180: `return getTrancheUnits(planConfig.value, product.value.units, index)` — rename `product.value.units` to `product.value.package_size`

---

## Frontend: New Files to Create

- `frontend/scripts/generate_ts_types.py` — script to auto-generate TS types from backend Pydantic schemas
- `frontend/src/api/generated.ts` — auto-generated types output (replaces manual `types.ts` sections)

---

## Tests: Files to Modify

### `backend/tests/test_products.py`
- Line 111: `units: int = 100,` — rename helper param to `package_size: int = 100`
- Line 120: `"units": units,` — rename to `"package_size": package_size`
- Line 169: `assert product["units"] == 100` — rename to `product["package_size"]`
- Line 224: `"units": 50,` — rename to `"package_size": 50`
- Line 563: `assert body["sold_units"] == 0` — stays; verify sold_units is still returned in public detail response

### `backend/tests/test_purchases.py`
- Line 113: `"units": units,` — rename to `"package_size": units` in `_create_product` helper
- Line 427: `assert data[0]["units"] == product["units"]` — right-hand `product["units"]` becomes `product["package_size"]`; left-hand `data[0]["units"]` is `Purchase.units` — NOT renamed
- Line 428: `assert data[0]["paid_cents"] == product["units"] * product["price_per_unit_cents"]` — rename `product["units"]` to `product["package_size"]`
- Line 577: `assert sale["units"] == 100` — `Purchase.units`, stays
- Line 579: `assert gift["units"] == 10` — `Purchase.units`, stays

### `backend/tests/test_installments.py`
- Line 146: `"units": units,` — rename to `"package_size": units` in `_create_product` helper

### `backend/tests/test_dashboard.py`
- Line 108: `"units": units,` — rename to `"package_size": units`
- Line 436: `assert p["units"] == 50` — this is `p["units"]` on a Purchase response; check whether this is `Purchase.units` (stays) or product field (rename)

### `backend/tests/test_leaderboard.py`
- Line 214: `json={"company_id": company_id, "name": f"Prod {suffix}", "units": 100},` — rename key to `"package_size": 100`

### `backend/tests/test_referrals.py`
- Line 132: `"units": 10,` — rename to `"package_size": 10` in `_create_company_and_product` helper

---

## Tests: New Test Cases Needed

- `test_pools.py` — Pool CRUD (create, read, deactivate), one-active-per-company constraint, prevent update when consumed > new total_supply
- `test_products.py` — `test_available_packages_decreases` (sold_units increments after purchase), `test_purchase_sold_out` (expect 409 when pool exhausted), `test_product_requires_pool` (cannot publish product without active pool)
- `test_purchases.py` — `test_gift_consumes_pool` (gift purchases decrement pool consumed), `test_gift_overflow_allowed` (gifts do not trigger sold-out 409)
- `test_installment_calculator.py` — preview endpoint roundtrip, tranche decomposition invariants with renamed `package_size`
- `test_company_dashboard.py` — company dashboard endpoints: auth, data shape, pool remaining

---

## Migration Notes

- Previous migration: `2026_04_17_0026_products_cover_url`
- `down_revision`: `"0025_documents_language"`
- New file: `backend/migrations/versions/2026_04_30_0027_option_pool_refactor.py`
- `revision`: `"0027_option_pool_refactor"`
- `down_revision`: `"0026_products_cover_url"`
- New tables: `option_pools` (`id`, `company_id` FK → `company_profiles.id`, `total_supply` BIGINT, `shares_per_option` INT, `consumed` BIGINT DEFAULT 0, `is_active` BOOL, `created_at`, `updated_at`)
- Altered tables:
  - `company_profiles`: add `total_supply BIGINT`, add `shares_per_option INT`
  - `products`: rename column `units` → `package_size`, add `pool_id UUID NULL` FK → `option_pools.id`
- New index: `uq_one_active_pool_per_company` — partial unique index on `option_pools(company_id)` WHERE `is_active = true`

---

## Seed Script Changes (`backend/scripts/seed_storefront.py`)

- Lines 234–445 (20 occurrences): rename all `"units": <value>` keys in the `PRODUCTS` list to `"package_size": <value>`
- Line 675: `units=spec["units"]` inside `_ensure_product()` → rename to `package_size=spec["package_size"]` (also rename the `Product(...)` constructor kwarg)
- Lines 27–30: update the comment block explaining the current model conflation — replace references to `Product.units` with `Product.package_size` and `Company.total_shares_issued` once new fields land
- Add pool seeding: after each company is created, seed one `OptionPool` with `total_supply` matching the sum of that company's product `package_size` values and an appropriate `shares_per_option`

---

## Risk Areas

- **`backend/app/modules/products/constants.py`** — `validate_plan_config()` receives `product_units` as a parameter name (not a model attribute); the call sites (`products/service.py:347`, `products/service.py:403`) pass `product.units` directly. All three must change atomically to avoid argument mismatch. The internal parameter name `product_units` can stay or change — but call sites must use `product.package_size`.
- **`backend/app/modules/processors/base.py:81`** — `PurchaseContext.units` field (the share-count carried through the engine) is named the same as the old `Product.units`. The comment `# product.units` is the only change needed here; the field itself is part of `Purchase.units` semantics and is explicitly excluded from renaming.
- **`backend/tests/test_purchases.py:427`** — mixed assertion: `data[0]["units"]` is `Purchase.units` (not renamed), but `product["units"]` is `Product.units` (renamed). Must rename only the right-hand side; risk of renaming both by accident.
- **`backend/tests/test_dashboard.py:436`** — `p["units"]` context is ambiguous without reading the full surrounding fixture; verify whether `p` is a purchase row or a product row before deciding whether to rename.
- **`sold_units` computation** — the current `sold_units = COUNT(purchases WHERE product_id=...)` in `get_sold_units_map()` counts all purchases including gifts. Sprint 4.3 spec says gifts should not consume pool quota; if `sold_units` on the public API is changed to reflect pool consumption rather than raw purchase count, the router logic in `products/router.py:79–96` and `137–155` and the schema default at `schemas.py:153` must all be updated consistently with the new pool `consumed` column.
- **Pool enforcement insertion point** — `execute_purchase()` in `purchases/service.py:264` calls `_load_product` (line 298) then `_load_company` (line 301) before building `PurchaseContext`. Pool validation and decrement must be inserted between those two calls and the `PurchaseContext` construction; this is in the middle of a DB transaction and must be atomic (SELECT FOR UPDATE on pool row or equivalent).
- **`frontend/src/views/investor/InstallmentView.vue:180`** — `getTrancheUnits` receives `product.value.units` as the `totalUnits` argument; if the tranche-units util (`frontend/src/utils/installmentPlans.ts`) is also tested, its test fixtures will need `package_size` instead of `units`.
