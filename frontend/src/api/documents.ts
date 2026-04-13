import { api } from './client'
import type { UserDocument, DocumentsFilter, SignDocumentRequest, PaginatedResponse } from './types'

export const documentsApi = {
  list(filters?: DocumentsFilter): Promise<PaginatedResponse<UserDocument>> {
    const params = new URLSearchParams()
    if (filters?.type) params.set('type', filters.type)
    if (filters?.status) params.set('status', filters.status)
    if (filters?.page) params.set('page', String(filters.page))
    if (filters?.per_page) params.set('per_page', String(filters.per_page))
    const query = params.toString()
    return api.get<PaginatedResponse<UserDocument>>(`/api/v1/documents${query ? `?${query}` : ''}`)
  },

  get(id: string): Promise<UserDocument> {
    return api.get<UserDocument>(`/api/v1/documents/${id}`)
  },

  sign(id: string, data: SignDocumentRequest): Promise<UserDocument> {
    return api.post<UserDocument>(`/api/v1/documents/${id}/sign`, data)
  },
}
