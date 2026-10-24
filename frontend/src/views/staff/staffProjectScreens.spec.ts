// =============================================================================
// the staff Home, Settings and a project's sections -- ONE MOUNT EACH
// =============================================================================
//
// Smoke-and-behaviour mounts with the API mocked, asserting through the
// rendered text (translation keys here: the test catalogue is empty on
// purpose, see test-setup.ts). Axes: the answer EMPTY, FULL and FAILED.
// =============================================================================

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: 'proj-1' }, query: {} }),
  useRouter: () => ({ push: vi.fn() }),
}))
vi.mock('@/composables/safeNavigate', () => ({ safeNavigate: vi.fn() }))
vi.mock('@/api/admin', () => ({
  fetchDashboardStats: vi.fn(),
  fetchAgentApplications: vi.fn(),
  fetchWithdrawalsStaff: vi.fn(),
}))
vi.mock('@/api/support', () => ({ listStaffSupportQueue: vi.fn() }))
vi.mock('@/api/products', () => ({ listProducts: vi.fn() }))
vi.mock('@/api/staff-products', async (importActual) => ({
  ...(await importActual<typeof import('@/api/staff-products')>()),
  createStaffProduct: vi.fn(),
  updateStaffProduct: vi.fn(),
  fetchStaffCompanyProducts: vi.fn(),
  updateStaffProductStatus: vi.fn(),
}))
vi.mock('@/api/staff-companies', () => ({
  fetchStaffCompanyPool: vi.fn(),
  createStaffCompanyPool: vi.fn(),
  fetchStaffCompanyAttachments: vi.fn(),
  reorderStaffCompanyAttachments: vi.fn(),
  deleteStaffCompanyAttachment: vi.fn(),
  createStaffAttachment: vi.fn(),
  updateStaffAttachment: vi.fn(),
  replaceStaffAttachmentFile: vi.fn(),
}))

import * as admin from '@/api/admin'
import * as support from '@/api/support'
import * as products from '@/api/products'
import * as staffProducts from '@/api/staff-products'
import * as staffCompanies from '@/api/staff-companies'
import { useAuthStore } from '@/stores/auth'
import { PERMISSION_KEYS } from '@/utils/staffRights'
import StaffDashboardView from './StaffDashboardView.vue'
import StaffSettingsView from './StaffSettingsView.vue'
import StaffCompanyPoolSection from './platform/StaffCompanyPoolSection.vue'
import StaffCompanyProductsSection from './platform/StaffCompanyProductsSection.vue'
import StaffCompanyDocumentsSection from './platform/StaffCompanyDocumentsSection.vue'

const fetchDashboardStats = vi.mocked(admin.fetchDashboardStats)
const fetchAgentApplications = vi.mocked(admin.fetchAgentApplications)
const fetchWithdrawalsStaff = vi.mocked(admin.fetchWithdrawalsStaff)
const listStaffSupportQueue = vi.mocked(support.listStaffSupportQueue)
const listProducts = vi.mocked(products.listProducts)
const createStaffProduct = vi.mocked(staffProducts.createStaffProduct)
const fetchStaffCompanyProducts = vi.mocked(staffProducts.fetchStaffCompanyProducts)
const updateStaffProductStatus = vi.mocked(staffProducts.updateStaffProductStatus)
const fetchStaffCompanyPool = vi.mocked(staffCompanies.fetchStaffCompanyPool)
const createStaffCompanyPool = vi.mocked(staffCompanies.createStaffCompanyPool)
const fetchStaffCompanyAttachments = vi.mocked(staffCompanies.fetchStaffCompanyAttachments)

function signInAs(held: readonly string[]): void {
  const auth = useAuthStore()
  auth.user = {
    id: 's1',
    role: 'staff',
    email: 'staff@example.com',
    language: 'en',
    profile: { first_name: 'Sam', last_name: 'Staff' },
    staff_profile: {
      id: 'p1',
      is_active: true,
      permissions: Object.fromEntries(PERMISSION_KEYS.map((key) => [key, held.includes(key)])),
    },
  } as unknown as typeof auth.user
}

beforeEach(() => {
  setActivePinia(createPinia())
  document.body.innerHTML = ''
  vi.clearAllMocks()
})

describe('the staff Home', () => {
  function okReads() {
    fetchDashboardStats.mockResolvedValue({
      total_users: 12,
      users_by_role: {},
      pending_kyc_count: 3,
      active_avatar_sessions: 0,
      frozen_payments_count: 0,
    } as never)
    fetchWithdrawalsStaff.mockResolvedValue({ items: [], total: 0, page: 1, per_page: 1 } as never)
    fetchAgentApplications.mockResolvedValue({ items: [], total: 0, page: 1, per_page: 1 } as never)
    listStaffSupportQueue.mockResolvedValue({ items: [], next_cursor: null } as never)
  }

  it('draws a counter for each queue the member may work and for nothing else', async () => {
    okReads()
    signInAs(['kyc_approve'])
    const wrapper = mount(StaffDashboardView)
    await flushPromises()
    const labels = wrapper.findAll('.ds-stat__label').map((l) => l.text())
    expect(labels).toEqual([
      'staff.users.stat',
      'staff.home.queues.kyc',
      'staff.home.queues.support',
    ])
    wrapper.unmount()
  })

  it('draws every counter for the administrator, a real zero among them', async () => {
    okReads()
    signInAs([...PERMISSION_KEYS])
    const wrapper = mount(StaffDashboardView)
    await flushPromises()
    expect(wrapper.findAll('.ds-stat')).toHaveLength(6)
    const values = wrapper.findAll('.ds-stat__value').map((v) => v.text())
    expect(values).toEqual(['12', '3', '0', '0', '0', '0'])
    wrapper.unmount()
  })

  it('shows a failed counter as a dash with the failure said, and offers to read again', async () => {
    okReads()
    fetchWithdrawalsStaff.mockRejectedValue(new Error('500'))
    signInAs([...PERMISSION_KEYS])
    const wrapper = mount(StaffDashboardView)
    await flushPromises()
    const cards = wrapper.findAll('.ds-stat')
    const failed = cards.find((c) => c.text().includes('staff.home.queues.withdrawals'))!
    expect(failed.find('.ds-stat__value').text()).toBe('—')
    expect(failed.text()).toContain('staff.home.loadFailed')
    expect(wrapper.find('.ds-alert').exists()).toBe(true)
    wrapper.unmount()
  })
})

describe('the staff Settings tab', () => {
  it('shows the profile, the role line and the version of the build', () => {
    signInAs(['user_block'])
    const wrapper = mount(StaffSettingsView, {
      global: {
        stubs: {
          TwoFactorSection: true,
          ActiveSessionsSection: true,
          NotificationPreferencesSection: true,
        },
      },
    })
    const text = wrapper.text()
    expect(text).toContain('Sam Staff')
    expect(text).toContain('staff@example.com')
    expect(text).toContain('staff.settings.roleStaff')
    expect(text).toContain('cabinets-1.5')
    expect(text).not.toContain('0.1.0')
    expect(text).toContain('staff.settings.documents')
    wrapper.unmount()
  })

  it('calls a member with every right the administrator', () => {
    signInAs([...PERMISSION_KEYS])
    const wrapper = mount(StaffSettingsView, {
      global: {
        stubs: {
          TwoFactorSection: true,
          ActiveSessionsSection: true,
          NotificationPreferencesSection: true,
        },
      },
    })
    expect(wrapper.text()).toContain('staff.settings.roleAdmin')
    wrapper.unmount()
  })
})

describe('a project: the pool of parts for sale', () => {
  it('says there is none and offers to create it to a member who may', async () => {
    fetchStaffCompanyPool.mockResolvedValue(null)
    signInAs(['project_manage', 'financial_operations'])
    const wrapper = mount(StaffCompanyPoolSection)
    await flushPromises()
    expect(wrapper.text()).toContain('staff.platform.pool.none')
    expect(wrapper.text()).toContain('staff.platform.pool.create')
    wrapper.unmount()
  })

  it('does not offer to create it to a member who lacks the financial right', async () => {
    fetchStaffCompanyPool.mockResolvedValue(null)
    signInAs(['project_manage'])
    const wrapper = mount(StaffCompanyPoolSection)
    await flushPromises()
    expect(wrapper.text()).toContain('staff.platform.pool.none')
    expect(wrapper.text()).not.toContain('staff.platform.pool.create')
    wrapper.unmount()
  })

  it('shows the pool the project has, and nothing that makes it larger', async () => {
    fetchStaffCompanyPool.mockResolvedValue({
      id: 'pool-1',
      company_id: 'proj-1',
      equity_percent: '25.0000',
      total_options: 250_000_000,
      status: 'active',
      created_at: '2026-10-01T00:00:00Z',
      updated_at: null,
      consumed: 1_000,
      remaining: 249_999_000,
    } as never)
    signInAs([...PERMISSION_KEYS])
    const wrapper = mount(StaffCompanyPoolSection)
    await flushPromises()
    expect(wrapper.text()).toContain('25.0000%')
    expect(wrapper.text()).toContain('staff.platform.pool.fixedNote')
    expect(wrapper.find('button').exists()).toBe(false)
    wrapper.unmount()
  })

  it('sends the percentage typed when it creates the pool', async () => {
    fetchStaffCompanyPool.mockResolvedValue(null)
    createStaffCompanyPool.mockResolvedValue({
      id: 'pool-1',
      company_id: 'proj-1',
      equity_percent: '25',
      total_options: 1,
      status: 'active',
      created_at: '',
      updated_at: null,
      consumed: 0,
      remaining: 1,
    } as never)
    signInAs([...PERMISSION_KEYS])
    const wrapper = mount(StaffCompanyPoolSection, { attachTo: document.body })
    await flushPromises()
    await wrapper.find('button').trigger('click')
    await flushPromises()
    const create = Array.from(document.body.querySelectorAll('.ds-dialog__panel button')).find(
      (b) => (b.textContent ?? '').includes('staff.platform.pool.create'),
    ) as HTMLButtonElement
    create.click()
    await flushPromises()
    expect(createStaffCompanyPool).toHaveBeenCalledWith('proj-1', { equity_percent: '25' })
    wrapper.unmount()
  })

  it('shows a failed read as a failure', async () => {
    fetchStaffCompanyPool.mockRejectedValue(new Error('500'))
    signInAs([...PERMISSION_KEYS])
    const wrapper = mount(StaffCompanyPoolSection)
    await flushPromises()
    expect(wrapper.text()).toContain('common.error')
    expect(wrapper.text()).not.toContain('staff.platform.pool.none')
    wrapper.unmount()
  })
})

describe('a project: products', () => {
  function product(id: string, status: string, name: string) {
    return {
      id,
      company_id: 'proj-1',
      pool_id: 'pool-1',
      name,
      description: 'A package',
      package_size: 1000,
      cover_url: null,
      purchase_config: null,
      price_per_unit_cents: 5,
      status,
      created_at: '2026-10-01T10:00:00Z',
      updated_at: null,
    }
  }
  const ALL_STATUSES = [
    product('p-active', 'active', 'Alpha'),
    product('p-hidden', 'hidden', 'Beta'),
    product('p-archived', 'archived', 'Gamma'),
  ]

  function listAll(): void {
    fetchStaffCompanyProducts.mockResolvedValue({
      items: ALL_STATUSES,
      total: 3,
      page: 1,
      per_page: 20,
    } as never)
  }

  /** The acts of one product's row (the items of its Action menu), by their text. */
  function buttonsOf(wrapper: ReturnType<typeof mount>, name: string): string[] {
    const row = wrapper.findAll('.scprod__item').find((li) => li.text().includes(name))!
    const items = row.findAll('[role="menuitem"]').map((b) => b.text())
    if (items.length) return items
    // A one-act row (an archived product) shows that act as a Button, not a menu
    return row
      .findAll('.ds-row__trail button')
      .map((b) => b.text())
      .filter(Boolean)
  }

  /** Open a product row's Action menu and pick the item with this text. */
  async function pick(
    wrapper: ReturnType<typeof mount>,
    name: string,
    item: string,
  ): Promise<void> {
    const row = wrapper.findAll('.scprod__item').find((li) => li.text().includes(name))!
    await row.find('.ds-menu__button').trigger('click')
    await row
      .findAll('[role="menuitem"]')
      .find((b) => b.text() === item)!
      .trigger('click')
  }

  it('reads the project products in every status and shows the status on each card', async () => {
    listAll()
    signInAs([...PERMISSION_KEYS])
    const wrapper = mount(StaffCompanyProductsSection)
    await flushPromises()
    expect(fetchStaffCompanyProducts).toHaveBeenCalledWith('proj-1', { page: 1, per_page: 20 })
    expect(listProducts).not.toHaveBeenCalled()
    const text = wrapper.text()
    expect(text).toContain('Alpha')
    expect(text).toContain('Beta')
    expect(text).toContain('Gamma')
    expect(text).toContain('active')
    expect(text).toContain('hidden')
    expect(text).toContain('archived')
    expect(text).toContain('staff.platform.products.create')
    wrapper.unmount()
  })

  it('offers only the moves the server allows from each status', async () => {
    listAll()
    signInAs([...PERMISSION_KEYS])
    const wrapper = mount(StaffCompanyProductsSection)
    await flushPromises()
    // active -> hide, archive; hidden -> return, archive; archived -> nothing
    expect(buttonsOf(wrapper, 'Alpha')).toEqual([
      'staff.platform.products.hide',
      'staff.platform.products.archive',
      'common.edit',
    ])
    expect(buttonsOf(wrapper, 'Beta')).toEqual([
      'staff.platform.products.return',
      'staff.platform.products.archive',
      'common.edit',
    ])
    expect(buttonsOf(wrapper, 'Gamma')).toEqual(['common.edit'])
    // ...and that one act is a Button of the row, with no menu around it
    const gamma = wrapper.findAll('.scprod__item').find((li) => li.text().includes('Gamma'))!
    expect(gamma.find('.ds-menu__button').exists()).toBe(false)
    wrapper.unmount()
  })

  it('hides a product through the status endpoint and reads the list again', async () => {
    listAll()
    updateStaffProductStatus.mockResolvedValue(product('p-active', 'hidden', 'Alpha') as never)
    signInAs([...PERMISSION_KEYS])
    const wrapper = mount(StaffCompanyProductsSection)
    await flushPromises()
    await pick(wrapper, 'Alpha', 'staff.platform.products.hide')
    await flushPromises()
    expect(updateStaffProductStatus).toHaveBeenCalledWith('p-active', 'hidden')
    expect(fetchStaffCompanyProducts).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('returns a hidden product to sale', async () => {
    listAll()
    updateStaffProductStatus.mockResolvedValue(product('p-hidden', 'active', 'Beta') as never)
    signInAs([...PERMISSION_KEYS])
    const wrapper = mount(StaffCompanyProductsSection)
    await flushPromises()
    await pick(wrapper, 'Beta', 'staff.platform.products.return')
    await flushPromises()
    expect(updateStaffProductStatus).toHaveBeenCalledWith('p-hidden', 'active')
    wrapper.unmount()
  })

  it('asks before archiving, and archives only on the confirmation', async () => {
    listAll()
    updateStaffProductStatus.mockResolvedValue(product('p-active', 'archived', 'Alpha') as never)
    signInAs([...PERMISSION_KEYS])
    const wrapper = mount(StaffCompanyProductsSection, { attachTo: document.body })
    await flushPromises()
    await pick(wrapper, 'Alpha', 'staff.platform.products.archive')
    await flushPromises()
    expect(updateStaffProductStatus).not.toHaveBeenCalled()
    const confirm = Array.from(document.body.querySelectorAll('.ds-dialog__panel button')).find(
      (b) => (b.textContent ?? '').includes('staff.platform.products.archive'),
    ) as HTMLButtonElement
    confirm.click()
    await flushPromises()
    expect(updateStaffProductStatus).toHaveBeenCalledWith('p-active', 'archived')
    wrapper.unmount()
  })

  it('offers neither create, edit nor a status move to a member who only reads', async () => {
    listAll()
    signInAs([])
    const wrapper = mount(StaffCompanyProductsSection)
    await flushPromises()
    expect(wrapper.text()).toContain('Alpha')
    expect(wrapper.text()).not.toContain('staff.platform.products.create')
    expect(wrapper.text()).not.toContain('common.edit')
    expect(wrapper.text()).not.toContain('staff.platform.products.hide')
    expect(wrapper.text()).not.toContain('staff.platform.products.archive')
    expect(wrapper.text()).not.toContain('staff.platform.products.return')
    expect(createStaffProduct).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('shows a failed read as a failure', async () => {
    fetchStaffCompanyProducts.mockRejectedValue(new Error('500'))
    signInAs([...PERMISSION_KEYS])
    const wrapper = mount(StaffCompanyProductsSection)
    await flushPromises()
    expect(wrapper.text()).toContain('common.error')
    wrapper.unmount()
  })
})

describe('a project: documents', () => {
  it('offers the upload to a member who may manage projects, even with no document yet', async () => {
    fetchStaffCompanyAttachments.mockResolvedValue([])
    signInAs(['project_manage'])
    const wrapper = mount(StaffCompanyDocumentsSection)
    await flushPromises()
    expect(wrapper.text()).toContain('staff.platform.documents.addCta')
    expect(wrapper.text()).toContain('staff.platform.documents.empty')
    wrapper.unmount()
  })

  it('does not offer the upload to a member who only reads', async () => {
    fetchStaffCompanyAttachments.mockResolvedValue([])
    signInAs(['company_manage'])
    const wrapper = mount(StaffCompanyDocumentsSection)
    await flushPromises()
    expect(wrapper.text()).not.toContain('staff.platform.documents.addCta')
    wrapper.unmount()
  })
})
