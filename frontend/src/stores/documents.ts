import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { documentsApi } from '@/api/documents'
import type { UserDocument, DocumentsFilter, SignDocumentRequest } from '@/api/types'

export const useDocumentsStore = defineStore('documents', () => {
  const documents = ref<UserDocument[]>([])
  const currentDocument = ref<UserDocument | null>(null)
  const total = ref(0)
  const page = ref(1)
  const perPage = ref(10)
  const loading = ref(false)
  const error = ref<string | null>(null)

  const hasDocuments = computed(() => documents.value.length > 0)
  const pendingDocuments = computed(() =>
    documents.value.filter((d) => d.status === 'pending_signature'),
  )
  const totalPages = computed(() => Math.ceil(total.value / perPage.value))

  async function fetchDocuments(filters?: DocumentsFilter): Promise<boolean> {
    loading.value = true
    error.value = null
    try {
      const response = await documentsApi.list({
        ...filters,
        page: filters?.page ?? page.value,
        per_page: filters?.per_page ?? perPage.value,
      })
      documents.value = response.data
      total.value = response.total
      page.value = response.page
      return true
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Failed to load documents'
      return false
    } finally {
      loading.value = false
    }
  }

  async function fetchDocument(id: string): Promise<boolean> {
    loading.value = true
    error.value = null
    try {
      currentDocument.value = await documentsApi.get(id)
      return true
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Failed to load document'
      return false
    } finally {
      loading.value = false
    }
  }

  async function signDocument(id: string, data: SignDocumentRequest): Promise<boolean> {
    loading.value = true
    error.value = null
    try {
      const updated = await documentsApi.sign(id, data)
      currentDocument.value = updated
      const idx = documents.value.findIndex((d) => d.id === id)
      if (idx !== -1) documents.value[idx] = updated
      return true
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Failed to sign document'
      return false
    } finally {
      loading.value = false
    }
  }

  function $reset() {
    documents.value = []
    currentDocument.value = null
    total.value = 0
    page.value = 1
    error.value = null
    loading.value = false
  }

  return {
    documents,
    currentDocument,
    total,
    page,
    perPage,
    loading,
    error,
    hasDocuments,
    pendingDocuments,
    totalPages,
    fetchDocuments,
    fetchDocument,
    signDocument,
    $reset,
  }
})
