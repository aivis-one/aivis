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
}))
vi.mock('@/api/media', async (importActual) => ({
  ...(await importActual<typeof import('@/api/media')>()),
  uploadStaffCompanyMedia: vi.fn(),
  deleteStaffCompanyMedia: vi.fn(),
}))

import * as staffCompanies from '@/api/staff-companies'
import * as media from '@/api/media'
import { useAuthStore } from '@/stores/auth'
import { PERMISSION_KEYS } from '@/utils/staffRights'
import StaffCompanyProfileSection from './StaffCompanyProfileSection.vue'
import { STAFF_COMPANY_KEY } from './staffCompanyContext'

const updateStaffCompany = vi.mocked(staffCompanies.updateStaffCompany)
const uploadStaffCompanyMedia = vi.mocked(media.uploadStaffCompanyMedia)
const deleteStaffCompanyMedia = vi.mocked(media.deleteStaffCompanyMedia)

const COMPANY = {
  id: 'proj-1',
  name: 'Project One',
  description: 'About it',
  status: 'active',
  logo_url: 'https://files.example.org/logo.png?sig=1',
  logo_dark_url: null,
  cover_url: null,
  promo_video_url: 'https://example.org/promo.mp4',
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
  return Array.from(document.body.querySelectorAll('.ds-dialog__panel button')).find((b) =>
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

  it("offers no control to change the number of a project's parts, whatever the rights", async () => {
    signInAs([...PERMISSION_KEYS])
    const { wrapper } = mountSection()
    await flushPromises()
    expect(wrapper.text()).toContain('staff.platform.profile.totalSupply')
    expect(wrapper.text()).not.toContain('staff.platform.profile.supplyEditCta')
    expect(wrapper.findAll('button').find((b) => b.text().includes('supplyEdit'))).toBeUndefined()
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
    const name = document.body.querySelector('.ds-dialog__panel input') as HTMLInputElement
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

  // Until H36 this cleared the LOGO link: the logo was a typed URL then. The
  // logo is a file now (its own endpoints, not this form), so the same
  // property -- a cleared link travels as an explicit null -- is held on the
  // promo video, a link the form still carries.
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
    // The inputs of the form, in order: name, promo video, presentation.
    const inputs = Array.from(
      document.body.querySelectorAll('.ds-dialog__panel input'),
    ) as HTMLInputElement[]
    expect(inputs).toHaveLength(3)
    const promo = inputs[1]!
    expect(promo.value).toBe('https://example.org/promo.mp4')
    promo.value = ''
    promo.dispatchEvent(new Event('input'))
    await flushPromises()
    modalButton('common.save').click()
    await flushPromises()
    expect(updateStaffCompany).toHaveBeenCalledWith('proj-1', { promo_video_url: null })
    wrapper.unmount()
  })
})

// =============================================================================
// THE PICTURES ARE FILES (H36 P-131)
// =============================================================================
//
// Axes: the three slots are three fields, each with its own endpoint slot
// (REPEAT); a stored logo is drawn, an absent dark logo and cover are not
// (EMPTINESS); a member who may not edit gets fields that do nothing.

describe('StaffCompanyProfileSection pictures', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    uploadStaffCompanyMedia.mockReset()
    deleteStaffCompanyMedia.mockReset()
    document.body.innerHTML = ''
  })

  function fileInputs(): HTMLInputElement[] {
    return Array.from(document.body.querySelectorAll('.scp input[type="file"]'))
  }

  async function pick(input: HTMLInputElement, file: File): Promise<void> {
    Object.defineProperty(input, 'files', { value: [file], configurable: true })
    input.dispatchEvent(new Event('change'))
    await flushPromises()
  }

  it('draws one field per slot, the stored logo as a thumb', async () => {
    signInAs(['project_manage'])
    const { wrapper } = mountSection()
    await flushPromises()
    expect(fileInputs()).toHaveLength(3)
    const thumbs = Array.from(document.body.querySelectorAll('.scp .ds-file__thumb img'))
    expect(thumbs.map((img) => img.getAttribute('src'))).toEqual([COMPANY.logo_url])
    wrapper.unmount()
  })

  it('uploads into the slot of its field and reloads the project', async () => {
    signInAs(['project_manage'])
    uploadStaffCompanyMedia.mockResolvedValue(COMPANY as never)
    const { wrapper, reload } = mountSection()
    await flushPromises()
    const file = new File(['png'], 'dark.png', { type: 'image/png' })
    await pick(fileInputs()[1]!, file)
    expect(uploadStaffCompanyMedia).toHaveBeenCalledWith('proj-1', 'logo-dark', file)
    expect(reload).toHaveBeenCalled()
    wrapper.unmount()
  })

  it('removes a stored picture after the confirmation', async () => {
    signInAs(['project_manage'])
    deleteStaffCompanyMedia.mockResolvedValue(undefined as never)
    const { wrapper, reload } = mountSection()
    await flushPromises()
    ;(document.body.querySelector('.scp .ds-file__remove') as HTMLButtonElement).click()
    await flushPromises()
    modalButton('common.media.remove').click()
    await flushPromises()
    expect(deleteStaffCompanyMedia).toHaveBeenCalledWith('proj-1', 'logo')
    expect(reload).toHaveBeenCalled()
    wrapper.unmount()
  })

  it('gives a member without project_manage fields that do nothing', async () => {
    signInAs([])
    const { wrapper } = mountSection()
    await flushPromises()
    const inputs = fileInputs()
    expect(inputs).toHaveLength(3)
    expect(inputs.every((input) => input.disabled)).toBe(true)
    expect(document.body.querySelector('.scp .ds-file__remove')).toBeNull()
    wrapper.unmount()
  })
})
