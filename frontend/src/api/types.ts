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
  title: string
  content_url: string
  status: string
  created_by: string
  created_at: string
  updated_at: string | null
  is_signed: boolean | null
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
