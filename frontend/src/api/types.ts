// =============================================================================
// CBSHOME Frontend -- API Type Definitions
// =============================================================================
//
// TypeScript interfaces matching backend Pydantic schemas.
// Source of truth: backend/app/modules/*/schemas.py
// =============================================================================

// ---------------------------------------------------------------------------
// User
// ---------------------------------------------------------------------------

export type UserRole = 'investor' | 'agent' | 'company' | 'staff' | 'platform'
export type KycStatus = 'not_started' | 'submitted' | 'approved' | 'rejected'

export interface UserResponse {
  id: string
  role: UserRole
  email: string | null
  is_active: boolean
  onboarding_step: string
  kyc_status: KycStatus
  profile: Record<string, unknown>
  payout_details: Record<string, unknown> | null
  language: string
  created_at: string
  updated_at: string | null
}

export interface UserUpdate {
  profile?: Record<string, unknown>
  language?: string
}

export interface SelectRoleRequest {
  role: 'investor' | 'agent' | 'company'
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export interface EmailRegisterRequest {
  email: string
  password: string
  referral_code?: string | null
}

export interface EmailLoginRequest {
  email: string
  password: string
}

export interface TelegramAuthRequest {
  init_data: string
  referral_code?: string | null
}

export interface AuthResponse {
  user: UserResponse
  session_token: string
}

export interface VerifyEmailRequest {
  code: string
}

// ---------------------------------------------------------------------------
// KYC
// ---------------------------------------------------------------------------

export interface KYCSubmitResponse {
  id: string
  status: string
  created_at: string
}

export interface KYCStatusResponse {
  kyc_status: string
  application_id: string | null
  application_status: string | null
}

// ---------------------------------------------------------------------------
// Documents
// ---------------------------------------------------------------------------

export interface DocumentResponse {
  id: string
  type: string
  version: number
  language: string
  title: string
  required_for_roles: string[]
  status: string
  created_by: string
  created_at: string
  updated_at: string | null
  is_signed: boolean
}

export interface DocumentSigningResponse {
  id: string
  document_id: string
  signed_at: string
}

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
// Staff (Phase F3) -- matches backend/app/modules/staff/* and related schemas
// ===========================================================================

// ---------------------------------------------------------------------------
// Staff profile (shared with admin types)
// ---------------------------------------------------------------------------

export type StaffPermissionKey =
  | 'avatar_mode'
  | 'kyc_approve'
  | 'payment_review'
  | 'user_block'
  | 'financial_operations'
  | 'agent_application_review'
  | 'translation_edit'
  | 'company_manage'

export type StaffPermissions = Partial<Record<StaffPermissionKey, boolean>>

export interface StaffProfileResponse {
  id: string
  user_id: string
  permissions: StaffPermissions
  is_active: boolean
  created_at: string
}

// ---------------------------------------------------------------------------
// Staff: dashboard (Sprint 3.3)
// ---------------------------------------------------------------------------

export interface DashboardStatsResponse {
  total_users: number
  users_by_role: Record<string, number>
  pending_kyc_count: number
  active_avatar_sessions: number
}

// ---------------------------------------------------------------------------
// Staff: users (Sprint 3.1 + 3.3)
// ---------------------------------------------------------------------------

export interface UserListItem {
  id: string
  role: UserRole
  is_active: boolean
  kyc_status: KycStatus
  email: string | null
  first_name: string | null
  last_name: string | null
  created_at: string
  staff_profile: StaffProfileResponse | null
}

export interface UserListResponse {
  items: UserListItem[]
  total: number
  page: number
  per_page: number
}

export interface UserDetailResponse {
  id: string
  role: UserRole
  is_active: boolean
  onboarding_step: string
  kyc_status: KycStatus
  profile: Record<string, unknown>
  language: string
  created_at: string
  updated_at: string | null
  email: string | null
  staff_profile: StaffProfileResponse | null
}

export interface BlockUserRequest {
  reason?: string | null
}

export interface CreateStaffRequest {
  user_id: string
}

export interface UpdatePermissionsRequest {
  avatar_mode?: boolean
  kyc_approve?: boolean
  payment_review?: boolean
  user_block?: boolean
  financial_operations?: boolean
  agent_application_review?: boolean
  translation_edit?: boolean
  company_manage?: boolean
}

// ---------------------------------------------------------------------------
// Staff: KYC queue (Sprint 3.3)
// ---------------------------------------------------------------------------

export interface KYCQueueItem {
  id: string
  user_id: string
  status: string
  created_at: string
  email: string | null
  first_name: string | null
  last_name: string | null
}

export interface KYCRejectRequest {
  reason?: string | null
}

// ---------------------------------------------------------------------------
// Staff: payments (Sprint 5.3)
// ---------------------------------------------------------------------------

export type PaymentType = 'crypto' | 'card' | 'bank'
export type PaymentStatusType = 'frozen' | 'confirmed' | 'reversed' | 'failed'

export interface StaffPaymentResponse {
  id: string
  user_id: string
  amount_cents: number
  currency: string
  payment_type: PaymentType | string
  provider: string
  status: PaymentStatusType | string
  provider_data: Record<string, unknown> | null
  created_at: string
  updated_at: string | null
}

export interface StaffPaymentListResponse {
  items: StaffPaymentResponse[]
  total: number
  page: number
  per_page: number
}

export interface ReversePaymentRequest {
  reason?: string | null
}

export interface ReversalResponse {
  payment_id: string
  total_reversed_cents: number
  active_entries_reversed: number
  passive_entries_reversed: number
  affected_user_ids: string[]
}

// ---------------------------------------------------------------------------
// Staff: withdrawals (Sprint 6.3)
// ---------------------------------------------------------------------------

export type WithdrawalStatusType =
  | 'pending'
  | 'confirmed'
  | 'processing'
  | 'completed'
  | 'rejected'
  | 'failed'

export interface WithdrawalResponse {
  id: string
  user_id: string
  amount_cents: number
  status: WithdrawalStatusType | string
  rejection_reason: string | null
  confirmed_at: string | null
  processing_at: string | null
  completed_at: string | null
  rejected_at: string | null
  created_at: string
}

export interface RejectWithdrawalRequest {
  reason: string
}

// ---------------------------------------------------------------------------
// Staff: avatar (Sprint 3.2)
// ---------------------------------------------------------------------------

export interface AvatarStartRequest {
  target_user_id: string
}

export interface AvatarStartResponse {
  avatar_session_id: string
  session_token: string
}

export interface AvatarSessionResponse {
  id: string
  staff_id: string
  target_user_id: string
  status: string
  ip_address: string
  created_at: string
  ended_at: string | null
}

// ---------------------------------------------------------------------------
// Staff: agent applications (Sprint 7.1)
// ---------------------------------------------------------------------------

export interface AgentApplicationResponse {
  id: string
  user_id: string
  status: string
  rejection_reason: string | null
  cooldown_until: string | null
  reviewed_at: string | null
  reviewed_by: string | null
  created_at: string
}

export interface RejectAgentApplicationRequest {
  reason: string
}

// ===========================================================================
// Phase F4.1 -- Public storefront (products + companies)
//
// Matches backend/app/modules/products/schemas.py (Public*) and
// backend/app/modules/companies/schemas.py (Public*, RoadmapItemResponse).
// ===========================================================================

// ---------------------------------------------------------------------------
// Products: installment plan template (public, surfaced on product detail)
// ---------------------------------------------------------------------------

export interface InstallmentResponse {
  id: string
  product_id: string
  name: string
  /**
   * plan_config shape (Sprint 6.2):
   *   {
   *     "tranches": [{"amount_cents": int, "units_percent": int}, ...],
   *     "bonus_units": int,
   *     "agent_bonus_units": int
   *   }
   */
  plan_config: Record<string, unknown>
  created_at: string
}

// ---------------------------------------------------------------------------
// Products: public storefront (Sprint 4.2 + F4.1 denormalisation)
// ---------------------------------------------------------------------------

export interface PublicProductResponse {
  id: string
  company_id: string
  name: string
  description: string | null
  units: number
  price_per_unit_cents: number
  cover_url: string | null
  sold_units: number

  // Denormalised from CompanyProfile by the public router (F4.1).
  // Client renders cards without a second round-trip.
  company_name: string
  company_logo_url: string | null
  company_cover_url: string | null
}

export interface PublicProductDetailResponse extends PublicProductResponse {
  installments: InstallmentResponse[]
}

export interface PublicProductListResponse {
  items: PublicProductResponse[]
  total: number
  page: number
  per_page: number
}

// ---------------------------------------------------------------------------
// Companies: public storefront (Sprint 4.1)
// ---------------------------------------------------------------------------

export interface RoadmapItemResponse {
  id: string
  title: string
  description: string | null
  target_date: string | null
  status: string
  order: number
  created_at: string
  updated_at: string | null
}

export interface PublicCompanyResponse {
  id: string
  name: string
  description: string | null
  logo_url: string | null
  cover_url: string | null
  promo_video_url: string | null
  presentation_url: string | null
  price_per_unit_cents: number
  status: string
  created_at: string
}

export interface PublicCompanyDetailResponse extends PublicCompanyResponse {
  roadmap: RoadmapItemResponse[]
}

export interface PublicCompanyListResponse {
  items: PublicCompanyResponse[]
  total: number
  page: number
  per_page: number
}

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

export type PurchaseLegalBasis =
  | 'sale'
  | 'gift'
  | 'installment_tranche'

export type PurchaseStatusType = 'active' | 'reversed'

/**
 * POST /api/v1/products/{id}/purchase -- request body.
 *
 * Empty body is valid (organic purchase). Pass referral_link_id
 * only when the flow originated from a referral link.
 */
export interface CreatePurchaseRequest {
  referral_link_id?: string | null
}

/**
 * Single purchase record. POST /products/{id}/purchase returns a
 * list: the sale record plus any gift purchases triggered by
 * purchase_config bonuses.
 */
export interface PurchaseResponse {
  id: string
  investor_id: string
  product_id: string
  company_id: string
  legal_basis: PurchaseLegalBasis | string
  units: number
  paid_cents: number
  price_per_unit_cents: number
  status: PurchaseStatusType | string
  created_at: string
}

// ---------------------------------------------------------------------------
// Installment plans (Sprint 6.2)
// ---------------------------------------------------------------------------

export type InstallmentPlanStatusType =
  | 'active'
  | 'completed'
  | 'defaulted'

export type InstallmentTrancheStatusType =
  | 'pending'
  | 'paid'
  | 'overdue'
  | 'cancelled'

/**
 * POST /api/v1/products/{id}/installment -- request body.
 *
 * product_installment_id picks which ProductInstallment template
 * to snapshot into the new plan. referral_link_id is optional
 * (Sprint 7.2 stub).
 */
export interface CreateInstallmentPlanRequest {
  product_installment_id: string
  referral_link_id?: string | null
}

export interface InstallmentTrancheResponse {
  id: string
  plan_id: string
  number: number
  // ISO-8601 date (YYYY-MM-DD).
  due_date: string
  amount_cents: number
  units_unlocked: number
  status: InstallmentTrancheStatusType | string
  paid_at: string | null
  purchase_id: string | null
}

export interface InstallmentPlanResponse {
  id: string
  investor_id: string
  product_id: string
  company_id: string
  product_installment_id: string
  total_price_cents: number
  total_units: number
  price_per_unit_cents: number
  status: InstallmentPlanStatusType | string
  created_at: string
  completed_at: string | null
  defaulted_at: string | null
}

export interface InstallmentPlanDetailResponse extends InstallmentPlanResponse {
  tranches: InstallmentTrancheResponse[]
}

export interface InstallmentPlanListResponse {
  items: InstallmentPlanResponse[]
  total: number
  page: number
  per_page: number
}

// ---------------------------------------------------------------------------
// Dashboard summary (Sprint 9.2)
//
// GET /api/v1/dashboard/summary returns ledger balances plus a
// per-company portfolio breakdown. F4.2 uses active_balance.confirmed
// as the spendable figure on the purchase/installment confirm screens;
// frozen amounts are excluded by the backend when executing a sale.
// ---------------------------------------------------------------------------

export interface BalanceResponse {
  frozen: number
  confirmed: number
}

export interface CompanySummaryResponse {
  company_id: string
  company_name: string
  logo_url: string | null
  total_units: number
  invested_cents: number
  current_value_cents: number
}

export interface DashboardSummaryResponse {
  active_balance: BalanceResponse
  passive_balance: BalanceResponse
  total_invested_cents: number
  total_units: number
  current_value_cents: number
  companies_count: number
  companies: CompanySummaryResponse[]
}

// ===========================================================================
// Phase F4.3 -- Investor payments (deposit) + transactions event log
//
// Matches:
//   backend/app/modules/payments/schemas.py       (Sprint 5.2)
//     CreateAddressRequest, DepositAddressResponse,
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
// Crypto deposit address (Sprint 5.2)
//
// Supported networks on backend: TRC20, ERC20, BEP20, PoS. F4.3
// hardcodes TRC20; the full selector is deferred (see F4.3 plan).
// CreateAddressRequest uses the strict CryptoNetwork union -- the
// frontend owns what it sends, so a compile-time typo catch wins
// over a `| string` escape hatch. DepositAddressResponse.network
// stays plain `string` since it comes from the backend.
// ---------------------------------------------------------------------------

export type CryptoNetwork = 'TRC20' | 'ERC20' | 'BEP20' | 'PoS'

export interface CreateAddressRequest {
  network: CryptoNetwork
}

export interface DepositAddressResponse {
  address: string
  network: string
  user_id: string
}

// ---------------------------------------------------------------------------
// Payment history (Sprint 5.2) -- investor view
//
// `payment_type` and `status` are strings on the backend (not enum
// columns), so union + `| string` escape matches the Staff pattern.
// ---------------------------------------------------------------------------

export interface PaymentResponse {
  id: string
  amount_cents: number
  currency: string
  payment_type: PaymentType | string
  provider: string
  status: PaymentStatusType | string
  frozen_until: string | null
  created_at: string
  updated_at: string | null
}

export interface PaymentHistoryResponse {
  items: PaymentResponse[]
  total: number
  page: number
  per_page: number
}

// ---------------------------------------------------------------------------
// Transactions: immutable event log (Sprint 6.4)
//
// Type format is `{entity}:{event}` -- backend accepts either an
// exact match (`deposit:received`) or a trailing-colon prefix
// (`deposit:`) in the `type` query parameter. F4.3 TransactionsView
// uses the prefix form for category tabs.
// ---------------------------------------------------------------------------

export type TransactionType =
  | 'deposit:received'
  | 'deposit:confirmed'
  | 'deposit:reversed'
  | 'purchase:completed'
  | 'purchase:gift'
  | 'installment:tranche_paid'
  | 'installment:completed'
  | 'installment:defaulted'
  | 'withdrawal:created'
  | 'withdrawal:confirmed'
  | 'withdrawal:rejected'
  | 'withdrawal:completed'
  | 'withdrawal:failed'
  | 'reversal:completed'

export type ReferenceType =
  | 'payment'
  | 'purchase'
  | 'withdrawal'
  | 'installment_plan'

/**
 * Single transaction event. `amount_cents` is signed:
 *   positive -- money in (deposit, refund)
 *   negative -- money out (purchase, withdrawal)
 * `details` JSONB is type-specific and rendered by the detail sheet;
 * frontend should treat each key as optional and never assume shape.
 */
export interface TransactionResponse {
  id: string
  user_id: string
  type: TransactionType | string
  amount_cents: number
  currency: string
  reference_id: string | null
  reference_type: ReferenceType | string | null
  details: Record<string, unknown> | null
  created_at: string
}

export interface TransactionListResponse {
  items: TransactionResponse[]
  total: number
  page: number
  per_page: number
}

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

export interface PortfolioPositionResponse {
  company_id: string
  company_name: string
  logo_url: string | null
  total_units: number
  sale_units: number
  gift_units: number
  total_paid_cents: number
  avg_price_cents: number
  current_price_cents: number
  current_value_cents: number
  purchases_count: number
}

export interface PortfolioResponse {
  positions: PortfolioPositionResponse[]
}

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

export interface PurchaseItemResponse {
  id: string
  product_id: string
  legal_basis: PurchaseLegalBasis | string
  units: number
  paid_cents: number
  price_per_unit_cents: number
  status: PurchaseStatusType | string
  created_at: string
}

export interface CompanyPositionDetailResponse {
  company_id: string
  company_name: string
  logo_url: string | null
  total_units: number
  sale_units: number
  gift_units: number
  total_paid_cents: number
  avg_price_cents: number
  current_price_cents: number
  current_value_cents: number
  purchases: PurchaseItemResponse[]
  total: number
  page: number
  per_page: number
}

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

export type AgentApplicationStatusType = 'pending' | 'approved' | 'rejected'

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

export interface AgentApplicationListResponse {
  items: AgentApplicationResponse[]
  total: number
}

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

export type PostOwnerType = 'platform' | 'company'

export interface PostResponse {
  id: string
  owner_type: PostOwnerType | string
  owner_id: string | null
  title: string
  body: string
  cover_url: string | null
  tags: string[] | null
  is_banner: boolean
  is_published: boolean
  published_at: string | null
  created_by: string
  created_at: string
  updated_at: string | null
  is_dismissed: boolean
}

export interface PostListResponse {
  items: PostResponse[]
  total: number
  page: number
  per_page: number
}

// ---------------------------------------------------------------------------
// Events (declared for F9.2 completeness, not consumed in F4.4)
// ---------------------------------------------------------------------------

export interface EventResponse {
  id: string
  title: string
  description: string | null
  cover_url: string | null
  starts_at: string
  ends_at: string | null
  location: string | null
  url: string | null
  is_published: boolean
  created_by: string
  created_at: string
  updated_at: string | null
}

export interface EventListResponse {
  items: EventResponse[]
  total: number
  page: number
  per_page: number
}
