import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useKycStore } from '@/stores/kyc'
import type { KycSubmission, KycDocument } from '@/api/types'

const mockKycApi = vi.hoisted(() => ({
  getStatus: vi.fn(),
  submit: vi.fn(),
  uploadDocument: vi.fn(),
  deleteDocument: vi.fn(),
}))

vi.mock('@/api/kyc', () => ({ kycApi: mockKycApi }))

function makeSubmission(overrides: Partial<KycSubmission> = {}): KycSubmission {
  return {
    id: 'sub-1',
    status: 'pending',
    submitted_at: '2026-04-12T00:00:00Z',
    documents: [],
    personal_data: {
      full_name: 'John Doe',
      date_of_birth: '1990-01-01',
      nationality: 'US',
      address: '123 Main St',
      tax_id: '123456789',
    },
    ...overrides,
  }
}

function makeDocument(overrides: Partial<KycDocument> = {}): KycDocument {
  return {
    id: 'doc-1',
    type: 'passport',
    filename: 'passport.pdf',
    url: 'https://cdn/passport.pdf',
    uploaded_at: '2026-04-12T00:00:00Z',
    ...overrides,
  }
}

describe('kyc store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  describe('initial state', () => {
    it('has none status and empty documents', () => {
      const store = useKycStore()
      expect(store.status).toBe('none')
      expect(store.submission).toBeNull()
      expect(store.documents).toEqual([])
      expect(store.loading).toBe(false)
    })
  })

  describe('fetchStatus', () => {
    it('sets status and submission on success', async () => {
      const sub = makeSubmission()
      mockKycApi.getStatus.mockResolvedValue({ status: 'pending', submission: sub })

      const store = useKycStore()
      await store.fetchStatus()

      expect(store.status).toBe('pending')
      expect(store.submission).toEqual(sub)
    })

    it('sets error on failure', async () => {
      mockKycApi.getStatus.mockRejectedValue(new Error('Network error'))

      const store = useKycStore()
      await expect(store.fetchStatus()).rejects.toThrow()
      expect(store.error).toBe('Network error')
    })
  })

  describe('submitKyc', () => {
    it('sets status to pending on success', async () => {
      mockKycApi.submit.mockResolvedValue(makeSubmission())

      const store = useKycStore()
      const result = await store.submitKyc({
        personal_data: makeSubmission().personal_data,
        document_ids: ['doc-1'],
      })

      expect(result).toBe(true)
      expect(store.status).toBe('pending')
    })

    it('returns false on error', async () => {
      mockKycApi.submit.mockRejectedValue(new Error('Submit failed'))

      const store = useKycStore()
      const result = await store.submitKyc({
        personal_data: makeSubmission().personal_data,
        document_ids: [],
      })

      expect(result).toBe(false)
      expect(store.error).toBe('Submit failed')
    })
  })

  describe('uploadDocument', () => {
    it('adds document to array on success', async () => {
      const doc = makeDocument()
      mockKycApi.uploadDocument.mockResolvedValue(doc)

      const store = useKycStore()
      const result = await store.uploadDocument(new File([''], 'test.pdf'), 'passport')

      expect(result).toBe(true)
      expect(store.documents).toHaveLength(1)
      expect(store.documents[0].id).toBe('doc-1')
    })
  })

  describe('deleteDocument', () => {
    it('removes document from array', async () => {
      mockKycApi.deleteDocument.mockResolvedValue(undefined)

      const store = useKycStore()
      store.documents = [makeDocument({ id: 'doc-1' }), makeDocument({ id: 'doc-2' })]
      const result = await store.deleteDocument('doc-1')

      expect(result).toBe(true)
      expect(store.documents).toHaveLength(1)
      expect(store.documents[0].id).toBe('doc-2')
    })
  })

  describe('getters', () => {
    it('isPending is true for pending/in_review', () => {
      const store = useKycStore()
      store.status = 'pending'
      expect(store.isPending).toBe(true)
      store.status = 'in_review'
      expect(store.isPending).toBe(true)
    })

    it('isApproved is true for approved', () => {
      const store = useKycStore()
      store.status = 'approved'
      expect(store.isApproved).toBe(true)
    })

    it('isRejected is true for rejected', () => {
      const store = useKycStore()
      store.status = 'rejected'
      expect(store.isRejected).toBe(true)
    })

    it('canSubmit is true for none or rejected', () => {
      const store = useKycStore()
      expect(store.canSubmit).toBe(true)
      store.status = 'rejected'
      expect(store.canSubmit).toBe(true)
      store.status = 'pending'
      expect(store.canSubmit).toBe(false)
    })

    it('hasDocuments reflects documents array', () => {
      const store = useKycStore()
      expect(store.hasDocuments).toBe(false)
      store.documents = [makeDocument()]
      expect(store.hasDocuments).toBe(true)
    })
  })
})
