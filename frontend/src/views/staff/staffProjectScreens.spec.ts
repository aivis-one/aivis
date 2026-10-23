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
vi.mock('@/api/staff-products', () => ({
  createStaffProduct: vi.fn(),
  updateStaffProduct: vi.fn(),
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
    const labels = wrapper.findAll('.c-stat__label').map((l) => l.text())
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
    expect(wrapper.findAll('.c-stat')).toHaveLength(6)
    const values = wrapper.findAll('.c-stat__value').map((v) => v.text())
    expect(values).toEqual(['12', '3', '0', '0', '0', '0'])
    wrapper.unmount()
  })

  it('shows a failed counter as a dash with the failure said, and offers to read again', async () => {
    okReads()
    fetchWithdrawalsStaff.mockRejectedValue(new Error('500'))
    signInAs([...PERMISSION_KEYS])
    const wrapper = mount(StaffDashboardView)
    await flushPromises()
    const cards = wrapper.findAll('.c-stat')
    const failed = cards.find((c) => c.text().includes('staff.home.queues.withdrawals'))!
    expect(failed.find('.c-stat__value').text()).toBe('—')
    expect(failed.text()).toContain('staff.home.loadFailed')
    expect(wrapper.find('.staff-dash__failed').exists()).toBe(true)
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
    expect(text).toContain('0.0.0-test')
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
    const create = Array.from(document.body.querySelectorAll('.c-modal-dialog button')).find((b) =>
      (b.textContent ?? '').includes('staff.platform.pool.create'),
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
  const PRODUCT = {
    id: 'prod-1',
    company_id: 'proj-1',
    name: 'Starter',
    description: 'A package',
    package_size: 1000,
    price_per_unit_cents: 5,
    price_per_pack_cents: 5000,
    available_packages: 7,
    company_name: 'Project One',
  }

  it('lists the products on sale and offers edit and create to a member who may', async () => {
    listProducts.mockResolvedValue({ items: [PRODUCT], total: 1, page: 1, per_page: 100 } as never)
    signInAs([...PERMISSION_KEYS])
    const wrapper = mount(StaffCompanyProductsSection)
    await flushPromises()
    expect(listProducts).toHaveBeenCalledWith({ company_id: 'proj-1', per_page: 100 })
    expect(wrapper.text()).toContain('Starter')
    expect(wrapper.text()).toContain('staff.platform.products.create')
    expect(wrapper.text()).toContain('common.edit')
    wrapper.unmount()
  })

  it('offers neither create nor edit to a member who only reads', async () => {
    listProducts.mockResolvedValue({ items: [PRODUCT], total: 1, page: 1, per_page: 100 } as never)
    signInAs([])
    const wrapper = mount(StaffCompanyProductsSection)
    await flushPromises()
    expect(wrapper.text()).toContain('Starter')
    expect(wrapper.text()).not.toContain('staff.platform.products.create')
    expect(wrapper.text()).not.toContain('common.edit')
    wrapper.unmount()
  })

  it('has no control that takes a product off sale', async () => {
    listProducts.mockResolvedValue({ items: [PRODUCT], total: 1, page: 1, per_page: 100 } as never)
    signInAs([...PERMISSION_KEYS])
    const wrapper = mount(StaffCompanyProductsSection)
    await flushPromises()
    expect(wrapper.text()).not.toMatch(/hide|archive/i)
    expect(createStaffProduct).not.toHaveBeenCalled()
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
