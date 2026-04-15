// =============================================================================
// CBSHOME Frontend -- API Client
// =============================================================================
//
// Typed fetch wrapper for CORS requests to api.cbshome.org.
//
// Features:
//   - Authorization: Bearer {token} auto-injection
//   - 401 → _onUnauthorized callback (session expired)
//   - 422 → parsed ValidationError joined into string
//   - 204 → returns undefined
//   - Network errors → ApiNetworkError
//   - AbortController + 15s timeout → ApiTimeoutError
//   - Accept-Language from current vue-i18n locale
// =============================================================================

import { i18n } from '@/i18n'
import type { ValidationErrorItem } from '@/api/types'

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'https://api.cbshome.org'
const TIMEOUT_MS = 15_000

// ---------------------------------------------------------------------------
// Error classes
// ---------------------------------------------------------------------------

export class ApiResponseError extends Error {
  status: number
  detail: string

  constructor(status: number, detail: string) {
    super(detail)
    this.name = 'ApiResponseError'
    this.status = status
    this.detail = detail
  }
}

export class ApiNetworkError extends Error {
  constructor(message = 'Network error') {
    super(message)
    this.name = 'ApiNetworkError'
  }
}

export class ApiTimeoutError extends Error {
  constructor(message = 'Request timed out') {
    super(message)
    this.name = 'ApiTimeoutError'
  }
}

// ---------------------------------------------------------------------------
// Module-level state
// ---------------------------------------------------------------------------

let _token: string | null = null
let _onUnauthorized: (() => void) | null = null

export function setAuthToken(token: string | null): void {
  _token = token
}

export function getAuthToken(): string | null {
  return _token
}

export function setOnUnauthorized(cb: () => void): void {
  _onUnauthorized = cb
}

// ---------------------------------------------------------------------------
// Parse 422 validation errors into human-readable string
// ---------------------------------------------------------------------------

function parseValidationErrors(detail: unknown): string {
  if (!Array.isArray(detail)) {
    return String(detail)
  }
  return (detail as ValidationErrorItem[])
    .map((e) => {
      const field = e.loc.slice(1).join('.')
      return field ? `${field}: ${e.msg}` : e.msg
    })
    .join('; ')
}

// ---------------------------------------------------------------------------
// Core request function
// ---------------------------------------------------------------------------

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const url = `${BASE_URL}${path}`

  const headers: Record<string, string> = {
    'Accept': 'application/json',
    'Accept-Language': i18n.global.locale.value,
  }

  if (_token) {
    headers['Authorization'] = `Bearer ${_token}`
  }

  if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
  }

  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), TIMEOUT_MS)

  let response: Response

  try {
    response = await fetch(url, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    })
  } catch (err: unknown) {
    if (err instanceof DOMException && err.name === 'AbortError') {
      throw new ApiTimeoutError()
    }
    throw new ApiNetworkError(err instanceof Error ? err.message : 'Network error')
  } finally {
    clearTimeout(timeoutId)
  }

  // 204 No Content -- no body to parse.
  if (response.status === 204) {
    return undefined as unknown as T
  }

  // 401 Unauthorized -- invoke callback, then throw.
  if (response.status === 401) {
    _onUnauthorized?.()
    throw new ApiResponseError(401, 'Unauthorized')
  }

  // Parse response body.
  let data: unknown
  try {
    data = await response.json()
  } catch {
    throw new ApiResponseError(response.status, `HTTP ${response.status}: non-JSON response`)
  }

  // 422 Validation Error -- parse detail array.
  if (response.status === 422) {
    const detail =
      data && typeof data === 'object' && 'detail' in data
        ? (data as { detail: unknown }).detail
        : data
    throw new ApiResponseError(422, parseValidationErrors(detail))
  }

  // Other error statuses.
  if (!response.ok) {
    const detail =
      data && typeof data === 'object' && 'detail' in data
        ? String((data as { detail: unknown }).detail)
        : JSON.stringify(data)
    throw new ApiResponseError(response.status, detail)
  }

  return data as T
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export const api = {
  get<T>(path: string): Promise<T> {
    return request<T>('GET', path)
  },

  post<T>(path: string, body?: unknown): Promise<T> {
    return request<T>('POST', path, body)
  },

  patch<T>(path: string, body?: unknown): Promise<T> {
    return request<T>('PATCH', path, body)
  },

  put<T>(path: string, body?: unknown): Promise<T> {
    return request<T>('PUT', path, body)
  },

  delete(path: string): Promise<void> {
    return request<void>('DELETE', path)
  },
}
