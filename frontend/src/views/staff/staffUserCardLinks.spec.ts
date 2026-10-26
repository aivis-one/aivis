// =============================================================================
// The user card -- links to the person's money and "Act as this user"
// =============================================================================
//
// The card links to the person's payments, withdrawals and purchases (the lists
// open narrowed to them) and starts the avatar mode. Each control follows the
// viewer's rights, and the avatar button is not offered for a staff member.
// =============================================================================

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

import { useAuthStore } from '@/stores/auth'
import { PERMISSION_KEYS } from '@/utils/staffRights'

const push = vi.fn()
const startAvatarSession = vi.fn()
vi.mock('vue-router', () => ({
  useRoute: () => ({ query: {} }),
  useRouter: () => ({ push }),
}))
vi.mock('@/composables/useAvatar', async () => {
  const { ref } = await import('vue')
  return { useAvatar: () => ({ loading: ref(false), startAvatarSession }) }
})
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

function signInAs(held: readonly string[]): void {
  const auth = useAuthStore()
  auth.user = {
    id: 'me',
    role: 'staff',
    staff_profile: {
      id: 'self-profile',
      is_active: true,
      permissions: Object.fromEntries(PERMISSION_KEYS.map((key) => [key, held.includes(key)])),
    },
  } as unknown as typeof auth.user
}

async function mountCard(role: string): Promise<VueWrapper> {
  const base = {
    id: 'target',
    role,
    is_active: true,
    kyc_status: 'approved',
    email: 'target@example.com',
    created_at: '2026-01-01T00:00:00Z',
  }
  fetchUsers.mockResolvedValue({ items: [base], total: 1, page: 1, per_page: 20 } as never)
  fetchUserDetail.mockResolvedValue({
    ...base,
    onboarding_step: 'done',
    profile: {},
    language: 'en',
    staff_profile: null,
    latest_application_id: null,
    latest_application_status: null,
    kyc_applications_history: [],
  } as never)
  const wrapper = mount(StaffUsersView, { attachTo: document.body })
  await flushPromises()
  await wrapper.find('.user-item').trigger('click')
  await flushPromises()
  return wrapper
}

function button(label: string): HTMLButtonElement | undefined {
  const all = Array.from(document.body.querySelectorAll('button'))
  return all.find((b) => b.textContent?.includes(label)) as HTMLButtonElement | undefined
}

beforeEach(() => {
  setActivePinia(createPinia())
  document.body.innerHTML = ''
  vi.clearAllMocks()
})

describe('the links to the money of the person', () => {
  it('open the payments, withdrawals and purchases narrowed to the person', async () => {
    signInAs(['payment_review', 'financial_operations'])
    const wrapper = await mountCard('investor')
    button('staff.hub.finance.payments')!.click()
    expect(push).toHaveBeenLastCalledWith({
      path: '/staff/finance/payments',
      query: { user_id: 'target' },
    })
    await flushPromises()
    wrapper.unmount()

    document.body.innerHTML = ''
    const again = await mountCard('investor')
    button('staff.hub.finance.withdrawals')!.click()
    expect(push).toHaveBeenLastCalledWith({
      path: '/staff/finance/withdrawals',
      query: { user_id: 'target' },
    })
    await flushPromises()
    again.unmount()

    document.body.innerHTML = ''
    const third = await mountCard('investor')
    button('staff.hub.finance.purchases')!.click()
    expect(push).toHaveBeenLastCalledWith({
      path: '/staff/finance/purchases',
      query: { buyer_id: 'target' },
    })
    third.unmount()
  })

  it('offer only what the rights allow', async () => {
    signInAs(['financial_operations'])
    const wrapper = await mountCard('investor')
    expect(button('staff.hub.finance.payments')).toBeUndefined()
    expect(button('staff.hub.finance.withdrawals')).toBeUndefined()
    expect(button('staff.hub.finance.purchases')).toBeDefined()
    wrapper.unmount()
  })

  it('are not drawn at all for a member with neither right, or for a staff card', async () => {
    signInAs(['avatar_mode'])
    const none = await mountCard('investor')
    expect(document.body.textContent).not.toContain('staff.userDetail.linksTitle')
    none.unmount()

    document.body.innerHTML = ''
    signInAs(['payment_review', 'financial_operations'])
    const staffCard = await mountCard('staff')
    expect(document.body.textContent).not.toContain('staff.userDetail.linksTitle')
    staffCard.unmount()
  })
})

describe('Act as this user', () => {
  it('asks to confirm, then starts the avatar mode for the person', async () => {
    signInAs(['avatar_mode'])
    const wrapper = await mountCard('investor')
    button('staff.userDetail.actAs')!.click()
    await flushPromises()
    expect(startAvatarSession).not.toHaveBeenCalled()
    button('staff.avatar.start')!.click()
    await flushPromises()
    expect(startAvatarSession).toHaveBeenCalledWith('target')
    wrapper.unmount()
  })

  it('is hidden for a member without avatar_mode and for staff and platform cards', async () => {
    signInAs(['payment_review'])
    const noRight = await mountCard('investor')
    expect(button('staff.userDetail.actAs')).toBeUndefined()
    noRight.unmount()

    for (const role of ['staff', 'platform']) {
      document.body.innerHTML = ''
      signInAs(['avatar_mode'])
      const wrapper = await mountCard(role)
      expect(button('staff.userDetail.actAs')).toBeUndefined()
      wrapper.unmount()
    }
  })
})
