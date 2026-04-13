import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { kycApi } from '@/api/kyc'
import type { KycStatus, KycSubmission, KycDocument, KycSubmitRequest } from '@/api/types'

export const useKycStore = defineStore('kyc', () => {
  const status = ref<KycStatus>('none')
  const submission = ref<KycSubmission | null>(null)
  const documents = ref<KycDocument[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  const isPending = computed(() => status.value === 'pending' || status.value === 'in_review')
  const isApproved = computed(() => status.value === 'approved')
  const isRejected = computed(() => status.value === 'rejected')
  const canSubmit = computed(() => status.value === 'none' || status.value === 'rejected')
  const hasDocuments = computed(() => documents.value.length > 0)

  async function fetchStatus() {
    loading.value = true
    error.value = null
    try {
      const response = await kycApi.getStatus()
      status.value = response.status
      submission.value = response.submission ?? null
      if (response.submission?.documents) {
        documents.value = response.submission.documents
      }
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Failed to load KYC status'
      throw e
    } finally {
      loading.value = false
    }
  }

  async function submitKyc(data: KycSubmitRequest): Promise<boolean> {
    loading.value = true
    error.value = null
    try {
      submission.value = await kycApi.submit(data)
      status.value = 'pending'
      return true
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Failed to submit KYC'
      return false
    } finally {
      loading.value = false
    }
  }

  async function uploadDocument(file: File, type: string): Promise<boolean> {
    loading.value = true
    error.value = null
    try {
      const doc = await kycApi.uploadDocument(file, type)
      documents.value.push(doc)
      return true
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Failed to upload document'
      return false
    } finally {
      loading.value = false
    }
  }

  async function deleteDocument(id: string): Promise<boolean> {
    loading.value = true
    error.value = null
    try {
      await kycApi.deleteDocument(id)
      documents.value = documents.value.filter((d) => d.id !== id)
      return true
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Failed to delete document'
      return false
    } finally {
      loading.value = false
    }
  }

  function resetForm() {
    documents.value = []
    error.value = null
  }

  return {
    status,
    submission,
    documents,
    loading,
    error,
    isPending,
    isApproved,
    isRejected,
    canSubmit,
    hasDocuments,
    fetchStatus,
    submitKyc,
    uploadDocument,
    deleteDocument,
    resetForm,
  }
})
