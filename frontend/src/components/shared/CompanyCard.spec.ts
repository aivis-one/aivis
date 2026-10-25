// =============================================================================
// CompanyCard -- one card per project, one call to action (K07)
// =============================================================================
//
// The storefront card's single link is the call to action "View the project": a
// block primary Button in the foot of the content (`.ds-card__action`), the
// hit area stretching over the card. The card holds no other link, and the
// description is cut by the system's clamp.
// =============================================================================

import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import ru from '@/i18n/locales/ru.json'
import CompanyCard from './CompanyCard.vue'

const company = {
  id: 'c1',
  name: 'SANKORD',
  description: 'A long description of the project.',
  cover_url: null,
} as never

function card(locale: 'en' | 'ru' = 'en') {
  return mount(CompanyCard, {
    props: { company, to: { name: 'investor-company-overview', params: { id: 'c1' } } },
    global: {
      plugins: [createI18n({ legacy: false, locale, messages: { en, ru }, missingWarn: false })],
      stubs: { RouterLink: { template: '<a><slot /></a>' } },
    },
  })
}

describe('CompanyCard', () => {
  it('has the call to action as its one link, a block primary Button at the foot', () => {
    const w = card()
    const links = w.findAll('a, button')
    expect(links).toHaveLength(1)
    const action = w.find('.ds-card__action > a')
    expect(action.classes()).toEqual(
      expect.arrayContaining([
        'ds-button',
        'ds-button--primary',
        'ds-button--block',
        'ds-card__link',
      ]),
    )
  })

  it('says "View the project" / "Смотреть проект"', () => {
    expect(card('en').find('.ds-card__action').text()).toContain('View the project')
    expect(card('ru').find('.ds-card__action').text()).toContain('Смотреть проект')
  })

  it('cuts the description with the system clamp and keeps the title a plain heading', () => {
    const w = card()
    expect(w.find('p.ds-card__body').classes()).toContain('ds-clamp')
    expect(w.find('.ds-card__title a').exists()).toBe(false)
    expect(w.find('.ds-card__title').text()).toBe('SANKORD')
  })

  it('draws no style of its own', () => {
    const w = card()
    expect(w.html()).not.toContain('style=')
  })
})
