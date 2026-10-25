// =============================================================================
// router/guards -- where an unfinished Telegram sign-in is held, and useAuth's
// Telegram auto-login that leaves the tokens for the guard
// =============================================================================

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import type { RouteLocationNormalized } from 'vue-router'

const platformMock = vi.hoisted(() => ({
  name: 'telegram',
  init: vi.fn(async () => {}),
  getInitData: vi.fn(() => 'init-data'),
  getStartParam: vi.fn(() => null as string | null),
  getStorageDriver: vi.fn(() => 'sessionStorage'),
}))
vi.mock('@/platform', () => ({ platform: platformMock }))
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

import { api } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import { useAuth } from '@/composables/useAuth'
import { globalGuard, telegramEntryRedirect } from './guards'

const post = vi.mocked(api.post)

function to(name: string, isPublic = true): RouteLocationNormalized {
  return { name, path: `/${name}`, fullPath: `/${name}`, meta: { public: isPublic } } as never
}

describe('telegramEntryRedirect', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('holds a person with a link token on the entry screen', () => {
    const store = useAuthStore()
    store.telegramLinkToken = 'LT1'
    expect(telegramEntryRedirect(to('login'), store)).toEqual({ name: 'telegram-entry' })
    expect(telegramEntryRedirect(to('investor-dashboard', false), store)).toEqual({
      name: 'telegram-entry',
    })
    expect(telegramEntryRedirect(to('telegram-entry'), store)).toBeNull()
    expect(telegramEntryRedirect(to('telegram-second-code'), store)).toEqual({
      name: 'telegram-entry',
    })
  })

  it('sends a two-factor person to the second-code screen', () => {
    const store = useAuthStore()
    store.telegramMfaToken = 'MT1'
    expect(telegramEntryRedirect(to('login'), store)).toEqual({ name: 'telegram-second-code' })
    expect(telegramEntryRedirect(to('telegram-second-code'), store)).toBeNull()
  })

  it('leads either screen without its token to /login and leaves other screens alone', () => {
    const store = useAuthStore()
    expect(telegramEntryRedirect(to('telegram-entry'), store)).toEqual({ name: 'login' })
    expect(telegramEntryRedirect(to('telegram-second-code'), store)).toEqual({ name: 'login' })
    expect(telegramEntryRedirect(to('login'), store)).toBeNull()
    expect(telegramEntryRedirect(to('public-companies'), store)).toBeNull()
  })
})

describe('Telegram auto-login routes by the guard', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    post.mockReset()
    sessionStorage.clear()
  })

  it('a new Telegram id: link token kept, no error screen, the guard leads to the entry screen', async () => {
    post.mockResolvedValueOnce({ link_required: true, link_token: 'LT1' })
    const { initAuth, authError } = useAuth()

    await initAuth()

    const store = useAuthStore()
    expect(authError.value).toBeNull()
    expect(store.telegramLinkToken).toBe('LT1')
    expect(await globalGuard(to('login'))).toEqual({ name: 'telegram-entry' })
    expect(await globalGuard(to('telegram-entry'))).toBeUndefined()
  })

  it('a two-factor account: pending token kept, the error text is gone, the guard leads to the second-code screen', async () => {
    post.mockResolvedValueOnce({ mfa_required: true, mfa_token: 'MT1' })
    const { initAuth, authError } = useAuth()

    await initAuth()

    const store = useAuthStore()
    expect(authError.value).toBeNull()
    expect(store.telegramMfaToken).toBe('MT1')
    expect(await globalGuard(to('login'))).toEqual({ name: 'telegram-second-code' })
    expect(await globalGuard(to('telegram-second-code'))).toBeUndefined()
  })

  it('a signed-in person never sees the entry screens', async () => {
    post.mockResolvedValueOnce({
      user: { id: 'u1', role: 'investor', language: 'en', onboarding_step: 'onboarding_complete' },
      session_token: 'S1',
    })
    const { initAuth } = useAuth()

    await initAuth()

    expect(await globalGuard(to('telegram-entry'))).toBe('/investor/dashboard')
    expect(await globalGuard(to('telegram-second-code'))).toBe('/investor/dashboard')
  })

  it('a web visitor with no Telegram token is never held on the entry screens', async () => {
    expect(await globalGuard(to('login'))).toBeUndefined()
    expect(await globalGuard(to('register'))).toBeUndefined()
    expect(await globalGuard(to('telegram-entry'))).toEqual({ name: 'login' })
  })
})
