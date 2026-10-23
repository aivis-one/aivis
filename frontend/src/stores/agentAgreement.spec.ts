import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { ApiResponseError } from '@/api/client'
import * as documents from '@/api/documents'
import { useAgentAgreementStore } from './agentAgreement'

vi.mock('@/api/documents', () => ({ getDocumentByType: vi.fn() }))

const getDocumentByType = vi.mocked(documents.getDocumentByType)

function doc(isSigned: boolean) {
  return { id: 'd1', type: 'agent_integrator_agreement', is_signed: isSigned } as never
}

describe('the agent-integrator agreement state', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    getDocumentByType.mockReset()
  })

  it('is unsigned while the document is not accepted', async () => {
    getDocumentByType.mockResolvedValue(doc(false))
    expect(await useAgentAgreementStore().ensure()).toBe('unsigned')
  })

  it('is signed once accepted, and is then not read again', async () => {
    getDocumentByType.mockResolvedValue(doc(true))
    const store = useAgentAgreementStore()
    expect(await store.ensure()).toBe('signed')
    await store.ensure()
    expect(getDocumentByType).toHaveBeenCalledTimes(1)
  })

  it('is missing when no active document exists', async () => {
    getDocumentByType.mockRejectedValue(new ApiResponseError(404, 'not found'))
    expect(await useAgentAgreementStore().ensure()).toBe('missing')
  })

  it('is an error when the state cannot be read, and is read again next time', async () => {
    const store = useAgentAgreementStore()
    getDocumentByType.mockRejectedValue(new Error('network'))
    expect(await store.ensure()).toBe('error')
    getDocumentByType.mockResolvedValue(doc(true))
    expect(await store.ensure()).toBe('signed')
  })
})
