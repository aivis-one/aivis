import { ApiError, UnauthorizedError, ForbiddenError, ValidationError, ServerError } from './types'

const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'https://api.cbshome.org'

function generateTraceId(): string {
  return crypto.randomUUID()
}

function getLocale(): string {
  return localStorage.getItem('cbs-lang') || 'en'
}

function getToken(): string | null {
  return localStorage.getItem('auth_token') || sessionStorage.getItem('auth_token')
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (response.ok) {
    if (response.status === 204) {
      return undefined as T
    }
    return response.json()
  }

  const body = await response.json().catch(() => ({}))
  const message = body.message || response.statusText

  switch (response.status) {
    case 401:
      throw new UnauthorizedError(message)
    case 403:
      throw new ForbiddenError(message)
    case 422:
      throw new ValidationError(message, body.errors)
    case 500:
    case 502:
    case 503:
      throw new ServerError(message)
    default:
      throw new ApiError(response.status, body.error || 'UNKNOWN', message)
  }
}

const MAX_RETRIES = 2
const RETRY_DELAYS = [1000, 2000]

function isRetryable(error: unknown): boolean {
  if (error instanceof TypeError) return true
  if (error instanceof ServerError) return true
  return false
}

async function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

export async function apiRequest<T>(
  method: string,
  path: string,
  body?: unknown,
  options?: { skipAuth?: boolean },
): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Accept: 'application/json',
    'Accept-Language': getLocale(),
    'X-Trace-ID': generateTraceId(),
  }

  const token = getToken()
  if (token && !options?.skipAuth) {
    headers['Authorization'] = `Bearer ${token}`
  }

  let lastError: unknown
  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    try {
      const controller = new AbortController()
      const timeout = setTimeout(() => controller.abort(), 15000)

      const response = await fetch(`${BASE_URL}${path}`, {
        method,
        headers,
        credentials: 'include',
        body: body ? JSON.stringify(body) : undefined,
        signal: controller.signal,
      })

      clearTimeout(timeout)
      return await handleResponse<T>(response)
    } catch (e: unknown) {
      lastError = e
      if (attempt < MAX_RETRIES && isRetryable(e)) {
        await sleep(RETRY_DELAYS[attempt])
        continue
      }
      throw e
    }
  }

  throw lastError
}

export async function apiUpload<T>(path: string, formData: FormData): Promise<T> {
  const headers: Record<string, string> = {
    Accept: 'application/json',
    'Accept-Language': getLocale(),
    'X-Trace-ID': generateTraceId(),
  }

  const token = getToken()
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const response = await fetch(`${BASE_URL}${path}`, {
    method: 'POST',
    headers,
    credentials: 'include',
    body: formData,
  })

  return handleResponse<T>(response)
}

export const api = {
  get: <T>(path: string, options?: { skipAuth?: boolean }) =>
    apiRequest<T>('GET', path, undefined, options),

  post: <T>(path: string, body?: unknown, options?: { skipAuth?: boolean }) =>
    apiRequest<T>('POST', path, body, options),

  put: <T>(path: string, body?: unknown) => apiRequest<T>('PUT', path, body),

  patch: <T>(path: string, body?: unknown) => apiRequest<T>('PATCH', path, body),

  delete: <T>(path: string) => apiRequest<T>('DELETE', path),
}
