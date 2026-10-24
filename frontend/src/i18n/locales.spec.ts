// =============================================================================
// the locale files -- ENGLISH AND RUSSIAN SAY THE SAME THINGS, IN THE RIGHT WORDS
// =============================================================================
//
// The cabinet offers English and Russian only; every key exists in both. In the
// staff texts and in the public project overview a part is a "part" -- never an
// option, equity, profit, dividend or revenue -- and a project is a "project".
// And the money check names its checks by codes with a hyphen (S-01, IS-07):
// the message path must resolve them.
// =============================================================================

import { describe, expect, it } from 'vitest'
import { createI18n } from 'vue-i18n'

import en from './locales/en.json'
import ru from './locales/ru.json'

type Tree = { [key: string]: string | Tree }

function leaves(tree: Tree, prefix = ''): [string, string][] {
  const out: [string, string][] = []
  for (const [key, value] of Object.entries(tree)) {
    const path = prefix ? `${prefix}.${key}` : key
    if (typeof value === 'string') out.push([path, value])
    else out.push(...leaves(value, path))
  }
  return out
}

const EN = leaves(en as unknown as Tree)
const RU = leaves(ru as unknown as Tree)

describe('the locale files', () => {
  it('have the same keys in English and Russian', () => {
    const enKeys = new Set(EN.map(([k]) => k))
    const ruKeys = new Set(RU.map(([k]) => k))
    expect([...enKeys].filter((k) => !ruKeys.has(k))).toEqual([])
    expect([...ruKeys].filter((k) => !enKeys.has(k))).toEqual([])
  })

  it('have no empty text', () => {
    expect(EN.filter(([, v]) => v.trim() === '').map(([k]) => k)).toEqual([])
    expect(RU.filter(([, v]) => v.trim() === '').map(([k]) => k)).toEqual([])
  })
})

describe('the words of the staff and public texts', () => {
  // The words a part must never be called. \boption(s)\b does not match
  // "optional"; a project's own name or a ruling's number is not in these keys.
  const FORBIDDEN_EN = /\boptions?\b|\bequity\b|\bdividends?\b|\bprofit\b|\brevenue\b|\bshares?\b/i
  const FORBIDDEN_RU = /опцион(?!ально)|акци[яий]|дивиденд|прибыл|выручк/i

  const inScope = ([key]: [string, string]) =>
    key.startsWith('staff.') || key.startsWith('public.companyOverview.stats.')

  it('never call a part an option, equity, a share, profit, a dividend or revenue (English)', () => {
    expect(
      EN.filter(inScope)
        .filter(([, v]) => FORBIDDEN_EN.test(v))
        .map(([k, v]) => `${k}: ${v}`),
    ).toEqual([])
  })

  it('never call a part by those words (Russian)', () => {
    expect(
      RU.filter(inScope)
        .filter(([, v]) => FORBIDDEN_RU.test(v))
        .map(([k, v]) => `${k}: ${v}`),
    ).toEqual([])
  })

  it('call a project a project in the staff texts', () => {
    const staffEn = EN.filter(([k]) => k.startsWith('staff.'))
    // "the company" survives only for the legal entity that gives a gift.
    const offenders = staffEn.filter(
      ([k, v]) =>
        /\bcompan(y|ies)\b/i.test(v) &&
        !k.startsWith('staff.gifts.') &&
        !k.endsWith('distribution.rows.reserve'),
    )
    expect(offenders.map(([k, v]) => `${k}: ${v}`)).toEqual([])
  })
})

describe('the money check names', () => {
  it('resolve through the message path although they carry a hyphen', () => {
    // The catalogue is loaded after the instance is made: typing the whole file
    // into createI18n's generics is too deep for the compiler to instantiate.
    const i18n = createI18n({ legacy: false, locale: 'en', missingWarn: false })
    i18n.global.setLocaleMessage('en', en as never)
    const t = (key: string): string => i18n.global.t(key)
    for (const code of ['S-01', 'S-13', 'IS-01', 'IS-07']) {
      expect(t(`staff.reconciliation.checks.${code}`)).not.toBe(
        `staff.reconciliation.checks.${code}`,
      )
    }
  })
})

describe('the basis line of a purchase card', () => {
  it('names the document and the Parts only, in the decided English words', () => {
    const b = (en as unknown as { inv: { companyPosition: { purchases: { basis: Record<string, string> } } } })
      .inv.companyPosition.purchases.basis
    expect(b.sale).toBe('Basis: Parts bought under the Buyer Agreement you accepted in the Cabinet.')
    expect(b.installment_tranche).toBe('Basis: one paid month of your instalment plan, its own purchase agreement accepted in the Cabinet.')
    expect(b.gift).toBe('Basis: Parts given by AIVIS.ONE LLC under its order on gifts, accepted by you in the Cabinet.')
  })
})
