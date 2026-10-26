// =============================================================================
// SetPasswordView -- the first password (H44): a password and its
// confirmation, both with the reveal control, the shared length rule, no skip,
// a way out
// =============================================================================

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import { defineComponent, h } from 'vue'

const replace = vi.hoisted(() => vi.fn(async () => {}))
vi.mock('vue-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('vue-router')>()
  return { ...actual, useRouter: () => ({ replace, push: replace }) }
})
vi.mock('@/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/client')>()
  return {
    ...actual,
    api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  }
})
vi.mock('@/api/users', () => ({ setPassword: vi.fn() }))
vi.mock('@/i18n', () => ({
  i18n: { global: { locale: { value: 'en' }, t: (k: string) => k } },
  setLocale: vi.fn(),
}))

import { api, ApiResponseError } from '@/api/client'
import { setPassword } from '@/api/users'
import { useAuthStore } from '@/stores/auth'
import en from '@/i18n/locales/en.json'
import SetPasswordView from './SetPasswordView.vue'

const send = vi.mocked(setPassword)
const get = vi.mocked(api.get)
const USER = {
  id: 'u1',
  role: 'investor',
  language: 'en',
  email: 'a@example.com',
  onboarding_step: 'email_verified',
  password_required: true,
}

const AuthShellStub = defineComponent({
  setup(_, { slots }) {
    return () => h('div', slots.default?.())
  },
})

function mountView(): VueWrapper {
  const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
  return mount(SetPasswordView, {
    global: { plugins: [i18n], stubs: { AuthShell: AuthShellStub } },
  })
}

async function fill(w: VueWrapper, password: string, confirm: string): Promise<void> {
  const inputs = w.findAll('input')
  await inputs[0].setValue(password)
  await inputs[1].setValue(confirm)
  await w.find('button.ds-button--primary').trigger('click')
  await flushPromises()
}

describe('SetPasswordView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    send.mockReset()
    get.mockReset()
    replace.mockClear()
    const store = useAuthStore()
    store.token = 'S1'
    store.user = USER as never
  })

  it('shows two password fields, each with its reveal control, and no skip', async () => {
    const w = mountView()
    const inputs = w.findAll('input')
    expect(inputs).toHaveLength(2)
    expect(inputs.every((i) => i.attributes('type') === 'password')).toBe(true)
    expect(inputs.every((i) => i.attributes('autocomplete') === 'new-password')).toBe(true)

    const reveals = w.findAll('button.ds-input-reveal')
    expect(reveals).toHaveLength(2)
    await reveals[0].trigger('click')
    expect(w.findAll('input')[0].attributes('type')).toBe('text')
    expect(w.findAll('input')[1].attributes('type')).toBe('password')
    await reveals[1].trigger('click')
    expect(w.findAll('input')[1].attributes('type')).toBe('text')

    expect(w.text()).toContain('a@example.com')
    expect(w.text()).toContain(en.auth.logout)
    expect(w.text().toLowerCase()).not.toContain('skip')
  })

  it('sends the password, takes the answer as the user and leaves the screen', async () => {
    send.mockResolvedValueOnce({ ...USER, password_required: false } as never)
    const w = mountView()

    await fill(w, 'Chosen-pass-1', 'Chosen-pass-1')

    expect(send).toHaveBeenCalledWith('Chosen-pass-1')
    expect(useAuthStore().user?.password_required).toBe(false)
    expect(replace).toHaveBeenCalledWith('/')
  })

  it.each([
    ['empty', '', '', en.auth.error.fillAllFields],
    ['not the same', 'Chosen-pass-1', 'Chosen-pass-2', en.auth.error.passwordMismatch],
    ['seven characters', 'x'.repeat(7), 'x'.repeat(7), 'Minimum 8 characters'],
    ['129 characters', 'x'.repeat(129), 'x'.repeat(129), 'Maximum 128 characters'],
  ])('refuses %s before sending', async (_name, password, confirm, message) => {
    const w = mountView()
    await fill(w, password, confirm)
    expect(send).not.toHaveBeenCalled()
    expect(w.find('[role="alert"]').text()).toContain(message)
  })

  it.each([8, 128])('takes %i characters', async (n) => {
    send.mockResolvedValueOnce({ ...USER, password_required: false } as never)
    const w = mountView()
    await fill(w, 'p'.repeat(n), 'p'.repeat(n))
    expect(send).toHaveBeenCalledWith('p'.repeat(n))
  })

  it('on a 409 re-reads the user and lets the guard decide', async () => {
    send.mockRejectedValueOnce(new ApiResponseError(409, 'This account already has a password'))
    get.mockResolvedValueOnce({ ...USER, password_required: false })
    const w = mountView()

    await fill(w, 'Chosen-pass-1', 'Chosen-pass-1')

    expect(get).toHaveBeenCalledWith('/api/v1/users/me')
    expect(useAuthStore().user?.password_required).toBe(false)
    expect(replace).toHaveBeenCalledTimes(1)
  })

  it('shows the server words of another refusal and stays', async () => {
    send.mockRejectedValueOnce(
      new ApiResponseError(422, 'String should have at least 8 characters'),
    )
    const w = mountView()

    await fill(w, 'Chosen-pass-1', 'Chosen-pass-1')

    expect(w.find('[role="alert"]').text()).toContain('String should have at least 8 characters')
    expect(replace).not.toHaveBeenCalled()
  })
})
