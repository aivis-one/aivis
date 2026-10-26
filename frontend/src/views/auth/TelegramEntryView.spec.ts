// =============================================================================
// TelegramEntryView -- consent, e-mail, code; the second code only when asked
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
vi.mock('@/i18n', () => ({
  i18n: { global: { locale: { value: 'en' }, t: (k: string) => k } },
  setLocale: vi.fn(),
}))

import { api, ApiResponseError } from '@/api/client'
import { REFERRAL_KEY, useAuthStore } from '@/stores/auth'
import en from '@/i18n/locales/en.json'
import TelegramEntryView from './TelegramEntryView.vue'

const post = vi.mocked(api.post)
const USER = { id: 'u1', role: 'investor', language: 'en', onboarding_step: 'onboarding_complete' }

const AuthShellStub = defineComponent({
  setup(_, { slots }) {
    return () => h('div', [slots.start?.(), slots.default?.()])
  },
})
const LegalDocModalStub = defineComponent({
  props: { open: Boolean, title: String, lang: String, type: String },
  setup(props) {
    return () =>
      props.open ? h('div', { class: 'doc-stub', 'data-type': props.type }, props.title) : null
  },
})

function apiError(status: number, code: string, retryAfter?: number): ApiResponseError {
  const err = new ApiResponseError(status, `server: ${code}`, retryAfter)
  err.code = code
  return err
}

function mountView(): VueWrapper {
  const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
  return mount(TelegramEntryView, {
    global: {
      plugins: [i18n],
      stubs: { AuthShell: AuthShellStub, LegalDocModal: LegalDocModalStub },
    },
  })
}

async function toEmailStep(w: VueWrapper): Promise<void> {
  const boxes = w.findAll('input[type="checkbox"]')
  await boxes[0]!.setValue(true)
  await boxes[1]!.setValue(true)
  await w.find('button.ds-button--primary').trigger('click')
}

async function sendEmail(w: VueWrapper, address = 'a@b.co'): Promise<void> {
  await w.find('input[type="email"]').setValue(address)
  await w.find('button.ds-button--primary').trigger('click')
  await flushPromises()
}

async function typeCode(w: VueWrapper, code = '123456'): Promise<void> {
  await w.findAll('.ds-otp__cell')[0]!.setValue(code)
}

describe('TelegramEntryView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    post.mockReset()
    push.mockClear()
    replace.mockClear()
    platformMock.name = 'telegram'
    sessionStorage.clear()
    useAuthStore().telegramLinkToken = 'LT1'
  })

  describe('step 1: consent', () => {
    it('keeps Continue disabled until both documents are ticked, and sends nothing', async () => {
      const w = mountView()
      const button = w.find('button.ds-button--primary')
      expect(button.attributes('disabled')).toBeDefined()

      const boxes = w.findAll('input[type="checkbox"]')
      expect(boxes).toHaveLength(2)
      await boxes[0]!.setValue(true)
      expect(button.attributes('disabled')).toBeDefined()
      await boxes[1]!.setValue(true)
      expect(button.attributes('disabled')).toBeUndefined()

      await button.trigger('click')
      expect(w.find('input[type="email"]').exists()).toBe(true)
      expect(post).not.toHaveBeenCalled()
    })

    it('opens the full text of each document in the document window', async () => {
      const w = mountView()
      const links = w.findAll('a')
      await links[0]!.trigger('click')
      expect(w.find('.doc-stub').attributes('data-type')).toBe('cabinet_terms')
      await links[1]!.trigger('click')
      expect(w.find('.doc-stub').attributes('data-type')).toBe('privacy_policy')
    })
  })

  describe('step 2: e-mail', () => {
    it('sends the e-mail with the consent and the referral code, then shows the code step', async () => {
      sessionStorage.setItem(REFERRAL_KEY, 'REF')
      post.mockResolvedValueOnce({ status: 'code_sent', code_ttl_minutes: 10 })
      const w = mountView()
      await toEmailStep(w)

      await sendEmail(w, 'a@b.co')

      expect(post).toHaveBeenCalledWith('/api/v1/auth/telegram/link/email', {
        link_token: 'LT1',
        email: 'a@b.co',
        consent_given: true,
        referral_code: 'REF',
      })
      expect(w.findAll('.ds-otp__cell')).toHaveLength(6)
    })

    it('answers every address the same way: the screen after the answer does not depend on the address', async () => {
      const screens: string[] = []
      for (const address of ['known@x.co', 'unknown@y.co']) {
        post.mockResolvedValueOnce({ status: 'code_sent', code_ttl_minutes: 10 })
        const w = mountView()
        await toEmailStep(w)
        await sendEmail(w, address)
        screens.push(w.text().replace(address, '<address>'))
        w.unmount()
      }
      expect(screens[0]).toBe(screens[1])
      expect(screens[0]).not.toMatch(/already|registered|exists|no account|not found/i)
    })

    it('shows the rate-limit answer on the e-mail step and holds the button for the wait', async () => {
      post.mockRejectedValueOnce(apiError(429, 'telegram_link_locked', 30))
      const w = mountView()
      await toEmailStep(w)

      await sendEmail(w)

      expect(w.find('.ds-alert--danger').text()).toBe(en.auth.error.rateLimited)
      expect(w.find('input[type="email"]').exists()).toBe(true)
      expect(w.find('button.ds-button--primary').attributes('disabled')).toBeDefined()
      w.unmount()
    })

    it('sends a corrected address at once after going back from the code step', async () => {
      post.mockResolvedValue({ status: 'code_sent', code_ttl_minutes: 10 })
      const w = mountView()
      await toEmailStep(w)
      await sendEmail(w, 'typo@b.co')
      expect(w.findAll('.ds-otp__cell')).toHaveLength(6)

      await w.findComponent({ name: 'CBackLink' }).trigger('click')
      await sendEmail(w, 'right@b.co')

      expect(post).toHaveBeenCalledTimes(2)
      expect(post).toHaveBeenLastCalledWith('/api/v1/auth/telegram/link/email', {
        link_token: 'LT1',
        email: 'right@b.co',
        consent_given: true,
        referral_code: null,
      })
      expect(w.find('.ds-auth__foot button.ds-button--ghost').exists()).toBe(false)
      w.unmount()
    })

    it('tells a spent daily allowance in its own words', async () => {
      post.mockRejectedValueOnce(apiError(429, 'telegram_link_emails_per_day'))
      const w = mountView()
      await toEmailStep(w)

      await sendEmail(w)

      expect(w.find('.ds-alert--danger').text()).toBe(en.auth.telegramEntry.emailsPerDay)
    })

    it('shows the expired state when the link token is gone', async () => {
      post.mockRejectedValueOnce(apiError(400, 'link_token_invalid'))
      const w = mountView()
      await toEmailStep(w)

      await sendEmail(w)

      expect(w.text()).toContain(en.auth.telegramEntry.expired)
      expect(w.find('input[type="email"]').exists()).toBe(false)
      expect(useAuthStore().telegramLinkToken).toBeNull()
    })
  })

  describe('step 3: code', () => {
    async function toCodeStep(): Promise<VueWrapper> {
      post.mockResolvedValueOnce({ status: 'code_sent', code_ttl_minutes: 10 })
      const w = mountView()
      await toEmailStep(w)
      await sendEmail(w)
      return w
    }

    it('shows no second-code field at first and signs in on the right code', async () => {
      const w = await toCodeStep()
      expect(w.text()).not.toContain(en.auth.telegramEntry.secondCodeLabel)

      post.mockResolvedValueOnce({ user: USER, session_token: 'S1' })
      await typeCode(w)
      await w.find('button.ds-button--primary').trigger('click')
      await flushPromises()

      expect(post).toHaveBeenLastCalledWith('/api/v1/auth/telegram/link/confirm', {
        link_token: 'LT1',
        code: '123456',
        second_code: null,
      })
      expect(useAuthStore().isAuthenticated).toBe(true)
      expect(push).toHaveBeenCalledTimes(1)
      w.unmount()
    })

    it('shows the authenticator field when the server answers second_code_required, and sends it', async () => {
      const w = await toCodeStep()
      post.mockRejectedValueOnce(apiError(400, 'second_code_required'))
      await typeCode(w)
      await w.find('button.ds-button--primary').trigger('click')
      await flushPromises()

      expect(w.text()).toContain(en.auth.telegramEntry.secondCodeLabel)
      // Asking for the second code is not an error.
      expect(w.find('.ds-alert--danger').exists()).toBe(false)
      expect(push).not.toHaveBeenCalled()

      post.mockResolvedValueOnce({ user: USER, session_token: 'S1' })
      const fields = w.findAll(
        'input.ds-field__input, input:not(.ds-otp__cell):not([type=checkbox])',
      )
      await fields[0]!.setValue('654321')
      await w.find('button.ds-button--primary').trigger('click')
      await flushPromises()

      expect(post).toHaveBeenLastCalledWith('/api/v1/auth/telegram/link/confirm', {
        link_token: 'LT1',
        code: '123456',
        second_code: '654321',
      })
      expect(push).toHaveBeenCalledTimes(1)
      w.unmount()
    })

    it('shows a wrong code as an error and clears the boxes', async () => {
      const w = await toCodeStep()
      post.mockRejectedValueOnce(apiError(400, 'invalid_code'))
      await typeCode(w)
      await w.find('button.ds-button--primary').trigger('click')
      await flushPromises()

      expect(w.find('.ds-alert--danger').text()).toBe(en.auth.telegramEntry.codeInvalid)
      expect(
        w.findAll('.ds-otp__cell').every((c) => (c.element as HTMLInputElement).value === ''),
      ).toBe(true)
      expect(push).not.toHaveBeenCalled()
      w.unmount()
    })

    it('shows a wrong second code as its own error', async () => {
      const w = await toCodeStep()
      post.mockRejectedValueOnce(apiError(400, 'second_code_required'))
      await typeCode(w)
      await w.find('button.ds-button--primary').trigger('click')
      await flushPromises()
      post.mockRejectedValueOnce(apiError(400, 'second_code_invalid'))
      const fields = w.findAll('input:not(.ds-otp__cell):not([type=checkbox])')
      await fields[0]!.setValue('000000')
      await w.find('button.ds-button--primary').trigger('click')
      await flushPromises()

      expect(w.find('.ds-alert--danger').text()).toBe(en.auth.telegramEntry.secondCodeInvalid)
      w.unmount()
    })

    it('shows the expired state when the link token ran out between the steps', async () => {
      const w = await toCodeStep()
      post.mockRejectedValueOnce(apiError(400, 'link_token_invalid'))
      await typeCode(w)
      await w.find('button.ds-button--primary').trigger('click')
      await flushPromises()

      expect(w.text()).toContain(en.auth.telegramEntry.expired)
      expect(w.findAll('.ds-otp__cell')).toHaveLength(0)
      w.unmount()
    })
  })

  describe('on the website (H45)', () => {
    beforeEach(() => {
      platformMock.name = 'standalone'
    })

    it('says to start again from the sign-in screen when the link is gone, with the way back', async () => {
      post.mockRejectedValueOnce(apiError(400, 'link_token_invalid'))
      const w = mountView()
      await toEmailStep(w)
      await sendEmail(w)

      expect(w.text()).toContain(en.auth.telegramEntry.expiredTitleWeb)
      expect(w.text()).toContain(en.auth.telegramEntry.expiredWeb)
      expect(w.text()).not.toContain(en.auth.telegramEntry.expired)
      await w.find('button.ds-button--primary').trigger('click')
      expect(replace).toHaveBeenCalledWith({ name: 'login' })
    })

    it('offers the way back at the consent step and drops the link token first', async () => {
      const w = mountView()
      expect(useAuthStore().telegramLinkToken).toBe('LT1')
      const back = w.findAll('button').find((b) => b.text() === en.auth.back)
      expect(back).toBeDefined()
      await back!.trigger('click')
      expect(useAuthStore().telegramLinkToken).toBeNull()
      expect(replace).toHaveBeenCalledWith({ name: 'login' })
    })

    it('shows no way back at the consent step in the Mini App', () => {
      platformMock.name = 'telegram'
      const w = mountView()
      expect(w.findAll('button').some((b) => b.text() === en.auth.back)).toBe(false)
    })
  })
})
