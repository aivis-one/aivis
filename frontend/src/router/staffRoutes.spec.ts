// =============================================================================
// the staff routes -- THE TABLE OF SECTIONS AND THE ROUTER SAY THE SAME THING
// =============================================================================
//
// utils/staffRights.ts is the one table of the staff sections and the right
// each one needs; the tab bar and the chips read it, and the route records take
// their lock from it (sectionMeta). These tests read the REAL router and pin
// the two together, so a section added to the table but not to the router (a
// chip that leads to a 404), or a route whose lock differs from its chip, fails
// here and not in a member's browser.
// =============================================================================

import { describe, expect, it } from 'vitest'

import { router } from './index'
import {
  FINANCE_SECTIONS,
  PLATFORM_SECTIONS,
  TAB_SECTIONS,
  USERS_SECTIONS,
} from '@/utils/staffRights'
import { STAFF_TABS } from './tabs'

function record(name: string) {
  const found = router.getRoutes().find((r) => r.name === name)
  if (!found) throw new Error(`no route named ${name}`)
  return found
}

describe('the staff tab bar', () => {
  it('is Home, Users, Finance, Platform, Settings', () => {
    expect(STAFF_TABS.map((t) => t.id)).toEqual([
      'home',
      'users',
      'finance',
      'platform',
      'settings',
    ])
  })

  it('has a hub table for each tab that opens a hub', () => {
    expect(Object.keys(TAB_SECTIONS).sort()).toEqual(['finance', 'platform', 'users'])
  })
})

describe('every section of every hub is a real route', () => {
  const all = [...USERS_SECTIONS, ...FINANCE_SECTIONS, ...PLATFORM_SECTIONS]

  it.each(all.map((s) => [s.id, s.path] as const))(
    '%s (%s) resolves to a staff screen',
    (_id, path) => {
      const resolved = router.resolve(path)
      expect(resolved.matched.length).toBeGreaterThan(0)
      expect(resolved.matched.some((m) => m.path === '/staff')).toBe(true)
      expect(resolved.name).toBeDefined()
    },
  )
})

describe('the lock of a route is the lock of its chip', () => {
  const cases: [string, (typeof PLATFORM_SECTIONS)[number]][] = [
    ['staff-platform-news', PLATFORM_SECTIONS[0]!],
    ['staff-platform-events', PLATFORM_SECTIONS[1]!],
    ['staff-platform-companies', PLATFORM_SECTIONS[2]!],
    ['staff-platform-settings', PLATFORM_SECTIONS[3]!],
    ['staff-payments', FINANCE_SECTIONS[0]!],
    ['staff-withdrawals', FINANCE_SECTIONS[1]!],
    ['staff-gifts', FINANCE_SECTIONS[2]!],
    ['staff-reconciliation', FINANCE_SECTIONS[3]!],
    ['staff-agent-apps', USERS_SECTIONS[1]!],
    ['staff-avatar', USERS_SECTIONS[2]!],
  ]

  it.each(cases)('%s carries the right its chip needs', (name, section) => {
    expect(record(name).meta.permission).toBe(section.permission)
    expect(record(name).meta.admin === true).toBe(section.admin === true)
  })

  it('opens the money check to the administrator only', () => {
    expect(record('staff-reconciliation').meta.admin).toBe(true)
  })

  it('leaves the user list and support open to every staff member', () => {
    expect(record('staff-users').meta.permission).toBeUndefined()
    expect(record('staff-support').meta.permission).toBeUndefined()
  })
})

describe('the addresses of the old layout', () => {
  it.each([
    ['/staff/payments', '/staff/finance/payments'],
    ['/staff/withdrawals', '/staff/finance/withdrawals'],
    ['/staff/agent-apps', '/staff/users/agent-apps'],
    ['/staff/avatar', '/staff/users/avatar'],
    ['/staff/support', '/staff/users/support'],
    ['/staff/more', '/staff/settings'],
    ['/staff/platform/companies', '/staff/platform/projects'],
  ])('%s leads to %s', async (from, to) => {
    const resolved = router.resolve(from)
    const target = resolved.matched.at(-1)?.redirect
    const redirected =
      typeof target === 'function' ? target(resolved, router.currentRoute.value) : target
    expect(redirected).toBe(to)
  })

  it('keeps the rest of a project address when it moves', () => {
    const resolved = router.resolve('/staff/platform/companies/abc/price')
    const target = resolved.matched.at(-1)?.redirect
    const redirected =
      typeof target === 'function' ? target(resolved, router.currentRoute.value) : target
    expect(redirected).toBe('/staff/platform/projects/abc/price')
  })
})
