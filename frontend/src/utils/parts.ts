// =============================================================================
// AIVIS.ONE Frontend -- Parts, the part's price and the buying path's lines
// =============================================================================
//
// The buyer sees PARTS, never the cabinet's lots: a lot (a product's `package_size`
// counts them, a purchase's `units` counts them) holds `shares_per_option` parts,
// so the count of parts is lots x parts-per-lot, and the price of one part is the
// lot's price over the same number (10 cents over 25 parts is 0.004 USD). Money
// stays in whole cents on the wire; a total is lots x the lot's cents and always
// closes in whole cents.
//
// The bonus a product brings when it is paid at once is not on the storefront
// answer (the public product hides its purchase configuration). A signed-in buyer
// gets it from the purchase preview; a visitor reads the leading "+N %" of the
// product's description first line, where the project writes it.
// =============================================================================

import { formatNumber } from '@/utils/format'
import type { PlanConfig } from '@/utils/installmentPlans'

/** The count of parts in `lots` lots of `sharesPerOption` parts each. */
export function partsOf(lots: number, sharesPerOption: number): number {
  return lots * sharesPerOption
}

/**
 * The valuation of a project in cents: every lot of the project (the pool) at the
 * lot's price, which is the price of a part times all the parts. Whole cents, no
 * rounding.
 */
export function valuationCents(poolLots: number, lotPriceCents: number): number {
  return poolLots * lotPriceCents
}

/** USD for a figure in cents: whole dollars without cents, else with two decimals. */
export function formatUsd(cents: number, locale: string): string {
  const whole = cents % 100 === 0
  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: whole ? 0 : 2,
    maximumFractionDigits: 2,
  }).format(cents / 100)
}

/** USD for a figure in cents, always dollars and cents (a total). */
export function formatUsdCents(cents: number, locale: string): string {
  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(cents / 100)
}

/** The price of one part, three decimals: a lot at 10 cents over 25 parts is 0.004 USD. */
export function formatPartPrice(
  lotPriceCents: number,
  sharesPerOption: number,
  locale: string,
): string {
  const perPart = sharesPerOption > 0 ? lotPriceCents / sharesPerOption / 100 : 0
  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 3,
    maximumFractionDigits: 3,
  }).format(perPart)
}

/** The first non-empty line of a text. */
export function firstLine(text: string | null | undefined): string {
  if (!text) return ''
  const line = text.split(/\r?\n/).find((l) => l.trim() !== '')
  return line ? line.trim() : ''
}

/**
 * The bonus percent a project writes at the head of a description's first line
 * ("+5% bonus parts when paid at once ..."); 0 when the line carries none.
 */
export function bonusPercentFromText(description: string | null | undefined): number {
  const m = /^\s*\+\s*(\d+(?:[.,]\d+)?)\s*%/.exec(firstLine(description))
  if (!m) return 0
  const n = Number(m[1].replace(',', '.'))
  return Number.isFinite(n) ? n : 0
}

/** The instalment's money and parts, read from the plan's tranches. */
export interface InstalmentLines {
  /** How many payments in all. */
  count: number
  /** Payments before the last, when they are all equal (cents); else null. */
  eachCents: number | null
  /** The last payment (cents). */
  lastCents: number
  /** The share of the parts each payment before the last unlocks, when equal; else null. */
  eachPercent: number | null
  /** The share of the parts the last payment unlocks. */
  lastPercent: number
}

export function instalmentLines(config: PlanConfig): InstalmentLines {
  const list = config.tranches
  const head = list.slice(0, -1)
  const last = list[list.length - 1]
  const eachCents =
    head.length > 0 && head.every((x) => x.amount_cents === head[0].amount_cents)
      ? head[0].amount_cents
      : null
  const eachPercent =
    head.length > 0 && head.every((x) => x.units_percent === head[0].units_percent)
      ? head[0].units_percent
      : null
  return {
    count: list.length,
    eachCents,
    lastCents: last.amount_cents,
    eachPercent,
    lastPercent: last.units_percent,
  }
}

/**
 * The average price of one part over the lots paid for: the money paid over the
 * parts it bought (gifts carry no money and are not in `paidLots`). Three
 * decimals, like the price of a part; 0.000 when nothing was bought.
 */
export function formatAveragePartPrice(
  totalPaidCents: number,
  paidLots: number,
  sharesPerOption: number,
  locale: string,
): string {
  return formatPartPrice(totalPaidCents, partsOf(paidLots, sharesPerOption), locale)
}

/**
 * The count of parts in `lots` lots, grouped for the locale; a dash while the
 * project's parts per lot is not known yet (never the lot count in its place).
 */
export function formatPartsCount(
  lots: number,
  sharesPerOption: number | null,
  locale: string,
): string {
  if (sharesPerOption === null) return '—'
  return formatNumber(partsOf(lots, sharesPerOption), locale)
}
