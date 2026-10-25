// =============================================================================
// stores/auth -- the Telegram entry: link token, e-mail step, code step
// =============================================================================
//
// POST /auth/telegram answers `link_required` for a Telegram id nobody holds: no
// session, a link token kept in memory. sendTelegramLinkEmail and
// confirmTelegramLink finish the sign-in; confirm sets the session the way a
// normal login does.
// =============================================================================

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/client')>()
  return {
    ...actual,
    api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  }
})
vi.mock('@/i18n', () => ({
  i18n: { global: { locale: { value: 'en' }, t: (k: string) => k } },
  setLocale: vi.fn(),
}))

import { api, ApiResponseError } from '@/api/client'
import { REFERRAL_KEY, useAuthStore } from './auth'

const post = vi.mocked(api.post)
const USER = { id: 'u1', email: 'a@b.co', language: 'en', onboarding_step: 'onboarding_complete' }

function secondCodeRequired(): ApiResponseError {
  const err = new ApiResponseError(400, 'Enter the code from your authenticator app.')
  err.code = 'second_code_required'
  return err
}

describe('auth store -- the Telegram entry', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    post.mockReset()
    sessionStorage.clear()
    localStorage.clear()
  })

  it('keeps the link token in memory and sets no session on link_required', async () => {
    post.mockResolvedValueOnce({ link_required: true, link_token: 'LT1' })
    const store = useAuthStore()

    const result = await store.loginViaTelegram('init', 'REF')

    expect(result).toEqual({ mfaRequired: false, linkRequired: true })
    expect(store.telegramLinkToken).toBe('LT1')
    expect(store.isAuthenticated).toBe(false)
    expect(store.token).toBeNull()
    // The token is never written to a storage.
    expect(JSON.stringify({ ...localStorage })).not.toContain('LT1')
    expect(JSON.stringify({ ...sessionStorage })).not.toContain('LT1')
  })

  it('keeps the pending token of a two-factor account for the second-code screen', async () => {
    post.mockResolvedValueOnce({ mfa_required: true, mfa_token: 'MT1' })
    const store = useAuthStore()

    const result = await store.loginViaTelegram('init')

    expect(result).toEqual({ mfaRequired: true, mfaToken: 'MT1' })
    expect(store.telegramMfaToken).toBe('MT1')
    expect(store.telegramLinkToken).toBeNull()
    expect(store.isAuthenticated).toBe(false)
  })

  it('sets the session on a plain Telegram login', async () => {
    post.mockResolvedValueOnce({ user: USER, session_token: 'S1' })
    const store = useAuthStore()

    const result = await store.loginViaTelegram('init')

    expect(result).toEqual({ mfaRequired: false })
    expect(store.isAuthenticated).toBe(true)
    expect(store.telegramLinkToken).toBeNull()
  })

  it('sendTelegramLinkEmail posts the token, the e-mail, the consent and the referral code', async () => {
    post.mockResolvedValueOnce({ link_required: true, link_token: 'LT1' })
    const store = useAuthStore()
    await store.loginViaTelegram('init')
    post.mockResolvedValueOnce({ status: 'code_sent', code_ttl_minutes: 10 })

    const answer = await store.sendTelegramLinkEmail('a@b.co', 'REF')

    expect(answer.code_ttl_minutes).toBe(10)
    expect(post).toHaveBeenLastCalledWith('/api/v1/auth/telegram/link/email', {
      link_token: 'LT1',
      email: 'a@b.co',
      consent_given: true,
      referral_code: 'REF',
    })
    // The e-mail step creates no session.
    expect(store.isAuthenticated).toBe(false)
  })

  it('sends a missing referral code as null, never as an empty string', async () => {
    post.mockResolvedValueOnce({ link_required: true, link_token: 'LT1' })
    const store = useAuthStore()
    await store.loginViaTelegram('init')
    post.mockResolvedValueOnce({ status: 'code_sent', code_ttl_minutes: 10 })

    await store.sendTelegramLinkEmail('a@b.co', '')

    expect(post.mock.calls.at(-1)?.[1]).toMatchObject({ referral_code: null })
  })

  it('refuses both steps when there is no link token', async () => {
    const store = useAuthStore()
    await expect(store.sendTelegramLinkEmail('a@b.co')).rejects.toThrow()
    await expect(store.confirmTelegramLink('123456')).rejects.toThrow()
    expect(post).not.toHaveBeenCalled()
  })

  it('confirmTelegramLink sets the session like a login and drops the token and referral code', async () => {
    post.mockResolvedValueOnce({ link_required: true, link_token: 'LT1' })
    const store = useAuthStore()
    await store.loginViaTelegram('init')
    sessionStorage.setItem(REFERRAL_KEY, 'REF')
    post.mockResolvedValueOnce({ user: USER, session_token: 'S1' })

    await store.confirmTelegramLink('123456')

    expect(post).toHaveBeenLastCalledWith('/api/v1/auth/telegram/link/confirm', {
      link_token: 'LT1',
      code: '123456',
      second_code: null,
    })
    expect(store.token).toBe('S1')
    expect(store.user).toEqual(USER)
    expect(store.isAuthenticated).toBe(true)
    expect(store.telegramLinkToken).toBeNull()
    expect(sessionStorage.getItem(REFERRAL_KEY)).toBeNull()
  })

  it('keeps the link token when the server asks for the second code, and sends it on the next call', async () => {
    post.mockResolvedValueOnce({ link_required: true, link_token: 'LT1' })
    const store = useAuthStore()
    await store.loginViaTelegram('init')
    post.mockRejectedValueOnce(secondCodeRequired())

    await expect(store.confirmTelegramLink('123456')).rejects.toMatchObject({
      code: 'second_code_required',
    })
    expect(store.telegramLinkToken).toBe('LT1')
    expect(store.isAuthenticated).toBe(false)

    post.mockResolvedValueOnce({ user: USER, session_token: 'S1' })
    await store.confirmTelegramLink('123456', '654321')

    expect(post).toHaveBeenLastCalledWith('/api/v1/auth/telegram/link/confirm', {
      link_token: 'LT1',
      code: '123456',
      second_code: '654321',
    })
    expect(store.isAuthenticated).toBe(true)
  })

  it('completeMfaLogin drops the pending Telegram token once the session is set', async () => {
    post.mockResolvedValueOnce({ mfa_required: true, mfa_token: 'MT1' })
    const store = useAuthStore()
    await store.loginViaTelegram('init')
    post.mockResolvedValueOnce({ user: USER, session_token: 'S1' })

    await store.completeMfaLogin('MT1', '123456')

    expect(store.isAuthenticated).toBe(true)
    expect(store.telegramMfaToken).toBeNull()
  })

  it('clearTelegramEntry forgets both tokens', async () => {
    post.mockResolvedValueOnce({ link_required: true, link_token: 'LT1' })
    const store = useAuthStore()
    await store.loginViaTelegram('init')

    store.clearTelegramEntry()

    expect(store.telegramLinkToken).toBeNull()
    expect(store.telegramMfaToken).toBeNull()
  })
})
