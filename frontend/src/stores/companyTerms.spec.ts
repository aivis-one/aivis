import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { ApiResponseError } from '@/api/client'
import * as documents from '@/api/documents'
import { useCompanyTermsStore } from './companyTerms'

vi.mock('@/api/documents', () => ({ getDocumentByType: vi.fn(), listDocuments: vi.fn() }))

const listDocuments = vi.mocked(documents.listDocuments)
const getDocumentByType = vi.mocked(documents.getDocumentByType)

function doc(type: string, isSigned: boolean) {
  return { id: type, type, language: 'en', is_signed: isSigned } as never
}

describe('the project account documents state', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    listDocuments.mockReset()
    getDocumentByType.mockReset()
  })

  it('is signed when every required document is accepted, and is then not read again', async () => {
    listDocuments.mockResolvedValue([doc('cabinet_terms', true), doc('privacy_policy', true)])
    const store = useCompanyTermsStore()
    expect(await store.ensure()).toBe('signed')
    await store.ensure()
    expect(listDocuments).toHaveBeenCalledTimes(1)
  })

  it('is unsigned and names what is left while a required document is not accepted', async () => {
    listDocuments.mockResolvedValue([doc('cabinet_terms', true), doc('privacy_policy', false)])
    getDocumentByType.mockRejectedValue(new ApiResponseError(404, 'not found'))
    const store = useCompanyTermsStore()
    expect(await store.ensure()).toBe('unsigned')
    expect(store.pending.map((d) => d.type)).toEqual(['privacy_policy'])
  })

  it('counts an acceptance recorded on the other language row', async () => {
    listDocuments.mockResolvedValue([doc('cabinet_terms', false)])
    getDocumentByType.mockResolvedValue({ id: 'x', is_signed: true } as never)
    expect(await useCompanyTermsStore().ensure()).toBe('signed')
    expect(getDocumentByType).toHaveBeenCalledWith('cabinet_terms', 'ru')
  })

  it('is an error when the state cannot be read, and is read again next time', async () => {
    const store = useCompanyTermsStore()
    listDocuments.mockRejectedValue(new Error('network'))
    expect(await store.ensure()).toBe('error')
    listDocuments.mockResolvedValue([])
    expect(await store.ensure()).toBe('signed')
  })
})
