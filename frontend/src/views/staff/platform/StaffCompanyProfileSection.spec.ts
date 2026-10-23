// =============================================================================
// StaffCompanyProfileSection -- A STAFF MEMBER CHANGES THE NAME, THE DESCRIPTION
// AND THE LINKS; THE DIVISION OF THE PARTS IS A TABLE NOTHING WRITES
// =============================================================================
//
// Axes: a member who MAY edit and one who may NOT; a save with NOTHING changed
// (no request), with ONE field changed (only that field travels), and with a
// link CLEARED (an explicit null, not an omitted key).
// =============================================================================

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { ref } from 'vue'

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: 'proj-1' }, query: {} }),
  useRouter: () => ({ push: vi.fn() }),
}))
vi.mock('@/api/staff-companies', () => ({
  updateStaffCompany: vi.fn(),
  updateStaffCompanySupply: vi.fn(),
  fetchStaffCompanyPool: vi.fn(),
}))

import * as staffCompanies from '@/api/staff-companies'
import { useAuthStore } from '@/stores/auth'
import { PERMISSION_KEYS } from '@/utils/staffRights'
import StaffCompanyProfileSection from './StaffCompanyProfileSection.vue'
import { STAFF_COMPANY_KEY } from './staffCompanyContext'

const updateStaffCompany = vi.mocked(staffCompanies.updateStaffCompany)

const COMPANY = {
  id: 'proj-1',
  name: 'Project One',
  description: 'About it',
  status: 'active',
  logo_url: 'cdn.example.org/logo.png',
  cover_url: null,
  promo_video_url: null,
  presentation_url: null,
  price_per_unit_cents: 5,
  total_supply: 1_000_000_000,
  shares_per_option: 1,
  distribution_config: { company_pct: 10, agent_levels: [5] },
  roadmap: [],
}

function signInAs(held: readonly string[]): void {
  const auth = useAuthStore()
  auth.user = {
    id: 's1',
    role: 'staff',
    staff_profile: {
      id: 'p1',
      is_active: true,
      permissions: Object.fromEntries(PERMISSION_KEYS.map((key) => [key, held.includes(key)])),
    },
  } as unknown as typeof auth.user
}

function mountSection() {
  const reload = vi.fn(async () => {})
  const wrapper = mount(StaffCompanyProfileSection, {
    attachTo: document.body,
    global: {
      provide: {
        [STAFF_COMPANY_KEY as symbol]: {
          company: ref(COMPANY),
          loading: ref(false),
          error: ref(false),
          reload,
        },
      },
    },
  })
  return { wrapper, reload }
}

function modalButton(label: string): HTMLButtonElement {
  return Array.from(document.body.querySelectorAll('.c-modal-dialog button')).find((b) =>
    (b.textContent ?? '').includes(label),
  ) as HTMLButtonElement
}

beforeEach(() => {
  setActivePinia(createPinia())
  document.body.innerHTML = ''
  vi.clearAllMocks()
})

describe('the project profile section', () => {
  it('shows the division of the parts as a read-only table, never as JSON', async () => {
    signInAs([...PERMISSION_KEYS])
    const { wrapper } = mountSection()
    await flushPromises()
    const text = wrapper.text()
    for (const percent of ['25%', '10%', '14%', '51%']) expect(text).toContain(percent)
    expect(text).not.toContain('company_pct')
    wrapper.unmount()
  })

  it('offers the edit to a member who may manage projects and to nobody else', async () => {
    signInAs(['company_manage'])
    const reader = mountSection()
    await flushPromises()
    expect(reader.wrapper.text()).not.toContain('staff.platform.profile.profileEditCta')
    reader.wrapper.unmount()

    signInAs(['project_manage'])
    const editor = mountSection()
    await flushPromises()
    expect(editor.wrapper.text()).toContain('staff.platform.profile.profileEditCta')
    editor.wrapper.unmount()
  })

  it('sends only the field that changed', async () => {
    signInAs(['project_manage'])
    updateStaffCompany.mockResolvedValue(COMPANY as never)
    const { wrapper, reload } = mountSection()
    await flushPromises()
    const open = wrapper
      .findAll('button')
      .find((b) => b.text().includes('staff.platform.profile.profileEditCta'))!
    await open.trigger('click')
    await flushPromises()
    const name = document.body.querySelector('.c-modal-dialog input') as HTMLInputElement
    name.value = 'Project Two'
    name.dispatchEvent(new Event('input'))
    await flushPromises()
    modalButton('common.save').click()
    await flushPromises()
    expect(updateStaffCompany).toHaveBeenCalledWith('proj-1', { name: 'Project Two' })
    expect(reload).toHaveBeenCalled()
    wrapper.unmount()
  })

  it('sends nothing when nothing changed', async () => {
    signInAs(['project_manage'])
    const { wrapper } = mountSection()
    await flushPromises()
    await wrapper
      .findAll('button')
      .find((b) => b.text().includes('staff.platform.profile.profileEditCta'))!
      .trigger('click')
    await flushPromises()
    modalButton('common.save').click()
    await flushPromises()
    expect(updateStaffCompany).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('clears a link with an explicit null', async () => {
    signInAs(['project_manage'])
    updateStaffCompany.mockResolvedValue(COMPANY as never)
    const { wrapper } = mountSection()
    await flushPromises()
    await wrapper
      .findAll('button')
      .find((b) => b.text().includes('staff.platform.profile.profileEditCta'))!
      .trigger('click')
    await flushPromises()
    // The inputs of the form, in order: name, logo, cover, promo video, presentation.
    const inputs = Array.from(
      document.body.querySelectorAll('.c-modal-dialog input'),
    ) as HTMLInputElement[]
    const logo = inputs[1]!
    logo.value = ''
    logo.dispatchEvent(new Event('input'))
    await flushPromises()
    modalButton('common.save').click()
    await flushPromises()
    expect(updateStaffCompany).toHaveBeenCalledWith('proj-1', { logo_url: null })
    wrapper.unmount()
  })
})
