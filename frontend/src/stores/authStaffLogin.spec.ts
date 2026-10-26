// =============================================================================
// stores/auth -- a staff sign-in reads the profile before the shell renders
// =============================================================================
//
// A login response carries no staff_profile; only GET /users/me builds it. The
// store reads it once more after a staff sign-in, so the rights are present
// when the menu is drawn. A login response of an investor is left as it is.
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

import { api } from '@/api/client'
import { useAuthStore } from './auth'
import { useStaffRights } from '@/composables/useStaffRights'
import { useStaffPermissions } from '@/composables/useStaffPermissions'
import { PERMISSION_KEYS, tabAllowed } from '@/utils/staffRights'
import { STAFF_TABS } from '@/router/tabs'

const get = vi.mocked(api.get)
const post = vi.mocked(api.post)

const ADMIN_PERMISSIONS = Object.fromEntries(PERMISSION_KEYS.map((key) => [key, true]))
const BARE = { id: 'u1', email: 'a@b.co', role: 'staff', language: 'en' }

describe('auth store -- a staff sign-in', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    get.mockReset()
    post.mockReset()
    sessionStorage.clear()
    localStorage.clear()
  })

  it('reads /users/me after an e-mail login, so an administrator has rights and five tabs', async () => {
    post.mockResolvedValueOnce({ user: BARE, session_token: 'S1' })
    get.mockResolvedValueOnce({ ...BARE, staff_profile: { permissions: ADMIN_PERMISSIONS } })
    const store = useAuthStore()

    await store.loginViaEmail('a@b.co', 'pw')

    expect(get).toHaveBeenCalledWith('/api/v1/users/me')
    expect(useStaffPermissions().canDo('payment_review').value).toBe(true)
    expect(useStaffPermissions().isAdmin.value).toBe(true)
    const rights = useStaffRights().current()
    expect(STAFF_TABS.filter((tab) => tabAllowed(tab.id, rights))).toHaveLength(5)
  })

  it('reads /users/me after a Telegram login too', async () => {
    post.mockResolvedValueOnce({ user: BARE, session_token: 'S1' })
    get.mockResolvedValueOnce({ ...BARE, staff_profile: { permissions: ADMIN_PERMISSIONS } })
    const store = useAuthStore()

    await store.loginViaTelegram('init')

    expect(useStaffPermissions().isAdmin.value).toBe(true)
  })

  it('keeps the sign-in when the profile read fails', async () => {
    post.mockResolvedValueOnce({ user: BARE, session_token: 'S1' })
    get.mockRejectedValueOnce(new Error('network'))
    const store = useAuthStore()

    await store.loginViaEmail('a@b.co', 'pw')

    expect(store.isAuthenticated).toBe(true)
    expect(useStaffPermissions().canDo('payment_review').value).toBe(false)
  })

  it('does not read the profile again for an investor', async () => {
    post.mockResolvedValueOnce({ user: { ...BARE, role: 'investor' }, session_token: 'S1' })
    const store = useAuthStore()

    await store.loginViaEmail('a@b.co', 'pw')

    expect(get).not.toHaveBeenCalled()
    expect(store.isAuthenticated).toBe(true)
  })
})
