// =============================================================================
// utils/parts -- what the buyer is shown: parts, the part's price, the total
// =============================================================================
//
// The buyer sees parts, never the cabinet's lot. A lot of 25 parts at 10 cents is
// 0.004 USD a part; a 1,000 USD portfolio is 10,000 lots, 250,000 parts, and the
// total closes in whole cents. The bonus rides in the description's first line
// because the storefront hides the purchase configuration.
// =============================================================================

import { describe, expect, it } from 'vitest'
import {
  bonusPercentFromText,
  firstLine,
  formatPartPrice,
  formatUsd,
  formatUsdCents,
  instalmentLines,
  partsOf,
} from '@/utils/parts'
import { parsePlanConfig } from '@/utils/installmentPlans'

describe('parts and their price', () => {
  it('counts parts as lots times the parts in a lot', () => {
    expect(partsOf(10_000, 25)).toBe(250_000)
    expect(partsOf(4_000_000, 25)).toBe(100_000_000)
  })

  it('prints the price of a part to three decimals, in both languages', () => {
    expect(formatPartPrice(10, 25, 'en')).toBe('$0.004')
    expect(formatPartPrice(10, 25, 'ru')).toContain('0,004')
  })

  it('closes a portfolio in whole cents: parts x part price = lots x lot price', () => {
    const lots = 10_000
    const lotCents = 10
    expect(partsOf(lots, 25) * (lotCents / 25)).toBeCloseTo(lots * lotCents, 9)
    expect(formatUsdCents(lots * lotCents, 'en')).toBe('$1,000.00')
  })

  it('writes whole dollars without cents and a total always with them', () => {
    expect(formatUsd(16_600, 'en')).toBe('$166')
    expect(formatUsd(16_650, 'en')).toBe('$166.50')
    expect(formatUsdCents(16_600, 'en')).toBe('$166.00')
  })
})

describe('the bonus in the description', () => {
  it('reads the leading +N % of the first line', () => {
    expect(bonusPercentFromText('+5% bonus parts when paid at once.\nThe agreement.')).toBe(5)
    expect(bonusPercentFromText('+20 % бонусными частями при оплате сразу.')).toBe(20)
    expect(bonusPercentFromText('\n  +10% bonus')).toBe(10)
  })

  it('is zero when the first line carries none', () => {
    expect(bonusPercentFromText('Paid at once or on instalment.')).toBe(0)
    expect(bonusPercentFromText('A text.\n+5% bonus')).toBe(0)
    expect(bonusPercentFromText(null)).toBe(0)
    expect(firstLine('\n\n  a\nb')).toBe('a')
  })
})

describe('the instalment lines', () => {
  const plan = (tr: Array<[number, number]>) =>
    parsePlanConfig({
      tranches: tr.map(([amount_cents, units_percent]) => ({ amount_cents, units_percent })),
    })!

  it('reads five equal payments and a larger last one (166 and 170 dollars)', () => {
    const l = instalmentLines(
      plan([
        [16_600, 10],
        [16_600, 10],
        [16_600, 10],
        [16_600, 10],
        [16_600, 10],
        [17_000, 50],
      ]),
    )
    expect(l).toEqual({
      count: 6,
      eachCents: 16_600,
      lastCents: 17_000,
      eachPercent: 10,
      lastPercent: 50,
    })
  })

  it('gives no "each" when the payments before the last differ', () => {
    const l = instalmentLines(
      plan([
        [10_000, 10],
        [12_000, 20],
        [18_000, 70],
      ]),
    )
    expect(l.eachCents).toBeNull()
    expect(l.eachPercent).toBeNull()
  })
})
