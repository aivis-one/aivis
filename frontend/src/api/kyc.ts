import { api, apiUpload } from './client'
import type { KycStatusResponse, KycSubmission, KycSubmitRequest, KycDocument } from './types'

export const kycApi = {
  getStatus(): Promise<KycStatusResponse> {
    return api.get<KycStatusResponse>('/api/v1/kyc/status')
  },

  submit(data: KycSubmitRequest): Promise<KycSubmission> {
    return api.post<KycSubmission>('/api/v1/kyc/submit', data)
  },

  uploadDocument(file: File, type: string): Promise<KycDocument> {
    const formData = new FormData()
    formData.append('document', file)
    formData.append('type', type)
    return apiUpload<KycDocument>('/api/v1/kyc/documents', formData)
  },

  deleteDocument(id: string): Promise<void> {
    return api.delete<void>(`/api/v1/kyc/documents/${id}`)
  },
}
