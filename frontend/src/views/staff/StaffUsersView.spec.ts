// =============================================================================
// StaffUsersView -- THE CARD OFFERS ONLY WHAT THE MEMBER MAY DO
// =============================================================================
//
// What a user's card shows follows the viewer's rights: the Block button needs
// user_block; appointing staff, the rights card with its preset buttons and
// taking a member off duty are the administrator's; the search box is open to
// every member and sends what was typed.
//
// Axes: a viewer with NO rights, with user_block ONLY, and the ADMINISTRATOR;
// the card of an ordinary user and the card of a staff member. The preset
// button is asserted through what it SENDS (the full set of ticks, the set's
// own on and every other off), not through a ref.
// =============================================================================

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

import { useAuthStore } from '@/stores/auth'
import { PERMISSION_KEYS } from '@/utils/staffRights'

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: {} }),
  useRouter: () => ({ push: vi.fn() }),
}))
vi.mock('@/api/kyc', () => ({
  KYC_DOCUMENT_URL_TTL_SECONDS: 300,
  fetchKycDocuments: vi.fn(async () => []),
  requestKycDocumentUrl: vi.fn(),
}))
vi.mock('@/api/admin', () => ({
  fetchUsers: vi.fn(),
  fetchUserDetail: vi.fn(),
  blockUser: vi.fn(),
  unblockUser: vi.fn(),
  changeUserEmail: vi.fn(),
  createStaff: vi.fn(),
  deactivateStaff: vi.fn(),
  updatePermissions: vi.fn(),
  approveKYC: vi.fn(),
  approveKYCUser: vi.fn(),
  rejectKYC: vi.fn(),
  revokeKYCUser: vi.fn(),
}))

import * as admin from '@/api/admin'
import StaffUsersView from './StaffUsersView.vue'

const fetchUsers = vi.mocked(admin.fetchUsers)
const fetchUserDetail = vi.mocked(admin.fetchUserDetail)
const updatePermissions = vi.mocked(admin.updatePermissions)

function permissions(held: readonly string[]): Record<string, boolean> {
  return Object.fromEntries(PERMISSION_KEYS.map((key) => [key, held.includes(key)]))
}

function signInAs(id: string, held: readonly string[]): void {
  const auth = useAuthStore()
  auth.user = {
    id,
    role: 'staff',
    staff_profile: { id: 'self-profile', permissions: permissions(held), is_active: true },
  } as unknown as typeof auth.user
}

function userItem(id: string, role: string) {
  return {
    id,
    role,
    is_active: true,
    kyc_status: 'approved',
    email: `${id}@example.com`,
    created_at: '2026-01-01T00:00:00Z',
  }
}

function detail(id: string, role: string, staffProfile: unknown = null) {
  return {
    ...userItem(id, role),
    onboarding_step: 'done',
    profile: {},
    language: 'en',
    staff_profile: staffProfile,
    latest_application_id: null,
    latest_application_status: null,
    kyc_applications_history: [],
  }
}

async function openCard(wrapper: VueWrapper): Promise<void> {
  await wrapper.find('.user-item').trigger('click')
  await flushPromises()
}

function bodyText(): string {
  return document.body.textContent ?? ''
}

async function mountWithUser(role: string, staffProfile: unknown = null): Promise<VueWrapper> {
  fetchUsers.mockResolvedValue({
    items: [userItem('target', role)],
    total: 1,
    page: 1,
    per_page: 20,
  } as never)
  fetchUserDetail.mockResolvedValue(detail('target', role, staffProfile) as never)
  const wrapper = mount(StaffUsersView, { attachTo: document.body })
  await flushPromises()
  await openCard(wrapper)
  return wrapper
}

describe("the user card follows the viewer's rights", () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    document.body.innerHTML = ''
    vi.clearAllMocks()
  })

  it('offers no Block button to a viewer without user_block', async () => {
    signInAs('viewer', [])
    const wrapper = await mountWithUser('investor')
    expect(bodyText()).not.toContain('staff.userDetail.block')
    expect(bodyText()).not.toContain('staff.userDetail.promoteToStaff')
    wrapper.unmount()
  })

  it('offers Block to a viewer with user_block, and still no appointing', async () => {
    signInAs('viewer', ['user_block'])
    const wrapper = await mountWithUser('investor')
    expect(bodyText()).toContain('staff.userDetail.block')
    expect(bodyText()).not.toContain('staff.userDetail.promoteToStaff')
    wrapper.unmount()
  })

  it('offers appointing to the administrator', async () => {
    signInAs('viewer', [...PERMISSION_KEYS])
    const wrapper = await mountWithUser('investor')
    expect(bodyText()).toContain('staff.userDetail.promoteToStaff')
    wrapper.unmount()
  })

  it('does not draw the rights card of a staff member to a viewer who is not the administrator', async () => {
    signInAs('viewer', ['user_block', 'kyc_approve'])
    const wrapper = await mountWithUser('staff', {
      id: 'p1',
      permissions: permissions(['avatar_mode']),
      is_active: true,
    })
    expect(bodyText()).not.toContain('staff.rights.presets.support')
    expect(bodyText()).not.toContain('staff.userDetail.deactivate')
    wrapper.unmount()
  })

  it('draws the four preset buttons to the administrator', async () => {
    signInAs('viewer', [...PERMISSION_KEYS])
    const wrapper = await mountWithUser('staff', {
      id: 'p1',
      permissions: permissions(['avatar_mode']),
      is_active: true,
    })
    for (const id of ['support', 'verification', 'finance', 'content']) {
      expect(bodyText()).toContain(`staff.rights.presets.${id}`)
    }
    expect(bodyText()).toContain('staff.userDetail.deactivate')
    wrapper.unmount()
  })

  it("does not offer to take the administrator's own card off duty", async () => {
    signInAs('target', [...PERMISSION_KEYS])
    const wrapper = await mountWithUser('staff', {
      id: 'p1',
      permissions: permissions([...PERMISSION_KEYS]),
      is_active: true,
    })
    expect(bodyText()).not.toContain('staff.userDetail.deactivate')
    wrapper.unmount()
  })

  it('sends the whole set when a preset is pressed: its rights on, every other off', async () => {
    signInAs('viewer', [...PERMISSION_KEYS])
    updatePermissions.mockResolvedValue({
      id: 'p1',
      permissions: permissions(['payment_review', 'financial_operations']),
      is_active: true,
    } as never)
    const wrapper = await mountWithUser('staff', {
      id: 'p1',
      permissions: permissions([...PERMISSION_KEYS]),
      is_active: true,
    })
    const finance = Array.from(document.body.querySelectorAll('.perm-presets button')).find((b) =>
      (b.textContent ?? '').includes('staff.rights.presets.finance'),
    ) as HTMLButtonElement
    finance.click()
    await flushPromises()
    // The card holds every right, so the press asks the remove warning first.
    expect(updatePermissions).not.toHaveBeenCalled()
    ;(
      Array.from(document.body.querySelectorAll('.ds-dialog__panel button')).find((b) =>
        (b.textContent ?? '').includes('common.confirm'),
      ) as HTMLButtonElement
    ).click()
    await flushPromises()
    expect(updatePermissions).toHaveBeenCalledTimes(1)
    const [profileId, body] = updatePermissions.mock.calls[0] as [string, Record<string, boolean>]
    expect(profileId).toBe('p1')
    const on = Object.keys(body).filter((k) => body[k])
    expect(on.sort()).toEqual(['financial_operations', 'payment_review'])
    expect(Object.keys(body).sort()).toEqual([...PERMISSION_KEYS].sort())
    wrapper.unmount()
  })
})

describe('the search box', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    document.body.innerHTML = ''
    vi.clearAllMocks()
    vi.useFakeTimers()
    signInAs('viewer', [])
    fetchUsers.mockResolvedValue({ items: [], total: 0, page: 1, per_page: 20 } as never)
  })

  it('reads the list again with what was typed, after the pause', async () => {
    const wrapper = mount(StaffUsersView, { attachTo: document.body })
    await flushPromises()
    expect(fetchUsers).toHaveBeenCalledTimes(1)
    await wrapper.find('input[type="search"]').setValue('ada@')
    await vi.advanceTimersByTimeAsync(400)
    await flushPromises()
    expect(fetchUsers).toHaveBeenCalledTimes(2)
    expect(fetchUsers.mock.calls[1]?.[0]).toMatchObject({ search: 'ada@' })
    wrapper.unmount()
    vi.useRealTimers()
  })

  it('does not search on a single letter', async () => {
    const wrapper = mount(StaffUsersView, { attachTo: document.body })
    await flushPromises()
    await wrapper.find('input[type="search"]').setValue('a')
    await vi.advanceTimersByTimeAsync(400)
    await flushPromises()
    expect(fetchUsers).toHaveBeenCalledTimes(1)
    wrapper.unmount()
    vi.useRealTimers()
  })
})

describe('the administrator mark on the rights card', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    document.body.innerHTML = ''
    vi.clearAllMocks()
    signInAs('viewer', [...PERMISSION_KEYS])
  })

  function press(label: string): void {
    const all = Array.from(document.body.querySelectorAll('button'))
    const found = all.find((b) => (b.textContent ?? '').includes(label)) as HTMLButtonElement
    found.click()
  }

  function tick(key: string, checked: boolean): void {
    const label = Array.from(document.body.querySelectorAll('label.ds-checkbox')).find(
      (l) => (l.textContent ?? '').trim() === key,
    )
    const input = label!.querySelector('input') as HTMLInputElement
    input.checked = checked
    input.dispatchEvent(new Event('change'))
  }

  const ninth = PERMISSION_KEYS.filter((k) => k !== 'project_manage')

  it('Make administrator warns first, then sends all ten keys on', async () => {
    updatePermissions.mockResolvedValue({
      id: 'p1',
      permissions: permissions([...PERMISSION_KEYS]),
      is_active: true,
    } as never)
    const wrapper = await mountWithUser('staff', {
      id: 'p1',
      permissions: permissions(['avatar_mode']),
      is_active: true,
    })
    press('staff.userDetail.makeAdmin')
    await flushPromises()
    expect(bodyText()).toContain('staff.userDetail.makeAdminWarning')
    expect(updatePermissions).not.toHaveBeenCalled()
    press('common.confirm')
    await flushPromises()
    const [, body] = updatePermissions.mock.calls[0] as [string, Record<string, boolean>]
    expect(Object.keys(body).sort()).toEqual([...PERMISSION_KEYS].sort())
    expect(Object.values(body).every(Boolean)).toBe(true)
    wrapper.unmount()
  })

  it('does not offer Make administrator to a member who already is one', async () => {
    const wrapper = await mountWithUser('staff', {
      id: 'p1',
      permissions: permissions([...PERMISSION_KEYS]),
      is_active: true,
    })
    expect(bodyText()).not.toContain('staff.userDetail.makeAdmin')
    wrapper.unmount()
  })

  it('the tick that marks the last right warns before it grants the mark', async () => {
    updatePermissions.mockResolvedValue({
      id: 'p1',
      permissions: permissions([...PERMISSION_KEYS]),
      is_active: true,
    } as never)
    const wrapper = await mountWithUser('staff', {
      id: 'p1',
      permissions: permissions(ninth),
      is_active: true,
    })
    tick('project_manage', true)
    await flushPromises()
    expect(bodyText()).toContain('staff.userDetail.grantAdminWarning')
    expect(updatePermissions).not.toHaveBeenCalled()
    press('common.confirm')
    await flushPromises()
    expect(updatePermissions).toHaveBeenCalledWith('p1', {
      project_manage: true,
      translation_edit: true,
    })
    wrapper.unmount()
  })

  it('clearing a right of an administrator warns, and cancelling sends nothing', async () => {
    const wrapper = await mountWithUser('staff', {
      id: 'p1',
      permissions: permissions([...PERMISSION_KEYS]),
      is_active: true,
    })
    tick('payment_review', false)
    await flushPromises()
    expect(bodyText()).toContain('staff.userDetail.removeAdminWarning')
    press('common.cancel')
    await flushPromises()
    expect(updatePermissions).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('a preset pressed on an administrator opens the remove warning and sends nothing until confirmed', async () => {
    updatePermissions.mockResolvedValue({
      id: 'p1',
      permissions: permissions(['payment_review', 'financial_operations']),
      is_active: true,
    } as never)
    const wrapper = await mountWithUser('staff', {
      id: 'p1',
      permissions: permissions([...PERMISSION_KEYS]),
      is_active: true,
    })
    press('staff.rights.presets.finance')
    await flushPromises()
    expect(bodyText()).toContain('staff.userDetail.removeAdminWarning')
    expect(updatePermissions).not.toHaveBeenCalled()
    press('common.confirm')
    await flushPromises()
    expect(updatePermissions).toHaveBeenCalledTimes(1)
    const [, body] = updatePermissions.mock.calls[0] as [string, Record<string, boolean>]
    expect(
      Object.keys(body)
        .filter((k) => body[k])
        .sort(),
    ).toEqual(['financial_operations', 'payment_review'])
    wrapper.unmount()
  })

  it('an ordinary tick sends at once with no warning', async () => {
    updatePermissions.mockResolvedValue({
      id: 'p1',
      permissions: permissions(['avatar_mode', 'user_block']),
      is_active: true,
    } as never)
    const wrapper = await mountWithUser('staff', {
      id: 'p1',
      permissions: permissions(['avatar_mode']),
      is_active: true,
    })
    tick('user_block', true)
    await flushPromises()
    expect(bodyText()).not.toContain('AdminWarning')
    expect(updatePermissions).toHaveBeenCalledWith('p1', {
      user_block: true,
      translation_edit: false,
    })
    wrapper.unmount()
  })
})
