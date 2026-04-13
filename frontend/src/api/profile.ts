import { api, apiUpload } from './client'
import type { ProfileData, ProfileUpdateRequest, AvatarUploadResponse } from './types'

export const profileApi = {
  get(): Promise<ProfileData> {
    return api.get<ProfileData>('/api/v1/profile')
  },

  update(data: ProfileUpdateRequest): Promise<ProfileData> {
    return api.patch<ProfileData>('/api/v1/profile', data)
  },

  uploadAvatar(file: File): Promise<AvatarUploadResponse> {
    const formData = new FormData()
    formData.append('avatar', file)
    return apiUpload<AvatarUploadResponse>('/api/v1/profile/avatar', formData)
  },
}
