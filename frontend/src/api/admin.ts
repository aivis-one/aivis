// =============================================================================
// CBSHOME Frontend -- Staff Admin API (Phase F3)
// =============================================================================
//
// Typed wrappers for all /api/v1/staff/* endpoints.
// Source of truth: backend routers (staff, admin, avatar, payments, withdrawals, agent-apps).
//
// F4.3 B1.1: fetchUsers and fetchPayments migrated from inline
// URLSearchParams to buildQueryString util (TD-F08e closure). No
// behavioural change -- the helper applies the same skip rules as
// the old `if (params?.x) q.set(...)` ternary.
// =============================================================================

import { api } from '@/api/client'
import { buildQueryString } from '@/utils/querystring'
import type {
  DashboardStatsResponse,
  UserListResponse,
  UserDetailResponse,
  BlockUserRequest,
  CreateStaffRequest,
  UpdatePermissionsRequest,
  StaffProfileResponse,
  KYCQueueItem,
  KYCRejectRequest,
  StaffPaymentListResponse,
  ReversePaymentRequest,
  ReversalResponse,
  WithdrawalResponse,
  RejectWithdrawalRequest,
  AvatarStartResponse,
  AvatarSessionResponse,
  AgentApplicationResponse,
  RejectAgentApplicationRequest,
} from '@/api/types'

// ---------------------------------------------------------------------------
// Dashboard (Sprint 3.3)
// ---------------------------------------------------------------------------

/** GET /api/v1/staff/dashboard/stats — platform-wide statistics. */
export function fetchDashboardStats(): Promise<DashboardStatsResponse> {
  return api.get<DashboardStatsResponse>('/api/v1/staff/dashboard/stats')
}

// ---------------------------------------------------------------------------
// Users (Sprint 3.1 + 3.3)
// ---------------------------------------------------------------------------

/** GET /api/v1/staff/users — paginated user list with optional role filter. */
export function fetchUsers(params?: {
  role?: string
  page?: number
  per_page?: number
}): Promise<UserListResponse> {
  const qs = buildQueryString({
    role: params?.role,
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

/** POST /api/v1/staff/users — promote user to staff (admin only). */
export function createStaff(body: CreateStaffRequest): Promise<StaffProfileResponse> {
  return api.post<StaffProfileResponse>('/api/v1/staff/users', body)
}

/** PATCH /api/v1/staff/users/{id}/permissions — update permissions (admin only). */
export function updatePermissions(
  staffProfileId: string,
  body: UpdatePermissionsRequest,
): Promise<StaffProfileResponse> {
  return api.patch<StaffProfileResponse>(
    `/api/v1/staff/users/${staffProfileId}/permissions`,
    body,
  )
}

// ---------------------------------------------------------------------------
// KYC queue (Sprint 3.3)
// ---------------------------------------------------------------------------

/** GET /api/v1/staff/kyc/queue — pending KYC applications. */
export function fetchKYCQueue(): Promise<KYCQueueItem[]> {
  return api.get<KYCQueueItem[]>('/api/v1/staff/kyc/queue')
}

/** POST /api/v1/staff/kyc/{id}/approve — approve KYC application. */
export function approveKYC(applicationId: string): Promise<void> {
  return api.post<void>(`/api/v1/staff/kyc/${applicationId}/approve`)
}

/** POST /api/v1/staff/kyc/{id}/reject — reject KYC application. */
export function rejectKYC(applicationId: string, body?: KYCRejectRequest): Promise<void> {
  return api.post<void>(`/api/v1/staff/kyc/${applicationId}/reject`, body ?? {})
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
  return api.post<ReversalResponse>(
    `/api/v1/staff/payments/${paymentId}/reverse`,
    body ?? {},
  )
}

// ---------------------------------------------------------------------------
// Withdrawals (Sprint 6.3)
// ---------------------------------------------------------------------------

/** POST /api/v1/staff/withdrawals/{id}/confirm — approve withdrawal. */
export function confirmWithdrawal(withdrawalId: string): Promise<WithdrawalResponse> {
  return api.post<WithdrawalResponse>(
    `/api/v1/staff/withdrawals/${withdrawalId}/confirm`,
  )
}

/** POST /api/v1/staff/withdrawals/{id}/reject — reject withdrawal. */
export function rejectWithdrawal(
  withdrawalId: string,
  body: RejectWithdrawalRequest,
): Promise<WithdrawalResponse> {
  return api.post<WithdrawalResponse>(
    `/api/v1/staff/withdrawals/${withdrawalId}/reject`,
    body,
  )
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

/** GET /api/v1/staff/agent-applications — pending agent applications queue. */
export function fetchAgentApplications(): Promise<AgentApplicationResponse[]> {
  return api.get<AgentApplicationResponse[]>('/api/v1/staff/agent-applications')
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
  return api.post<void>(
    `/api/v1/staff/agent-applications/${applicationId}/reject`,
    body,
  )
}
