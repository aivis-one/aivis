// =============================================================================
// useStaffPermissions -- isAdmin (H28 P-105)
// =============================================================================
//
// isAdmin decides whether the staff screen offers admin-only actions (the
// support email change). It mirrors the backend's is_admin(): every effective
// permission True. The backend re-checks every call; these tests pin what the
// screen shows.
//
// Axes: EMPTINESS -- no user, no staff profile, an empty permission dict
// (every() over nothing is true, so this is the case the non-empty check
// exists for); SHORTAGE -- one permission false or missing a value; and the
// pair: a full dict of true reads as admin.
// =============================================================================

import { describe, it, expect, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { useAuthStore } from '@/stores/auth'
import { useStaffPermissions } from './useStaffPermissions'

const ALL_TRUE = {
  user_block: true,
  kyc_approve: true,
  content_manage: true,
  project_manage: true,
}

function withPermissions(permissions: Record<string, boolean> | null | undefined): boolean {
  const authStore = useAuthStore()
  authStore.user = (permissions === undefined
    ? { id: 'u1', role: 'investor', staff_profile: null }
    : {
        id: 'u1',
        role: 'staff',
        staff_profile: { permissions },
      }) as unknown as typeof authStore.user
  return useStaffPermissions().isAdmin.value
}

describe('useStaffPermissions().isAdmin', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('is false with nobody logged in', () => {
    useAuthStore().user = null
    expect(useStaffPermissions().isAdmin.value).toBe(false)
  })

  it('is false for a user with no staff profile', () => {
    expect(withPermissions(undefined)).toBe(false)
  })

  it('is false for a staff profile with no permission dict', () => {
    expect(withPermissions(null)).toBe(false)
  })

  it('is false for an empty permission dict', () => {
    expect(withPermissions({})).toBe(false)
  })

  it('is false when a single permission is false', () => {
    expect(withPermissions({ ...ALL_TRUE, kyc_approve: false })).toBe(false)
  })

  it('is true when every permission is true', () => {
    expect(withPermissions(ALL_TRUE)).toBe(true)
  })

  it('follows a permission change in the same session', () => {
    const authStore = useAuthStore()
    authStore.user = {
      id: 'u1',
      role: 'staff',
      staff_profile: { permissions: { ...ALL_TRUE } },
    } as unknown as typeof authStore.user
    const { isAdmin } = useStaffPermissions()
    expect(isAdmin.value).toBe(true)
    authStore.user = {
      id: 'u1',
      role: 'staff',
      staff_profile: { permissions: { ...ALL_TRUE, user_block: false } },
    } as unknown as typeof authStore.user
    expect(isAdmin.value).toBe(false)
  })
})
