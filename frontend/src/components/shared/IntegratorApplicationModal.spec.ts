// =============================================================================
// IntegratorApplicationModal -- what the window tells the applicant
// =============================================================================
//
// The pools, the bonus parts and the withdrawal as the model has them, the price of
// an identity verification read from the server (never a figure in the texts), and
// the integrator's icon in the title.
// =============================================================================

import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter } from 'vue-router'
import en from '@/i18n/locales/en.json'
import ru from '@/i18n/locales/ru.json'

const getKycStatus = vi.fn()
vi.mock('@/api/kyc', () => ({ getKycStatus: () => getKycStatus() }))

import IntegratorApplicationModal from './IntegratorApplicationModal.vue'

async function mountModal(locale: 'en' | 'ru' = 'en') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div />' } }],
  })
  await router.push('/')
  const w = mount(IntegratorApplicationModal, {
    props: { open: true, sent: false, submitting: false },
    global: {
      plugins: [
        router,
        createI18n({ legacy: false, locale, messages: { en, ru }, missingWarn: false }),
      ],
      stubs: { LegalDocModal: true, Teleport: true },
    },
  })
  await flushPromises()
  return w
}

describe('IntegratorApplicationModal', () => {
  it('states the fee read from the server, for each attempt', async () => {
    getKycStatus.mockResolvedValue({ fee_cents: 1500 })
    const w = await mountModal('en')
    expect(w.text()).toContain('Identity verification costs $15.00 for each attempt.')
  })

  it('states it in Russian', async () => {
    getKycStatus.mockResolvedValue({ fee_cents: 1500 })
    const w = await mountModal('ru')
    expect(w.text()).toContain('Проверка личности стоит $15.00 за каждую попытку.')
  })

  it('leaves the line out when the fee cannot be read', async () => {
    getKycStatus.mockRejectedValue(new Error('down'))
    const w = await mountModal('en')
    expect(w.text()).not.toContain('Identity verification costs')
  })

  it('tells the pools, the bonus parts and the withdrawal account', async () => {
    getKycStatus.mockResolvedValue({ fee_cents: 1000 })
    const w = await mountModal('en')
    const text = w.text()
    expect(text).toContain('20 integrators')
    expect(text).toContain('2 percent')
    expect(text).toContain('10 with the largest share 1 percent')
    expect(text).toContain('bonus parts')
    expect(text).toContain('separate withdrawal account')
    expect(text).toContain('14 days after your request')
    expect(text).not.toContain('to your wallet')
  })

  it('draws the integrator icon in the title', async () => {
    getKycStatus.mockResolvedValue({ fee_cents: 1000 })
    const w = await mountModal('en')
    expect(w.find('.ds-dialog__title svg').exists()).toBe(true)
    expect(w.get('.ds-dialog__title').text()).toContain('Become an integrator')
  })

  it('keeps no money figure in the fee text itself', () => {
    expect(en.inv.settings.agent.modal.feeLine).toContain('{fee}')
    expect(ru.inv.settings.agent.modal.feeLine).toContain('{fee}')
  })
})
