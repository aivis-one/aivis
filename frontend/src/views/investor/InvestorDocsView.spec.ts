// =============================================================================
// InvestorDocsView -- the documents to sign stand first, the read-only ones below
// =============================================================================

import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter } from 'vue-router'
import en from '@/i18n/locales/en.json'
import ru from '@/i18n/locales/ru.json'

const doc = (id: string, type: string, signed = false) => ({
  id,
  type,
  title: `Title of ${type}`,
  language: 'en',
  is_signed: signed,
})

vi.mock('@/api/documents', () => ({
  listDocuments: async () => [doc('1', 'cabinet_terms', true), doc('2', 'privacy_policy')],
  getDocumentByType: async (type: string) => doc(`x-${type}`, type),
  signDocument: vi.fn(),
}))

import InvestorDocsView from './InvestorDocsView.vue'

async function mountDocs(locale: 'en' | 'ru') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div />' } }],
  })
  await router.push('/investor/docs')
  await router.isReady()
  const w = mount(InvestorDocsView, {
    global: {
      plugins: [
        router,
        createPinia(),
        createI18n({ legacy: false, locale, messages: { en, ru }, missingWarn: false }),
      ],
    },
  })
  await flushPromises()
  return w
}

describe('InvestorDocsView groups', () => {
  it('lists the documents to sign first and the read-only ones below', async () => {
    const w = await mountDocs('en')
    const groups = w.findAll('section.docs__group')
    expect(groups).toHaveLength(2)
    expect(groups[0]!.get('h2').text()).toBe('To sign')
    expect(groups[1]!.get('h2').text()).toBe('To read')
    const titles = (i: number) => groups[i]!.findAll('.ds-row__title').map((t) => t.text())
    expect(titles(0)).toEqual([
      'Title of cabinet_terms',
      'Title of privacy_policy',
      'Title of kyc_notice',
    ])
    // accepted at each purchase, or bound into the agreement, or only to read
    expect(titles(1)).toEqual([
      'Title of buyer_agreement',
      'Title of pre_purchase_disclosure',
      'Title of index_rules',
    ])
  })

  it('names the groups in Russian', async () => {
    const w = await mountDocs('ru')
    expect(w.findAll('section.docs__group h2').map((h) => h.text())).toEqual([
      'Для подписания',
      'Для ознакомления',
    ])
  })
})
