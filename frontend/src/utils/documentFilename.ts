// =============================================================================
// AIVIS.ONE Frontend -- Saved document file name (P-106)
// =============================================================================
//
// AgreementSheet's "Save" hands the reader the very blob shown in its iframe:
// the backend's HTML render, nothing regenerated (owner's decision: no PDF in
// any form). This module only names that file.
//
// THE NAME CARRIES THE DOCUMENT, NEVER THE PERSON. Type, company, and the
// document's own reference -- the agreement number for an agreement, the
// date of the copy for a certificate -- and nothing about the investor.
//
//   agreement : <type>-<company>-<agreement number>.html
//               <type> follows Purchase.legal_basis; the number is the
//               backend's _short_id (agreement_service.py): first UUID group,
//               uppercased -- the same number the email title carries.
//   ownership : ownership-certificate-<company>-<YYYY-MM-DD>.html
//               a certificate is a live aggregate with no number, so the
//               date of the copy tells two saved copies apart.
//
// A company name that is not known yet, or reduces to nothing once unsafe
// characters are dropped, leaves its segment out instead of leaving a gap.
// =============================================================================

const TYPE_BY_LEGAL_BASIS: Record<string, string> = {
  sale: 'purchase-agreement',
  gift: 'gift-certificate',
  installment_tranche: 'installment-subcontract',
}

/** Longest company segment kept, so a long legal name cannot dominate the name. */
const COMPANY_SEGMENT_MAX = 60

/**
 * Reduce a free-text value to a file-name segment: letters and digits of any
 * script survive, every other run of characters (separators, path and
 * reserved characters, controls, spaces) becomes one '-', and dashes are
 * trimmed from both ends.
 */
function segment(value: string | null | undefined, max = COMPANY_SEGMENT_MAX): string {
  if (!value) return ''
  return value
    .replace(/[^\p{L}\p{N}]+/gu, '-')
    .slice(0, max)
    .replace(/^-+|-+$/g, '')
}

function isoDate(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

export type DocumentFilenameInput =
  | {
      mode: 'agreement'
      purchaseId: string
      legalBasis?: string | null
      companyName?: string | null
    }
  | {
      mode: 'ownership'
      companyName?: string | null
      now?: Date
    }

/** File name for a saved document. Always ends in `.html`, never empty. */
export function documentFilename(input: DocumentFilenameInput): string {
  const company = segment(input.companyName)
  let parts: string[]
  if (input.mode === 'agreement') {
    const type = TYPE_BY_LEGAL_BASIS[input.legalBasis ?? ''] ?? 'document'
    const number = segment(input.purchaseId.split('-')[0]).toUpperCase()
    parts = [type, company, number]
  } else {
    parts = ['ownership-certificate', company, isoDate(input.now ?? new Date())]
  }
  return `${parts.filter((p) => p !== '').join('-')}.html`
}
