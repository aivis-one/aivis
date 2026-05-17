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
//   - 429 → ApiResponseError carrying parsed Retry-After header
//   - 204 → returns undefined
//   - Network errors → ApiNetworkError
//   - AbortController + 15s timeout → ApiTimeoutError
//   - Accept-Language from current vue-i18n locale
//
// iter 2.6 Batch 1: ApiResponseError gained an optional `retryAfter`
// field. On HTTP 429 the core `request()` reads the canonical
// `Retry-After` response header (introduced backend-side in
// iter 2.5-finishing) and threads it into the thrown error. The field
// is undefined for non-429 responses or when the header is missing /
// not a positive integer. Existing `instanceof ApiResponseError`
// checks compile and run unchanged -- the new field is purely additive.
//
// iter 2.6 Batch 1 R20 fix (FE-20-01): parseRetryAfterHeader() is now
// exported so api/attachments.ts (which speaks fetch() directly to
// reach the 302-redirected download endpoint) can reuse the same
// parser instead of inlining a copy. Single source of truth if the
// parsing rules ever change (e.g. add HTTP-date support).
// =============================================================================

import { i18n } from '@/i18n'
import type { ValidationErrorItem } from '@/api/types'

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'https://api.cbshome.org'
const TIMEOUT_MS = 15_000

/**
 * Absolute API base URL. Exported so non-JSON endpoints (e.g. the
 * certificate HTML served as text/html) can build absolute URLs
 * via `${API_BASE_URL}${path}` without duplicating the env lookup
 * or the https://api.cbshome.org fallback.
 *
 * JSON endpoints should keep using `api.get`/`api.post` -- those
 * already handle BASE_URL, auth header, timeout, and JSON parsing.
 */
export const API_BASE_URL: string = BASE_URL

// ---------------------------------------------------------------------------
// Error classes
// ---------------------------------------------------------------------------

export class ApiResponseError extends Error {
  status: number
  detail: string
  /**
   * Parsed `Retry-After` response header value in seconds. Populated
   * only for HTTP 429 responses where the header is present and parses
   * as a positive integer; undefined for every other case.
   *
   * Callers showing a "try again in N seconds" toast on 429 should
   * read this field and fall back to a generic "try again in a minute"
   * message when undefined (header missing, malformed, or non-positive).
   *
   * Note: HTTP defines Retry-After as either delta-seconds (int) or an
   * HTTP-date. Our backend (app/main.py CBSError handler) only emits
   * delta-seconds; the date variant is intentionally not parsed here.
   */
  retryAfter?: number

  constructor(status: number, detail: string, retryAfter?: number) {
    super(detail)
    this.name = 'ApiResponseError'
    this.status = status
    this.detail = detail
    this.retryAfter = retryAfter
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
// Extract human-readable error message from response body
// ---------------------------------------------------------------------------

function extractErrorMessage(status: number, data: unknown): string {
  if (!data || typeof data !== 'object') {
    return `HTTP ${status}`
  }

  const obj = data as Record<string, unknown>

  // FastAPI format: { detail: "..." } or { detail: [...] }
  if ('detail' in obj) {
    if (status === 422) {
      return parseValidationErrors(obj.detail)
    }
    return String(obj.detail)
  }

  // Rate limiter / middleware format: { error: "...", message: "..." }
  if ('message' in obj && typeof obj.message === 'string') {
    return obj.message
  }

  // Fallback: stringify the object.
  return JSON.stringify(data)
}

// ---------------------------------------------------------------------------
// Parse Retry-After response header for HTTP 429
// ---------------------------------------------------------------------------

/**
 * Read `Retry-After` from a Response and return seconds as a positive
 * integer. Returns undefined when the header is absent, not parseable
 * as a base-10 integer, or non-positive.
 *
 * Backend emits delta-seconds only (see app/main.py CBSError handler);
 * the HTTP-date variant of Retry-After is out of scope.
 *
 * Exported (R20 FE-20-01) so api/attachments.ts can reuse the same
 * parser inside its raw-fetch download path. Single source of truth.
 */
export function parseRetryAfterHeader(response: Response): number | undefined {
  const raw = response.headers.get('Retry-After')
  if (raw === null) return undefined
  // Number(raw) is too permissive ("12abc" -> NaN, but " 12 " -> 12);
  // parseInt with radix 10 matches the backend's int(value) shape.
  const parsed = parseInt(raw, 10)
  if (Number.isNaN(parsed) || parsed <= 0) return undefined
  return parsed
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
    // Non-JSON 4xx/5xx still needs Retry-After plumbed for the 429
    // case -- a misconfigured upstream could in theory emit 429 with
    // an empty/non-JSON body. Read it before throwing.
    const retryAfter =
      response.status === 429 ? parseRetryAfterHeader(response) : undefined
    throw new ApiResponseError(
      response.status,
      `HTTP ${response.status}: non-JSON response`,
      retryAfter,
    )
  }

  // Error responses (4xx, 5xx).
  if (!response.ok) {
    const retryAfter =
      response.status === 429 ? parseRetryAfterHeader(response) : undefined
    throw new ApiResponseError(
      response.status,
      extractErrorMessage(response.status, data),
      retryAfter,
    )
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
