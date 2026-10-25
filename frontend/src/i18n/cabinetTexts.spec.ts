// =============================================================================
// the cabinet's words: Projects, the plan names by months, Dashboard, Log out,
// the avatar sentence, and where the exits stand in Settings
// =============================================================================

import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { createI18n } from 'vue-i18n'

import en from './locales/en.json'
import ru from './locales/ru.json'
import { AGENT_TABS, COMPANY_TABS, INVESTOR_TABS, STAFF_TABS } from '@/router/tabs'
import * as icons from '@/components/ui/icons'
import { planMonthsLabel } from '@/utils/installmentPlans'

type Tree = { [key: string]: string | Tree }

function leaves(tree: Tree, prefix = ''): [string, string][] {
  return Object.entries(tree).flatMap(([key, value]) => {
    const path = prefix ? `${prefix}.${key}` : key
    return typeof value === 'string' ? [[path, value] as [string, string]] : leaves(value, path)
  })
}

const EN = leaves(en as unknown as Tree)
const RU = leaves(ru as unknown as Tree)

function i18n(locale: 'en' | 'ru') {
  return createI18n({ legacy: false, locale, messages: { en, ru }, missingWarn: false }).global
}

function plan(months: number, name = 'Stored English name') {
  return {
    name,
    plan_config: {
      tranches: Array.from({ length: months }, () => ({ amount_cents: 100, units_percent: 1 })),
    },
  }
}

describe('point 1 -- the tab is "Projects"', () => {
  it('names the tab, its screen and the back-links Projects / Проекты', () => {
    expect(en.tab.market).toBe('Projects')
    expect(ru.tab.market).toBe('Проекты')
    expect(en.inv.companyList.title).toBe(en.tab.market)
    expect(ru.inv.companyList.title).toBe(ru.tab.market)
    expect(en.inv.product.backToMarket).toBe('Back to Projects')
    expect(ru.inv.product.backToMarket).toBe('К проектам')
  })

  it('leaves no key that names the tab Store or Витрина', () => {
    const keys = ['tab.market', 'inv.market.title', 'inv.product.backToMarket', 'buy.toStorefront']
    for (const [k, v] of EN.filter(([k]) => keys.includes(k))) expect(v, k).not.toMatch(/store/i)
    for (const [k, v] of RU.filter(([k]) => keys.includes(k))) expect(v, k).not.toMatch(/витрин/i)
  })
})

describe('point 3 -- the instalment plan names come from the months', () => {
  const cases: Array<['en' | 'ru', number, string]> = [
    ['en', 6, '6 months'],
    ['en', 12, '12 months'],
    ['en', 24, '24 months'],
    ['ru', 6, '6 месяцев'],
    ['ru', 12, '12 месяцев'],
    ['ru', 24, '24 месяца'],
  ]
  it.each(cases)('%s: %i months reads "%s", not the stored name', (locale, months, text) => {
    const g = i18n(locale)
    expect(planMonthsLabel(plan(months), g.t as never, locale)).toBe(text)
  })

  it('keeps the stored name for a plan whose config cannot be read', () => {
    const g = i18n('en')
    expect(planMonthsLabel({ name: 'Odd', plan_config: {} }, g.t as never, 'en')).toBe('Odd')
  })
})

describe('point 4 -- the home tab is Dashboard / Главная with the gauge', () => {
  it('says Dashboard in English and Главная in Russian in every cabinet', () => {
    for (const [e, r] of [
      [en.tab.home, ru.tab.home],
      [en.tab.comp.home, ru.tab.comp.home],
      [en.tab.staff.home, ru.tab.staff.home],
    ]) {
      expect(e).toBe('Dashboard')
      expect(r).toBe('Главная')
    }
  })

  it('titles the dashboard pages as the tab, with no greeting', () => {
    expect(en.inv.dashboard.title).toBe(en.tab.home)
    expect(ru.inv.dashboard.title).toBe(ru.tab.home)
    expect(en.comp.dashboard.title).toBe(en.tab.comp.home)
    expect(ru.comp.dashboard.title).toBe(ru.tab.comp.home)
    const view = readFileSync('src/views/staff/StaffDashboardView.vue', 'utf8')
    expect(view).toContain("title: () => t('tab.staff.home')")
    for (const [k, v] of [...EN, ...RU].filter(([k]) => /dashboard\.title$/.test(k)))
      expect(v, k).not.toMatch(/welcome|hello|добро пожаловать|привет|здравствуйте/i)
  })

  it('draws the home tab with the design system gauge, not the house', () => {
    for (const tabs of [INVESTOR_TABS, AGENT_TABS, COMPANY_TABS, STAFF_TABS]) {
      const home = tabs.find((t) => t.id === 'home')
      expect(home?.icon).toBe('Gauge')
    }
    expect(icons.Gauge).toBeTruthy()
    const sprite = readFileSync('src/assets/icons/ds-icons.svg', 'utf8')
    expect(sprite).toContain('id="i-gauge"')
  })
})

describe('point 5 -- Log out everywhere in English', () => {
  it('has no "Sign out" in the English texts, and keeps Выйти in Russian', () => {
    expect(EN.filter(([, v]) => /sign(ed)?[ -]out/i.test(v)).map(([k]) => k)).toEqual([])
    expect(en.auth.logout).toBe('Log out')
    expect(en.inv.settings.actions.logoutAll).toBe('Log out of all devices')
    expect(en.inv.settings.actions.logout).toBe('Log out')
    expect(en.comp.settings.actions.logout).toBe('Log out')
    expect(ru.auth.logout).toBe('Выйти')
    expect(ru.inv.settings.actions.logout).toBe('Выйти')
  })
})

describe('point 6 -- the staff avatar screen says only what is true', () => {
  it('has one plain sentence and no list of restricted operations', () => {
    expect(en.staff.avatar.note).toMatch(/act as the user/)
    expect(en.staff.avatar.note).toMatch(/audit/)
    expect(ru.staff.avatar.note).toMatch(/аудит/)
    for (const k of [
      'restrictions',
      'noPurchase',
      'noWithdraw',
      'noPassword',
      'noDelete',
      'noKyc',
    ]) {
      expect(en.staff.avatar).not.toHaveProperty(k)
      expect(ru.staff.avatar).not.toHaveProperty(k)
    }
    const view = readFileSync('src/views/staff/StaffAvatarView.vue', 'utf8')
    expect(view).toContain("t('staff.avatar.note')")
    expect(view).not.toContain('restrictions')
  })
})

describe('point 2 -- the exits are a last card apart', () => {
  it('stands the company and staff exits in a card of their own', () => {
    const company = readFileSync('src/views/company/CompanySettingsView.vue', 'utf8')
    const actions = company.indexOf('aria-labelledby="cset-actions"')
    const leave = company.indexOf('aria-labelledby="cset-leave"')
    expect(leave).toBeGreaterThan(actions)
    expect(company.indexOf('<DeactivateAccountSection')).toBeGreaterThan(leave)
    expect(company.indexOf("t('comp.settings.actions.logout')")).toBeGreaterThan(leave)
    const staff = readFileSync('src/views/staff/StaffSettingsView.vue', 'utf8')
    const staffLeave = staff.indexOf('aria-labelledby="staff-settings-leave"')
    expect(staffLeave).toBeGreaterThan(staff.indexOf("t('staff.settings.about')"))
    expect(staff.indexOf("t('staff.settings.logout')")).toBeGreaterThan(staffLeave)
  })
})
