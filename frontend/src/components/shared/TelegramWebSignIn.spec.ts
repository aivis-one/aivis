// =============================================================================
// TelegramWebSignIn -- "Continue with Telegram" on the website (H45)
// =============================================================================

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'

const platformMock = vi.hoisted(() => ({ name: 'standalone' as string }))
vi.mock('@/platform', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/platform')>()
  return {
    platform: new Proxy(actual.platform, {
      get: (target, key) => (key === 'name' ? platformMock.name : Reflect.get(target, key)),
    }),
  }
})
vi.mock('@/api/auth', () => ({
  getTelegramWebAvailability: vi.fn(),
  startTelegramWebLogin: vi.fn(),
}))
vi.mock('@/i18n', () => ({
  i18n: { global: { locale: { value: 'en' }, t: (k: string) => k } },
  setLocale: vi.fn(),
}))

import { ApiResponseError } from '@/api/client'
import { getTelegramWebAvailability, startTelegramWebLogin } from '@/api/auth'
import { REFERRAL_KEY } from '@/stores/auth'
import { takeLoginMark } from '@/platform/webLogin'
import en from '@/i18n/locales/en.json'
import ru from '@/i18n/locales/ru.json'
import TelegramWebSignIn from './TelegramWebSignIn.vue'

const available = vi.mocked(getTelegramWebAvailability)
const start = vi.mocked(startTelegramWebLogin)
const assign = vi.fn()

function mountButton(locale: 'en' | 'ru' = 'en'): VueWrapper {
  const i18n = createI18n({ legacy: false, locale, messages: { en, ru } })
  return mount(TelegramWebSignIn, { global: { plugins: [i18n] } })
}

describe('TelegramWebSignIn', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    platformMock.name = 'standalone'
    available.mockReset()
    start.mockReset()
    assign.mockReset()
    sessionStorage.clear()
    localStorage.clear()
    vi.stubGlobal('location', { ...window.location, assign })
  })
  afterEach(() => vi.unstubAllGlobals())

  it('shows the button when the server offers the sign-in', async () => {
    available.mockResolvedValueOnce({ available: true })
    const w = mountButton()
    await flushPromises()
    const button = w.find('button.ds-button--telegram')
    expect(button.exists()).toBe(true)
    expect(button.text()).toBe(en.auth.telegramWeb.button)
  })

  it.each([
    ['the server says no', () => available.mockResolvedValueOnce({ available: false })],
    ['the question fails', () => available.mockRejectedValueOnce(new Error('down'))],
  ])('shows nothing when %s', async (_name, arrange) => {
    arrange()
    const w = mountButton()
    await flushPromises()
    expect(w.find('button').exists()).toBe(false)
  })

  it('never asks inside the Mini App and shows nothing there', async () => {
    platformMock.name = 'telegram'
    const w = mountButton()
    await flushPromises()
    expect(available).not.toHaveBeenCalled()
    expect(w.find('button').exists()).toBe(false)
  })

  it('starts with a fresh mark, the referral code and the language, remembers the mark, goes to Telegram', async () => {
    available.mockResolvedValueOnce({ available: true })
    start.mockResolvedValueOnce({ url: 'https://telegram.example/auth?x=1', state: 'S1' })
    sessionStorage.setItem(REFERRAL_KEY, 'REF42')
    const w = mountButton('ru')
    await flushPromises()

    await w.find('button.ds-button--telegram').trigger('click')
    await flushPromises()

    expect(start).toHaveBeenCalledTimes(1)
    const body = start.mock.calls[0][0]
    expect(body.referral_code).toBe('REF42')
    expect(body.language).toBe('ru')
    expect(body.mark).toMatch(/^[A-Za-z0-9_-]{43}$/)
    expect(takeLoginMark()).toEqual({ state: 'S1', mark: body.mark })
    expect(assign).toHaveBeenCalledWith('https://telegram.example/auth?x=1')
  })

  it('stays with a message when the start is refused', async () => {
    available.mockResolvedValueOnce({ available: true })
    start.mockRejectedValueOnce(new ApiResponseError(429, 'slow down'))
    const w = mountButton()
    await flushPromises()
    await w.find('button.ds-button--telegram').trigger('click')
    await flushPromises()
    expect(w.find('[role="alert"]').text()).toContain(en.auth.error.rateLimited)
    expect(assign).not.toHaveBeenCalled()
    expect(takeLoginMark()).toBeNull()
  })
})
