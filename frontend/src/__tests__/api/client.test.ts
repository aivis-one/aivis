import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { apiRequest } from '@/api/client'

// Mock fetch globally
const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

function jsonResponse(data: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: 'OK',
    json: () => Promise.resolve(data),
    headers: new Headers(),
    redirected: false,
    type: 'basic',
    url: '',
    clone: () => ({}) as Response,
    body: null,
    bodyUsed: false,
    arrayBuffer: () => Promise.resolve(new ArrayBuffer(0)),
    blob: () => Promise.resolve(new Blob()),
    formData: () => Promise.resolve(new FormData()),
    text: () => Promise.resolve(''),
  } as Response
}

describe('apiRequest', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
    localStorage.clear()
    sessionStorage.clear()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('returns data on success', async () => {
    mockFetch.mockResolvedValue(jsonResponse({ id: 1, name: 'test' }))
    const result = await apiRequest<{ id: number; name: string }>('GET', '/test')
    expect(result).toEqual({ id: 1, name: 'test' })
  })

  it('retries on network error and succeeds', async () => {
    mockFetch
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValueOnce(jsonResponse({ ok: true }))

    const promise = apiRequest('GET', '/test')
    await vi.advanceTimersByTimeAsync(1000)
    const result = await promise

    expect(result).toEqual({ ok: true })
    expect(mockFetch).toHaveBeenCalledTimes(2)
  })

  it('retries on 503 and succeeds', async () => {
    mockFetch
      .mockResolvedValueOnce(jsonResponse({ message: 'Service unavailable' }, 503))
      .mockResolvedValueOnce(jsonResponse({ ok: true }))

    const promise = apiRequest('GET', '/test')
    await vi.advanceTimersByTimeAsync(1000)
    const result = await promise

    expect(result).toEqual({ ok: true })
    expect(mockFetch).toHaveBeenCalledTimes(2)
  })

  it('does NOT retry on 401', async () => {
    mockFetch.mockResolvedValue(jsonResponse({ message: 'Unauthorized' }, 401))

    await expect(apiRequest('GET', '/test')).rejects.toThrow('Unauthorized')
    expect(mockFetch).toHaveBeenCalledTimes(1)
  })

  it('does NOT retry on 422', async () => {
    mockFetch.mockResolvedValue(jsonResponse({ message: 'Validation error' }, 422))

    await expect(apiRequest('GET', '/test')).rejects.toThrow('Validation error')
    expect(mockFetch).toHaveBeenCalledTimes(1)
  })

  it('gives up after max retries', async () => {
    mockFetch.mockRejectedValue(new TypeError('Failed to fetch'))

    const promise = apiRequest('GET', '/test').catch((e) => e)
    await vi.advanceTimersByTimeAsync(1000)
    await vi.advanceTimersByTimeAsync(2000)

    const error = await promise
    expect(error).toBeInstanceOf(TypeError)
    expect(error.message).toBe('Failed to fetch')
    expect(mockFetch).toHaveBeenCalledTimes(3)
  })
})
