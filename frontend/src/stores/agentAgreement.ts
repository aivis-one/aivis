// =============================================================================
// AIVIS.ONE Frontend -- Agent-integrator agreement state (Pinia)
// =============================================================================
//
// Where the signed-in integrator stands with the agent-integrator agreement.
// The router guard reads it before every integrator screen: until the
// agreement is accepted the only screen open is the acceptance screen.
//
//   unknown   -- not read yet
//   signed    -- accepted; the cabinet is open (cached for the session)
//   unsigned  -- the document exists and the person has not accepted it
//   missing   -- no active document of that type exists; nothing can be
//                accepted and no link can be issued until it is published
//   error     -- the state could not be read (network, server)
//
// A state other than 'signed' is read again at every check, so the screen
// moves on as soon as the person accepts, here or in another tab.
// =============================================================================

import { ref } from 'vue'
import { defineStore } from 'pinia'

import { ApiResponseError } from '@/api/client'
import { getDocumentByType } from '@/api/documents'

export const AGENT_AGREEMENT_TYPE = 'agent_integrator_agreement'

export type AgentAgreementStatus = 'unknown' | 'signed' | 'unsigned' | 'missing' | 'error'

export const useAgentAgreementStore = defineStore('agentAgreement', () => {
  const status = ref<AgentAgreementStatus>('unknown')
  let epoch = 0

  /** Reads the state from the server unless it is already known to be signed. */
  async function ensure(): Promise<AgentAgreementStatus> {
    if (status.value === 'signed') return status.value
    const mine = ++epoch
    let next: AgentAgreementStatus
    try {
      const doc = await getDocumentByType(AGENT_AGREEMENT_TYPE)
      let signed = !!doc.is_signed
      if (!signed) {
        // An acceptance counts whatever its language (the backend's link gate
        // reads it by type): the other shipped language is read too.
        const other = doc.language === 'ru' ? 'en' : 'ru'
        try {
          signed = !!(await getDocumentByType(AGENT_AGREEMENT_TYPE, other)).is_signed
        } catch (err) {
          if (!(err instanceof ApiResponseError && err.status === 404)) throw err
        }
      }
      next = signed ? 'signed' : 'unsigned'
    } catch (err) {
      next = err instanceof ApiResponseError && err.status === 404 ? 'missing' : 'error'
    }
    if (mine === epoch) status.value = next
    return status.value
  }

  function markSigned(): void {
    epoch++
    status.value = 'signed'
  }

  function markMissing(): void {
    epoch++
    status.value = 'missing'
  }

  function reset(): void {
    epoch++
    status.value = 'unknown'
  }

  return { status, ensure, markSigned, markMissing, reset }
})
