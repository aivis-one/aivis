// =============================================================================
// InvestorSettingsView -- the profile's name rows, the heading, and the order of
// the panels
// =============================================================================

import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter } from 'vue-router'
import en from '@/i18n/locales/en.json'
import ru from '@/i18n/locales/ru.json'

vi.mock('@/api/users', () => ({ updateMe: vi.fn() }))
vi.mock('@/api/agent-apps', () => ({
  submitAgentApplication: vi.fn(),
  getMyAgentApplications: async () => [],
}))

import InvestorSettingsView from './InvestorSettingsView.vue'
import { useAuthStore } from '@/stores/auth'

const SECTIONS = {
  TwoFactorSection: true,
  EmailSection: true,
  ActiveSessionsSection: true,
  NotificationPreferencesSection: true,
  DeactivateAccountSection: true,
  IntegratorApplicationModal: true,
}

async function mountSettings(profile: Record<string, unknown>, locale: 'en' | 'ru' = 'en') {
  const pinia = createPinia()
  setActivePinia(pinia)
  const auth = useAuthStore()
  auth.token = 't'
  auth.user = {
    id: 'u1',
    email: 'anna@example.com',
    role: 'investor',
    language: 'en',
    profile,
  } as never
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/investor/docs', name: 'investor-docs', component: { template: '<div />' } },
      { path: '/investor/support', name: 'investor-support', component: { template: '<div />' } },
      { path: '/investor/faq', name: 'investor-faq', component: { template: '<div />' } },
      { path: '/:pathMatch(.*)*', component: { template: '<div />' } },
    ],
  })
  await router.push('/investor/settings')
  await router.isReady()
  const w = mount(InvestorSettingsView, {
    global: {
      plugins: [
        router,
        pinia,
        createI18n({ legacy: false, locale, messages: { en, ru }, missingWarn: false }),
      ],
      stubs: SECTIONS,
    },
  })
  await flushPromises()
  return w
}

describe('InvestorSettingsView profile', () => {
  it('shows the first and last name as rows, and "Not set" where missing', async () => {
    const w = await mountSettings({ first_name: 'Anna', phone: '+1' })
    const rows = w.findAll('.ds-kv__row').map((r) => r.text().replace(/\s+/g, ' '))
    expect(rows).toContain('First nameAnna')
    expect(rows).toContain('Last nameNot set')
  })

  it('does not call a person with no name "No name": the heading is the e-mail', async () => {
    const w = await mountSettings({})
    expect(w.get('#sett-name').text()).toBe('anna@example.com')
    expect(w.text()).not.toMatch(/No name/i)
    // the e-mail is not said twice
    expect(w.findAll('.sett__email')).toHaveLength(0)
  })

  it('heads the card with the name when there is one', async () => {
    const w = await mountSettings({ first_name: 'Anna', last_name: 'Petrova' })
    expect(w.get('#sett-name').text()).toBe('Anna Petrova')
    expect(w.get('.sett__email').text()).toBe('anna@example.com')
  })

  it('offers "Fill in details" when the name is missing, even with phone and country', async () => {
    const w = await mountSettings({ first_name: 'Anna', phone: '+1', country: 'GE' })
    expect(w.text()).toContain('Fill in details')
  })

  it('does not offer it when nothing is missing', async () => {
    const w = await mountSettings({
      first_name: 'Anna',
      last_name: 'Petrova',
      phone: '+1',
      country: 'GE',
    })
    expect(w.text()).not.toContain('Fill in details')
  })
})

describe('InvestorSettingsView order', () => {
  it('puts verification, security and documents and notifications before the preferences', async () => {
    const w = await mountSettings({ first_name: 'Anna', last_name: 'Petrova' })
    const ids = w.findAll('section[aria-labelledby]').map((s) => s.attributes('aria-labelledby'))
    expect(ids.indexOf('sett-actions')).toBeGreaterThan(ids.indexOf('sett-profile'))
    expect(ids.indexOf('sett-prefs')).toBeGreaterThan(ids.indexOf('sett-actions'))
    // the verification row opens the actions panel, the notifications sit inside it
    expect(w.get('section[aria-labelledby="sett-actions"]').text()).toContain('Identity')
  })
})

describe('InvestorSettingsView leaving', () => {
  it('stands the log outs and the deactivation in a last card, apart from the actions', async () => {
    const w = await mountSettings({ first_name: 'Anna', last_name: 'Petrova' })
    const ids = w.findAll('section[aria-labelledby]').map((s) => s.attributes('aria-labelledby'))
    expect(ids[ids.length - 1]).toBe('sett-leave')
    const leave = w.get('section[aria-labelledby="sett-leave"]')
    expect(leave.text()).toContain('Log out of all devices')
    expect(leave.text()).toMatch(/Log out\s*$/)
    expect(leave.find('deactivate-account-section-stub').exists()).toBe(true)
    const actions = w.get('section[aria-labelledby="sett-actions"]')
    expect(actions.text()).not.toContain('Log out')
    expect(actions.find('deactivate-account-section-stub').exists()).toBe(false)
  })
})
