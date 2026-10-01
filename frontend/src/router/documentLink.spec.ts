// =============================================================================
// documentLink -- THE EMAIL LINK CONTRACT (H27 P-106)
// =============================================================================
//
// WHAT THIS GUARDS. A document email links to /portfolio/<company>?doc=...,
// built by backend document_utils.py::documents_link without knowing the
// reader's role. Two pure functions carry the whole frontend half:
//
//   documentLinkTarget -- which shell's position screen the reader lands on;
//   parseDocumentQuery -- which document that screen opens.
//
// The three axes are asserted on the query, the only input a reader can bend
// by hand: a REPEATED key, an EMPTY value, a MISSING companion.
// =============================================================================

import { describe, it, expect } from 'vitest'
import type { LocationQuery } from 'vue-router'

import { documentLinkTarget, parseDocumentQuery } from './documentLink'

const COMPANY = '11111111-2222-4333-8444-555555555555'
const PURCHASE = '1a2b3c4d-0000-4000-8000-000000000001'

describe('documentLinkTarget', () => {
  const query: LocationQuery = { doc: 'agreement', purchase: PURCHASE }

  it('sends an investor to the investor position screen, query intact', () => {
    expect(documentLinkTarget('investor', COMPANY, query)).toEqual({
      path: `/investor/portfolio/${COMPANY}`,
      query,
    })
  })

  it('sends an agent to the agent position screen, query intact', () => {
    expect(documentLinkTarget('agent', COMPANY, query)).toEqual({
      path: `/agent/portfolio/${COMPANY}`,
      query,
    })
  })

  it('sends a role with no portfolio to its own dashboard', () => {
    expect(documentLinkTarget('company', COMPANY, query)).toBe('/company/dashboard')
    expect(documentLinkTarget('staff', COMPANY, query)).toBe('/staff/dashboard')
  })
})

describe('parseDocumentQuery', () => {
  it('names the certificate', () => {
    expect(parseDocumentQuery({ doc: 'ownership' })).toEqual({ kind: 'ownership' })
  })

  it('names the agreement of one purchase', () => {
    expect(parseDocumentQuery({ doc: 'agreement', purchase: PURCHASE })).toEqual({
      kind: 'agreement',
      purchaseId: PURCHASE,
    })
  })

  it('names nothing when the query names nothing', () => {
    expect(parseDocumentQuery({})).toBeNull()
    expect(parseDocumentQuery({ doc: 'invoice' })).toBeNull()
  })

  // REPETITION: vue-router hands a repeated key over as an array.
  it('refuses a repeated key instead of picking one', () => {
    expect(parseDocumentQuery({ doc: ['ownership', 'agreement'] })).toBeNull()
    expect(parseDocumentQuery({ doc: 'agreement', purchase: [PURCHASE, PURCHASE] })).toBeNull()
  })

  // EMPTINESS: a key present with no value.
  it('refuses an empty value', () => {
    expect(parseDocumentQuery({ doc: '' })).toBeNull()
    expect(parseDocumentQuery({ doc: 'agreement', purchase: '' })).toBeNull()
  })

  // SHORTAGE: one half of the agreement pair without the other.
  it('refuses an agreement without its purchase, and a purchase without doc', () => {
    expect(parseDocumentQuery({ doc: 'agreement' })).toBeNull()
    expect(parseDocumentQuery({ purchase: PURCHASE })).toBeNull()
  })
})
