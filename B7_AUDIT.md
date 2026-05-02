# B7 Frontend Rename — Audit Report

**Branch:** `main`
**Date:** 2026-05-01
**Scope:** Sprint 4.3 TD-F07 / Batch B7 — `units → package_size`, `sold_units → available_packages` in `PublicProductResponse` and related
**Status:** Read-only audit. No files were modified.

---

## Section 1: `generated.ts` inventory

Command run:
```bash
grep -E "^export (interface|type) " frontend/src/api/generated.ts \
  | sed -E 's/^export (interface|type) ([A-Za-z_]+).*/\2/' | sort -u
```

### Full list (116 names)

| # | Name |
|---|------|
| 1 | AgentApplicationListResponse |
| 2 | AgentApplicationResponse |
| 3 | AuthResponse |
| 4 | AvatarSessionResponse |
| 5 | AvatarStartRequest |
| 6 | AvatarStartResponse |
| 7 | BalanceResponse |
| 8 | BlockRequest |
| 9 | CommissionEntry |
| 10 | CommissionListResponse |
| 11 | CompanyAnalyticsResponse |
| 12 | CompanyDashboardResponse |
| 13 | CompanyPositionDetailResponse |
| 14 | CompanyPositionResponse |
| 15 | CompanyResponse |
| 16 | CompanySummaryResponse |
| 17 | CompanyTransactionResponse |
| 18 | ConsistencyResponse |
| 19 | CreateAddressRequest |
| 20 | CreateCompanyRequest |
| 21 | CreateEventRequest |
| 22 | CreateInstallmentPlanRequest |
| 23 | CreateInstallmentRequest |
| 24 | CreatePoolRequest |
| 25 | CreatePostRequest |
| 26 | CreateProductRequest |
| 27 | CreatePurchaseRequest |
| 28 | CreateRoadmapItemRequest |
| 29 | CreateStaffRequest |
| 30 | CreateWithdrawalRequest |
| 31 | CryptoWebhookRequest |
| 32 | DashboardStatsResponse |
| 33 | DashboardSummaryResponse |
| 34 | DepositAddressResponse |
| 35 | DocumentCreateRequest |
| 36 | DocumentResponse |
| 37 | DocumentSigningResponse |
| 38 | DocumentUpdateRequest |
| 39 | EmailLoginRequest |
| 40 | EmailRegisterRequest |
| 41 | EventListResponse |
| 42 | EventResponse |
| 43 | InstallmentPlanDetailResponse |
| 44 | InstallmentPlanListResponse |
| 45 | InstallmentPlanResponse |
| 46 | InstallmentPreviewRequest |
| 47 | InstallmentPreviewResponse |
| 48 | InstallmentPreviewSummary |
| 49 | InstallmentResponse |
| 50 | InstallmentTrancheResponse |
| 51 | KYCQueueItem |
| 52 | KYCRejectRequest |
| 53 | KYCStatusResponse |
| 54 | KYCSubmitResponse |
| 55 | KYCWebhookRequest |
| 56 | LeaderboardEntry |
| 57 | LeaderboardResponse |
| 58 | NotificationDeliveryResponse |
| 59 | NotificationListResponse |
| 60 | PaymentHistoryResponse |
| 61 | PaymentResponse |
| 62 | PayoutDetailsResponse |
| 63 | PoolEmbedResponse |
| 64 | PoolResponse |
| 65 | PortfolioResponse |
| 66 | PostListResponse |
| 67 | PostResponse |
| 68 | ProductResponse |
| 69 | PublicCompanyDetailResponse |
| 70 | PublicCompanyListResponse |
| 71 | PublicCompanyResponse |
| 72 | PublicProductDetailResponse |
| 73 | PublicProductListResponse |
| 74 | PublicProductResponse |
| 75 | PurchaseItemResponse |
| 76 | PurchaseResponse |
| 77 | ReadAllResponse |
| 78 | ReferralLinkListResponse |
| 79 | ReferralLinkResponse |
| 80 | ReferralStatsResponse |
| 81 | RejectRequest |
| 82 | RejectWithdrawalRequest |
| 83 | ReorderRoadmapRequest |
| 84 | ReversalResponse |
| 85 | ReversePaymentRequest |
| 86 | RoadmapItemResponse |
| 87 | SalesByMonthEntry |
| 88 | SalesByProductEntry |
| 89 | SelectRoleRequest |
| 90 | SemaphoreResult |
| 91 | StaffPaymentListResponse |
| 92 | StaffPaymentResponse |
| 93 | StaffProfileResponse |
| 94 | TelegramAuthRequest |
| 95 | TransactionListResponse |
| 96 | TransactionResponse |
| 97 | UnreadCountResponse |
| 98 | UpdateCompanyRequest |
| 99 | UpdateEventRequest |
| 100 | UpdateInstallmentRequest |
| 101 | UpdatePayoutDetailsRequest |
| 102 | UpdatePermissionsRequest |
| 103 | UpdatePoolRequest |
| 104 | UpdatePostRequest |
| 105 | UpdatePriceRequest |
| 106 | UpdateProductRequest |
| 107 | UpdateProductStatusRequest |
| 108 | UpdateRoadmapItemRequest |
| 109 | UserDetailResponse |
| 110 | UserListItem |
| 111 | UserListResponse |
| 112 | UserResponse |
| 113 | UserUpdate |
| 114 | VerifyEmailRequest |
| 115 | WithdrawalListResponse |
| 116 | WithdrawalResponse |

**Total count: 116**

> Note: The repo intro described 117 types; the actual grep count is 116. No discrepancy in content — just a documentation drift.

### Double-underscore names (`__`)

**(none found)** — all names are clean identifiers. Backend B-pragmatic has already resolved any OpenAPI name-mangling.

### `BalanceResponse` presence

`BalanceResponse` appears **exactly once** in `generated.ts` (line 61). ✓

---

## Section 2: `types.ts` inventory

Command run:
```bash
grep -E "^export (interface|type) " frontend/src/api/types.ts \
  | sed -E 's/^export (interface|type) ([A-Za-z_]+).*/\2/' | sort -u
```

### Full list (84 names)

| # | Name |
|---|------|
| 1 | AgentApplicationListResponse |
| 2 | AgentApplicationResponse |
| 3 | AgentApplicationStatusType |
| 4 | AuthResponse |
| 5 | AvatarSessionResponse |
| 6 | AvatarStartRequest |
| 7 | AvatarStartResponse |
| 8 | BalanceResponse |
| 9 | BlockUserRequest |
| 10 | CompanyPositionDetailResponse |
| 11 | CompanySummaryResponse |
| 12 | CreateAddressRequest |
| 13 | CreateInstallmentPlanRequest |
| 14 | CreatePurchaseRequest |
| 15 | CreateStaffRequest |
| 16 | CryptoNetwork |
| 17 | DashboardStatsResponse |
| 18 | DashboardSummaryResponse |
| 19 | DepositAddressResponse |
| 20 | DocumentResponse |
| 21 | DocumentSigningResponse |
| 22 | EmailLoginRequest |
| 23 | EmailRegisterRequest |
| 24 | EventListResponse |
| 25 | EventResponse |
| 26 | InstallmentPlanDetailResponse |
| 27 | InstallmentPlanListResponse |
| 28 | InstallmentPlanResponse |
| 29 | InstallmentPlanStatusType |
| 30 | InstallmentResponse |
| 31 | InstallmentTrancheResponse |
| 32 | InstallmentTrancheStatusType |
| 33 | KYCQueueItem |
| 34 | KYCRejectRequest |
| 35 | KYCStatusResponse |
| 36 | KYCSubmitResponse |
| 37 | KycStatus |
| 38 | PaginatedResponse |
| 39 | PaymentHistoryResponse |
| 40 | PaymentResponse |
| 41 | PaymentStatusType |
| 42 | PaymentType |
| 43 | PortfolioPositionResponse |
| 44 | PortfolioResponse |
| 45 | PostListResponse |
| 46 | PostOwnerType |
| 47 | PostResponse |
| 48 | PublicCompanyDetailResponse |
| 49 | PublicCompanyListResponse |
| 50 | PublicCompanyResponse |
| 51 | PublicProductDetailResponse |
| 52 | PublicProductListResponse |
| 53 | PublicProductResponse |
| 54 | PurchaseItemResponse |
| 55 | PurchaseLegalBasis |
| 56 | PurchaseResponse |
| 57 | PurchaseStatusType |
| 58 | ReferenceType |
| 59 | RejectAgentApplicationRequest |
| 60 | RejectWithdrawalRequest |
| 61 | ReversalResponse |
| 62 | ReversePaymentRequest |
| 63 | RoadmapItemResponse |
| 64 | SelectRoleRequest |
| 65 | StaffPaymentListResponse |
| 66 | StaffPaymentResponse |
| 67 | StaffPermissionKey |
| 68 | StaffPermissions |
| 69 | StaffProfileResponse |
| 70 | TelegramAuthRequest |
| 71 | TransactionListResponse |
| 72 | TransactionResponse |
| 73 | TransactionType |
| 74 | UpdatePermissionsRequest |
| 75 | UserDetailResponse |
| 76 | UserListItem |
| 77 | UserListResponse |
| 78 | UserResponse |
| 79 | UserRole |
| 80 | UserUpdate |
| 81 | ValidationErrorItem |
| 82 | VerifyEmailRequest |
| 83 | WithdrawalResponse |
| 84 | WithdrawalStatusType |

**Total count: 84**

---

## Section 3: Diff between `types.ts` and `generated.ts`

### 3a. In handwritten `types.ts` BUT NOT in `generated.ts` (21 frontend-only types)

These must remain in handwritten form after the VELO refactor.

| Name | Kind | Definition |
|------|------|------------|
| `AgentApplicationStatusType` | union | `type AgentApplicationStatusType = 'pending' \| 'approved' \| 'rejected'` |
| `BlockUserRequest` | interface | `interface BlockUserRequest { reason?: string \| null }` — **name differs** from generated `BlockRequest`; see Section 8 |
| `CryptoNetwork` | union | `type CryptoNetwork = 'TRC20' \| 'ERC20' \| 'BEP20' \| 'PoS'` |
| `InstallmentPlanStatusType` | union | `type InstallmentPlanStatusType = 'active' \| 'completed' \| 'defaulted'` |
| `InstallmentTrancheStatusType` | union | `type InstallmentTrancheStatusType = 'pending' \| 'paid' \| 'overdue' \| 'cancelled'` |
| `KycStatus` | union | `type KycStatus = 'not_started' \| 'submitted' \| 'approved' \| 'rejected'` |
| `PaginatedResponse` | generic interface | `interface PaginatedResponse<T> { items: T[]; total: number; page: number; per_page: number }` |
| `PaymentStatusType` | union | `type PaymentStatusType = 'frozen' \| 'confirmed' \| 'reversed' \| 'failed'` |
| `PaymentType` | union | `type PaymentType = 'crypto' \| 'card' \| 'bank'` |
| `PortfolioPositionResponse` | interface | Frontend rename of backend `CompanyPositionResponse`; see Section 8 |
| `PostOwnerType` | union | `type PostOwnerType = 'platform' \| 'company'` |
| `PurchaseLegalBasis` | union | `type PurchaseLegalBasis = 'sale' \| 'gift' \| 'installment_tranche'` |
| `PurchaseStatusType` | union | `type PurchaseStatusType = 'active' \| 'reversed'` |
| `ReferenceType` | union | `type ReferenceType = 'payment' \| 'purchase' \| 'withdrawal' \| 'installment_plan'` |
| `RejectAgentApplicationRequest` | interface | `interface RejectAgentApplicationRequest { reason: string }` — **name differs** from generated `RejectRequest`; see Section 8 |
| `StaffPermissionKey` | union | Long union of 8 permission key strings |
| `StaffPermissions` | alias | `type StaffPermissions = Partial<Record<StaffPermissionKey, boolean>>` |
| `TransactionType` | union | Long union of 14 `entity:event` string literals |
| `UserRole` | union | `type UserRole = 'investor' \| 'agent' \| 'company' \| 'staff' \| 'platform'` |
| `ValidationErrorItem` | interface | `interface ValidationErrorItem { loc: (string \| number)[]; msg: string; type: string }` — FastAPI 422 shape |
| `WithdrawalStatusType` | union | `type WithdrawalStatusType = 'pending' \| 'confirmed' \| 'processing' \| 'completed' \| 'rejected' \| 'failed'` |

### 3b. In `generated.ts` BUT NOT in `types.ts` (53 names — re-export candidates)

These are backend types not yet surfaced in the frontend. Wire them in during the VELO refactor.

BlockRequest, CommissionEntry, CommissionListResponse, CompanyAnalyticsResponse, CompanyDashboardResponse, CompanyPositionResponse, CompanyResponse, CompanyTransactionResponse, ConsistencyResponse, CreateCompanyRequest, CreateEventRequest, CreateInstallmentRequest, CreatePoolRequest, CreatePostRequest, CreateProductRequest, CreateRoadmapItemRequest, CreateWithdrawalRequest, CryptoWebhookRequest, DocumentCreateRequest, DocumentUpdateRequest, InstallmentPreviewRequest, InstallmentPreviewResponse, InstallmentPreviewSummary, KYCWebhookRequest, LeaderboardEntry, LeaderboardResponse, NotificationDeliveryResponse, NotificationListResponse, PayoutDetailsResponse, PoolEmbedResponse, PoolResponse, ProductResponse, ReadAllResponse, ReferralLinkListResponse, ReferralLinkResponse, ReferralStatsResponse, RejectRequest, ReorderRoadmapRequest, SalesByMonthEntry, SalesByProductEntry, SemaphoreResult, UnreadCountResponse, UpdateCompanyRequest, UpdateEventRequest, UpdateInstallmentRequest, UpdatePayoutDetailsRequest, UpdatePoolRequest, UpdatePostRequest, UpdatePriceRequest, UpdateProductRequest, UpdateProductStatusRequest, UpdateRoadmapItemRequest, WithdrawalListResponse

> Note: `BlockRequest` and `RejectRequest` are name-alias candidates (see Section 8), not straight re-exports.

### 3c. In BOTH (63 names — safe re-export candidates pending shape verification)

**Count: 63**

AgentApplicationListResponse, AgentApplicationResponse, AuthResponse, AvatarSessionResponse, AvatarStartRequest, AvatarStartResponse, BalanceResponse, CompanyPositionDetailResponse, CompanySummaryResponse, CreateAddressRequest, CreateInstallmentPlanRequest, CreatePurchaseRequest, CreateStaffRequest, DashboardStatsResponse, DashboardSummaryResponse, DepositAddressResponse, DocumentResponse, DocumentSigningResponse, EmailLoginRequest, EmailRegisterRequest, EventListResponse, EventResponse, InstallmentPlanDetailResponse, InstallmentPlanListResponse, InstallmentPlanResponse, InstallmentResponse, InstallmentTrancheResponse, KYCQueueItem, KYCRejectRequest, KYCStatusResponse, KYCSubmitResponse, PaymentHistoryResponse, PaymentResponse, PortfolioResponse, PostListResponse, PostResponse, PublicCompanyDetailResponse, PublicCompanyListResponse, PublicCompanyResponse, PublicProductDetailResponse, PublicProductListResponse, PublicProductResponse, PurchaseItemResponse, PurchaseResponse, RejectWithdrawalRequest, ReversalResponse, ReversePaymentRequest, RoadmapItemResponse, SelectRoleRequest, StaffPaymentListResponse, StaffPaymentResponse, StaffProfileResponse, TelegramAuthRequest, TransactionListResponse, TransactionResponse, UpdatePermissionsRequest, UserDetailResponse, UserListItem, UserListResponse, UserResponse, UserUpdate, VerifyEmailRequest, WithdrawalResponse

---

## Section 4: Field-shape mismatches between `types.ts` and `generated.ts`

For every name in Section 3c, only cases with at least one field mismatch are listed. Types that match exactly are omitted.

Legend: **G** = generated.ts, **H** = handwritten types.ts. `?:` means optional-and-nullable; `:` means required.

---

### `AgentApplicationResponse`

| Field | Handwritten | Generated | Issue |
|-------|-------------|-----------|-------|
| `rejection_reason` | `: string \| null` | `?: string \| null` | required vs optional |
| `cooldown_until` | `: string \| null` | `?: string \| null` | required vs optional |
| `reviewed_at` | `: string \| null` | `?: string \| null` | required vs optional |
| `reviewed_by` | `: string \| null` | `?: string \| null` | required vs optional |

---

### `AvatarSessionResponse`

| Field | Handwritten | Generated | Issue |
|-------|-------------|-----------|-------|
| `ended_at` | `: string \| null` | `?: string \| null` | required vs optional |

---

### `BalanceResponse`

| Field | Handwritten | Generated | Issue |
|-------|-------------|-----------|-------|
| `frozen` | `: number` | `?: number` | required vs optional |
| `confirmed` | `: number` | `?: number` | required vs optional |

> **Impact:** `dashboardStore.activeBalance.confirmed` is used as a hard number in PurchaseView and InstallmentView. If naively re-exported from generated.ts, `confirmed` becomes optional and those lines will require null-guards.

---

### `CreateAddressRequest`

| Field | Handwritten | Generated | Issue |
|-------|-------------|-----------|-------|
| `network` | `: CryptoNetwork` | `: string` | narrowed union vs bare string |

---

### `DashboardStatsResponse`

| Field | Handwritten | Generated | Issue |
|-------|-------------|-----------|-------|
| `users_by_role` | `: Record<string, number>` | `: Record<string, unknown>` | typed value vs unknown |

---

### `DocumentResponse`

| Field | Handwritten | Generated | Issue |
|-------|-------------|-----------|-------|
| `required_for_roles` | `: string[]` | `?: string[]` | required vs optional |
| `updated_at` | `: string \| null` | `?: string \| null` | required vs optional |
| `is_signed` | `: boolean` | `?: boolean \| null` | required non-null vs optional nullable |

---

### `EventResponse`

| Field | Handwritten | Generated | Issue |
|-------|-------------|-----------|-------|
| `description` | `: string \| null` | `?: string \| null` | required vs optional |
| `cover_url` | `: string \| null` | `?: string \| null` | required vs optional |
| `ends_at` | `: string \| null` | `?: string \| null` | required vs optional |
| `location` | `: string \| null` | `?: string \| null` | required vs optional |
| `url` | `: string \| null` | `?: string \| null` | required vs optional |
| `updated_at` | `: string \| null` | `?: string \| null` | required vs optional |

---

### `InstallmentPlanDetailResponse`

In `types.ts` this is declared as `extends InstallmentPlanResponse { tranches: InstallmentTrancheResponse[] }`. In `generated.ts` it is a standalone flat interface.

| Field | Handwritten | Generated | Issue |
|-------|-------------|-----------|-------|
| `tranches` | `: InstallmentTrancheResponse[]` (required) | `?: InstallmentTrancheResponse[]` | required vs optional |
| `status` | `: InstallmentPlanStatusType \| string` | `: string` | narrowed vs bare |

---

### `InstallmentPlanResponse`

| Field | Handwritten | Generated | Issue |
|-------|-------------|-----------|-------|
| `status` | `: InstallmentPlanStatusType \| string` | `: string` | narrowed vs bare |

---

### `InstallmentTrancheResponse`

| Field | Handwritten | Generated | Issue |
|-------|-------------|-----------|-------|
| `status` | `: InstallmentTrancheStatusType \| string` | `: string` | narrowed vs bare |

---

### `KYCQueueItem`

| Field | Handwritten | Generated | Issue |
|-------|-------------|-----------|-------|
| `email` | `: string \| null` | `?: string \| null` | required vs optional |
| `first_name` | `: string \| null` | `?: string \| null` | required vs optional |
| `last_name` | `: string \| null` | `?: string \| null` | required vs optional |

---

### `KYCStatusResponse`

| Field | Handwritten | Generated | Issue |
|-------|-------------|-----------|-------|
| `application_id` | `: string \| null` | `?: string \| null` | required vs optional |
| `application_status` | `: string \| null` | `?: string \| null` | required vs optional |

---

### `PaymentResponse` (investor-facing)

| Field | Handwritten | Generated | Issue |
|-------|-------------|-----------|-------|
| `payment_type` | `: PaymentType \| string` | `: string` | narrowed vs bare |
| `status` | `: PaymentStatusType \| string` | `: string` | narrowed vs bare |
| `frozen_until` | `: string \| null` | `?: string \| null` | required vs optional |
| `updated_at` | `: string \| null` | `?: string \| null` | required vs optional |

---

### `PortfolioResponse`

| Field | Handwritten | Generated | Issue |
|-------|-------------|-----------|-------|
| `positions` | `: PortfolioPositionResponse[]` | `: CompanyPositionResponse[]` | different element type identifier (same shape — see Section 8) |

---

### `PostResponse`

| Field | Handwritten | Generated | Issue |
|-------|-------------|-----------|-------|
| `owner_type` | `: PostOwnerType \| string` | `: string` | narrowed vs bare |
| `owner_id` | `: string \| null` | `?: string \| null` | required vs optional |
| `cover_url` | `: string \| null` | `?: string \| null` | required vs optional |
| `tags` | `: string[] \| null` | `?: string[] \| null` | required vs optional |
| `published_at` | `: string \| null` | `?: string \| null` | required vs optional |
| `updated_at` | `: string \| null` | `?: string \| null` | required vs optional |
| `is_dismissed` | `: boolean` | `?: boolean` | required vs optional |

---

### `PublicCompanyDetailResponse`

In `types.ts` this is `extends PublicCompanyResponse { roadmap: RoadmapItemResponse[] }`.
In `generated.ts` this is a flat interface.

| Field | Handwritten (combined) | Generated | Issue |
|-------|------------------------|-----------|-------|
| `total_supply` | **absent** (not in `PublicCompanyResponse`) | `: number` | missing field in handwritten |
| `shares_per_option` | **absent** | `: number` | missing field in handwritten |
| `roadmap` | `: RoadmapItemResponse[]` (required) | `?: RoadmapItemResponse[]` | required vs optional |

---

### `PublicCompanyResponse`

| Field | Handwritten | Generated | Issue |
|-------|-------------|-----------|-------|
| `total_supply` | **absent** | `: number` | missing field in handwritten |
| `shares_per_option` | **absent** | `: number` | missing field in handwritten |

---

### `PublicProductDetailResponse` ⚠️ B7 critical

In `types.ts` this is `extends PublicProductResponse { installments: InstallmentResponse[] }`.
In `generated.ts` this is a flat interface.

| Field | Handwritten (combined) | Generated | Issue |
|-------|------------------------|-----------|-------|
| `units` | `: number` (required) | **absent** — replaced by `package_size: number` | **B7 RENAME TARGET** |
| `sold_units` | `: number` (required) | **absent** — replaced by `available_packages?: number` | **B7 RENAME TARGET** |
| `package_size` | **absent** | `: number` (required) | new field name |
| `available_packages` | **absent** | `?: number` (optional) | new field name; semantics inverted (remaining packs, not sold count) |
| `cover_url` | `: string \| null` | `?: string \| null` | required vs optional |
| `company_name` | `: string` | `?: string` | required vs optional |
| `company_logo_url` | `: string \| null` | `?: string \| null` | required vs optional |
| `company_cover_url` | `: string \| null` | `?: string \| null` | required vs optional |
| `installments` | `: InstallmentResponse[]` (required) | `?: InstallmentResponse[]` | required vs optional |

---

### `PublicProductResponse` ⚠️ B7 critical

| Field | Handwritten | Generated | Issue |
|-------|-------------|-----------|-------|
| `units` | `: number` (required) | **absent** — replaced by `package_size: number` | **B7 RENAME TARGET** |
| `sold_units` | `: number` (required) | **absent** — replaced by `available_packages?: number` | **B7 RENAME TARGET** |
| `package_size` | **absent** | `: number` | new field name |
| `available_packages` | **absent** | `?: number` | new field name; now OPTIONAL |
| `cover_url` | `: string \| null` | `?: string \| null` | required vs optional |
| `company_name` | `: string` | `?: string` | required vs optional |
| `company_logo_url` | `: string \| null` | `?: string \| null` | required vs optional |
| `company_cover_url` | `: string \| null` | `?: string \| null` | required vs optional |

> **Critical note on `available_packages` optionality:** The generated type marks this `?: number`. All consumers that currently compute `units - sold_units` must be rewritten to use `available_packages ?? 0` (not just `available_packages`). Forgetting the nullish-coalescing guard will silently render `NaN` in the UI.

---

### `PurchaseItemResponse`

| Field | Handwritten | Generated | Issue |
|-------|-------------|-----------|-------|
| `legal_basis` | `: PurchaseLegalBasis \| string` | `: string` | narrowed vs bare |
| `status` | `: PurchaseStatusType \| string` | `: string` | narrowed vs bare |

---

### `PurchaseResponse`

| Field | Handwritten | Generated | Issue |
|-------|-------------|-----------|-------|
| `legal_basis` | `: PurchaseLegalBasis \| string` | `: string` | narrowed vs bare |
| `status` | `: PurchaseStatusType \| string` | `: string` | narrowed vs bare |

---

### `SelectRoleRequest`

| Field | Handwritten | Generated | Issue |
|-------|-------------|-----------|-------|
| `role` | `'investor' \| 'agent' \| 'company'` | `: string` | narrowed vs bare |

---

### `StaffPaymentResponse`

| Field | Handwritten | Generated | Issue |
|-------|-------------|-----------|-------|
| `payment_type` | `: PaymentType \| string` | `: string` | narrowed vs bare |
| `status` | `: PaymentStatusType \| string` | `: string` | narrowed vs bare |
| `frozen_until` | **absent** | `?: string \| null` | missing field in handwritten |
| `provider_data` | `: Record<string, unknown> \| null` | **absent** | extra field in handwritten (not in generated) |
| `updated_at` | `: string \| null` | `?: string \| null` | required vs optional |

> **Highest risk mismatch:** `provider_data` exists in `types.ts` but not in `generated.ts`. If any Vue component reads `payment.provider_data`, removing the handwritten definition will break that code silently. Verify before deleting.

---

### `StaffProfileResponse`

| Field | Handwritten | Generated | Issue |
|-------|-------------|-----------|-------|
| `permissions` | `: StaffPermissions` | `: Record<string, unknown>` | typed alias vs unknown |

---

### `TransactionResponse`

| Field | Handwritten | Generated | Issue |
|-------|-------------|-----------|-------|
| `type` | `: TransactionType \| string` | `: string` | narrowed vs bare |
| `reference_id` | `: string \| null` | `?: string \| null` | required vs optional |
| `reference_type` | `: ReferenceType \| string \| null` | `?: string \| null` | required + narrowed vs optional bare |
| `details` | `: Record<string, unknown> \| null` | `?: Record<string, unknown> \| null` | required vs optional |

---

### `UpdatePermissionsRequest`

| Field | Handwritten | Generated | Issue |
|-------|-------------|-----------|-------|
| All 8 fields | `?: boolean` | `?: boolean \| null` | non-nullable vs nullable optional |

---

### `UserDetailResponse`

| Field | Handwritten | Generated | Issue |
|-------|-------------|-----------|-------|
| `role` | `: UserRole` | `: string` | narrowed vs bare |
| `kyc_status` | `: KycStatus` | `: string` | narrowed vs bare |
| `updated_at` | `: string \| null` | `?: string \| null` | required vs optional |
| `email` | `: string \| null` | `?: string \| null` | required vs optional |
| `staff_profile` | `: StaffProfileResponse \| null` | `?: StaffProfileResponse \| null` | required vs optional |

---

### `UserListItem`

| Field | Handwritten | Generated | Issue |
|-------|-------------|-----------|-------|
| `role` | `: UserRole` | `: string` | narrowed vs bare |
| `kyc_status` | `: KycStatus` | `: string` | narrowed vs bare |
| `email` | `: string \| null` | `?: string \| null` | required vs optional |
| `first_name` | `: string \| null` | `?: string \| null` | required vs optional |
| `last_name` | `: string \| null` | `?: string \| null` | required vs optional |
| `staff_profile` | `: StaffProfileResponse \| null` | `?: StaffProfileResponse \| null` | required vs optional |

---

### `UserResponse`

| Field | Handwritten | Generated | Issue |
|-------|-------------|-----------|-------|
| `role` | `: UserRole` | `: string` | narrowed vs bare |
| `email` | `: string \| null` | `?: string \| null` | required vs optional |
| `kyc_status` | `: KycStatus` | `: string` | narrowed vs bare |
| `payout_details` | `: Record<string, unknown> \| null` | `?: Record<string, unknown> \| null` | required vs optional |
| `updated_at` | `: string \| null` | `?: string \| null` | required vs optional |

---

### `UserUpdate`

| Field | Handwritten | Generated | Issue |
|-------|-------------|-----------|-------|
| `profile` | `?: Record<string, unknown>` | `?: Record<string, unknown> \| null` | non-nullable vs nullable optional |
| `language` | `?: string` | `?: string \| null` | non-nullable vs nullable optional |

---

### `WithdrawalResponse`

| Field | Handwritten | Generated | Issue |
|-------|-------------|-----------|-------|
| `status` | `: WithdrawalStatusType \| string` | `: string` | narrowed vs bare |
| `payout_details_snapshot` | **absent** | `: Record<string, unknown>` | missing required field in handwritten |
| `rejection_reason` | `: string \| null` | `?: string \| null` | required vs optional |
| `confirmed_at` | `: string \| null` | `?: string \| null` | required vs optional |
| `processing_at` | `: string \| null` | `?: string \| null` | required vs optional |
| `completed_at` | `: string \| null` | `?: string \| null` | required vs optional |
| `rejected_at` | `: string \| null` | `?: string \| null` | required vs optional |
| `failed_at` | **absent** | `?: string \| null` | missing field in handwritten |

---

## Section 5: Vue/TS consumers of the renamed fields

### Search results

#### `\bunits\b` (excluding exempt patterns)

| File | Line | Content | In-scope? | Notes |
|------|------|---------|-----------|-------|
| `frontend/src/api/types.ts` | 388 | `  units: number` | ✓ | `PublicProductResponse.units` — **B7 rename target** |
| `frontend/src/api/types.ts` | 496 | `  units: number` | context only | `PurchaseResponse.units` — NOT renamed in B7 |
| `frontend/src/api/types.ts` | 803 | `  units: number` | context only | `PurchaseItemResponse.units` — NOT renamed in B7 |
| `frontend/src/components/shared/ProductCard.vue` | 45 | `() => props.product.units - props.product.sold_units,` | ✓ | availability computed |
| `frontend/src/views/investor/ProductDetailView.vue` | 90 | `return p ? p.units - p.sold_units : 0` | ✓ | availability computed |
| `frontend/src/views/investor/PurchaseView.vue` | 89 | `return p ? p.units * p.price_per_unit_cents : 0` | ✓ | `totalCents` computed |
| `frontend/src/views/investor/PurchaseView.vue` | 94 | `return p ? Math.max(p.units - p.sold_units, 0) : 0` | ✓ | `available` computed |
| `frontend/src/views/investor/PurchaseView.vue` | 277 | `{{ formatNumber(product.units, locale) }}` | ✓ | template — "Package size" label |
| `frontend/src/views/investor/InstallmentView.vue` | 180 | `return getTrancheUnits(planConfig.value, product.value.units, index)` | ✓ | passes `units` as `totalUnits` arg |
| `frontend/src/views/investor/CompanyPositionView.vue` | 304 | `{{ formatNumber(p.units, locale) }}` | ⚠️ OUT-OF-SCOPE | `p` is `PurchaseItemResponse` — `units` here is NOT the B7 renamed field; no change needed |

#### `sold_units`

| File | Line | Content | In-scope? |
|------|------|---------|-----------|
| `frontend/src/api/types.ts` | 391 | `  sold_units: number` | ✓ |
| `frontend/src/components/shared/ProductCard.vue` | 45 | `() => props.product.units - props.product.sold_units,` | ✓ |
| `frontend/src/views/investor/ProductDetailView.vue` | 90 | `return p ? p.units - p.sold_units : 0` | ✓ |
| `frontend/src/views/investor/PurchaseView.vue` | 94 | `return p ? Math.max(p.units - p.sold_units, 0) : 0` | ✓ |

#### `package_size`

| File | Line | Content | Notes |
|------|------|---------|-------|
| `frontend/src/api/generated.ts` | 259 | `  package_size: number` | `CreateProductRequest` field |
| `frontend/src/api/generated.ts` | 457 | `  package_size: number` | `InstallmentPreviewSummary` field |
| `frontend/src/api/generated.ts` | 650 | `  package_size: number` | `ProductResponse` (staff) field |
| `frontend/src/api/generated.ts` | 706 | `  package_size: number` | `PublicProductDetailResponse` field |
| `frontend/src/api/generated.ts` | 730 | `  package_size: number` | `PublicProductResponse` field |

No hits in any Vue component files yet. `package_size` is not yet referenced in Vue/TS consumers — the rename from B7 will introduce it.

#### `available_packages`

| File | Line | Content | Notes |
|------|------|---------|-------|
| `frontend/src/api/generated.ts` | 709 | `  available_packages?: number` | `PublicProductDetailResponse` field |
| `frontend/src/api/generated.ts` | 733 | `  available_packages?: number` | `PublicProductResponse` field |

No hits in any Vue component files yet. Same as `package_size` — not yet consumed.

### Summary of files needing changes in B7

| File | Changes needed |
|------|----------------|
| `frontend/src/api/types.ts` | Replace `units: number` + `sold_units: number` with `package_size: number` + `available_packages?: number` in `PublicProductResponse`; fix `PublicProductDetailResponse` extension accordingly |
| `frontend/src/components/shared/ProductCard.vue` | Line 45: `props.product.units - props.product.sold_units` → `props.product.available_packages ?? 0` |
| `frontend/src/views/investor/ProductDetailView.vue` | Line 90: `p.units - p.sold_units` → `p.available_packages ?? 0` |
| `frontend/src/views/investor/PurchaseView.vue` | Line 89: `p.units * p.price_per_unit_cents` → `p.package_size * p.price_per_unit_cents`; Line 94: `Math.max(p.units - p.sold_units, 0)` → `p.available_packages ?? 0`; Line 277: `product.units` → `product.package_size` |
| `frontend/src/views/investor/InstallmentView.vue` | Line 180: `product.value.units` → `product.value.package_size` |
| `frontend/src/utils/installmentPlans.ts` | **No changes needed.** `getTrancheUnits` accepts `totalUnits` as a plain `number` parameter; the call-site change in `InstallmentView.vue` is sufficient. |

---

## Section 6: i18n keys

### Specified keys

| Key | Status | Value (if present) |
|-----|--------|-------------------|
| `inv.market.packsAvailable` | **ABSENT** | — |
| `inv.product.packsAvailability` | **ABSENT** | — |
| `inv.product.soldOut` | **PRESENT** | `"Sold out"` |
| `inv.market.available` | **ABSENT** | — (but see note below) |

> Note on `inv.market.available`: There is no `inv.market.available` key. The "available" label used in ProductCard.vue (line 74) and ProductDetailView.vue (line 181) resolves from `inv.available` (top-level under the `inv` namespace), which is `"available"`. This is the legacy key referenced in the spec.

### All keys under `inv.market.*`

```
inv.market.title          = "Marketplace"
inv.market.subtitle       = "Available Investment Products"
inv.market.filter.all     = "All companies"
inv.market.filter.company = "Company"
inv.market.filter.title   = "Filter by company"
inv.market.filter.search  = "Search companies..."
inv.market.filter.clear   = "Clear filter"
inv.market.filter.empty   = "No companies found"
inv.market.empty.title          = "No products available"
inv.market.empty.desc           = "Check back later for new investment opportunities"
inv.market.empty.filteredTitle  = "No products for this company"
inv.market.empty.filteredDesc   = "Try another filter or clear it"
```

> No `inv.market.packsAvailable` key exists. B7 will need to add it if the spec requires a "N packs available" label on the marketplace card.

### All keys under `inv.product.*`

```
inv.product.notFound.title   = "Product not found"
inv.product.notFound.desc    = "This product may have been removed or is no longer available"
inv.product.backToMarket     = "Back to marketplace"
inv.product.priceLabel       = "Price per unit"
inv.product.availability     = "Availability"
inv.product.description      = "About"
inv.product.installments     = "Installment plans"
inv.product.installmentsEmpty = "No installment plans available for this product"
inv.product.installmentsBonus = "+{n} bonus units"
inv.product.buy              = "Buy now"
inv.product.soldOut          = "Sold out"
```

> No `inv.product.packsAvailability` key exists. B7 will need to add it if the spec requires a "packs available" label on the product detail stats grid.

### Adjacent relevant keys

```
inv.unit                    = "unit"          ← used as "/ unit" price suffix
inv.available               = "available"     ← used as "N available" suffix (legacy; to review in B7)
inv.purchase.packageSize    = "Package size"  ← already updated; used in PurchaseView.vue template
```

---

## Section 7: Sold-out logic in Vue files

### `ProductCard.vue`

```
Line 44-46:
  const available = computed(
    () => props.product.units - props.product.sold_units,
  )
```

The card renders availability as plain text (`{{ formatNumber(available, locale) }} {{ t('inv.available') }}`). There is **no sold-out indicator on the card** itself — no disabled state, no "Sold out" badge, no class binding tied to `available <= 0`. The card only shows how many units are available; sold-out state is only communicated implicitly by the number reaching 0.

**After B7:** `available` computed becomes `props.product.available_packages ?? 0`. The `?? 0` guard is mandatory because `available_packages` is optional in generated.ts (the backend may omit it).

### `ProductDetailView.vue`

```
Line 88-91:
  const available = computed<number>(() => {
    const p = product.value
    return p ? p.units - p.sold_units : 0
  })
```

Three bindings depend on `available`:

```
Line 209 (plan card class binding):
  :class="{ 'pd__plan--disabled': available <= 0 }"

Line 237 (buy button disabled):
  :disabled="available <= 0"

Lines 242-244 (buy button label):
  available > 0
    ? t('inv.product.buy')       → "Buy now"
    : t('inv.product.soldOut')   → "Sold out"
```

Additionally in `openInstallmentPlan()` (line 109):
```
  if (available.value <= 0) return
```

All four places gate on the same `available` computed. After B7, replacing the computed with `p.available_packages ?? 0` updates all four simultaneously.

---

## Section 8: Aliases needed

Three handwritten names have no exact match in generated.ts but map to a semantically identical generated name.

### 8a. `BlockUserRequest` → `BlockRequest`

| | Handwritten `BlockUserRequest` | Generated `BlockRequest` |
|-|-------------------------------|--------------------------|
| Definition | `interface BlockUserRequest { reason?: string \| null }` | `interface BlockRequest { reason?: string \| null }` |
| Shape identical? | **Yes** | |

**Recommendation:** `export type BlockUserRequest = BlockRequest` alias re-export. Any Vue component calling a block-user endpoint passes this type; keeping the name avoids a rename sweep.

### 8b. `RejectAgentApplicationRequest` → `RejectRequest`

| | Handwritten `RejectAgentApplicationRequest` | Generated `RejectRequest` |
|-|---------------------------------------------|--------------------------|
| Definition | `interface RejectAgentApplicationRequest { reason: string }` | `interface RejectRequest { reason: string }` |
| Shape identical? | **Yes** | |

**Recommendation:** `export type RejectAgentApplicationRequest = RejectRequest` alias re-export.

> Note: `RejectRequest` in `generated.ts` is the body for rejecting *agent applications* specifically (per the backend endpoint `POST /staff/agent-applications/{id}/reject`). The name `RejectRequest` is generic enough that it could confuse — the alias keeps the intent explicit on the frontend side.

### 8c. `PortfolioPositionResponse` → `CompanyPositionResponse`

| | Handwritten `PortfolioPositionResponse` | Generated `CompanyPositionResponse` |
|-|-----------------------------------------|-------------------------------------|
| All fields | `company_id, company_name, logo_url: string \| null, total_units, sale_units, gift_units, total_paid_cents, avg_price_cents, current_price_cents, current_value_cents, purchases_count: number` | Identical |
| Shape identical? | **Yes** | |

**Recommendation:** `export type PortfolioPositionResponse = CompanyPositionResponse` alias re-export. The renaming rationale is documented inline in `types.ts` (to distinguish from `CompanySummaryResponse`). That rationale is still valid.

**Important downstream effect:** `PortfolioResponse.positions` in `types.ts` is `PortfolioPositionResponse[]` but in `generated.ts` it is `CompanyPositionResponse[]`. After re-export, `PortfolioPositionResponse` and `CompanyPositionResponse` are the same TypeScript type, so this mismatch becomes structural and resolves automatically. No further action needed on `PortfolioResponse` itself.

---

## Section 9: Frontend-only types beyond plain re-export

These all remain in `types.ts` after the VELO refactor. None is a rename target in B7.

| Name | Kind | Keep-reason summary |
|------|------|---------------------|
| `AgentApplicationStatusType` | union | Narrows `AgentApplicationResponse.status: string`; no backend enum exported |
| `CryptoNetwork` | union | Frontend-owned selector; `CreateAddressRequest.network` is plain `string` in generated |
| `InstallmentPlanStatusType` | union | Narrows `InstallmentPlanResponse.status: string` |
| `InstallmentTrancheStatusType` | union | Narrows `InstallmentTrancheResponse.status: string` |
| `KycStatus` | union | Narrows `UserResponse.kyc_status: string`; also used in router guards |
| `PaginatedResponse<T>` | generic interface | Generic pagination helper not in OpenAPI (backend emits concrete types) |
| `PaymentStatusType` | union | Narrows payment status; reused by both investor and staff shapes |
| `PaymentType` | union | Narrows payment type; same |
| `PortfolioPositionResponse` | alias interface | Intentional rename of `CompanyPositionResponse` for frontend disambiguation (see Section 8c) |
| `PostOwnerType` | union | Narrows `PostResponse.owner_type: string` |
| `PurchaseLegalBasis` | union | Narrows `PurchaseResponse.legal_basis: string`; used in portfolio detail |
| `PurchaseStatusType` | union | Narrows `PurchaseResponse.status: string` |
| `ReferenceType` | union | Narrows `TransactionResponse.reference_type`; used in transaction detail sheet |
| `StaffPermissionKey` | union | Typed key for the permissions record; keeps UpdatePermissionsRequest fields type-safe |
| `StaffPermissions` | alias | `Partial<Record<StaffPermissionKey, boolean>>` helper; replaces `Record<string, unknown>` from generated |
| `TransactionType` | union | 14-literal union; used for transaction tab filtering and type display in TransactionListView |
| `UserRole` | union | Narrows `UserResponse.role: string`; used in routing and conditional rendering across many views |
| `ValidationErrorItem` | interface | FastAPI 422 error body shape; HTTP-boundary type, not in OpenAPI schema |
| `WithdrawalStatusType` | union | Narrows `WithdrawalResponse.status: string` |

---

## Section 10: Risks / surprises

### 10.1 No direct `@/api/generated` imports found

All Vue components and utility files import exclusively from `@/api/types`. No file bypasses the types facade. ✓

### 10.2 No TODO/FIXME/TD-F07 comments in frontend source

No inline markers referencing B7, TD-F07, or any pending fixme related to the rename were found. ✓

### 10.3 `available_packages` is optional — `NaN` risk in all consumers

`PublicProductResponse.available_packages?: number` is marked optional in `generated.ts`. The current pattern `units - sold_units` always produces a number. After B7, if any consumer writes `product.available_packages` without `?? 0`, the computed will be `undefined` and any arithmetic (e.g., `available <= 0`) will silently evaluate to `false`, making every product appear available. **Every B7-consumer site must use `?? 0`.**

### 10.4 `StaffPaymentResponse.provider_data` exists in `types.ts` but not in `generated.ts`

`types.ts` declares `provider_data: Record<string, unknown> | null` on `StaffPaymentResponse`. The generated type has no such field. Either:
- The backend never emitted `provider_data` and the field was added speculatively, or
- It was removed in a backend refactor that was not reflected in `types.ts`.

Search for any Vue component reading `payment.provider_data` before deleting it.

### 10.5 `WithdrawalResponse` is missing `payout_details_snapshot` and `failed_at`

`generated.ts` declares `payout_details_snapshot: Record<string, unknown>` (required) and `failed_at?: string | null`. Neither appears in `types.ts`. If any staff view renders payout details from a withdrawal object, it is currently untyped. This is independent of B7 but should be caught before the VELO re-export.

### 10.6 `PublicCompanyResponse` and `PublicCompanyDetailResponse` are missing `total_supply` / `shares_per_option`

Both fields are present in `generated.ts` but absent from the handwritten types. If any company-detail view wants to render total supply or shares-per-option, it currently has no typed path. After VELO re-export, they will appear automatically.

### 10.7 `InstallmentView.vue` line 180 IS a B7 rename target

`InstallmentView.vue` is listed in the spec file list. Line 180 passes `product.value.units` as the `totalUnits` argument to `getTrancheUnits`. The product is typed as `PublicProductDetailResponse`. This is a B7 rename target. Only the call-site changes (`product.value.units` → `product.value.package_size`); the `getTrancheUnits` signature in `installmentPlans.ts` does not change.

### 10.8 `CompanyPositionView.vue` is an out-of-scope `units` reference

`CompanyPositionView.vue:304` (`{{ formatNumber(p.units, locale) }}`) references `PurchaseItemResponse.units`, which is **not** being renamed in B7. The grep will produce a hit on this line during the B7 rename, but it is a false positive. The file is not in the spec list and should not be touched.

### 10.9 `ProductCard.vue` has no sold-out card state

After B7, `available_packages` will be `0` (or missing) when sold out. ProductCard currently shows `"0 available"` with no visual sold-out indicator. The spec's mention of `inv.product.soldOut` key only applies to ProductDetailView's CTA button. Whether the card itself needs a "Sold out" badge is not addressed by B7 spec, but worth flagging.

### 10.10 `PortfolioResponse` mismatch resolves automatically via alias

The `PortfolioResponse.positions` field is typed `PortfolioPositionResponse[]` in `types.ts` and `CompanyPositionResponse[]` in `generated.ts`. Once `PortfolioPositionResponse` is declared as a type alias for `CompanyPositionResponse` (Section 8c), TypeScript will treat them as the same type and the mismatch disappears. No additional change to `PortfolioResponse` is needed.

### 10.11 `PublicProductDetailResponse` extends pattern will break on VELO refactor

In `types.ts`, `PublicProductDetailResponse extends PublicProductResponse`. In `generated.ts`, it is a flat standalone interface. After VELO re-export, the extension pattern must be dropped — the generated flat interface already includes all fields from `PublicProductResponse` plus the detail-only fields. Keeping the `extends` after switching to the generated type would result in a duplicate-field conflict.

### 10.12 `inv.purchase.packageSize` key exists but `inv.product.packsAvailability` does not

PurchaseView already uses `t('inv.purchase.packageSize')` on line 274 to label the package size row — this i18n key was presumably added in an earlier sprint as part of Sprint 4.3 prep. However the `inv.product.packsAvailability` and `inv.market.packsAvailable` keys specified in the B7 spec are absent and must be added.

---

## Final state check

```
git status output: On branch claude/audit-cbshome-frontend-rename-8X5oY
Untracked files:
  B7_AUDIT.md

No modified tracked files.
```

Only `B7_AUDIT.md` is new. No existing tracked files were touched.

---

Audit complete. Review B7_AUDIT.md.
