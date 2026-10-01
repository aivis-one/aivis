// =============================================================================
// documentFilename -- THE SAVED FILE'S NAME (H27 P-106)
// =============================================================================
//
// WHAT THIS GUARDS. AgreementSheet's "Save" names the file it hands over. The
// name carries the document -- type, company, the document's own reference --
// and never the person. Every "has no X" assertion below is paired with "has
// Y and Y is non-empty": a name with no slash that is also just ".html" would
// pass the first half alone.
// =============================================================================

import { describe, it, expect } from 'vitest'

import { documentFilename } from './documentFilename'

const PURCHASE = '1a2b3c4d-0000-4000-8000-000000000001'
const DAY = new Date(2026, 9, 1, 12, 0, 0)

describe('documentFilename -- agreement', () => {
  it('names type, company and the agreement number', () => {
    expect(
      documentFilename({
        mode: 'agreement',
        purchaseId: PURCHASE,
        legalBasis: 'sale',
        companyName: 'Acme Robotics',
      }),
    ).toBe('purchase-agreement-Acme-Robotics-1A2B3C4D.html')
  })

  it('follows the legal basis, and an unknown or absent one reads as a document', () => {
    const base = { mode: 'agreement' as const, purchaseId: PURCHASE, companyName: 'Acme' }
    expect(documentFilename({ ...base, legalBasis: 'gift' })).toBe(
      'gift-certificate-Acme-1A2B3C4D.html',
    )
    expect(documentFilename({ ...base, legalBasis: 'installment_tranche' })).toBe(
      'installment-subcontract-Acme-1A2B3C4D.html',
    )
    expect(documentFilename({ ...base, legalBasis: 'barter' })).toBe('document-Acme-1A2B3C4D.html')
    expect(documentFilename({ ...base, legalBasis: null })).toBe('document-Acme-1A2B3C4D.html')
  })
})

describe('documentFilename -- ownership', () => {
  it('names the certificate, the company and the date of the copy', () => {
    expect(documentFilename({ mode: 'ownership', companyName: 'Acme', now: DAY })).toBe(
      'ownership-certificate-Acme-2026-10-01.html',
    )
  })
})

describe('documentFilename -- the company segment', () => {
  it('keeps letters of any script and folds everything else to one dash', () => {
    expect(
      documentFilename({ mode: 'ownership', companyName: 'ООО «Ромашка» / R&D', now: DAY }),
    ).toBe('ownership-certificate-ООО-Ромашка-R-D-2026-10-01.html')
  })

  it('never lets a path or reserved character through, and the name stays non-empty', () => {
    const name = documentFilename({
      mode: 'agreement',
      purchaseId: PURCHASE,
      legalBasis: 'sale',
      companyName: '../..\\evil:*?"<>|\u0000name',
    })
    expect(name).not.toMatch(/[/\\:*?"<>|\u0000]/)
    expect(name).toBe('purchase-agreement-evil-name-1A2B3C4D.html')
  })

  // EMPTINESS / SHORTAGE: the position detail has not loaded, or the name
  // reduces to nothing -- the segment goes, no doubled dash is left behind.
  it('drops an absent, empty or all-symbol company name without leaving a gap', () => {
    for (const companyName of [undefined, null, '', '   ', '«»/\\']) {
      const name = documentFilename({ mode: 'ownership', companyName, now: DAY })
      expect(name).toBe('ownership-certificate-2026-10-01.html')
      expect(name).not.toContain('--')
    }
  })

  it('caps a long company name', () => {
    const name = documentFilename({ mode: 'ownership', companyName: 'A'.repeat(300), now: DAY })
    expect(name).toBe(`ownership-certificate-${'A'.repeat(60)}-2026-10-01.html`)
  })

  // REPETITION: the same document saved twice gets the same name.
  it('names one document the same way every time', () => {
    const input = { mode: 'agreement' as const, purchaseId: PURCHASE, companyName: 'Acme' }
    expect(documentFilename(input)).toBe(documentFilename(input))
  })
})
