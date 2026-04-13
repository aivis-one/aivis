import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useDocumentsStore } from '@/stores/documents'
import type { UserDocument } from '@/api/types'

const mockDocumentsApi = vi.hoisted(() => ({
  list: vi.fn(),
  get: vi.fn(),
  sign: vi.fn(),
}))

vi.mock('@/api/documents', () => ({ documentsApi: mockDocumentsApi }))

function makeDocument(overrides: Partial<UserDocument> = {}): UserDocument {
  return {
    id: 'doc-1',
    title: 'Investment Agreement',
    type: 'agreement',
    status: 'pending_signature',
    description: 'Agreement text',
    file_url: 'https://cdn/doc.pdf',
    file_size: 1024,
    created_at: '2026-04-12',
    updated_at: '2026-04-12',
    signed_at: null,
    expires_at: null,
    ...overrides,
  }
}

describe('documents store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  describe('fetchDocuments', () => {
    it('populates state on success', async () => {
      const docs = [makeDocument(), makeDocument({ id: 'doc-2', title: 'Contract' })]
      mockDocumentsApi.list.mockResolvedValue({ data: docs, total: 2, page: 1, per_page: 10 })

      const store = useDocumentsStore()
      const result = await store.fetchDocuments()

      expect(result).toBe(true)
      expect(store.documents).toHaveLength(2)
      expect(store.total).toBe(2)
    })

    it('sets error on failure', async () => {
      mockDocumentsApi.list.mockRejectedValue(new Error('Network error'))

      const store = useDocumentsStore()
      const result = await store.fetchDocuments()

      expect(result).toBe(false)
      expect(store.error).toBe('Network error')
    })
  })

  describe('fetchDocument', () => {
    it('sets currentDocument on success', async () => {
      const doc = makeDocument()
      mockDocumentsApi.get.mockResolvedValue(doc)

      const store = useDocumentsStore()
      const result = await store.fetchDocument('doc-1')

      expect(result).toBe(true)
      expect(store.currentDocument?.id).toBe('doc-1')
    })

    it('sets error on failure', async () => {
      mockDocumentsApi.get.mockRejectedValue(new Error('Not found'))

      const store = useDocumentsStore()
      const result = await store.fetchDocument('bad-id')

      expect(result).toBe(false)
      expect(store.error).toBe('Not found')
    })
  })

  describe('signDocument', () => {
    it('updates currentDocument and list item', async () => {
      const signed = makeDocument({ status: 'signed', signed_at: '2026-04-12' })
      mockDocumentsApi.sign.mockResolvedValue(signed)

      const store = useDocumentsStore()
      store.documents = [makeDocument()]
      const result = await store.signDocument('doc-1', {
        agreement_accepted: true,
        signature_text: 'John Doe',
      })

      expect(result).toBe(true)
      expect(store.currentDocument?.status).toBe('signed')
      expect(store.documents[0].status).toBe('signed')
    })

    it('sets error on failure', async () => {
      mockDocumentsApi.sign.mockRejectedValue(new Error('Sign failed'))

      const store = useDocumentsStore()
      const result = await store.signDocument('doc-1', {
        agreement_accepted: true,
        signature_text: 'John',
      })

      expect(result).toBe(false)
      expect(store.error).toBe('Sign failed')
    })
  })

  describe('$reset', () => {
    it('clears all state', async () => {
      mockDocumentsApi.list.mockResolvedValue({
        data: [makeDocument()],
        total: 1,
        page: 1,
        per_page: 10,
      })

      const store = useDocumentsStore()
      await store.fetchDocuments()
      store.$reset()

      expect(store.documents).toEqual([])
      expect(store.currentDocument).toBeNull()
      expect(store.total).toBe(0)
      expect(store.page).toBe(1)
    })
  })

  describe('computed', () => {
    it('hasDocuments reflects state', () => {
      const store = useDocumentsStore()
      expect(store.hasDocuments).toBe(false)
      store.documents = [makeDocument()]
      expect(store.hasDocuments).toBe(true)
    })

    it('pendingDocuments filters correctly', () => {
      const store = useDocumentsStore()
      store.documents = [
        makeDocument({ id: '1', status: 'pending_signature' }),
        makeDocument({ id: '2', status: 'signed' }),
        makeDocument({ id: '3', status: 'pending_signature' }),
      ]
      expect(store.pendingDocuments).toHaveLength(2)
    })

    it('totalPages computes correctly', () => {
      const store = useDocumentsStore()
      store.total = 25
      store.perPage = 10
      expect(store.totalPages).toBe(3)
    })
  })
})
