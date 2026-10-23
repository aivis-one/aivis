// =============================================================================
// AIVIS.ONE Frontend -- Staff Admin API (Phase F3)
// =============================================================================
//
// Typed wrappers for all /api/v1/staff/* endpoints.
// Source of truth: backend routers (staff, admin, avatar, payments, withdrawals, agent-apps).
//
// F4.3 B1.1: fetchUsers and fetchPayments migrated from inline
// URLSearchParams to buildQueryString util (TD-F08e closure). No
// behavioural change -- the helper applies the same skip rules as
// the old `if (params?.x) q.set(...)` ternary.
//
// iter 2.7 Block A3 (R1 §3 + iter 2.6c B1):
//   fetchUsers gains an optional `kyc_status` query parameter.
//   StaffUsersView consumes it via the KYC filter chips
//   (all / not_started / submitted / approved / rejected) in
//   commit A5 -- backend accepts these exact strings and 422s on
//   anything else (KYCStatus StrEnum). Combines freely with the
//   existing `role` param. No behavioural change for the existing
//   role/page/per_page callers.
// =============================================================================

import { api } from '@/api/client'
import { buildQueryString } from '@/utils/querystring'
import type {
  DashboardStatsResponse,
  UserListResponse,
  UserDetailResponse,
  BlockUserRequest,
  ChangeEmailRequest,
  CreateStaffRequest,
  UpdatePermissionsRequest,
  StaffProfileResponse,
  KYCDecisionRequest,
  StaffPaymentListResponse,
  ReversePaymentRequest,
  ReversalResponse,
  WithdrawalResponse,
  RejectWithdrawalRequest,
  StaffWithdrawalListResponse,
  AvatarStartResponse,
  AvatarSessionResponse,
  AgentApplicationResponse,
  RejectAgentApplicationRequest,
} from '@/api/types'
import type {
  ConsistencyResponse,
  PurchaseResponse,
  StaffPurchaseListResponse,
} from '@/api/generated'

// ---------------------------------------------------------------------------
// Dashboard (Sprint 3.3)
// ---------------------------------------------------------------------------

/** GET /api/v1/staff/dashboard/stats — platform-wide statistics. */
export function fetchDashboardStats(): Promise<DashboardStatsResponse> {
  return api.get<DashboardStatsResponse>('/api/v1/staff/dashboard/stats')
}

// ---------------------------------------------------------------------------
// Users (Sprint 3.1 + 3.3 + iter 2.6c B1 + iter 2.7 A3)
// ---------------------------------------------------------------------------

/**
 * GET /api/v1/staff/users — paginated user list with optional filters.
 *
 * Filters (all optional, combinable):
 *   - role:       'investor' | 'agent' | 'company' | 'staff'
 *   - kyc_status: 'not_started' | 'submitted' | 'approved' | 'rejected'
 *                 | 'revoked'
 *                 (iter 2.6c B1; backend validates via KYCStatus StrEnum,
 *                  422 on any other value). `revoked` landed with H12 and
 *                  was missing from this list until P-65 gave the panel a
 *                  button that produces it -- a vocabulary that omits the
 *                  status the same file can now create would read as "the
 *                  backend refuses this filter", which is false.
 *   - search:     case-insensitive substring match on email, first_name,
 *                 or last_name (TASK-30 admin-capability gap). Backs the
 *                 UserPicker component -- the only way to find a user's
 *                 UUID through the product before this was to already
 *                 know it.
 *
 * Pagination: page (1-indexed), per_page. Sort is fixed server-side.
 */
export function fetchUsers(params?: {
  role?: string
  kyc_status?: string
  search?: string
  page?: number
  per_page?: number
}): Promise<UserListResponse> {
  const qs = buildQueryString({
    role: params?.role,
    kyc_status: params?.kyc_status,
    search: params?.search,
    page: params?.page,
    per_page: params?.per_page,
  })
  return api.get<UserListResponse>(`/api/v1/staff/users${qs}`)
}

/** GET /api/v1/staff/users/{id} — full user detail. */
export function fetchUserDetail(userId: string): Promise<UserDetailResponse> {
  return api.get<UserDetailResponse>(`/api/v1/staff/users/${userId}`)
}

/** PATCH /api/v1/staff/users/{id}/block — block user. */
export function blockUser(userId: string, body?: BlockUserRequest): Promise<void> {
  return api.patch<void>(`/api/v1/staff/users/${userId}/block`, body ?? {})
}

/**
 * PATCH /api/v1/staff/users/{id}/unblock — unblock user.
 *
 * No request body: unlike block, unblock does not take a `reason` --
 * see admin_service.unblock_user's docstring on the backend for why.
 */
export function unblockUser(userId: string): Promise<void> {
  return api.patch<void>(`/api/v1/staff/users/${userId}/unblock`, {})
}

/**
 * PATCH /api/v1/staff/users/{id}/email — change a user's email (admin only).
 *
 * Support is the only way an address changes; the reason is required and
 * lands in the audit log.
 */
export function changeUserEmail(userId: string, body: ChangeEmailRequest): Promise<void> {
  return api.patch<void>(`/api/v1/staff/users/${userId}/email`, body)
}

/** POST /api/v1/staff/users — promote user to staff (admin only). */
export function createStaff(body: CreateStaffRequest): Promise<StaffProfileResponse> {
  return api.post<StaffProfileResponse>('/api/v1/staff/users', body)
}

/** PATCH /api/v1/staff/users/{id}/permissions — update permissions (admin only). */
export function updatePermissions(
  staffProfileId: string,
  body: UpdatePermissionsRequest,
): Promise<StaffProfileResponse> {
  return api.patch<StaffProfileResponse>(`/api/v1/staff/users/${staffProfileId}/permissions`, body)
}

// H17 P-85: fetchKYCQueue (GET /api/v1/staff/kyc/queue) removed. It
// had exactly one reference in this file -- its own declaration --
// since iter 2.7 A2 moved the real queue view onto fetchUsers'
// kyc_status filter. See admin_schemas.py's header on the backend for
// the fuller account.

/** POST /api/v1/staff/kyc/{id}/approve — approve KYC application.
 *
 * The body is REQUIRED since H10 and so is its reason: the backend
 * answers 422 without one. It used to take no body at all.
 */
export function approveKYC(applicationId: string, body: KYCDecisionRequest): Promise<void> {
  return api.post<void>(`/api/v1/staff/kyc/${applicationId}/approve`, body)
}

/** POST /api/v1/staff/kyc/{id}/reject — reject KYC application.
 *
 * Same body, and the reason is no longer optional here either.
 */
export function rejectKYC(applicationId: string, body: KYCDecisionRequest): Promise<void> {
  return api.post<void>(`/api/v1/staff/kyc/${applicationId}/reject`, body)
}

/** POST /api/v1/staff/kyc/users/{id}/approve — approve a PERSON.
 *
 * The pair above decides an APPLICATION: somebody paid, submitted
 * documents and is waiting in the queue. This one decides a PERSON, and
 * needs no application to exist. That is the point of it -- an old user
 * arriving under a new address has never submitted and cannot submit
 * without paying, while this path is free.
 *
 * 409 `kyc_already_approved` when the person is approved already.
 */
export function approveKYCUser(userId: string, body: KYCDecisionRequest): Promise<void> {
  return api.post<void>(`/api/v1/staff/kyc/users/${userId}/approve`, body)
}

/** POST /api/v1/staff/kyc/users/{id}/revoke — withdraw an approval.
 *
 * Person-level like the one above, and the only way back out: the
 * application-level pair can refuse a submission but cannot take back an
 * approval already granted. Same `kyc_approve` permission as granting
 * it, so that nobody can let a person in and then be unable to correct
 * their own mistake.
 *
 * 409 `kyc_not_approved` when the person is not currently approved.
 */
export function revokeKYCUser(userId: string, body: KYCDecisionRequest): Promise<void> {
  return api.post<void>(`/api/v1/staff/kyc/users/${userId}/revoke`, body)
}

// ---------------------------------------------------------------------------
// Payments (Sprint 5.3)
// ---------------------------------------------------------------------------

/** GET /api/v1/staff/payments — paginated payment list with filters. */
export function fetchPayments(params?: {
  status?: string
  user_id?: string
  page?: number
  per_page?: number
}): Promise<StaffPaymentListResponse> {
  const qs = buildQueryString({
    status: params?.status,
    user_id: params?.user_id,
    page: params?.page,
    per_page: params?.per_page,
  })
  return api.get<StaffPaymentListResponse>(`/api/v1/staff/payments${qs}`)
}

/** POST /api/v1/staff/payments/{id}/reverse — chargeback reversal. */
export function reversePayment(
  paymentId: string,
  body?: ReversePaymentRequest,
): Promise<ReversalResponse> {
  return api.post<ReversalResponse>(`/api/v1/staff/payments/${paymentId}/reverse`, body ?? {})
}

// ---------------------------------------------------------------------------
// Withdrawals (Sprint 6.3)
// ---------------------------------------------------------------------------

/** GET /api/v1/staff/withdrawals — paginated withdrawal list with filters. */
export function fetchWithdrawalsStaff(params?: {
  status?: string
  user_id?: string
  page?: number
  per_page?: number
}): Promise<StaffWithdrawalListResponse> {
  const qs = buildQueryString({
    status: params?.status,
    user_id: params?.user_id,
    page: params?.page,
    per_page: params?.per_page,
  })
  return api.get<StaffWithdrawalListResponse>(`/api/v1/staff/withdrawals${qs}`)
}

/** POST /api/v1/staff/withdrawals/{id}/confirm — approve withdrawal. */
export function confirmWithdrawal(withdrawalId: string): Promise<WithdrawalResponse> {
  return api.post<WithdrawalResponse>(`/api/v1/staff/withdrawals/${withdrawalId}/confirm`)
}

/** POST /api/v1/staff/withdrawals/{id}/reject — reject withdrawal. */
export function rejectWithdrawal(
  withdrawalId: string,
  body: RejectWithdrawalRequest,
): Promise<WithdrawalResponse> {
  return api.post<WithdrawalResponse>(`/api/v1/staff/withdrawals/${withdrawalId}/reject`, body)
}

// ---------------------------------------------------------------------------
// Avatar (Sprint 3.2)
// ---------------------------------------------------------------------------

/** POST /api/v1/staff/avatar/start — start avatar session. */
export function startAvatar(targetUserId: string): Promise<AvatarStartResponse> {
  return api.post<AvatarStartResponse>('/api/v1/staff/avatar/start', {
    target_user_id: targetUserId,
  })
}

/** POST /api/v1/staff/avatar/end — end active avatar session. */
export function endAvatar(): Promise<void> {
  return api.post<void>('/api/v1/staff/avatar/end')
}

/** GET /api/v1/staff/avatar/active — get active avatar session (null if none). */
export function fetchActiveAvatar(): Promise<AvatarSessionResponse | null> {
  return api.get<AvatarSessionResponse | null>('/api/v1/staff/avatar/active')
}

// ---------------------------------------------------------------------------
// Agent applications (Sprint 7.1)
// ---------------------------------------------------------------------------

/**
 * One pending application in the staff queue, with the applicant: the name,
 * the e-mail (null for an account that came in through Telegram without one)
 * and the identity-check status, read by the server from the applicant's row.
 */
export interface AgentApplicationQueueItem extends AgentApplicationResponse {
  applicant_name: string
  applicant_email: string | null
  applicant_kyc_status: string
}

/** One page of the pending integrator applications, oldest first. */
export interface AgentApplicationQueueResponse {
  items: AgentApplicationQueueItem[]
  total: number
  page: number
  per_page: number
}

/**
 * GET /api/v1/staff/agent-applications -- the pending applications, paged,
 * each with the applicant's name, e-mail and identity-check status. Needs
 * agent_application_review.
 */
export function fetchAgentApplications(params?: {
  page?: number
  per_page?: number
}): Promise<AgentApplicationQueueResponse> {
  const qs = buildQueryString({ page: params?.page, per_page: params?.per_page })
  return api.get<AgentApplicationQueueResponse>(`/api/v1/staff/agent-applications${qs}`)
}

/** POST /api/v1/staff/agent-applications/{id}/approve — approve application. */
export function approveAgentApplication(applicationId: string): Promise<void> {
  return api.post<void>(`/api/v1/staff/agent-applications/${applicationId}/approve`)
}

/** POST /api/v1/staff/agent-applications/{id}/reject — reject application. */
export function rejectAgentApplication(
  applicationId: string,
  body: RejectAgentApplicationRequest,
): Promise<void> {
  return api.post<void>(`/api/v1/staff/agent-applications/${applicationId}/reject`, body)
}

// ---------------------------------------------------------------------------
// Staff members (administrator)
// ---------------------------------------------------------------------------

/**
 * POST /api/v1/staff/users/{staffProfileId}/deactivate -- take a staff member
 * off duty (administrator only). The profile stays with its history; the member
 * loses access and every session at once. Takes the STAFF PROFILE id, not the
 * user id.
 */
export function deactivateStaff(staffProfileId: string): Promise<StaffProfileResponse> {
  return api.post<StaffProfileResponse>(`/api/v1/staff/users/${staffProfileId}/deactivate`)
}

// ---------------------------------------------------------------------------
// The money check (reconciliation)
// ---------------------------------------------------------------------------

/**
 * GET /api/v1/staff/consistency -- runs every consistency check over the
 * platform's money and returns the results (needs financial_operations; the
 * screen is the administrator's). A failing check is also written to the
 * server's audit log.
 */
export function fetchConsistency(): Promise<ConsistencyResponse> {
  return api.get<ConsistencyResponse>('/api/v1/staff/consistency')
}

// ---------------------------------------------------------------------------
// Gifts of the company
// ---------------------------------------------------------------------------

/** The body of a gift grant: a verified investor, a product of the project, a number of parts. */
export interface StaffGrantGiftRequest {
  user_id: string
  product_id: string
  units: number
}

/**
 * POST /api/v1/staff/purchases/gifts -- grant gift parts (needs
 * financial_operations). The gift waits for the recipient's acceptance; nothing
 * is credited and no pool unit is used before it. The recipient must be an
 * active investor who passed the paid identity check.
 */
export function grantGift(body: StaffGrantGiftRequest): Promise<PurchaseResponse> {
  return api.post<PurchaseResponse>('/api/v1/staff/purchases/gifts', body)
}

/**
 * GET /api/v1/staff/purchases -- the purchases list, read-only and paged, newest
 * first (needs financial_operations). Filters: status, company_id (the project),
 * buyer_id (the buyer). per_page is at most 100.
 */
export function fetchStaffPurchases(params?: {
  status?: string
  company_id?: string
  buyer_id?: string
  page?: number
  per_page?: number
}): Promise<StaffPurchaseListResponse> {
  const qs = buildQueryString({
    status: params?.status,
    company_id: params?.company_id,
    buyer_id: params?.buyer_id,
    page: params?.page,
    per_page: params?.per_page,
  })
  return api.get<StaffPurchaseListResponse>(`/api/v1/staff/purchases${qs}`)
}

/** POST /api/v1/staff/purchases/gifts/{id}/cancel -- cancel a gift not yet accepted. */
export function cancelGift(purchaseId: string): Promise<PurchaseResponse> {
  return api.post<PurchaseResponse>(`/api/v1/staff/purchases/gifts/${purchaseId}/cancel`)
}
