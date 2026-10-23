// =============================================================================
// router/staffHubs -- WHERE A HUB OPENS, AND WHAT LOCK EACH SECTION'S ROUTE CARRIES
// =============================================================================
//
// "Platform" used to redirect to News whatever the member could use. It now
// opens on the first section the member has the right to, and the meta of every
// section record comes from the same table the chips read.
//
// Axes: a member with a right to ONLY a later section, with NONE, and the
// administrator; and a section id that is not in its hub (a typo must throw,
// not hand out an unlocked route).
// =============================================================================

import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { useAuthStore } from '@/stores/auth'
import { FINANCE_SECTIONS, PERMISSION_KEYS, PLATFORM_SECTIONS } from '@/utils/staffRights'
import { hubStart, sectionMeta } from './staffHubs'

function signInAsStaff(held: readonly string[]): void {
  const auth = useAuthStore()
  auth.user = {
    id: 'staff-1',
    role: 'staff',
    staff_profile: {
      permissions: Object.fromEntries(PERMISSION_KEYS.map((key) => [key, held.includes(key)])),
    },
  } as unknown as typeof auth.user
}

describe('where a hub opens', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('opens Platform on the first section the member may use', () => {
    signInAsStaff(['company_manage'])
    expect(hubStart(PLATFORM_SECTIONS)).toBe('/staff/platform/projects')
    signInAsStaff(['kyc_approve'])
    expect(hubStart(PLATFORM_SECTIONS)).toBe('/staff/platform/settings')
    signInAsStaff(['content_manage', 'company_manage'])
    expect(hubStart(PLATFORM_SECTIONS)).toBe('/staff/platform/news')
  })

  it('sends a member with no right to any section back to the Home', () => {
    signInAsStaff([])
    expect(hubStart(PLATFORM_SECTIONS)).toBe('/staff/dashboard')
    expect(hubStart(FINANCE_SECTIONS)).toBe('/staff/dashboard')
  })

  it('opens Finance on payments for a member who may check payments', () => {
    signInAsStaff(['payment_review'])
    expect(hubStart(FINANCE_SECTIONS)).toBe('/staff/finance/payments')
  })

  it('opens Finance on purchases for a member who has only the financial operations', () => {
    signInAsStaff(['financial_operations'])
    expect(hubStart(FINANCE_SECTIONS)).toBe('/staff/finance/purchases')
  })

  it('opens Finance on payments for the administrator, and the money check is open to them', () => {
    signInAsStaff([...PERMISSION_KEYS])
    expect(hubStart(FINANCE_SECTIONS)).toBe('/staff/finance/payments')
  })
})

describe('the meta a section record carries', () => {
  it('carries the permission of the section, taken from the table', () => {
    expect(sectionMeta(PLATFORM_SECTIONS, 'settings')).toEqual({ permission: 'kyc_approve' })
    expect(sectionMeta(PLATFORM_SECTIONS, 'news')).toEqual({ permission: 'content_manage' })
  })

  it("marks the money check as the administrator's, with its permission", () => {
    expect(sectionMeta(FINANCE_SECTIONS, 'reconciliation')).toEqual({
      permission: 'financial_operations',
      admin: true,
    })
  })

  it('throws for a section that is not in the hub, so a typo cannot leave a route unlocked', () => {
    expect(() => sectionMeta(PLATFORM_SECTIONS, 'newz')).toThrow()
  })
})
