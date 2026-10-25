// =============================================================================
// PendingGifts -- a gift waiting for acceptance is named in parts
// =============================================================================
//
// A gift counts lots; the line says the parts (lots x the project's parts per lot).
// =============================================================================

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import ru from '@/i18n/locales/ru.json'

vi.mock('@/api/purchases', () => ({
  acceptGift: vi.fn(),
  listPendingGifts: async () => ({
    total: 1,
    items: [{ id: 'g1', company_id: 'c1', units: 4, created_at: '2026-10-23T10:00:00Z' }],
  }),
}))
vi.mock('@/api/companies', () => ({ getCompany: async () => ({ shares_per_option: 25 }) }))

import PendingGifts from './PendingGifts.vue'
import { resetSharesPerOptionCache } from '@/composables/useSharesPerOption'

beforeEach(() => resetSharesPerOptionCache())

async function gifts(locale: 'en' | 'ru') {
  const w = mount(PendingGifts, {
    global: {
      plugins: [createI18n({ legacy: false, locale, messages: { en, ru }, missingWarn: false })],
      stubs: { AgreementSheet: true },
    },
  })
  await flushPromises()
  return w
}

describe('PendingGifts', () => {
  it('names the gift in parts, not lots', async () => {
    const w = await gifts('en')
    expect(w.find('.ds-row__title').text()).toBe('100 parts as a gift')
  })

  it('names it in Russian', async () => {
    const w = await gifts('ru')
    expect(w.find('.ds-row__title').text()).toBe('Частей в подарок: 100')
  })
})
