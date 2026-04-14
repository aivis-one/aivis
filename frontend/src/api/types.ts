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
export type KycStatus = 'none' | 'submitted' | 'approved' | 'rejected'

export interface UserResponse {
  id: string
  role: UserRole
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
