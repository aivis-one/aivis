import { api } from './client'
import type { UserSettings, SettingsUpdateRequest } from './types'

export const settingsApi = {
  get(): Promise<UserSettings> {
    return api.get<UserSettings>('/api/v1/settings')
  },

  update(data: SettingsUpdateRequest): Promise<UserSettings> {
    return api.patch<UserSettings>('/api/v1/settings', data)
  },
}
