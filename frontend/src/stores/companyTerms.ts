// =============================================================================
// AIVIS.ONE Frontend -- the project account's documents state (Pinia)
// =============================================================================
//
// Where the signed-in project account stands with the documents its role signs
// at the first sign-in (the Cabinet Terms and the Privacy Policy, and any other
// document the platform marks as required for the project role). The router
// guard reads it before every project screen: until each is accepted the only
// screen open is the acceptance screen.
//
//   unknown   -- not read yet
//   signed    -- every required document is accepted (cached for the session)
//   unsigned  -- at least one required document is not accepted yet
//   error     -- the state could not be read (network, server)
//
// An acceptance counts whatever its language: an unsigned row is checked on
// the other shipped language before the document is reported as unsigned.
// =============================================================================

import { ref } from 'vue'
import { defineStore } from 'pinia'

import { ApiResponseError } from '@/api/client'
import { getDocumentByType, listDocuments } from '@/api/documents'
import type { DocumentResponse } from '@/api/types'

export type CompanyTermsStatus = 'unknown' | 'signed' | 'unsigned' | 'error'

async function signedInAnyLanguage(doc: DocumentResponse): Promise<boolean> {
  if (doc.is_signed) return true
  const other = doc.language === 'ru' ? 'en' : 'ru'
  try {
    return !!(await getDocumentByType(doc.type, other)).is_signed
  } catch (err) {
    if (err instanceof ApiResponseError && err.status === 404) return false
    throw err
  }
}

export const useCompanyTermsStore = defineStore('companyTerms', () => {
  const status = ref<CompanyTermsStatus>('unknown')
  const pending = ref<DocumentResponse[]>([])
  let epoch = 0

  /** Reads the state from the server unless it is already known to be signed. */
  async function ensure(): Promise<CompanyTermsStatus> {
    if (status.value === 'signed') return status.value
    const mine = ++epoch
    let next: CompanyTermsStatus
    let open: DocumentResponse[] = []
    try {
      const required = await listDocuments()
      const flags = await Promise.all(required.map((d) => signedInAnyLanguage(d)))
      open = required.filter((_, i) => !flags[i])
      next = open.length === 0 ? 'signed' : 'unsigned'
    } catch {
      next = 'error'
    }
    if (mine === epoch) {
      status.value = next
      pending.value = open
    }
    return status.value
  }

  function markSigned(): void {
    epoch++
    status.value = 'signed'
    pending.value = []
  }

  function reset(): void {
    epoch++
    status.value = 'unknown'
    pending.value = []
  }

  return { status, pending, ensure, markSigned, reset }
})
