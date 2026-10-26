// =============================================================================
// TelegramReturnView -- the return of the website sign-in through Telegram (H45)
// =============================================================================

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import { defineComponent, h } from 'vue'

const replace = vi.hoisted(() => vi.fn(async () => {}))
const query = vi.hoisted(() => ({ value: {} as Record<string, string> }))
vi.mock('vue-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('vue-router')>()
  return {
    ...actual,
    useRouter: () => ({ replace, push: replace }),
    useRoute: () => ({ query: query.value }),
  }
})
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
import { useAuthStore } from '@/stores/auth'
import { LOGIN_MARK_KEY, rememberLoginMark } from '@/platform/webLogin'
import en from '@/i18n/locales/en.json'
import TelegramReturnView from './TelegramReturnView.vue'

const post = vi.mocked(api.post)
const USER = { id: 'u1', role: 'investor', language: 'en', onboarding_step: 'onboarding_complete' }

const AuthShellStub = defineComponent({
  setup(_, { slots }) {
    return () => h('div', slots.default?.())
  },
})

async function mountView(): Promise<VueWrapper> {
  const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
  const w = mount(TelegramReturnView, {
    global: { plugins: [i18n], stubs: { AuthShell: AuthShellStub } },
  })
  await flushPromises()
  return w
}

function apiError(status: number, code: string): ApiResponseError {
  const err = new ApiResponseError(status, 'server words')
  err.code = code
  return err
}

describe('TelegramReturnView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    replace.mockClear()
    post.mockReset()
    localStorage.clear()
    sessionStorage.clear()
    query.value = { code: 'C1', state: 'S1' }
  })

  it('wipes the address, completes with the mark and lands where a signed-in person goes', async () => {
    rememberLoginMark({ state: 'S1', mark: 'M1' })
    post.mockResolvedValueOnce({ user: USER, session_token: 'T1' })
    await mountView()

    expect(replace).toHaveBeenNthCalledWith(1, { name: 'telegram-return', query: {} })
    expect(post).toHaveBeenCalledWith('/api/v1/auth/telegram/web/complete', {
      code: 'C1',
      state: 'S1',
      mark: 'M1',
    })
    expect(useAuthStore().isAuthenticated).toBe(true)
    expect(replace).toHaveBeenLastCalledWith('/')
    expect(localStorage.getItem(LOGIN_MARK_KEY)).toBeNull()
  })

  it('leads a Telegram nobody holds to the entry steps', async () => {
    rememberLoginMark({ state: 'S1', mark: 'M1' })
    post.mockResolvedValueOnce({ link_required: true, link_token: 'LT1' })
    await mountView()
    expect(useAuthStore().telegramLinkToken).toBe('LT1')
    expect(replace).toHaveBeenLastCalledWith({ name: 'telegram-entry' })
  })

  it('leads a two-factor account to the second-code screen', async () => {
    rememberLoginMark({ state: 'S1', mark: 'M1' })
    post.mockResolvedValueOnce({ mfa_required: true, mfa_token: 'MT1' })
    await mountView()
    expect(useAuthStore().telegramMfaToken).toBe('MT1')
    expect(replace).toHaveBeenLastCalledWith({ name: 'telegram-second-code' })
  })

  it.each([
    ['no mark in this browser', null],
    ['a mark for another state', { state: 'OTHER', mark: 'M1' }],
  ])('refuses a return with %s, without a request', async (_name, mark) => {
    if (mark) rememberLoginMark(mark)
    const w = await mountView()
    expect(post).not.toHaveBeenCalled()
    expect(w.find('[role="alert"]').text()).toContain(en.auth.telegramWeb.foreign)
  })

  it('says the sign-in was cancelled when Telegram returns an error', async () => {
    query.value = { error: 'access_denied', state: 'S1' }
    rememberLoginMark({ state: 'S1', mark: 'M1' })
    const w = await mountView()
    expect(post).not.toHaveBeenCalled()
    expect(w.find('[role="alert"]').text()).toContain(en.auth.telegramWeb.cancelled)
    expect(localStorage.getItem(LOGIN_MARK_KEY)).toBeNull()
  })

  it('calls an address without code or state expired', async () => {
    query.value = {}
    const w = await mountView()
    expect(post).not.toHaveBeenCalled()
    expect(w.find('[role="alert"]').text()).toContain(en.auth.telegramWeb.expired)
  })

  it.each([
    ['login_expired', 400, en.auth.telegramWeb.expired],
    ['login_foreign', 400, en.auth.telegramWeb.foreign],
    ['telegram_failed', 400, en.auth.telegramWeb.failed],
    ['account_blocked', 403, 'server words'],
  ])('turns %s into its words and offers the way back', async (code, status, words) => {
    rememberLoginMark({ state: 'S1', mark: 'M1' })
    post.mockRejectedValueOnce(apiError(status, code))
    const w = await mountView()
    expect(w.find('[role="alert"]').text()).toContain(words)
    await w.find('button.ds-button--primary').trigger('click')
    expect(replace).toHaveBeenLastCalledWith({ name: 'login' })
  })
})
