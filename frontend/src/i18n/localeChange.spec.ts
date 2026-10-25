// =============================================================================
// A locale switch re-reads the project data on screen (H38 P-132)
// =============================================================================
//
// The backend answers project data in the language of the request. Data
// fetched before a switch is in the old language, so setLocale() notifies
// its subscribers AFTER the new locale is active (the API client already
// sends it): the data stores through stores/localeReload.ts, a view's own
// fetch through useReloadOnLocale while it is mounted.
//
// Axes:
//   REPEAT    -- two switches, two calls; the same locale twice, one call
//   EMPTINESS -- a store with nothing loaded is not fetched
//   SHORTAGE  -- an unsupported locale changes nothing and notifies nobody;
//                a listener that throws does not stop the others; an
//                unmounted view is no longer called
// =============================================================================

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/api/companies', async (importActual) => ({
  ...(await importActual<typeof import('@/api/companies')>()),
  getMyCompany: vi.fn(),
  listCompanies: vi.fn(),
}))

import * as companiesApi from '@/api/companies'
import { i18n, onLocaleChange, setLocale } from '@/i18n'
import { useReloadOnLocale } from '@/composables/useReloadOnLocale'
import { reloadProjectStores } from '@/stores/localeReload'
import { useCompanyProfileStore } from '@/stores/companyProfile'
import { useCompanyListStore } from '@/stores/companyList'

const getMyCompany = vi.mocked(companiesApi.getMyCompany)
const listCompanies = vi.mocked(companiesApi.listCompanies)

beforeEach(async () => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
  await setLocale('en')
})

afterEach(async () => {
  await setLocale('en')
})

describe('setLocale notifies', () => {
  it('after the switch, with the new locale active, once per real switch', async () => {
    const seen: string[] = []
    const stop = onLocaleChange((locale) => seen.push(`${locale}:${i18n.global.locale.value}`))
    await setLocale('ru')
    await setLocale('ru')
    await setLocale('en')
    await setLocale('xx')
    stop()
    await setLocale('ru')
    expect(seen).toEqual(['ru:ru', 'en:en'])
  })

  it('every listener, even when one throws', async () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => {})
    const second = vi.fn()
    const stopA = onLocaleChange(() => {
      throw new Error('boom')
    })
    const stopB = onLocaleChange(second)
    await setLocale('ru')
    expect(second).toHaveBeenCalledWith('ru')
    stopA()
    stopB()
    error.mockRestore()
  })
})

describe('useReloadOnLocale', () => {
  it('re-runs the load while mounted and stops when unmounted', async () => {
    const load = vi.fn()
    const View = defineComponent({
      setup() {
        useReloadOnLocale(load)
        return () => h('div')
      },
    })
    const wrapper = mount(View)
    await setLocale('ru')
    expect(load).toHaveBeenCalledTimes(1)
    wrapper.unmount()
    await setLocale('en')
    expect(load).toHaveBeenCalledTimes(1)
  })
})

describe('reloadProjectStores', () => {
  it('re-reads a loaded store in place and leaves an empty one alone', async () => {
    const profile = useCompanyProfileStore()
    const list = useCompanyListStore()
    // Nothing loaded: nothing fetched.
    reloadProjectStores()
    expect(getMyCompany).not.toHaveBeenCalled()
    expect(listCompanies).not.toHaveBeenCalled()

    profile.applyProfile({ id: 'c1', name: 'Farm' } as never)
    getMyCompany.mockResolvedValue({ id: 'c1', name: 'Ферма' } as never)
    list.items = [{ id: 'c1', name: 'Farm' }] as never
    listCompanies.mockResolvedValue({ items: [{ id: 'c1', name: 'Ферма' }], total: 1 } as never)

    reloadProjectStores()
    await vi.waitFor(() => expect(profile.profile?.name).toBe('Ферма'))
    await vi.waitFor(() => expect(list.items[0]?.name).toBe('Ферма'))
    expect(getMyCompany).toHaveBeenCalledTimes(1)
    expect(listCompanies).toHaveBeenCalledTimes(1)
  })

  it('keeps the cached profile when the re-read fails', async () => {
    const profile = useCompanyProfileStore()
    profile.applyProfile({ id: 'c1', name: 'Farm' } as never)
    getMyCompany.mockRejectedValue(new Error('offline'))
    await profile.refresh()
    expect(profile.profile?.name).toBe('Farm')
    expect(profile.error).toBeNull()
  })
})
