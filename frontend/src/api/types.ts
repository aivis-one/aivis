// =============================================================================
// AIVIS.ONE Frontend -- API Type Definitions
// =============================================================================
//
// TypeScript interfaces matching backend Pydantic schemas.
// Source of truth: backend/app/modules/*/schemas.py
// =============================================================================

// Aliases from auto-generated OpenAPI types (B7 / VELO migration).
import type { BlockRequest, CompanyPositionResponse, RejectRequest } from './generated'

// ---------------------------------------------------------------------------
// User
// ---------------------------------------------------------------------------

export type { UserResponse } from './generated'

export type { UserUpdate } from './generated'

export type { SelectRoleRequest } from './generated'

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export type { EmailRegisterRequest } from './generated'

export type { EmailLoginRequest } from './generated'

export type { TelegramAuthRequest } from './generated'

export type { AuthResponse } from './generated'

export type { VerifyEmailRequest } from './generated'

// TASK-38 (2FA). LoginResponse replaces AuthResponse as the response
// shape for /email/login and /telegram -- see generated.ts's
// LoginResponse docstring (mirrored from backend/app/modules/auth/
// schemas.py) for the mfa_required discriminant.
export type { LoginResponse } from './generated'

export type { TwoFactorSetupRequest } from './generated'

export type { TwoFactorSetupResponse } from './generated'

export type { TwoFactorConfirmRequest } from './generated'

export type { TwoFactorConfirmResponse } from './generated'

export type { TwoFactorDisableRequest } from './generated'

export type { TwoFactorLoginVerifyRequest } from './generated'

export type { PasswordResetRequest } from './generated'

export type { PasswordResetConfirmRequest } from './generated'

export type { PasswordResetRequestResponse } from './generated'

// ---------------------------------------------------------------------------
// KYC
// ---------------------------------------------------------------------------

export type { KYCSubmitResponse } from './generated'

export type { KYCStatusResponse } from './generated'

// ---------------------------------------------------------------------------
// Documents
// ---------------------------------------------------------------------------

export type { DocumentResponse } from './generated'

export type { DocumentSigningResponse } from './generated'

// ---------------------------------------------------------------------------
// Pagination (generic)
// ---------------------------------------------------------------------------

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  per_page: number
}

// ---------------------------------------------------------------------------
// Validation error (FastAPI 422 detail format)
// ---------------------------------------------------------------------------

export interface ValidationErrorItem {
  loc: (string | number)[]
  msg: string
  type: string
}

// ===========================================================================
// Frontend-only narrowing types (Sprint 4.4 / B7 follow-up)
//
// Backend stores user role and KYC status as bare `String(20)` columns
// (no DB-side enum) and the OpenAPI generator surfaces them as plain
// `string` on UserResponse / UserListItem / UserDetailResponse. That
// makes ` === 'investor'` and ` === 'approved'` checks unsafe -- a
// typo in the literal is a silent runtime miss, not a compile-time
// error.
//
// Two pieces here:
//   1. The string-literal unions themselves -- the canonical list of
//      values the backend can actually emit. Sourced from
//      backend/app/modules/users/models.py (UserRole, KYCStatus).
//   2. Runtime guards that convert an unknown `string | null | undefined`
//      from the wire into `UserRole | null` (or `KycStatus | null`) by
//      checking against the union's value set. Unknown values resolve
//      to `null`, never to an unsafe cast -- so adding a new role on
//      the backend without rebuilding the frontend gives `null` and a
//      visible "fallback" path, not a silent type lie.
//
// Used by stores/auth.ts (computed role + kycStatus) and by any
// component that wants typed comparisons against UserResponse.role
// or UserResponse.kyc_status. The runtime guard lives next to the
// union so the two cannot drift.
// ===========================================================================

export type UserRole = 'investor' | 'agent' | 'company' | 'staff' | 'platform'

// Single source of truth for the runtime value list.
//
// `as const satisfies readonly UserRole[]` catches the first
// direction: a typo or a value that is NOT a UserRole fails the array
// literal -- the type checker rejects the file before the build.
//
// _USER_ROLE_VALUES_COMPLETE catches the OTHER direction: if a new
// value is added to the UserRole union but forgotten here, the
// conditional resolves to the error-object type, which is not
// assignable to `true`. The use-site assignment `const _: ... = true`
// is what fails -- a bare type alias would only show as a tooltip.
//
// Same paranoia pattern that StaffUsersView.vue uses for
// ALL_PERMISSION_KEYS / UpdatePermissionsRequest.
const _USER_ROLE_VALUES_ARRAY = [
  'investor',
  'agent',
  'company',
  'staff',
  'platform',
] as const satisfies readonly UserRole[]

type _UserRoleValuesComplete =
  Exclude<UserRole, (typeof _USER_ROLE_VALUES_ARRAY)[number]> extends never
    ? true
    : { readonly error: 'UserRole has values missing from _USER_ROLE_VALUES_ARRAY' }
const _userRoleValuesComplete: _UserRoleValuesComplete = true
void _userRoleValuesComplete

const _USER_ROLE_VALUES: ReadonlySet<UserRole> = new Set(_USER_ROLE_VALUES_ARRAY)

/**
 * Narrow an unknown `string | null | undefined` from the wire into
 * `UserRole | null`. Returns `null` for missing or unrecognised values
 * -- callers MUST handle the null path (block the action, redirect to
 * a generic dashboard, etc.) rather than assuming a default role.
 *
 * The function is the only authorised entry point from `string` into
 * `UserRole`. Direct `as UserRole` casts elsewhere are a code smell.
 */
export function asUserRole(raw: string | null | undefined): UserRole | null {
  if (raw === null || raw === undefined) return null
  return _USER_ROLE_VALUES.has(raw as UserRole) ? (raw as UserRole) : null
}

export type KycStatus = 'not_started' | 'submitted' | 'approved' | 'rejected'

// Same two-direction guard as UserRole above.
const _KYC_STATUS_VALUES_ARRAY = [
  'not_started',
  'submitted',
  'approved',
  'rejected',
] as const satisfies readonly KycStatus[]

type _KycStatusValuesComplete =
  Exclude<KycStatus, (typeof _KYC_STATUS_VALUES_ARRAY)[number]> extends never
    ? true
    : { readonly error: 'KycStatus has values missing from _KYC_STATUS_VALUES_ARRAY' }
const _kycStatusValuesComplete: _KycStatusValuesComplete = true
void _kycStatusValuesComplete

const _KYC_STATUS_VALUES: ReadonlySet<KycStatus> = new Set(_KYC_STATUS_VALUES_ARRAY)

/**
 * Narrow an unknown `string | null | undefined` from the wire into
 * `KycStatus | null`. Same contract as `asUserRole`: unknown values
 * become `null`, never an unsafe cast.
 *
 * Used by stores/auth.ts to expose `kycStatus: KycStatus | null` so
 * gating checks like `kycStatus === 'approved'` are typed.
 */
export function asKycStatus(raw: string | null | undefined): KycStatus | null {
  if (raw === null || raw === undefined) return null
  return _KYC_STATUS_VALUES.has(raw as KycStatus) ? (raw as KycStatus) : null
}

// ===========================================================================
// Staff (Phase F3) -- matches backend/app/modules/staff/* and related schemas
// ===========================================================================

// ---------------------------------------------------------------------------
// Staff profile (shared with admin types)
// ---------------------------------------------------------------------------

export type { StaffProfileResponse } from './generated'

// ---------------------------------------------------------------------------
// Staff: dashboard (Sprint 3.3)
// ---------------------------------------------------------------------------

export type { DashboardStatsResponse } from './generated'

// ---------------------------------------------------------------------------
// Staff: users (Sprint 3.1 + 3.3)
// ---------------------------------------------------------------------------

export type { UserListItem } from './generated'

export type { UserListResponse } from './generated'

export type { UserDetailResponse } from './generated'

// Backend: BlockRequest. Aliased to keep the call-site name explicit
// (block USER vs. any other future block target).
export type BlockUserRequest = BlockRequest

export type { CreateStaffRequest } from './generated'

export type { UpdatePermissionsRequest } from './generated'

// ---------------------------------------------------------------------------
// Staff: KYC queue (Sprint 3.3)
// ---------------------------------------------------------------------------

export type { KYCQueueItem } from './generated'

export type { KYCRejectRequest } from './generated'

// ---------------------------------------------------------------------------
// Staff: payments (Sprint 5.3)
// ---------------------------------------------------------------------------

export type { StaffPaymentResponse } from './generated'

export type { StaffPaymentListResponse } from './generated'

export type { ReversePaymentRequest } from './generated'

export type { ReversalResponse } from './generated'

// ---------------------------------------------------------------------------
// Withdrawals + payout details (Sprint 6.3)
//
// Mix of user-side and staff-side schemas:
//   - User:  WithdrawalResponse, WithdrawalListResponse,
//            PayoutDetailsResponse  (consumed by F5.2 B3/B4 in
//            CompanyBalanceView and api/{withdrawals,users}.ts)
//   - Staff: RejectWithdrawalRequest, StaffWithdrawalListResponse
//            (consumed by staff queue UI)
// ---------------------------------------------------------------------------

export type { WithdrawalResponse } from './generated'

export type { WithdrawalListResponse } from './generated'

export type { PayoutDetailsResponse } from './generated'

export type { RejectWithdrawalRequest } from './generated'

export type { StaffWithdrawalListResponse } from './generated'

// ---------------------------------------------------------------------------
// Staff: avatar (Sprint 3.2)
// ---------------------------------------------------------------------------

export type { AvatarStartRequest } from './generated'

export type { AvatarStartResponse } from './generated'

export type { AvatarSessionResponse } from './generated'

// ---------------------------------------------------------------------------
// Staff: agent applications (Sprint 7.1)
// ---------------------------------------------------------------------------

export type { AgentApplicationResponse } from './generated'

// Backend: RejectRequest (generic name -- bound to the agent-application
// reject endpoint POST /staff/agent-applications/{id}/reject). Aliased
// on the frontend to keep the intent explicit at the call site.
export type RejectAgentApplicationRequest = RejectRequest

// ===========================================================================
// Phase F4.1 -- Public storefront (products + companies)
//
// Matches backend/app/modules/products/schemas.py (Public*) and
// backend/app/modules/companies/schemas.py (Public*, RoadmapItemResponse).
// ===========================================================================

// ---------------------------------------------------------------------------
// Products: installment plan template (public, surfaced on product detail)
// ---------------------------------------------------------------------------

export type { InstallmentResponse } from './generated'

// ---------------------------------------------------------------------------
// Products: public storefront (Sprint 4.2 + F4.1 denormalisation)
// ---------------------------------------------------------------------------

export type { PublicProductResponse } from './generated'

export type { PublicProductDetailResponse } from './generated'

export type { PublicProductListResponse } from './generated'

// ---------------------------------------------------------------------------
// Companies: public storefront (Sprint 4.1)
// ---------------------------------------------------------------------------

export type { RoadmapItemResponse } from './generated'

export type { PublicCompanyResponse } from './generated'

export type { PublicCompanyDetailResponse } from './generated'

export type { PublicCompanyListResponse } from './generated'

// ===========================================================================
// Phase F5 -- Company UI (Sprint 4.5 endpoint, Sprint 4.3 B5 dashboard
//                          + analytics)
//
// Matches:
//   backend/app/modules/companies/router.py     GET /companies/me
//     -> CompanyResponse (staff-side full profile)
//   backend/app/modules/company_dashboard/...   GET /company/dashboard
//     -> CompanyDashboardResponse
//   backend/app/modules/company_dashboard/...   GET /company/analytics
//     -> CompanyAnalyticsResponse
//
// CompanyResponse is the staff-side schema. The public /companies/{id}
// endpoint emits PublicCompanyDetailResponse (no distribution_config,
// no user_id, no updated_at) and 404s on non-active status -- which
// is wrong for the company-itself caller. Sprint 4.5 added
// /companies/me precisely to give the company-role caller their full
// profile via the staff schema. The frontend uses it for Settings and
// for acquiring `company_id` to drive products / analytics views.
//
// CompanyDashboardResponse / CompanyAnalyticsResponse are already
// generated by Sprint 4.3 B5; this section just surfaces them via
// types.ts so Phase F5 components don't reach into generated.ts
// directly.
//
// Sub-types (BalanceResponse, PoolEmbedResponse, CompanyTransactionResponse,
// SalesByMonthEntry, SalesByProductEntry) are pulled in transitively
// from generated.ts when the parent types are imported -- no separate
// re-exports needed here.
// ===========================================================================

export type { CompanyResponse } from './generated'

// TASK-30 ruling 10/12 + TASK-39 item 6 (time-boxed supersession, owner
// decision 2026-08): PATCH /api/v1/companies/me project self-service
// body. Separate type from UpdateCompanyRequest (the staff-side PATCH
// body, exported below in the staff-companies block) -- carries the
// project-editable field subset, now including name / price_per_unit_cents
// / total_supply / shares_per_option alongside the original presentation
// fields (distribution_config stays admin-only, unaffected). `status` is
// restricted server-side (update_own_company) to the single ACTIVE ->
// HIDDEN transition. See generated.ts docstring for the full rationale.
export type { UpdateOwnCompanyRequest } from './generated'

export type { CompanyDashboardResponse } from './generated'

export type { CompanyAnalyticsResponse } from './generated'

export type { PoolEmbedResponse } from './generated'

export type { CompanyTransactionResponse } from './generated'

export type { SalesByMonthEntry } from './generated'

export type { SalesByProductEntry } from './generated'

// ===========================================================================
// Phase F4.2 -- Purchase + Installment + Dashboard summary
//
// Matches:
//   backend/app/modules/purchases/schemas.py       (Sprint 6.1)
//   backend/app/modules/installments/schemas.py    (Sprint 6.2)
//   backend/app/modules/dashboard/schemas.py       (Sprint 9.2)
//
// Status/legal-basis unions keep a `| string` escape hatch so an
// unknown backend enum value cannot narrow the response type into
// a runtime type error -- same pattern used for staff payments /
// withdrawals above.
// ===========================================================================

// ---------------------------------------------------------------------------
// Purchase (Sprint 6.1)
// ---------------------------------------------------------------------------

export type { CreatePurchaseRequest } from './generated'

export type { PurchaseResponse } from './generated'

// ---------------------------------------------------------------------------
// Installment plans (Sprint 6.2)
// ---------------------------------------------------------------------------

export type { CreateInstallmentPlanRequest } from './generated'

export type { InstallmentTrancheResponse } from './generated'

export type { InstallmentPlanResponse } from './generated'

export type { InstallmentPlanDetailResponse } from './generated'

export type { InstallmentPlanListResponse } from './generated'

// ---------------------------------------------------------------------------
// Dashboard summary (Sprint 9.2)
//
// GET /api/v1/dashboard/summary returns ledger balances plus a
// per-company portfolio breakdown. F4.2 uses active_balance.confirmed
// as the spendable figure on the purchase/installment confirm screens;
// frozen amounts are excluded by the backend when executing a sale.
// ---------------------------------------------------------------------------

export type { BalanceResponse } from './generated'

export type { CompanySummaryResponse } from './generated'

export type { DashboardSummaryResponse } from './generated'

// ===========================================================================
// Phase F4.3 -- Investor payments (deposit) + transactions event log
//
// Matches:
//   backend/app/modules/payments/schemas.py       (Sprint 5.2, H7)
//     CreateInvoiceRequest, InvoiceResponse,
//     SubmitTxidRequest, TxidResultResponse,
//     PaymentResponse (investor view -- no user_id/provider_data),
//     PaymentHistoryResponse
//   backend/app/modules/transactions/schemas.py   (Sprint 6.4)
//   backend/app/modules/transactions/constants.py (TransactionType,
//     ReferenceType)
//
// PaymentResponse is the INVESTOR-facing shape; Staff already has
// its own StaffPaymentResponse above that adds user_id and
// provider_data. They are intentionally independent types.
//
// PaymentType / PaymentStatusType unions are reused from the Staff
// block above -- same backend enum, same `| string` escape hatch.
// ===========================================================================

// ---------------------------------------------------------------------------
// Crypto deposit invoices (H7)
//
// THERE IS NO CryptoNetwork UNION AND THERE MUST NOT BE ONE. The note
// that stood here promised a strict union over TRC20 | ERC20 | BEP20 |
// PoS on the grounds that "the frontend owns what it sends". It does
// not: which networks are served is the payments service's fact, it
// refuses the rest with 400 network_not_supported, and a union here
// would be a second list that disagrees with that one silently -- the
// disagreement surfacing only as a user's refused deposit.
//
// For the record, no such union was ever declared. The note described a
// type that did not exist and both `network` fields were plain strings
// the whole time, which is why removing the note removes nothing.
//
// The one network name this frontend sends lives in
// InvestorDepositView.vue as a const. That const says what this screen
// asks for; it is not a registry of what is available.
// ---------------------------------------------------------------------------

// THESE FOUR RE-EXPORTS DO NOT RESOLVE UNTIL THE GENERATOR HAS RUN, AND
// THAT IS THE INTENDED STATE OF THIS COMMIT. generated.ts is machine
// -owned and says so in its own header; H7 changed the backend schemas
// these names come from, so the file is simply behind until
// backend/scripts/generate_ts_types.py is run against a live instance
// and its output is committed.
//
// Declaring the four shapes by hand here would have made the tree
// type-check today and left a permanent duplicate: the generator emits
// the same four names, so after the next run there would be two
// declarations of each, drifting silently and with nothing in the tree
// to remind anyone to remove one. A build that fails loudly for one
// cycle was chosen over a duplicate that fails quietly forever.
//
// What this costs, precisely: `npm run type-check` fails, and
// `npm run build` fails because it runs the type-check first. `vite
// build` on its own still produces a working bundle -- these are
// type-only exports and are erased before bundling -- so the failure is
// a gate, not a broken application.
export type { CreateInvoiceRequest } from './generated'

export type { InvoiceResponse } from './generated'

export type { SubmitTxidRequest } from './generated'

export type { TxidResultResponse } from './generated'

// ---------------------------------------------------------------------------
// Payment history (Sprint 5.2) -- investor view
//
// `payment_type` and `status` are strings on the backend (not enum
// columns), so union + `| string` escape matches the Staff pattern.
// ---------------------------------------------------------------------------

export type { PaymentResponse } from './generated'

export type { PaymentHistoryResponse } from './generated'

// ---------------------------------------------------------------------------
// Transactions: immutable event log (Sprint 6.4)
//
// Type format is `{entity}:{event}` -- backend accepts either an
// exact match (`deposit:received`) or a trailing-colon prefix
// (`deposit:`) in the `type` query parameter. F4.3 TransactionsView
// uses the prefix form for category tabs.
// ---------------------------------------------------------------------------

export type { TransactionResponse } from './generated'

export type { TransactionListResponse } from './generated'

// ===========================================================================
// Phase F4.4 -- Portfolio + Certificates + Agent applications (investor)
//
// Matches:
//   backend/app/modules/portfolio/schemas.py              (Sprint 9.2)
//     CompanyPositionResponse       -> PortfolioPositionResponse
//     PortfolioResponse
//     PurchaseItemResponse
//     CompanyPositionDetailResponse
//   backend/app/modules/agent_applications/constants.py   (Sprint 7.1)
//     AgentApplicationStatus        -> AgentApplicationStatusType
//
// NAMING NOTE -- backend `CompanyPositionResponse` is renamed to
// `PortfolioPositionResponse` on the frontend. Rationale:
// `CompanySummaryResponse` (already above in the F4.2 block) lives
// inside DashboardSummaryResponse.companies[] and carries a
// narrower shape (no sale/gift split, no avg_price). Keeping the
// backend's "CompanyPosition" name next to "CompanySummary" invited
// exactly the confusion this frontend typing should prevent. The
// wire contract is unchanged -- only the TypeScript identifier.
//
// `AgentApplicationResponse` is NOT re-declared here -- the staff
// block above already exports it, and both investor and staff
// endpoints return the same shape. `AgentApplicationStatusType`
// below is a new string union that the staff block only alluded to
// via the bare `status: string` field; no breakage -- it's a
// compatible refinement callers may opt into.
// ===========================================================================

// ---------------------------------------------------------------------------
// Portfolio: per-company aggregate in the top-level list (Sprint 9.2)
//
// Backend: CompanyPositionResponse. Renamed on the frontend to
// disambiguate from CompanySummaryResponse (F4.2).
//
// `avg_price_cents` is SUM(paid_cents) / SUM(units WHERE legal_basis='sale').
// If sale_units is zero (gift-only portfolio in this company), the
// backend returns 0 -- callers should not divide by it without a
// guard, but for display `formatPrice(0)` renders as '$0.00' which
// is the intended empty state.
// ---------------------------------------------------------------------------

export type PortfolioPositionResponse = CompanyPositionResponse

export type { PortfolioResponse } from './generated'

// ---------------------------------------------------------------------------
// Portfolio: per-company detail + paginated purchases (Sprint 9.2)
//
// Backend: CompanyPositionDetailResponse. The aggregate block
// mirrors PortfolioPositionResponse minus purchases_count (it's
// replaced by `total` which is the count used for pagination).
// PurchaseItemResponse is a slimmer shape than F4.2's
// PurchaseResponse -- no investor_id/company_id (implied by the
// route) and no currency (single-currency MVP).
// ---------------------------------------------------------------------------

export type { PurchaseItemResponse } from './generated'

export type { CompanyPositionDetailResponse } from './generated'

// ---------------------------------------------------------------------------
// Agent applications: status union (Sprint 7.1)
//
// Backend enum AgentApplicationStatus. Terminal: approved, rejected.
// Pending is the only non-terminal. `rejected -> pending` is modelled
// as a NEW AgentApplication row, not a status change -- the old row
// stays rejected with cooldown_until set.
//
// The existing `AgentApplicationResponse.status: string` field in
// the staff block above remains `string` for compatibility; callers
// that want the narrower union can cast via the `| string` escape
// hatch pattern used elsewhere (PaymentStatusType, etc.).
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Agent applications: investor list wrapper (Sprint 7.1)
//
// Backend: AgentApplicationListResponse -- returned by
// GET /api/v1/agent-applications/me. Uniquely for this endpoint
// the shape is `{ items, total }` with no `page` / `per_page`
// echoed back (the backend schema omits them). The investor-side
// UI does not paginate -- per-user application counts are tiny --
// so the absence of page/per_page is irrelevant at the consumer.
//
// The staff queue endpoint returns a plain `list[AgentApplicationResponse]`
// with no wrapper at all, which is why this list type was not
// needed before F4.4.
// ---------------------------------------------------------------------------

export type { AgentApplicationListResponse } from './generated'

// ===========================================================================
// Phase F9.1 -- Posts + Events (public feed)
//
// Matches backend/app/modules/posts/schemas.py (Sprint 9.1).
//
// F4.4 B2 touches only the Post side: InvestorDashboardView uses the
// top-N posts widget. Full Posts + Events UI (detail, filters, banner
// dismiss, upcoming events) lands in F9.2. The typed surface is kept
// intentionally narrow for now -- just enough for the dashboard probe.
// `EventResponse` is also declared here so F9.2 can pick it up without
// another types.ts commit.
// ===========================================================================

// ---------------------------------------------------------------------------
// Posts
//
// Backend: Post.owner_type is one of "platform" | "company" (Literal
// in Pydantic CreatePostRequest), but the response keeps it as bare
// `str` for forward compatibility. Mirror with the union + `| string`
// escape hatch.
//
// `is_dismissed` is computed per-user (LEFT JOIN on PostDismiss) and
// is `false` for anonymous callers. The dashboard widget treats it
// as a read-only hint; full dismiss flow arrives in F9.2.
// ---------------------------------------------------------------------------

export type { PostResponse } from './generated'

export type { PostListResponse } from './generated'

// Company self-service post write bodies (TASK-30 W4, POST/PATCH
// /api/v1/company/posts). Distinct from the staff CreatePostRequest/
// UpdatePostRequest -- no owner_type/owner_id/is_banner, the caller's
// own company is resolved server-side.
export type { CreateCompanyPostRequest } from './generated'

export type { UpdateCompanyPostRequest } from './generated'

// ---------------------------------------------------------------------------
// Events (declared for F9.2 completeness, not consumed in F4.4)
// ---------------------------------------------------------------------------

export type { EventResponse } from './generated'

export type { EventListResponse } from './generated'

// ===========================================================================
// iter 2.5 -- R2 §7.1 + R2 §3.3 (company attachments, Investor read flow)
//
// The auth-flow attachment endpoints landed in iter 2.2 backend; the
// frontend simply did not call them until iter 2.5. The Investor
// CompanyOverviewView consumes the list to render the "Документы
// компании" section (L1-grouping by category, mime icons, client-side
// language filter, hide-when-empty).
//
// Source of truth: backend/app/modules/companies/attachments_router.py
//   and backend/app/modules/companies/schemas.py::AttachmentResponse.
//
// AttachmentPatchBody was NOT re-exported here at first -- staff UI
// (R2 §6.2) shipped read-only in iter 2.7 with no write form yet. TASK-30
// company self-service (api/company-attachments.ts) is the first
// consumer that needs it, so it is re-exported below alongside
// ReorderAttachmentsRequest (already re-exported for staff, iter 2.7 C2).
//
// Public-flow variant (AttachmentResponse via /api/v1/public/...) uses
// the same DTO shape; when iter 2.6 wired PublicShell, no new type
// re-export was required.
// ===========================================================================

export type { AttachmentResponse } from './generated'

export type { AttachmentPatchBody } from './generated'

// ===========================================================================
// iter 2.7 Block B -- Staff Platform tab (posts / events / companies write
//                                          surfaces + staff company list)
//
// The Staff Platform tab (R1 §4) drives create / update flows that the
// earlier read-only re-exports above did not need:
//
//   - Posts / Events: the F9.1 section re-exported the read shapes
//     (PostResponse / PostListResponse / EventResponse /
//     EventListResponse) for the dashboard widget and public feed.
//     Block B adds the staff write shapes (Create* / Update*) consumed
//     by PostListEditor and EventEditor via api/staff-posts.ts and
//     api/staff-events.ts.
//
//   - Companies: CompanyListResponse backs StaffCompaniesListView's
//     all-statuses list (api/staff-companies.ts::fetchStaffCompanies),
//     distinct from the public PublicCompanyListResponse already
//     re-exported above. PriceHistoryListResponse backs the Block C
//     price-history surface; declared here so Block C picks it up
//     without another types.ts commit (same forward-declare pattern
//     as the F9.1 EventResponse note above).
//
// Source of truth:
//   backend/app/modules/posts/schemas.py     (Create/Update Post/Event)
//   backend/app/modules/companies/schemas.py (CompanyListResponse,
//                                             PriceHistoryListResponse)
// ===========================================================================

// ---------------------------------------------------------------------------
// Posts / Events -- staff write surfaces
// ---------------------------------------------------------------------------

export type { CreatePostRequest } from './generated'

export type { UpdatePostRequest } from './generated'

export type { CreateEventRequest } from './generated'

export type { UpdateEventRequest } from './generated'

// ---------------------------------------------------------------------------
// Companies -- staff list + price history (price history forward-declared
// for Block C)
// ---------------------------------------------------------------------------

export type { CompanyListResponse } from './generated'

// Staff-side PATCH /api/v1/staff/companies/{id} body (name / description /
// media / distribution_config / status). No direction restriction on
// `status` at this type level -- update_company() validates against
// VALID_COMPANY_STATUS_TRANSITIONS server-side: hidden -> {active,
// archived}, active -> {hidden, archived}, archived -> {} (terminal,
// no transition out of it for anyone, staff included). See
// backend/app/modules/companies/constants.py.
export type { UpdateCompanyRequest } from './generated'

// Promote an EXISTING user to company (TASK-30 admin-capability gap,
// POST /staff/companies/assign). Mirrors CreateCompanyRequest minus
// email/password, plus user_id. See backend/app/modules/companies/
// schemas.py::AssignCompanyRequest.
export type { AssignCompanyRequest } from './generated'

// Create a BRAND-NEW company (user + profile) in one call (POST
// /staff/companies). See backend/app/modules/companies/
// schemas.py::CreateCompanyRequest.
export type { CreateCompanyRequest } from './generated'

export type { PriceHistoryListResponse } from './generated'

// Admin audit feed of project writes (TASK-30 W3, GET
// /api/v1/staff/audit/companies). CompanyAuditEntryResponse mirrors one
// AuditLog row recorded by record_audit(target_type="company");
// CompanyAuditFeedResponse is the paginated envelope.
export type { CompanyAuditEntryResponse } from './generated'

export type { CompanyAuditFeedResponse } from './generated'

// Company self-service audit feed (TASK-39 item 7, GET
// /api/v1/company/audit). DELIBERATELY NARROWER than
// CompanyAuditEntryResponse above -- no actor_id / performed_by /
// on_behalf_of, no raw `data`, only changed_fields (field NAMES, never
// values). See backend/app/modules/audit/schemas.py for the full
// reasoning.
export type { CompanySelfAuditEntryResponse } from './generated'

export type { CompanySelfAuditFeedResponse } from './generated'

// CompanyDetailResponse (staff): CompanyResponse + inline roadmap.
// Backed by GET /staff/companies/{id} (iter 2.7 Block C enabler
// mini-iter). Consumed by StaffCompanyDetailView (header name) and
// StaffCompanyProfileSection (read-only profile inspection).
export type { CompanyDetailResponse } from './generated'

// Price change (iter 2.7 C2). UpdatePriceRequest is the PATCH body for
// /staff/companies/{id}/price; PriceHistoryResponse types each row of
// the price-history table rendered by StaffCompanyPriceSection.
export type { UpdatePriceRequest } from './generated'

export type { PriceHistoryResponse } from './generated'

// Supply change (TASK-39 item 6 dilution ruling, 2026-08-29).
// UpdateSupplyRequest is the PATCH body for /staff/companies/{id}/supply;
// PoolResponse is the GET /staff/companies/{id}/pool read used to preview
// the equity_percent consequence before submitting. Both rendered by
// StaffCompanyProfileSection.
export type { UpdateSupplyRequest } from './generated'

export type { PoolResponse } from './generated'

// Templates (iter 2.7 C2, R2 §6.3). Read-only staff inspection.
// TemplateResponse = list row (+ is_platform_default computed flag);
// TemplateDetailResponse adds html_content + storage_prefix for the
// per-template inspect modal in StaffCompanyTemplatesSection.
export type { TemplateResponse } from './generated'

export type { TemplateDetailResponse } from './generated'

// Attachments (iter 2.7 C2, R2 §6.2). Staff document list +
// reorder + soft-delete. StaffAttachmentResponse carries storage_key
// (MinIO deep-link) and operational flags hidden from the public
// AttachmentResponse; ReorderAttachmentsRequest is the {category,
// item_ids} body for the per-category reorder endpoint. TASK-30
// company self-service (api/company-attachments.ts) reuses
// ReorderAttachmentsRequest as-is -- same {category, item_ids} shape,
// no company_id anywhere in it -- but uses the plain AttachmentResponse
// (re-exported above) rather than StaffAttachmentResponse, since a
// project has no use for storage_key / created_by_id / is_deleted.
export type { StaffAttachmentResponse } from './generated'

export type { ReorderAttachmentsRequest } from './generated'

// ---------------------------------------------------------------------------
// Roadmap CRUD (iter 2.7 D1, R1 §5)
//
// Write surfaces for StaffCompanyRoadmapSection. RoadmapItemResponse
// itself is already re-exported in the F4.1 public-storefront block
// above (the public CompanyOverview timeline consumes the same shape),
// so it is NOT repeated here -- only the staff write-side request
// bodies plus the kind enum land below.
//
// `kind` is required + immutable on create (CreateRoadmapItemRequest);
// UpdateRoadmapItemRequest deliberately omits it. RoadmapItemStatus is
// NOT a generated TS type -- the backend types status as bare `str` on
// the wire, so the section owns a local `as const` status list for its
// select options + badge variants (same narrowing rationale as the
// UserRole / KycStatus unions near the top of this file).
// ---------------------------------------------------------------------------

export type { CreateRoadmapItemRequest } from './generated'

export type { UpdateRoadmapItemRequest } from './generated'

export type { ReorderRoadmapRequest } from './generated'

export type { RoadmapItemKind } from './generated'

// ---------------------------------------------------------------------------
// Agent referrals + commissions (Task 2 Block A, Phase F6.1)
//
// Read/write surfaces for AgentHubView / AgentDashboardView and the
// upcoming Task 3 views (CommissionsView / LeaderboardView reuse this
// exact layer -- do not re-declare there).
//
// ReferralLinkResponse carries the per-link funnel counters added by
// backend Task 1 Block D (click_count / registration_count /
// purchase_count + is_active); ReferralStatsResponse carries the
// aggregate funnel (total_clicks / total_registrations on top of the
// pre-existing totals). Both regenerate from OpenAPI -- this block
// only re-exports.
// ---------------------------------------------------------------------------

export type { ReferralLinkResponse } from './generated'

export type { ReferralLinkListResponse } from './generated'

export type { ReferralStatsResponse } from './generated'

export type { LeaderboardEntry } from './generated'

export type { LeaderboardResponse } from './generated'

export type { CommissionEntry } from './generated'

export type { CommissionListResponse } from './generated'

// Downline (Task 2b backend, Task 3 Block A frontend). Two collections
// consumed by ReferralsView: investors at commission-mirror levels
// L1-L3 and sub-agents at agent-hop depth 1-3. display_name is masked
// server-side. CommissionSummaryResponse backs the Dashboard
// month-to-date widget (server aggregate replacing the old client-side
// sum). Re-export only -- shapes regenerate from OpenAPI.

export type { ReferralDownlineResponse } from './generated'

export type { DownlineInvestorEntry } from './generated'

export type { DownlineSubAgentEntry } from './generated'

export type { CommissionSummaryResponse } from './generated'

// ---------------------------------------------------------------------------
// Email change + self-deactivation (TASK-38)
//
// Consumed by api/users.ts + InvestorSettingsView / AgentSettingsView /
// CompanySettingsView's Actions section. See users/schemas.py for the
// full three-step email-change flow (request -> resend -> confirm) and
// users/service.py for why it is its own endpoint rather than folded
// into UserUpdate.
// ---------------------------------------------------------------------------

export type { RequestEmailChangeRequest } from './generated'

export type { ConfirmEmailChangeRequest } from './generated'

export type { DeactivateAccountRequest } from './generated'

// ---------------------------------------------------------------------------
// Active sessions (TASK-38)
//
// Consumed by api/auth.ts + ActiveSessionsSection.vue. session_id is
// NEVER the bearer token -- see auth/service.py's "PUBLIC SESSION ID"
// module note on the backend for the exact non-reversible mechanism.
// ---------------------------------------------------------------------------

export type { SessionItemResponse } from './generated'

export type { SessionListResponse } from './generated'
