# Sprint 4.3 Impact Analysis Report

Generated: 2026-04-30
Repository: cbshome @ 31b5e28
Branch: `claude/sprint-4.3-impact-analysis-gBvEj`

## Summary

- **Total backend files affected**: 14 (models, services, routers, processors, migrations)
- **Total frontend files affected**: 6 (types + 4 views/components + 1 utility)
- **Total test files affected**: 7
- **New backend files to create**: 11 (`pools/` module 5 files + `company_dashboard/` module 4 files + `companies/dependencies.py` + migration 0027)
- **New frontend files to create**: 2 (`scripts/generate_ts_types.py`, `src/api/generated.ts`)
- **Latest migration**: `0026_products_cover_url` → next migration is **0027** (spec mentioned 0028, actual is 0027)

> **NOTE on migration number**: The original spec example referenced `0028_option_pool_refactor.py`, but the current alembic head is `0026`. The next migration must be **0027**.

---

## Backend: Files to Modify

### `backend/app/modules/products/models.py`
- Line 75–78: `units: Mapped[int] = mapped_column(Integer, ...)` — **RENAME column** to `package_size` (DB column rename via migration 0027)
- Line 114: `f"units={self.units} status={self.status}>"` — update `__repr__` to print `package_size`
- **NEW field needed**: `pool_id: Mapped[UUID]` FK → `option_pools.id` (nullable=False, ondelete RESTRICT)
- Note: `company_id` FK **stays** as denormalization (immutable after creation, per spec §5)

### `backend/app/modules/products/constants.py`
- Lines 22, 69, 104, 115, 121, 132, 133, 137, 139, 142, 143 — comments/docstrings reference `product.units` and `product_units`; update to `package_size`

### `backend/app/modules/products/service.py`
- Line 347: `product_units=product.units` — change to `product.package_size`
- Line 403: `product_units=product.units` — change to `product.package_size`
- Lines 272, 477: `Product.company_id == company_id` filters — **NO CHANGE** (denormalized FK stays)
- Lines 464–490: `cascade_price()` — **NO CHANGE** (price cascade unchanged)

### `backend/app/modules/products/router.py`
- Line 53, 79, 137: three call sites of `get_sold_units_map()` — rename to `get_available_packages_map()`
- Line 83: `company_ids = list({p.company_id for p in products})` — **NO CHANGE** (denormalized FK)
- Lines 145, 151: `CompanyProfile.id == product.company_id` — **NO CHANGE**

### `backend/app/modules/products/staff_router.py`
- Line 90: reads `body.units` — update to `body.package_size` (after schema rename)

### `backend/app/modules/products/schemas.py`
- Line 153: `sold_units: int = 0  # Populated by router` — **field name STAYS** for API response backward compat; update comment to reflect new computation source (pool-based)
- `CreateProductRequest` / `UpdateProductRequest` — rename `units` field to `package_size`

### `backend/app/modules/processors/base.py`
- Line 81: `units: int  # product.units` (in PurchaseContext) — **field name STAYS** per spec §8; update comment from `# product.units` to `# snapshot of product.package_size at purchase time`

### `backend/app/modules/purchases/service.py`
- Line 9: import `get_sold_units_map` — rename to `get_available_packages_map`
- Lines 108–135: `async def get_sold_units_map()` — **RENAME function** to `get_available_packages_map()`; new formula must derive availability from `OptionPool` (subtract sold packages from `pool.total_packages`, or directly read `pool.available_units // shares_per_option / package_size` per spec)
- Line 264–350: `async def execute_purchase()` — **insert pool validation step** after `_load_company` (≈ line 301): load `OptionPool` by `product.pool_id`, raise `BadRequestError` if `pool.available_units < product.package_size * shares_per_option * units_to_purchase`
- Line 320: `product.units * product.price_per_unit_cents` — change to `product.package_size`
- Line 329: `units=product.units` — change to `product.package_size`
- Line 357: `(p for p in purchases if p.legal_basis != "gift")` — **NO CHANGE** (filter logic unchanged; gift purchases just additionally consume pool now per spec §9)
- Lines 183–199 `_load_product()` / 202–218 `_load_company()` — **NO CHANGE**; ADD a sibling `async def _load_pool(pool_id, session) -> OptionPool`

### `backend/app/modules/purchases/engine.py`
- Line 73–134 `execute()` — **NO CHANGE** to engine signature; pool validation happens in service before context build
- Line 200: `if txn.legal_basis == PurchaseLegalBasis.GIFT` — **NO CHANGE**

### `backend/app/modules/purchases/router.py`
- Line 60: `purchases = await execute_purchase(...)` — **NO CHANGE** (call site unchanged)

### `backend/app/modules/processors/gift.py`
- Lines 63, 118 (`legal_basis="gift"`) and Line 150 (`context.units * pct / 100`) — **NO CHANGE**; gifts now consume pool but processor logic itself doesn't change (pool validated upstream)

### `backend/app/modules/installments/service.py`
- Line 133: `await _load_company_active(product.company_id, session)` — **NO CHANGE**
- Line 150: `total_units = product.units` — change to `product.package_size`
- Lines 345, 387, 389, 798–811, 872, 903 — **NO CHANGE** (gift basis checks, distribution config resolution)

### `backend/app/modules/dashboard/service.py`
- Lines 53, 67: `func.sum(Purchase.units)` — **NO CHANGE** (excluded per spec, this is `Purchase.units` not `Product.units`)

### `backend/app/modules/dashboard/schemas.py`
- Line 11: comment referencing units calculation — update to `package_size`

### `backend/app/modules/portfolio/service.py`
- Lines 60, 66, 78, 100, 152, 158, 170: `func.sum(Purchase.units)` — **NO CHANGE** (all `Purchase.units`)

### `backend/app/modules/staff/consistency/service.py`
- Lines 336, 346, 356, 360, 401: `Purchase.units` / `legal_basis == "gift"` — **NO CHANGE**

### `backend/app/modules/commissions/worker.py`
- Lines 143, 181: `Purchase.legal_basis != PurchaseLegalBasis.GIFT` — **NO CHANGE**

### `backend/app/modules/companies/models.py`
- Lines 45–116 (CompanyProfile class) — **ADD** two new columns:
  - `total_supply: Mapped[int] = mapped_column(BigInteger, nullable=False)`
  - `shares_per_option: Mapped[int] = mapped_column(Integer, nullable=False)`

### `backend/app/modules/companies/service.py`
- Lines 244–268 `update_price()` — **NO CHANGE** (calls cascade_price, untouched)

### `backend/app/modules/purchases/certificate_service.py`
- Line 167: `data.purchase.price_per_unit_cents` — **NO CHANGE** (reads snapshot, not Product)

### `backend/scripts/seed_storefront.py`
- Lines 27–30: comments referencing `units` and `total_shares_issued` — update to new model
- Lines 234, 245, 256, 267, 279, 293, 301, 313, 324, 335, 346, 357, 373, 381, 392, 401, 411, 419, 428, 436, 445 — **21 product payloads** with `"units": <value>` → rename key to `"package_size"`
- Line 700: `product.units * product.price_per_unit_cents` — change to `product.package_size`
- Lines 672, 675, 702: product creation calls — pass `package_size` instead of `units`
- **Add OptionPool seeding** before products (FK requires pool to exist first)
- **Add Company fields** `total_supply` and `shares_per_option` to each seeded company
- Lines 215, 222, 471, 480, 710, 711: `bonus_units_percent`, `agent_bonus_units` — **NO CHANGE** (excluded)

---

## Backend: New Files to Create

- `backend/app/modules/pools/__init__.py`
- `backend/app/modules/pools/models.py` — `OptionPool` model (id, company_id FK, total_units / available_units, status, created_at, updated_at)
- `backend/app/modules/pools/schemas.py` — `CreatePoolRequest`, `UpdatePoolRequest`, `PoolResponse`
- `backend/app/modules/pools/service.py` — Pool CRUD; one-active-pool-per-company invariant; "cannot update below consumed" check
- `backend/app/modules/pools/router.py` — staff endpoints `POST /staff/companies/{id}/pool`, `PATCH /staff/companies/{id}/pool`
- `backend/app/modules/company_dashboard/__init__.py`
- `backend/app/modules/company_dashboard/router.py` — company-side dashboard endpoints
- `backend/app/modules/company_dashboard/service.py`
- `backend/app/modules/company_dashboard/schemas.py`
- `backend/app/modules/companies/dependencies.py` — `get_current_company_profile()` FastAPI dependency
- `backend/migrations/versions/2026_04_30_0027_option_pool_refactor.py` — migration 0027:
  1. Create `option_pools` table with check constraint `available_units >= 0`
  2. Add `pool_id UUID FK` (nullable initially for backfill, then NOT NULL) to `products`
  3. Add `total_supply BIGINT NOT NULL` and `shares_per_option INT NOT NULL` to `company_profiles`
  4. Rename `products.units` → `products.package_size`
  5. Backfill: create one OptionPool per company; assign all products of that company to it; set `total_supply = SUM(package_size) * shares_per_option` (or per spec backfill rule)
  6. Add partial unique index `uq_one_active_pool_per_company` on `(company_id) WHERE status = 'active'`
  7. Add `ix_option_pools_company_id`, `ix_products_pool_id`

**New endpoint** (in installments router, not a new file): `POST /staff/products/{id}/installments/preview` (calculator)

---

## Frontend: Files to Modify

### `frontend/src/api/types.ts`
- Line 388: `units: number` (in `PublicProductResponse`) — rename to `package_size: number`
- Line 391: `sold_units: number` — rename to `available_packages: number` (per backend convention)
- Line 400: `PublicProductDetailResponse extends PublicProductResponse` — auto-inherits
- Line 426: `PublicCompanyResponse` — **add** `total_supply: number`, `shares_per_option: number` (if exposed in public API)
- Line 803: `units` on `PurchaseItemResponse` — **NO CHANGE** (this is purchase count, not product field)

### `frontend/src/components/shared/ProductCard.vue`
- Line 45: `props.product.units - props.product.sold_units` — change to `props.product.package_size - <…>` and `available_packages`
- Line 73: CSS class `product-card__units` — **NO CHANGE** (CSS, not data)

### `frontend/src/views/investor/ProductDetailView.vue`
- Line 90: `p.units - p.sold_units` (computed `available`) — rename both fields
- Lines 109, 179, 242–244: dependent gates / soldOut conditional — auto-fixed by computed rename

### `frontend/src/views/investor/PurchaseView.vue`
- Line 89: `p.units * p.price_per_unit_cents` — rename `units` → `package_size`
- Line 94: `Math.max(p.units - p.sold_units, 0)` — rename both fields
- Line 277: `formatNumber(product.units, locale)` — rename to `package_size`
- Lines 117, 324–326: dependent gates — auto-fixed

### `frontend/src/views/investor/InstallmentView.vue`
- Line 180: `getTrancheUnits(planConfig.value, product.value.units, index)` — rename `product.value.units` → `product.value.package_size`

### `frontend/src/utils/installmentPlans.ts`
- Lines 125, 131: `getTrancheUnits` parameter `totalUnits` — internal name; consider renaming for consistency, but no functional change required

### Files NOT requiring changes (auto-inherited from type rename)
- `frontend/src/api/products.ts`, `frontend/src/api/companies.ts`
- `frontend/src/stores/products.ts`, `frontend/src/stores/companies.ts`
- All i18n locale files (`inv.available`, `inv.product.soldOut`, `inv.purchase.packageSize` remain semantically correct)

---

## Frontend: New Files to Create

- `frontend/scripts/generate_ts_types.py` — auto-generator from OpenAPI → TS (directory `frontend/scripts/` does NOT exist; must create)
- `frontend/src/api/generated.ts` — auto-generated; gitignored or committed per project policy

---

## Tests: Files to Modify

### `backend/tests/test_products.py`
- Lines 64–130: `_create_company()` and `_create_product()` helpers — change request body from `"units": …` to `"package_size": …`; helpers must additionally seed an OptionPool (or accept pool_id) since Product.pool_id will be NOT NULL
- Lines 120, 169, 224: request payloads / `product["units"]` assertions — rename to `package_size`
- Line 540: assertion mentioning `sold_units` — update to `available_packages` (response field) if API renames it; keep otherwise
- Line 563: `assert body["sold_units"] == 0` — update if response field renamed
- Line 17: top-of-file comment — update terminology

### `backend/tests/test_purchases.py`
- Lines 113, 427, 428, 577, 579: product creation + unit assertions — rename `units` → `package_size` in factory calls and direct Product reads

### `backend/tests/test_installments.py`
- Line 146: product creation passes `units` — rename

### `backend/tests/test_referrals.py`
- Lines 94, 132: `_create_company_and_product()` factory call — rename param

### `backend/tests/test_dashboard.py`
- Lines 108, 436: product creation + reads — rename

### `backend/tests/test_leaderboard.py`
- Line 214: product creation — rename

### `backend/tests/helpers.py` (and `conftest.py`)
- Inspect for `_make_context()` / shared product factories — update to use `package_size` and pool

---

## Tests: New Test Cases Needed

- `test_pools.py` — Pool CRUD; one-active-pool-per-company unique index; "cannot update available_units below consumed" rejection; staff-only access
- `test_products.py` (additions) — `available_packages_decreases_after_purchase`, `purchase_sold_out_when_pool_empty`, `requires_pool_id_on_create`
- `test_purchases.py` (additions) — `gift_consumes_pool` (verify pool decrement on gift_basis), `gift_overflow_allowed_when_pool_zero` (per spec semantics)
- `test_installment_calculator.py` — `POST /staff/products/{id}/installments/preview` invariants (sum of tranches = 100%, bonus + base = total, etc.)
- `test_company_dashboard.py` — auth via `get_current_company_profile()`, dashboard endpoints

---

## Migration Notes

- **Previous migration**: `0026_products_cover_url` (file: `2026_04_17_0026_products_cover_url.py`)
- **Next migration**: **0027** (NOT 0028 as spec example used)
- **down_revision**: `0026_products_cover_url` (revision identifier as defined in that file)
- **New tables**: `option_pools`
- **Altered tables**:
  - `company_profiles`: `+total_supply BIGINT NOT NULL`, `+shares_per_option INT NOT NULL`
  - `products`: `+pool_id UUID FK NOT NULL`, rename `units → package_size`
- **New indexes**:
  - `uq_one_active_pool_per_company` — partial unique on `option_pools(company_id) WHERE status = 'active'`
  - `ix_option_pools_company_id`
  - `ix_products_pool_id`
- **Constraints**: `ck_option_pools_available_units` CHECK (`available_units >= 0`)
- **Backfill order** (critical):
  1. Add columns as nullable
  2. Create one OptionPool per existing company
  3. Set every Product.pool_id to its company's pool
  4. Compute `total_supply = SUM(package_size) * shares_per_option` (or per spec rule); set `shares_per_option = 1` default
  5. Apply NOT NULL
  6. Rename `units → package_size` last

---

## Seed Script Changes (`backend/scripts/seed_storefront.py`)

- Update header comments (lines 27–30) to describe pool-based model; remove obsolete `total_shares_issued` mention
- For each company: add `total_supply`, `shares_per_option` to seed payload
- Before seeding products: create one `OptionPool` per company (status=active)
- For each of the 21 product definitions (lines 234, 245, 256, 267, 279, 293, 301, 313, 324, 335, 346, 357, 373, 381, 392, 401, 411, 419, 428, 436, 445): rename JSON key `"units"` → `"package_size"`; pass `pool_id` (or have service auto-resolve)
- Line 700: rename `product.units` → `product.package_size`
- Lines 672, 675, 702: factory call signatures
- **NO CHANGE** to `bonus_units_percent`, `agent_bonus_units` (lines 215, 222, 471, 480, 710, 711)

---

## Risk Areas

1. **Migration 0027 backfill ordering** — Product.pool_id NOT NULL must be applied AFTER backfill; rename `units → package_size` must happen LAST so backfill code can still read old column. Alembic op order matters.
2. **`get_sold_units_map` semantic shift** — function rename is straightforward, but the **formula** changes: previously summed `Purchase.units WHERE legal_basis != 'gift'`, now derives from pool state. Spec §9 says gifts now also consume pool, so the legal_basis filter likely **drops entirely**. Confirm with spec author before implementing.
3. **execute_purchase pool validation** — must occur BEFORE building `PurchaseContext` (line ≈ 250–301 area). Race conditions: pool decrement should be inside the same DB transaction with row-level lock (`SELECT … FOR UPDATE`) on `option_pools` row to prevent oversell under concurrent purchases.
4. **Gift consumption semantics** (spec §9) — the report assumes gifts decrement the pool like sales. If "gift_overflow_allowed" is intended (gifts can dip below zero or have separate budget), the WHERE clauses and validation differ significantly. **Clarify with spec author.**
5. **`PurchaseContext.units` vs `Product.units`** — field names collide; only Product is renamed. Ensure nothing accidentally renames context.units (covered by exclusion list, but easy to miss in mass find/replace).
6. **`sold_units` API response field name** — spec is ambiguous whether the response field also renames. Recommended: rename to `available_packages` for clarity, but it's a frontend-visible breaking change. Currently kept as `sold_units` in `products/schemas.py:153` — confirm naming.
7. **One-active-pool-per-company invariant** — partial unique index requires PostgreSQL; verify dev/test DB compatibility.
8. **Test factory ripple** — `_create_product()` is used in 7+ test files. Updating it to require pool seeding may cascade test setup changes; consider making pool auto-creation a default in the helper.
9. **`CompanyProfile.total_supply` vs old spec name `total_shares_issued`** — only comments reference the old name (seed_storefront.py:30); no code uses it. Confirm `total_supply` is the final name.
10. **Frontend availability formula** — currently `units - sold_units`. New formula likely `available_packages` directly from server. If installment plans pre-reserve packages, frontend may need to display "X of Y available" differently.
