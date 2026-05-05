# B7 Frontend Rename — Audit Report (Re-run on updated main)

**Branch audited:** `origin/main` (commit `19b5840`)
**Date:** 2026-05-05
**Scope:** Sprint 4.3 TD-F07 / Batch B7 — `units → package_size`, `sold_units → available_packages` in `PublicProductResponse` and related; Sprint 4.4 B7 UX follow-up (`price_per_pack_cents`, `available_packages` made required)
**Status:** Read-only audit. No files were modified.

> **Δ vs first audit** (branch point `e5779c8`): B8 + Sprint 4.4 B7 UX have both landed on main since the original report. All changes are reflected here. Differences from the first audit are called out inline.

---

## Section 1: `generated.ts` inventory

### Full list (116 names — unchanged from first audit)

| # | Name | # | Name |
|---|------|---|------|
| 1 | AgentApplicationListResponse | 59 | NotificationListResponse |
| 2 | AgentApplicationResponse | 60 | PaymentHistoryResponse |
| 3 | AuthResponse | 61 | PaymentResponse |
| 4 | AvatarSessionResponse | 62 | PayoutDetailsResponse |
| 5 | AvatarStartRequest | 63 | PoolEmbedResponse |
| 6 | AvatarStartResponse | 64 | PoolResponse |
| 7 | BalanceResponse | 65 | PortfolioResponse |
| 8 | BlockRequest | 66 | PostListResponse |
| 9 | CommissionEntry | 67 | PostResponse |
| 10 | CommissionListResponse | 68 | ProductResponse |
| 11 | CompanyAnalyticsResponse | 69 | PublicCompanyDetailResponse |
| 12 | CompanyDashboardResponse | 70 | PublicCompanyListResponse |
| 13 | CompanyPositionDetailResponse | 71 | PublicCompanyResponse |
| 14 | CompanyPositionResponse | 72 | PublicProductDetailResponse |
| 15 | CompanyResponse | 73 | PublicProductListResponse |
| 16 | CompanySummaryResponse | 74 | PublicProductResponse |
| 17 | CompanyTransactionResponse | 75 | PurchaseItemResponse |
| 18 | ConsistencyResponse | 76 | PurchaseResponse |
| 19 | CreateAddressRequest | 77 | ReadAllResponse |
| 20 | CreateCompanyRequest | 78 | ReferralLinkListResponse |
| 21 | CreateEventRequest | 79 | ReferralLinkResponse |
| 22 | CreateInstallmentPlanRequest | 80 | ReferralStatsResponse |
| 23 | CreateInstallmentRequest | 81 | RejectRequest |
| 24 | CreatePoolRequest | 82 | RejectWithdrawalRequest |
| 25 | CreatePostRequest | 83 | ReorderRoadmapRequest |
| 26 | CreateProductRequest | 84 | ReversalResponse |
| 27 | CreatePurchaseRequest | 85 | ReversePaymentRequest |
| 28 | CreateRoadmapItemRequest | 86 | RoadmapItemResponse |
| 29 | CreateStaffRequest | 87 | SalesByMonthEntry |
| 30 | CreateWithdrawalRequest | 88 | SalesByProductEntry |
| 31 | CryptoWebhookRequest | 89 | SelectRoleRequest |
| 32 | DashboardStatsResponse | 90 | SemaphoreResult |
| 33 | DashboardSummaryResponse | 91 | StaffPaymentListResponse |
| 34 | DepositAddressResponse | 92 | StaffPaymentResponse |
| 35 | DocumentCreateRequest | 93 | StaffProfileResponse |
| 36 | DocumentResponse | 94 | TelegramAuthRequest |
| 37 | DocumentSigningResponse | 95 | TransactionListResponse |
| 38 | DocumentUpdateRequest | 96 | TransactionResponse |
| 39 | EmailLoginRequest | 97 | UnreadCountResponse |
| 40 | EmailRegisterRequest | 98 | UpdateCompanyRequest |
| 41 | EventListResponse | 99 | UpdateEventRequest |
| 42 | EventResponse | 100 | UpdateInstallmentRequest |
| 43 | InstallmentPlanDetailResponse | 101 | UpdatePayoutDetailsRequest |
| 44 | InstallmentPlanListResponse | 102 | UpdatePermissionsRequest |
| 45 | InstallmentPlanResponse | 103 | UpdatePoolRequest |
| 46 | InstallmentPreviewRequest | 104 | UpdatePostRequest |
| 47 | InstallmentPreviewResponse | 105 | UpdatePriceRequest |
| 48 | InstallmentPreviewSummary | 106 | UpdateProductRequest |
| 49 | InstallmentResponse | 107 | UpdateProductStatusRequest |
| 50 | InstallmentTrancheResponse | 108 | UpdateRoadmapItemRequest |
| 51 | KYCQueueItem | 109 | UserDetailResponse |
| 52 | KYCRejectRequest | 110 | UserListItem |
| 53 | KYCStatusResponse | 111 | UserListResponse |
| 54 | KYCSubmitResponse | 112 | UserResponse |
| 55 | KYCWebhookRequest | 113 | UserUpdate |
| 56 | LeaderboardEntry | 114 | VerifyEmailRequest |
| 57 | LeaderboardResponse | 115 | WithdrawalListResponse |
| 58 | NotificationDeliveryResponse | 116 | WithdrawalResponse |

**Total: 116**

### Double-underscore names (`__`)
**(none)** ✓

### `BalanceResponse` presence
Appears **exactly once** (line 7 of interface list). ✓

### ⚠️ New in Sprint 4.4 — schema changes on key B7 types

**`PublicProductResponse`** (was the B7 rename subject):
```typescript
export interface PublicProductResponse {
  id: string
  company_id: string
  name: string
  description: string | null
  package_size: number
  price_per_unit_cents: number
  price_per_pack_cents: number          // ← NEW (Sprint 4.4)
  cover_url?: string | null
  available_packages: number            // ← was `?: number` in B8; NOW REQUIRED
  company_name: string                  // ← was `?: string`; NOW REQUIRED
  company_logo_url?: string | null
  company_cover_url?: string | null
}
```

**`PublicProductDetailResponse`** — same changes plus `installments` guaranteed:
```typescript
export interface PublicProductDetailResponse {
  id: string
  company_id: string
  name: string
  description: string | null
  package_size: number
  price_per_unit_cents: number
  price_per_pack_cents: number          // ← NEW (Sprint 4.4)
  cover_url?: string | null
  available_packages: number            // ← now required
  company_name: string                  // ← now required
  company_logo_url?: string | null
  company_cover_url?: string | null
  installments: InstallmentResponse[]
}
```

**`BalanceResponse`** — fixed from first audit (was `?: number`, now required):
```typescript
export interface BalanceResponse {
  frozen: number
  confirmed: number
}
```

---

## Section 2: `types.ts` inventory

`types.ts` is now a **VELO-style facade** (433 lines, down from 939). It contains:

### Re-exports from `./generated` (70 names)
AgentApplicationListResponse, AgentApplicationResponse, AuthResponse, AvatarSessionResponse, AvatarStartRequest, AvatarStartResponse, BalanceResponse, CompanyAnalyticsResponse, CompanyDashboardResponse, CompanyPositionDetailResponse, CompanyResponse, CompanySummaryResponse, CompanyTransactionResponse, CreateAddressRequest, CreateInstallmentPlanRequest, CreatePurchaseRequest, CreateStaffRequest, DashboardStatsResponse, DashboardSummaryResponse, DepositAddressResponse, DocumentResponse, DocumentSigningResponse, EmailLoginRequest, EmailRegisterRequest, EventListResponse, EventResponse, InstallmentPlanDetailResponse, InstallmentPlanListResponse, InstallmentPlanResponse, InstallmentResponse, InstallmentTrancheResponse, KYCQueueItem, KYCRejectRequest, KYCStatusResponse, KYCSubmitResponse, PaymentHistoryResponse, PaymentResponse, PayoutDetailsResponse, PoolEmbedResponse, PortfolioResponse, PostListResponse, PostResponse, PublicCompanyDetailResponse, PublicCompanyListResponse, PublicCompanyResponse, PublicProductDetailResponse, PublicProductListResponse, PublicProductResponse, PurchaseItemResponse, PurchaseResponse, RejectWithdrawalRequest, ReversalResponse, ReversePaymentRequest, RoadmapItemResponse, SalesByMonthEntry, SalesByProductEntry, SelectRoleRequest, StaffPaymentListResponse, StaffPaymentResponse, StaffProfileResponse, TelegramAuthRequest, TransactionListResponse, TransactionResponse, UpdatePermissionsRequest, UserDetailResponse, UserListItem, UserListResponse, UserResponse, UserUpdate, VerifyEmailRequest, WithdrawalListResponse, WithdrawalResponse

### Type aliases (5 names)
| Alias | Points to |
|-------|-----------|
| `BlockUserRequest` | `BlockRequest` |
| `RejectAgentApplicationRequest` | `RejectRequest` |
| `PortfolioPositionResponse` | `CompanyPositionResponse` |
| `UserRole` | *(frontend union — see Section 9)* |
| `KycStatus` | *(frontend union — see Section 9)* |

### Handwritten interfaces + functions (4 names)
| Name | Kind |
|------|------|
| `PaginatedResponse<T>` | generic interface |
| `ValidationErrorItem` | interface |
| `asUserRole(raw)` | runtime narrowing function |
| `asKycStatus(raw)` | runtime narrowing function |

**Total exports: 79** (70 re-exports + 5 aliases/unions + 4 handwritten)

---

## Section 3: Diff between `types.ts` and `generated.ts`

### 3a. In `types.ts` BUT NOT in `generated.ts` — frontend-only (7 names)

| Name | Kind | Definition / notes |
|------|------|-------------------|
| `UserRole` | union | `'investor' \| 'agent' \| 'company' \| 'staff' \| 'platform'` + completeness guard + `asUserRole()` |
| `KycStatus` | union | `'not_started' \| 'submitted' \| 'approved' \| 'rejected'` + completeness guard + `asKycStatus()` |
| `PaginatedResponse<T>` | generic interface | Generic pagination helper |
| `ValidationErrorItem` | interface | FastAPI 422 error body |
| `BlockUserRequest` | alias | `= BlockRequest` (see Section 8) |
| `RejectAgentApplicationRequest` | alias | `= RejectRequest` (see Section 8) |
| `PortfolioPositionResponse` | alias | `= CompanyPositionResponse` (see Section 8) |

> **Δ vs first audit:** The original 21 frontend-only types are now down to 7. All narrowing unions (`PaymentStatusType`, `PaymentType`, `PurchaseLegalBasis`, `PurchaseStatusType`, `ReferenceType`, `TransactionType`, `InstallmentPlanStatusType`, `InstallmentTrancheStatusType`, `PostOwnerType`, `AgentApplicationStatusType`, `WithdrawalStatusType`, `StaffPermissionKey`, `StaffPermissions`, `CryptoNetwork`) have been **removed** in the VELO refactor. `UserRole` and `KycStatus` were also briefly removed but restored with upgraded runtime guards (`asUserRole` / `asKycStatus`).

### 3b. In `generated.ts` BUT NOT re-exported via `types.ts` (42 names)

These are backend types not yet surfaced to the frontend. They are available in `generated.ts` and can be re-exported as needed.

BlockRequest, CommissionEntry, CommissionListResponse, CompanyPositionResponse *(only via alias)*, ConsistencyResponse, CreateCompanyRequest, CreateEventRequest, CreateInstallmentRequest, CreatePoolRequest, CreatePostRequest, CreateProductRequest, CreateRoadmapItemRequest, CreateWithdrawalRequest, CryptoWebhookRequest, DocumentCreateRequest, DocumentUpdateRequest, InstallmentPreviewRequest, InstallmentPreviewResponse, InstallmentPreviewSummary, KYCWebhookRequest, LeaderboardEntry, LeaderboardResponse, NotificationDeliveryResponse, NotificationListResponse, PoolResponse, ProductResponse, ReadAllResponse, ReferralLinkListResponse, ReferralLinkResponse, ReferralStatsResponse, RejectRequest *(only via alias)*, ReorderRoadmapRequest, SemaphoreResult, UnreadCountResponse, UpdateCompanyRequest, UpdateEventRequest, UpdateInstallmentRequest, UpdatePayoutDetailsRequest, UpdatePoolRequest, UpdatePostRequest, UpdatePriceRequest, UpdateProductRequest, UpdateProductStatusRequest, UpdateRoadmapItemRequest

> **Δ vs first audit:** `WithdrawalListResponse` and `PayoutDetailsResponse` have been added to `types.ts` (F5.2 needed them). `CompanyResponse`, `CompanyDashboardResponse`, `CompanyAnalyticsResponse`, `PoolEmbedResponse`, `CompanyTransactionResponse`, `SalesByMonthEntry`, `SalesByProductEntry` also added (F5.2 company dashboard/analytics).

### 3c. In BOTH (70 names — all re-exported from generated, zero handwritten duplicates)

Since all 70 shared types are now pure `export type { X } from './generated'`, there are **zero handwritten duplicates** that could drift from the generated shape. The type facade is consistent by construction.

---

## Section 4: Field-shape mismatches between `types.ts` and `generated.ts`

**Result: ZERO mismatches.**

All shared types in `types.ts` are `export type { X } from './generated'` — they are literally the same type object. There is no handwritten interface that could diverge from the generated one. The entire class of drift bugs identified in the first audit has been eliminated by the VELO refactor.

> **Δ vs first audit:** The first audit found 25 types with field-shape mismatches (optionality, narrowed unions, missing fields, different field names). All resolved.

**Residual shape notes (not mismatches — informational):**

| Type | Note |
|------|-------|
| `BalanceResponse` | `frozen`/`confirmed` are now required `number` — first audit flagged them as `?: number`. Fixed in generated.ts. |
| `PublicProductResponse` | `available_packages` is now required `number` (was `?: number`). All consumer `?? 0` guards correctly removed. |
| `StaffPaymentResponse` | `provider_data` that existed in old `types.ts` is gone. Correct — it was never in generated.ts. |
| `WithdrawalResponse` | `payout_details_snapshot` and `failed_at` now correctly surfaced via re-export. |

---

## Section 5: Vue/TS consumers of the renamed fields

### `\bunits\b` (excluding exempt patterns) — on main

| File | Line | Content | In-scope? | Notes |
|------|------|---------|-----------|-------|
| `frontend/src/api/types.ts` | — | *(no hits)* | ✓ | No `units` field definitions remain |
| `frontend/src/components/shared/ProductCard.vue` | — | *(no hits)* | ✓ | Clean |
| `frontend/src/views/investor/ProductDetailView.vue` | — | *(no hits)* | ✓ | Clean |
| `frontend/src/views/investor/PurchaseView.vue` | — | *(no hits)* | ✓ | Clean |
| `frontend/src/views/investor/InstallmentView.vue` | 178 | `* Tranche row units -- thin wrapper...` | context | JSDoc comment, not a field access |
| `frontend/src/utils/installmentPlans.ts` | — | *(no hits)* | ✓ | Clean |

### `sold_units` — on main

**(no hits anywhere in `frontend/src/`)** ✓

### `package_size` — on main (consumers)

| File | Line | Content |
|------|------|---------|
| `frontend/src/api/generated.ts` | multiple | Field definitions in `CreateProductRequest`, `InstallmentPreviewSummary`, `ProductResponse`, `PublicProductDetailResponse`, `PublicProductResponse` |
| `frontend/src/views/investor/PurchaseView.vue` | 107 | `return p ? p.package_size * p.price_per_unit_cents : 0` |
| `frontend/src/views/investor/PurchaseView.vue` | 296 | `{{ formatNumber(product.package_size, locale) }}` |
| `frontend/src/views/investor/InstallmentView.vue` | 183 | `return getTrancheUnits(planConfig.value, product.value.package_size, index)` |

### `available_packages` — on main (consumers)

| File | Line | Content |
|------|------|---------|
| `frontend/src/api/generated.ts` | multiple | Field definitions in `PublicProductResponse`, `PublicProductDetailResponse` |
| `frontend/src/components/shared/ProductCard.vue` | 57 | `const available = computed(() => props.product.available_packages)` |
| `frontend/src/views/investor/ProductDetailView.vue` | 103 | `return p ? p.available_packages : 0` |
| `frontend/src/views/investor/PurchaseView.vue` | 113 | `return p ? p.available_packages : 0` |

### `price_per_pack_cents` — on main (NEW field, Sprint 4.4)

| File | Line | Content |
|------|------|---------|
| `frontend/src/api/generated.ts` | 708, 733 | Field in `PublicProductDetailResponse`, `PublicProductResponse` |
| `frontend/src/components/shared/ProductCard.vue` | 82 | `formatPrice(product.price_per_pack_cents, product.currency)` |
| `frontend/src/views/investor/ProductDetailView.vue` | 183 | `formatPrice(product.price_per_pack_cents, product.currency)` |
| `frontend/src/views/investor/PurchaseView.vue` | 306 | `formatPrice(product.price_per_pack_cents, product.currency)` |

### Summary: B7 rename — COMPLETE on main ✓

| File | Status |
|------|--------|
| `frontend/src/api/types.ts` | ✅ VELO re-export; `units`/`sold_units` gone |
| `frontend/src/components/shared/ProductCard.vue` | ✅ `available_packages` (no `?? 0` — field now required) |
| `frontend/src/views/investor/ProductDetailView.vue` | ✅ `available_packages` (no `?? 0`) |
| `frontend/src/views/investor/PurchaseView.vue` | ✅ `package_size` + `available_packages` |
| `frontend/src/views/investor/InstallmentView.vue` | ✅ `package_size` |
| `frontend/src/utils/installmentPlans.ts` | ✅ No changes needed |

---

## Section 6: i18n keys

### Specified keys

| Key | Status | Value |
|-----|--------|-------|
| `inv.market.packsAvailable` | **PRESENT** ✓ | `'packs available'` |
| `inv.product.packsAvailability` | **PRESENT** ✓ | `'Packs availability'` |
| `inv.product.soldOut` | **PRESENT** ✓ | `'Sold out'` |
| `inv.market.available` | **ABSENT** | — (legacy key, never added; `inv.available` exists at top level) |

> **Δ vs first audit:** The two previously-absent keys (`packsAvailable`, `packsAvailability`) have been added. Audit recommendation fulfilled.

### All keys under `inv.market.*`

```
inv.market.title              = 'Marketplace'
inv.market.subtitle           = 'Available Investment Products'
inv.market.filter.all         = 'All companies'
inv.market.filter.company     = 'Company'
inv.market.filter.title       = 'Filter by company'
inv.market.filter.search      = 'Search companies...'
inv.market.filter.clear       = 'Clear filter'
inv.market.filter.empty       = 'No companies found'
inv.market.empty.title        = 'No products available'
inv.market.empty.desc         = 'Check back later for new investment opportunities'
inv.market.empty.filteredTitle = 'No products for this company'
inv.market.empty.filteredDesc  = 'Try another filter or clear it'
inv.market.packsAvailable     = 'packs available'         ← NEW (Sprint 4.4 B7)
```

### All keys under `inv.product.*`

```
inv.product.notFound.title    = 'Product not found'
inv.product.notFound.desc     = 'This product may have been removed...'
inv.product.backToMarket      = 'Back to marketplace'
inv.product.pricePerPack      = 'Price per pack'          ← NEW (replaced priceLabel)
inv.product.availability      = 'Availability'
inv.product.description       = 'About'
inv.product.installments      = 'Installment plans'
inv.product.installmentsEmpty = 'No installment plans available for this product'
inv.product.installmentsBonus = '+{n} bonus units'
inv.product.buy               = 'Buy now'
inv.product.soldOut           = 'Sold out'
inv.product.packsAvailability = 'Packs availability'      ← NEW (Sprint 4.4 B7)
```

> **Note:** `inv.product.priceLabel` has been **removed** and replaced by `inv.product.pricePerPack`. The old key does not exist in `en.json`. The view code (`ProductDetailView.vue`) already uses `t('inv.product.pricePerPack')`.

### Newly required keys (Sprint 4.4 B7)

```
inv.pack       = 'pack'        ← NEW; used as "/ pack" price suffix in ProductCard + ProductDetailView
inv.unit       = 'unit'        (unchanged)
inv.available  = 'available'   (unchanged; still used in ProductDetailView stat block)
```

---

## Section 7: Sold-out logic in Vue files

### `ProductCard.vue`

```
Line 57:
  const available = computed(() => props.product.available_packages)
```

Template (line 91):
```html
{{ formatNumber(available, locale) }} {{ t('inv.market.packsAvailable') }}
```

The card renders "N packs available". There is **no sold-out indicator** on the card (no disabled state, no "Sold out" badge). Sold-out state is communicated only implicitly when the count reaches 0.

> **Δ vs first audit:** `available_packages` is now required — no `?? 0` guard needed. Label changed from `t('inv.available')` to `t('inv.market.packsAvailable')`. Price display expanded to show both pack price and per-unit reference.

### `ProductDetailView.vue`

```
Lines 101-103:
  const available = computed<number>(() => {
    const p = product.value
    return p ? p.available_packages : 0
  })
```

Four bindings depend on `available`:

```
Line 122 (openInstallmentPlan guard):
  if (available.value <= 0) return

Line 225 (plan card class):
  :class="{ 'pd__plan--disabled': available <= 0 }"

Line 253 (buy button disabled):
  :disabled="available <= 0"

Lines 258-260 (buy button label):
  available > 0
    ? t('inv.product.buy')       → "Buy now"
    : t('inv.product.soldOut')   → "Sold out"
```

Price stat label (line 180) now uses `t('inv.product.pricePerPack')` = "Price per pack" (was `priceLabel` = "Price per unit").
Availability stat block (line 197) still uses `t('inv.available')` = "available" as the unit suffix.

---

## Section 8: Aliases — status on main

All three aliases from the first audit recommendation are in place:

### `BlockUserRequest = BlockRequest`
```typescript
export type BlockUserRequest = BlockRequest
// BlockRequest: { reason?: string | null }
```
Shape identical ✓. Alias in `types.ts` line ~104.

### `RejectAgentApplicationRequest = RejectRequest`
```typescript
export type RejectAgentApplicationRequest = RejectRequest
// RejectRequest: { reason: string }
```
Shape identical ✓. Alias in `types.ts` line ~158.

### `PortfolioPositionResponse = CompanyPositionResponse`
```typescript
export type PortfolioPositionResponse = CompanyPositionResponse
// CompanyPositionResponse: { company_id, company_name, logo_url, total_units,
//   sale_units, gift_units, total_paid_cents, avg_price_cents,
//   current_price_cents, current_value_cents, purchases_count }
```
Shape identical ✓. Alias in `types.ts` line ~347. `PortfolioResponse.positions` typed as `CompanyPositionResponse[]` in generated.ts; the alias makes `PortfolioPositionResponse[]` structurally equivalent — no conflict.

---

## Section 9: Frontend-only types beyond plain re-export

Reduced from 21 (first audit) to **7** after VELO refactor. All other narrowing unions removed.

| Name | Kind | Keep-reason |
|------|------|-------------|
| `UserRole` | union + runtime guard | Narrows `UserResponse.role: string`; `asUserRole()` is the only authorised entry point from `string` into `UserRole`. Exhaustiveness check via `satisfies readonly UserRole[]` catches missing values at compile time. |
| `KycStatus` | union + runtime guard | Same pattern. `asKycStatus()` used by `stores/auth.ts` to expose `kycStatus: KycStatus \| null` for typed comparisons in route guards and onboarding logic. |
| `PaginatedResponse<T>` | generic interface | Generic pagination helper; backend emits concrete list types, not a generic. |
| `ValidationErrorItem` | interface | FastAPI 422 error body; HTTP-boundary type, not in OpenAPI schema. |
| `BlockUserRequest` | alias | `= BlockRequest`; keeps call-site name explicit. |
| `RejectAgentApplicationRequest` | alias | `= RejectRequest`; keeps intent explicit at the call site. |
| `PortfolioPositionResponse` | alias | `= CompanyPositionResponse`; prevents confusion with `CompanySummaryResponse`. |

> **Δ vs first audit:** `UserRole` and `KycStatus` were removed during the initial B8 refactor but restored with runtime guards (`asUserRole`, `asKycStatus`) in the Sprint 4.4 follow-up. This is a strict improvement: types are narrower AND safe (no unsafe casts; unknown values resolve to `null`).

---

## Section 10: Risks / surprises

### 10.1 No direct `@/api/generated` imports ✓
No Vue component or utility file imports from `@/api/generated` directly. All types flow through `@/api/types`. ✓

### 10.2 No actionable TODO/FIXME/TD-F07 markers ✓
The "B7" references found in source files are retrospective documentation comments (`// F4.4 B7 UX:`, `// B7 / VELO migration`), not pending tasks. ✓

### 10.3 `available_packages` is now required — `?? 0` guards correctly removed
Sprint 4.4 made `available_packages: number` required (not `?: number`) in both `PublicProductResponse` and `PublicProductDetailResponse`. All three Vue consumers have correctly removed the `?? 0` fallback. The backend comment in generated.ts confirms: *"missing populate is a server bug, not a soft fallback."*

### 10.4 `price_per_pack_cents` is a new Sprint 4.4 field — verify backend deploy
`price_per_pack_cents: number` (required) was added to `PublicProductResponse` and `PublicProductDetailResponse`. Three Vue files already consume it. If the backend deploy lags the frontend, this field will be missing from API responses and render as `NaN` / `$NaN`. Confirm backend version matches generated.ts before releasing the frontend.

### 10.5 `inv.product.priceLabel` removed — check other locale files
`en.json` no longer has `inv.product.priceLabel` (replaced by `inv.product.pricePerPack`). The ru/de/ar i18n catchup commits (series `i18n: ru/de/ar catchup for F4.4 B2-B6 keys`) appear to cover this sprint range, but it is worth verifying that the `pricePerPack` key exists and `priceLabel` is absent in all four locale files to avoid missing-key fallbacks in non-English UIs.

### 10.6 `InstallmentView.vue` — `?? []` guard retained from B7 era
Line 117 comment: *"`?? []` compensation that B7 carried over from the previous schema."* Line 131: `const tranches = planConfig.value?.tranches ?? []`. This guard is for `plan_config.tranches` (JSONB parsing, not a B7-renamed field) and remains valid. No action needed, but the comment creates minor confusion — it refers to a B7 schema state, not a current issue.

### 10.7 `CompanyPositionResponse` not directly exported — only via alias
`CompanyPositionResponse` is imported in `types.ts` for the alias (`PortfolioPositionResponse = CompanyPositionResponse`) but is not itself re-exported. Code that tries to import `CompanyPositionResponse` from `@/api/types` will fail to resolve. Currently no Vue file does this (all use `PortfolioPositionResponse`), but the gap is worth noting for future consumers.

### 10.8 42 generated types still not surfaced via `types.ts`
These are primarily staff-facing admin/operational types (pool management, consistency checks, leaderboard, referral links, etc.) and not needed by current frontend views. No immediate risk, but any new view that reaches into `generated.ts` directly (bypassing `types.ts`) is a code smell — route those through `types.ts` instead.

### 10.9 `inv.available` still in use alongside `inv.market.packsAvailable`
`ProductDetailView.vue` line 197 uses `t('inv.available')` = "available" as the suffix in the availability stat block ("N available"). `ProductCard.vue` now uses `t('inv.market.packsAvailable')` = "packs available". These are two different screens showing the same data with slightly different labels. Intentional or inconsistency — worth confirming with design.

---

## Final state check

```
git status: On branch claude/audit-cbshome-frontend-rename-8X5oY
Modified: B7_AUDIT.md (this report — only file changed)
No other tracked files touched.
```

---

Audit complete. Review `B7_AUDIT.md`.
