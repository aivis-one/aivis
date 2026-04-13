// API error classes

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: Record<string, string[]>,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

export class UnauthorizedError extends ApiError {
  constructor(message = 'Unauthorized') {
    super(401, 'UNAUTHORIZED', message)
    this.name = 'UnauthorizedError'
  }
}

export class ForbiddenError extends ApiError {
  constructor(message = 'Forbidden') {
    super(403, 'FORBIDDEN', message)
    this.name = 'ForbiddenError'
  }
}

export class ValidationError extends ApiError {
  constructor(message: string, details?: Record<string, string[]>) {
    super(422, 'VALIDATION_ERROR', message, details)
    this.name = 'ValidationError'
  }
}

export class ServerError extends ApiError {
  constructor(message = 'Internal server error') {
    super(500, 'SERVER_ERROR', message)
    this.name = 'ServerError'
  }
}

// Response types

export interface PaginatedResponse<T> {
  data: T[]
  total: number
  page: number
  per_page: number
}

// Auth types

export interface LoginRequest {
  email: string
  password: string
}

export interface RegisterRequest {
  email: string
  password: string
}

export interface TelegramAuthRequest {
  init_data: string
}

export interface AuthResponse {
  user: UserResponse
  session_token: string
}

// Profile

export interface ProfileData {
  first_name: string
  last_name: string
  phone: string
  avatar_url: string | null
  bio: string
  country: string
  city: string
  language: string
  timezone: string
}

export interface ProfileUpdateRequest {
  first_name?: string
  last_name?: string
  phone?: string
  bio?: string
  country?: string
  city?: string
  language?: string
  timezone?: string
}

export interface AvatarUploadResponse {
  avatar_url: string
}

// Settings

export interface UserSettings {
  theme: 'light' | 'dark' | 'system'
  language: string
  notifications_email: boolean
  notifications_push: boolean
  notifications_sms: boolean
}

export interface SettingsUpdateRequest {
  theme?: 'light' | 'dark' | 'system'
  language?: string
  notifications_email?: boolean
  notifications_push?: boolean
  notifications_sms?: boolean
}

// KYC

export type KycStatus = 'none' | 'pending' | 'in_review' | 'approved' | 'rejected'

export interface KycDocument {
  id: string
  type: string
  filename: string
  url: string
  uploaded_at: string
}

export interface KycPersonalData {
  full_name: string
  date_of_birth: string
  nationality: string
  address: string
  tax_id: string
}

export interface KycSubmission {
  id: string
  status: KycStatus
  submitted_at: string
  reviewed_at?: string
  rejection_reason?: string
  documents: KycDocument[]
  personal_data: KycPersonalData
}

export interface KycStatusResponse {
  status: KycStatus
  submission?: KycSubmission
}

export interface KycSubmitRequest {
  personal_data: KycPersonalData
  document_ids: string[]
}

// Documents

export type DocumentStatus = 'draft' | 'pending_signature' | 'signed' | 'expired' | 'rejected'
export type DocumentType = 'contract' | 'agreement' | 'disclosure' | 'report' | 'receipt'

export interface UserDocument {
  id: string
  title: string
  type: DocumentType
  status: DocumentStatus
  description: string
  file_url: string | null
  file_size: number | null
  created_at: string
  updated_at: string
  signed_at: string | null
  expires_at: string | null
}

export interface DocumentsFilter {
  type?: DocumentType
  status?: DocumentStatus
  page?: number
  per_page?: number
}

export interface SignDocumentRequest {
  agreement_accepted: boolean
  signature_text: string
}

// Onboarding

export type OnboardingStep = 'profile_filled' | 'kyc_submitted' | 'documents_signed' | 'completed'

export interface OnboardingStepDef {
  key: OnboardingStep
  labelKey: string
  isComplete: boolean
}

// User

export interface UserResponse {
  id: string
  role: 'investor' | 'agent' | 'company' | 'staff' | 'platform'
  is_active: boolean
  onboarding_step: string
  kyc_status: KycStatus
  profile: ProfileData
  language: string
  created_at: string
  updated_at: string
}
