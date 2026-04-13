import { api } from './client'
import type {
  AuthResponse,
  LoginRequest,
  RegisterRequest,
  TelegramAuthRequest,
  UserResponse,
} from './types'

export const authApi = {
  login(data: LoginRequest): Promise<AuthResponse> {
    return api.post<AuthResponse>('/api/v1/auth/email/login', data, { skipAuth: true })
  },

  register(data: RegisterRequest): Promise<AuthResponse> {
    return api.post<AuthResponse>('/api/v1/auth/email/register', data, { skipAuth: true })
  },

  telegramAuth(data: TelegramAuthRequest): Promise<AuthResponse> {
    return api.post<AuthResponse>('/api/v1/auth/telegram', data, { skipAuth: true })
  },

  logout(): Promise<void> {
    return api.post('/api/v1/auth/logout')
  },

  logoutAll(): Promise<void> {
    return api.post('/api/v1/auth/logout-all')
  },

  me(): Promise<UserResponse> {
    return api.get<UserResponse>('/api/v1/users/me')
  },
}
