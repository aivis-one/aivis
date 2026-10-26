// =============================================================================
// TelegramSecondCodeView -- the second code of a returning two-factor person
// =============================================================================

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import { defineComponent, h } from 'vue'

const push = vi.hoisted(() => vi.fn(async () => {}))
const replace = vi.hoisted(() => vi.fn(async () => {}))
vi.mock('vue-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('vue-router')>()
  return { ...actual, useRouter: () => ({ push, replace }) }
})
// The screen runs in the Mini App and, since H45, on the website; the tests
// above the website block are the Mini App's, so that is the default here.
const platformMock = vi.hoisted(() => ({ name: 'telegram' as string }))
vi.mock('@/platform', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/platform')>()
  // The real platform (its storage driver serves the store); only the name
  // answers from platformMock.
  return {
    platform: new Proxy(actual.platform, {
      get: (target, key) => (key === 'name' ? platformMock.name : Reflect.get(target, key)),
    }),
  }
})
vi.mock('@/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/client')>()
  return {
    ...actual,
    api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  }
})
vi.mock('@/api/auth', () => ({ verifyTwoFactorLogin: vi.fn() }))
vi.mock('@/i18n', () => ({
  i18n: { global: { locale: { value: 'en' }, t: (k: string) => k } },
  setLocale: vi.fn(),
}))

import { ApiResponseError } from '@/api/client'
import { verifyTwoFactorLogin } from '@/api/auth'
import { useAuthStore } from '@/stores/auth'
import en from '@/i18n/locales/en.json'
import TelegramSecondCodeView from './TelegramSecondCodeView.vue'

const verify = vi.mocked(verifyTwoFactorLogin)
const USER = { id: 'u1', role: 'investor', language: 'en', onboarding_step: 'onboarding_complete' }

const AuthShellStub = defineComponent({
  setup(_, { slots }) {
    return () => h('div', slots.default?.())
  },
})

function mountView(): VueWrapper {
  const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
  return mount(TelegramSecondCodeView, {
    global: { plugins: [i18n], stubs: { AuthShell: AuthShellStub } },
  })
}

describe('TelegramSecondCodeView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    verify.mockReset()
    push.mockClear()
    replace.mockClear()
    platformMock.name = 'telegram'
    useAuthStore().telegramMfaToken = 'MT1'
  })

  it('completes the sign-in with the pending token and the typed code', async () => {
    verify.mockResolvedValueOnce({ user: USER, session_token: 'S1' } as never)
    const w = mountView()

    await w.find('input').setValue('123456')
    await w.find('button.ds-button--primary').trigger('click')
    await flushPromises()

    expect(verify).toHaveBeenCalledWith({ mfa_token: 'MT1', code: '123456' })
    expect(useAuthStore().isAuthenticated).toBe(true)
    expect(useAuthStore().telegramMfaToken).toBeNull()
    expect(push).toHaveBeenCalledTimes(1)
  })

  it('switches to a backup code and back', async () => {
    const w = mountView()
    expect(w.text()).toContain(en.auth.login.mfa.codeLabel)
    await w.find('.ds-auth__foot button').trigger('click')
    expect(w.text()).toContain(en.auth.login.mfa.backupCodeLabel)
  })

  it('asks for the app to be opened again when the code is refused, since the token is used up', async () => {
    verify.mockRejectedValueOnce(new ApiResponseError(400, 'Invalid verification code'))
    const w = mountView()

    await w.find('input').setValue('000000')
    await w.find('button.ds-button--primary').trigger('click')
    await flushPromises()

    expect(w.text()).toContain(en.auth.telegramEntry.secondCodeEnded)
    expect(w.find('input').exists()).toBe(false)
    expect(useAuthStore().telegramMfaToken).toBeNull()
    expect(push).not.toHaveBeenCalled()
  })

  it('keeps the screen and shows the rate-limit text on a 429', async () => {
    verify.mockRejectedValueOnce(new ApiResponseError(429, 'slow down'))
    const w = mountView()

    await w.find('input').setValue('000000')
    await w.find('button.ds-button--primary').trigger('click')
    await flushPromises()

    expect(w.find('.ds-alert--danger').text()).toBe(en.auth.error.rateLimited)
    expect(useAuthStore().telegramMfaToken).toBe('MT1')
  })

  it('on the website says to start again from the sign-in screen, with the way back (H45)', async () => {
    platformMock.name = 'standalone'
    verify.mockRejectedValueOnce(new ApiResponseError(400, 'Invalid verification code'))
    const w = mountView()

    await w.find('input').setValue('000000')
    await w.find('button.ds-button--primary').trigger('click')
    await flushPromises()

    expect(w.text()).toContain(en.auth.telegramEntry.secondCodeEndedWeb)
    expect(w.text()).not.toContain(en.auth.telegramEntry.secondCodeEnded)
    await w.find('button.ds-button--primary').trigger('click')
    expect(replace).toHaveBeenCalledWith({ name: 'login' })
  })
})
