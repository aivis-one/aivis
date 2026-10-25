// =============================================================================
// CAppControls -- one language per person
// =============================================================================
//
// The header's language list switches the interface and, for a signed-in person,
// saves the account's language through the same call the profile edit makes. A
// failed save never undoes the switch.
// =============================================================================

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'

const setLocale = vi.fn(async (_code: string) => undefined)
const updateMe = vi.fn()

vi.mock('@/i18n', () => ({ setLocale: (code: string) => setLocale(code) }))
vi.mock('@/api/users', () => ({ updateMe: (body: unknown) => updateMe(body) }))

import CAppControls from './CAppControls.vue'
import { useAuthStore } from '@/stores/auth'

function mountControls(signedInWith: string | null) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const auth = useAuthStore()
  if (signedInWith) {
    auth.token = 't'
    auth.user = { id: 'u1', language: signedInWith } as never
  }
  const w = mount(CAppControls, {
    global: {
      plugins: [
        pinia,
        createI18n({ legacy: false, locale: 'en', messages: { en: {} }, missingWarn: false }),
      ],
    },
  })
  return { w, auth }
}

async function pick(w: ReturnType<typeof mountControls>['w'], code: string) {
  await w.get('button[aria-haspopup="listbox"]').trigger('click')
  const options = w.findAll('[role="option"]')
  const index = ['en', 'ru'].indexOf(code)
  await options[index]!.trigger('click')
  await flushPromises()
}

describe('CAppControls language', () => {
  beforeEach(() => {
    setLocale.mockClear()
    updateMe.mockReset()
    updateMe.mockResolvedValue({})
  })

  it('saves the account language when signed in', async () => {
    const { w, auth } = mountControls('en')
    await pick(w, 'ru')
    expect(setLocale).toHaveBeenCalledWith('ru')
    expect(updateMe).toHaveBeenCalledWith({ language: 'ru' })
    expect(auth.user?.language).toBe('ru')
  })

  it('does not save for a visitor who is not signed in', async () => {
    const { w } = mountControls(null)
    await pick(w, 'ru')
    expect(setLocale).toHaveBeenCalledWith('ru')
    expect(updateMe).not.toHaveBeenCalled()
  })

  it('does not call the server when the language is already the account language', async () => {
    const { w } = mountControls('ru')
    await pick(w, 'ru')
    expect(updateMe).not.toHaveBeenCalled()
  })

  it('keeps the switch when the save fails', async () => {
    updateMe.mockRejectedValue(new Error('down'))
    const { w, auth } = mountControls('en')
    await pick(w, 'ru')
    expect(setLocale).toHaveBeenCalledWith('ru')
    expect(auth.user?.language).toBe('en')
  })
})
