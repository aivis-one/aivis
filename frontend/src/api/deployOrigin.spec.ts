// =============================================================================
// AIVIS.ONE Frontend -- requireOrigin (H35 P-127)
// =============================================================================
//
// The one rule every deployment address of the frontend passes through: the
// build (vite.config.ts), the Docker build (both origins) and the running
// bundle (client.ts). Each refusal names the variable -- that is the whole
// contract an operator meets, so every case asserts the name is in the message.
// =============================================================================

import { describe, expect, it } from 'vitest'
import { requireOrigin } from '@/api/deployOrigin'

const NAME = 'VITE_API_BASE_URL'
const PROD = { allowHttp: false }
const DEV = { allowHttp: true }

function refusal(value: string | undefined, rule = PROD): string {
  try {
    requireOrigin(NAME, value, rule)
  } catch (err) {
    return (err as Error).message
  }
  throw new Error(`accepted ${JSON.stringify(value)}`)
}

describe('requireOrigin', () => {
  it('returns an exact https origin unchanged, and it is not empty (the pair)', () => {
    const value = requireOrigin(NAME, 'https://api.example.com', PROD)
    expect(value).toBe('https://api.example.com')
    expect(value.length).toBeGreaterThan(0)
  })

  it('keeps an explicit non-default port', () => {
    expect(requireOrigin(NAME, 'https://api.example.com:8443', PROD)).toBe(
      'https://api.example.com:8443',
    )
  })

  // SHORTAGE: nothing there.
  it('refuses a variable that is not set, by name', () => {
    const msg = refusal(undefined)
    expect(msg).toContain(NAME)
    expect(msg).toContain('not set')
  })

  // EMPTINESS: there, and nothing in it.
  it('refuses an empty value, by name', () => {
    const msg = refusal('')
    expect(msg).toContain(NAME)
    expect(msg).toContain('empty')
  })

  it('refuses surrounding blanks', () => {
    expect(refusal(' https://api.example.com')).toContain(NAME)
    expect(refusal('https://api.example.com ')).toContain(NAME)
  })

  // REPEAT: two origins where one is expected.
  it('refuses two origins in one value', () => {
    expect(refusal('https://api.example.com,https://api.example.org')).toContain(NAME)
    expect(refusal('https://api.example.com https://api.example.org')).toContain(NAME)
  })

  it.each([
    ['a trailing slash', 'https://api.example.com/'],
    ['a path', 'https://api.example.com/v1'],
    ['a query', 'https://api.example.com?x=1'],
    ['a fragment', 'https://api.example.com#x'],
    ['credentials', 'https://user@api.example.com'],
    ['the default port spelled out', 'https://api.example.com:443'],
    ['uppercase in the host', 'https://API.example.com'],
  ])('refuses %s: an origin must be exact', (_what, value) => {
    const msg = refusal(value)
    expect(msg).toContain(NAME)
    expect(msg).toContain('must be an origin')
  })

  it('refuses a bare host and a non-URL', () => {
    expect(refusal('api.example.com')).toContain(NAME)
    expect(refusal('https://')).toContain(NAME)
  })

  it('refuses http:// for a production build and accepts it in development', () => {
    expect(refusal('http://api.example.com')).toContain('must start with https://')
    expect(requireOrigin(NAME, 'http://localhost:8000', DEV)).toBe('http://localhost:8000')
  })

  it('refuses any other scheme even in development', () => {
    expect(refusal('ftp://api.example.com', DEV)).toContain(NAME)
  })
})
