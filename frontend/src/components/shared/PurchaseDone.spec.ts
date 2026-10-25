// =============================================================================
// PurchaseDone -- the done screen (step 3)
// =============================================================================
//
// The step line, a success Alert whose title is the congratulation ("Congratulations
// — you are now a co-owner of {project}." / "A visionary for visionaries."), the
// documents the purchase issued as rows, and "To my portfolio".
// =============================================================================

import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import ru from '@/i18n/locales/ru.json'
import PurchaseDone from './PurchaseDone.vue'

function done(locale: 'en' | 'ru') {
  return mount(PurchaseDone, {
    props: {
      projectName: 'SANKORD',
      companyId: 'c1',
      documents: [{ kind: 'agreement', id: 'p1', legalBasis: 'sale' }, { kind: 'ownership' }],
    },
    slots: { default: '<p class="summary">summary</p>' },
    global: {
      plugins: [createI18n({ legacy: false, locale, messages: { en, ru }, missingWarn: false })],
      stubs: { AgreementSheet: true },
    },
  })
}

describe('PurchaseDone', () => {
  it('congratulates the new co-owner by name, in English with the em dash', () => {
    const w = done('en')
    const alert = w.find('.ds-alert--success')
    expect(alert.find('.ds-alert__title').text()).toBe(
      'Congratulations — you are now a co-owner of SANKORD.',
    )
    expect(alert.find('.ds-alert__text').text()).toBe('A visionary for visionaries.')
  })

  it('congratulates in Russian', () => {
    const w = done('ru')
    const alert = w.find('.ds-alert--success')
    expect(alert.find('.ds-alert__title').text()).toBe(
      'Поздравляем — теперь вы совладелец SANKORD.',
    )
    expect(alert.find('.ds-alert__text').text()).toBe('Визионер для визионеров.')
  })

  it('shows the third step, the summary slot, the documents and the one action', () => {
    const w = done('en')
    expect(w.find('.ds-dots__text').text()).toBe('Step 3 of 3 · Done')
    expect(w.find('.summary').exists()).toBe(true)
    const rows = w.findAll('.ds-rows .ds-row__title').map((r) => r.text())
    expect(rows).toEqual(['Purchase agreement', 'Ownership certificate'])
    expect(w.find('button.ds-button--primary').text()).toBe('To my portfolio')
  })

  it('emits portfolio from the action', async () => {
    const w = done('en')
    await w.find('button.ds-button--primary').trigger('click')
    expect(w.emitted('portfolio')).toHaveLength(1)
  })
})
