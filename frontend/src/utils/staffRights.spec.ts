// =============================================================================
// utils/staffRights -- WHAT THE STAFF MEMBER IS OFFERED FOLLOWS WHAT THEY MAY DO
// =============================================================================
//
// The table of sections with their rights, the hiding of tabs and chips, the
// hub that opens on the first section the member may use, and the permission
// presets are pure functions over a rights context, so they are pinned here
// without a router or a store.
//
// Axes: a member with NO rights, a member with ONE right, the ADMINISTRATOR;
// and for the presets, a member who holds MORE than the set (the press must
// take the extra away), who holds EXACTLY the set, and who holds NOTHING.
// =============================================================================

import { describe, expect, it } from 'vitest'

import {
  FINANCE_SECTIONS,
  PERMISSION_KEYS,
  PERMISSION_PRESETS,
  PLATFORM_SECTIONS,
  USERS_SECTIONS,
  adminChangeOfTick,
  adminPatch,
  allowedSections,
  firstAllowedSection,
  holdsEveryPermission,
  matchingPreset,
  presetPatch,
  sectionAllowed,
  tabAllowed,
} from './staffRights'
import type { RightsContext } from './staffRights'
import type { StaffPermissionKey } from '@/composables/useStaffPermissions'

function rights(held: readonly StaffPermissionKey[], admin = false): RightsContext {
  return { can: (key) => held.includes(key), admin }
}

const NOBODY = rights([])
const EVERYTHING = rights(PERMISSION_KEYS, true)

describe('the sections a member may use', () => {
  it('draws only the Users sections the member has the right to', () => {
    // No right at all: the list and support are open to every staff member.
    expect(allowedSections(USERS_SECTIONS, NOBODY).map((s) => s.id)).toEqual(['users', 'support'])
    expect(allowedSections(USERS_SECTIONS, rights(['avatar_mode'])).map((s) => s.id)).toEqual([
      'users',
      'avatar',
      'support',
    ])
    expect(allowedSections(USERS_SECTIONS, EVERYTHING).map((s) => s.id)).toEqual([
      'users',
      'agent-apps',
      'avatar',
      'support',
    ])
  })

  it('hides the gift grant and the money check from everyone who is not the administrator', () => {
    const financeMember = rights(['payment_review', 'financial_operations'])
    const ids = allowedSections(FINANCE_SECTIONS, financeMember).map((s) => s.id)
    expect(ids).toEqual(['payments', 'withdrawals', 'purchases'])
    expect(ids).not.toContain('gifts')
    expect(ids).not.toContain('reconciliation')
    const everything = allowedSections(FINANCE_SECTIONS, EVERYTHING).map((s) => s.id)
    expect(everything).toContain('gifts')
    expect(everything).toContain('reconciliation')
  })

  it('does not let the administrator mark alone open a section that needs a permission', () => {
    // The administrator is "every permission on"; a context with the mark but
    // not the permission is not a real administrator and gets nothing extra.
    const odd: RightsContext = { can: () => false, admin: true }
    expect(sectionAllowed(PLATFORM_SECTIONS[0]!, odd)).toBe(false)
  })
})

describe('a tab that opens a hub', () => {
  it('is drawn only when the member may use at least one of its sections', () => {
    expect(tabAllowed('finance', NOBODY)).toBe(false)
    expect(tabAllowed('platform', NOBODY)).toBe(false)
    expect(tabAllowed('finance', rights(['financial_operations']))).toBe(true)
    expect(tabAllowed('platform', rights(['kyc_approve']))).toBe(true)
  })

  it('draws the Users tab for everyone, because its list is open to every staff member', () => {
    expect(tabAllowed('users', NOBODY)).toBe(true)
  })

  it('draws Home and Settings for everyone', () => {
    expect(tabAllowed('home', NOBODY)).toBe(true)
    expect(tabAllowed('settings', NOBODY)).toBe(true)
  })
})

describe('"Platform" opens on the first section the member may use', () => {
  it('opens on News for a member with the content right', () => {
    expect(firstAllowedSection(PLATFORM_SECTIONS, rights(['content_manage']))?.id).toBe('news')
  })

  it('skips News and Events for a member who only manages projects', () => {
    expect(firstAllowedSection(PLATFORM_SECTIONS, rights(['company_manage']))?.id).toBe('projects')
  })

  it('opens on the settings for a member who only decides identity checks', () => {
    expect(firstAllowedSection(PLATFORM_SECTIONS, rights(['kyc_approve']))?.id).toBe('settings')
  })

  it('opens on nothing for a member with no right to any section', () => {
    expect(firstAllowedSection(PLATFORM_SECTIONS, NOBODY)).toBeNull()
  })
})

describe('the permission presets', () => {
  const byId = (id: string) => PERMISSION_PRESETS.find((p) => p.id === id)!

  it('are the four sets, with the rights the card promises', () => {
    expect(PERMISSION_PRESETS.map((p) => p.id)).toEqual([
      'support',
      'verification',
      'finance',
      'content',
    ])
    expect(byId('support').keys).toEqual(['avatar_mode', 'user_block'])
    expect(byId('verification').keys).toEqual(['kyc_approve', 'agent_application_review'])
    expect(byId('finance').keys).toEqual(['payment_review', 'financial_operations'])
    expect(byId('content').keys).toEqual(['content_manage', 'company_manage', 'project_manage'])
  })

  it('marks exactly the set: its rights on, every other off', () => {
    const patch = presetPatch(byId('support'))
    expect(Object.keys(patch).sort()).toEqual([...PERMISSION_KEYS].sort())
    const on = PERMISSION_KEYS.filter((key) => patch[key])
    expect(on).toEqual(['avatar_mode', 'user_block'])
  })

  it('takes away what a broader default had given (the press replaces, it does not add)', () => {
    const broad = Object.fromEntries(PERMISSION_KEYS.map((key) => [key, true]))
    const applied = { ...broad, ...presetPatch(byId('finance')) }
    expect(applied.payment_review).toBe(true)
    expect(applied.financial_operations).toBe(true)
    expect(applied.avatar_mode).toBe(false)
    expect(applied.project_manage).toBe(false)
    expect(holdsEveryPermission(applied)).toBe(false)
  })

  it('knows which preset a member holds exactly, and none when it is a mix', () => {
    const held = presetPatch(byId('verification'))
    expect(matchingPreset(held)?.id).toBe('verification')
    expect(matchingPreset({ ...held, user_block: true })).toBeNull()
    expect(matchingPreset(null)).toBeNull()
    expect(matchingPreset({})).toBeNull()
  })

  it('is not the administrator: only every right at once is', () => {
    for (const preset of PERMISSION_PRESETS) {
      expect(holdsEveryPermission(presetPatch(preset))).toBe(false)
    }
    expect(holdsEveryPermission(Object.fromEntries(PERMISSION_KEYS.map((k) => [k, true])))).toBe(
      true,
    )
    expect(holdsEveryPermission({})).toBe(false)
    expect(holdsEveryPermission(undefined)).toBe(false)
  })
})

describe('the administrator mark of a tick', () => {
  const all = Object.fromEntries(PERMISSION_KEYS.map((key) => [key, true]))
  const allButOne = { ...all, project_manage: false, translation_edit: false }

  it('adminPatch turns all ten keys on', () => {
    const patch = adminPatch()
    expect(Object.keys(patch).sort()).toEqual([...PERMISSION_KEYS].sort())
    expect(Object.values(patch).every(Boolean)).toBe(true)
  })

  it('a tick that marks the last shown right grants the mark', () => {
    expect(adminChangeOfTick(allButOne, 'project_manage', true)).toBe('grant')
  })

  it('a tick that clears a right of an administrator removes the mark', () => {
    expect(adminChangeOfTick(all, 'payment_review', false)).toBe('remove')
  })

  it('any other tick changes nothing about the mark', () => {
    expect(adminChangeOfTick({ avatar_mode: true }, 'user_block', true)).toBeNull()
    expect(adminChangeOfTick(allButOne, 'avatar_mode', false)).toBeNull()
    expect(adminChangeOfTick(null, 'avatar_mode', true)).toBeNull()
  })
})
