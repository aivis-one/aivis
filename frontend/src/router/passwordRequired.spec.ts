// =============================================================================
// router/guards -- the first password (H44): an account whose e-mail is
// confirmed and that has no password is held on /set-password, before
// anything else, in the Mini App and in the cabinet alike
// =============================================================================

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import type { RouteLocationNormalized } from 'vue-router'

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
// The guard waits for the auth bootstrap; here the store is filled by the
// login actions themselves, so the bootstrap is already over.
vi.mock('@/composables/useAuth', () => ({
  useAuth: () => ({ waitUntilReady: async () => {} }),
}))
const agreement = vi.hoisted(() => ({ status: 'unsigned' as string }))
vi.mock('@/stores/agentAgreement', () => ({
  useAgentAgreementStore: () => ({ ensure: async () => agreement.status }),
}))
const terms = vi.hoisted(() => ({ status: 'unsigned' as string }))
vi.mock('@/stores/companyTerms', () => ({
  useCompanyTermsStore: () => ({ ensure: async () => terms.status }),
}))

import { api } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import { setAvatarActive } from '@/composables/avatarState'
import { globalGuard, passwordRedirect, SET_PASSWORD_ROUTE } from './guards'

const post = vi.mocked(api.post)
const get = vi.mocked(api.get)

function to(name: string, meta: Record<string, unknown> = {}): RouteLocationNormalized {
  return { name, path: `/${name}`, fullPath: `/${name}`, meta, params: {}, query: {} } as never
}

function user(overrides: Record<string, unknown> = {}) {
  return {
    id: 'u1',
    role: 'investor',
    language: 'en',
    email: 'a@example.com',
    onboarding_step: 'onboarding_complete',
    password_required: true,
    ...overrides,
  }
}

/** Signed in the way the Mini App signs in (POST /auth/telegram). */
async function viaMiniApp(u: Record<string, unknown>) {
  post.mockResolvedValueOnce({ user: u, session_token: 'S-tg' })
  await useAuthStore().loginViaTelegram('init-data')
}

/** Signed in the way the cabinet signs in (POST /auth/email/login). */
async function viaCabinet(u: Record<string, unknown>) {
  post.mockResolvedValueOnce({ user: u, session_token: 'S-web' })
  await useAuthStore().loginViaEmail('a@example.com', 'whatever-1')
}

beforeEach(() => {
  setActivePinia(createPinia())
  post.mockReset()
  get.mockReset()
  sessionStorage.clear()
  setAvatarActive(false)
  agreement.status = 'unsigned'
  terms.status = 'unsigned'
})

afterEach(() => setAvatarActive(false))

describe('the password step of globalGuard', () => {
  it.each([
    ['the Mini App', viaMiniApp],
    ['the cabinet', viaCabinet],
  ])(
    'holds an account without a password on the screen from any protected route (%s)',
    async (_n, signIn) => {
      await signIn(user())
      for (const name of [
        'investor-dashboard',
        'investor-settings',
        'staff-dashboard',
        'onboarding-docs',
      ]) {
        expect(await globalGuard(to(name)), name).toEqual({ name: SET_PASSWORD_ROUTE })
      }
      expect(await globalGuard(to(SET_PASSWORD_ROUTE, { skipOnboarding: true }))).toBeUndefined()
    },
  )

  it('comes before every onboarding step', async () => {
    await viaCabinet(user({ onboarding_step: 'email_verified' }))
    expect(await globalGuard(to('investor-dashboard'))).toEqual({ name: SET_PASSWORD_ROUTE })
    expect(await globalGuard(to('verify', { skipOnboarding: true }))).toEqual({
      name: SET_PASSWORD_ROUTE,
    })
  })

  it('keeps an integrator and a project account on the screen, without a loop', async () => {
    await viaCabinet(user({ role: 'agent' }))
    expect(await globalGuard(to('agent-welcome'))).toEqual({ name: SET_PASSWORD_ROUTE })
    expect(await globalGuard(to(SET_PASSWORD_ROUTE, { skipOnboarding: true }))).toBeUndefined()

    setActivePinia(createPinia())
    await viaCabinet(user({ role: 'company' }))
    expect(await globalGuard(to('company-welcome'))).toEqual({ name: SET_PASSWORD_ROUTE })
    expect(await globalGuard(to(SET_PASSWORD_ROUTE, { skipOnboarding: true }))).toBeUndefined()
  })

  it.each([
    ['the Mini App', viaMiniApp],
    ['the cabinet', viaCabinet],
  ])(
    'lets an account with a password through and leads it off the screen (%s)',
    async (_n, signIn) => {
      await signIn(user({ password_required: false }))
      expect(await globalGuard(to('investor-dashboard'))).toBeUndefined()
      expect(await globalGuard(to(SET_PASSWORD_ROUTE, { skipOnboarding: true }))).toBe(
        '/investor/dashboard',
      )
    },
  )

  it('treats a missing flag as no requirement', async () => {
    const u = user()
    delete (u as Record<string, unknown>).password_required
    await viaCabinet(u)
    expect(await globalGuard(to('investor-dashboard'))).toBeUndefined()
  })

  it('does not hold a staff member operating as the person', async () => {
    await viaCabinet(user())
    setAvatarActive(true)
    expect(await globalGuard(to('investor-dashboard'))).toBeUndefined()
    expect(await globalGuard(to(SET_PASSWORD_ROUTE, { skipOnboarding: true }))).toBe(
      '/investor/dashboard',
    )
  })

  it('leaves the public routes open to the person', async () => {
    await viaCabinet(user())
    expect(await globalGuard(to('public-companies', { public: true }))).toBeUndefined()
    expect(await globalGuard(to('password-reset-request', { public: true }))).toBeUndefined()
  })

  it('is silent while nobody is signed in', async () => {
    const store = useAuthStore()
    expect(store.user).toBeNull()
    expect(passwordRedirect(to('investor-dashboard'), store)).toBeNull()
    expect(await globalGuard(to('investor-dashboard'))).toEqual({
      name: 'login',
      query: { next: '/investor-dashboard' },
    })
  })
})
