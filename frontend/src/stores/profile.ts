import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { profileApi } from '@/api/profile'
import { settingsApi } from '@/api/settings'
import { useAuthStore } from '@/stores/auth'
import type {
  ProfileData,
  ProfileUpdateRequest,
  UserSettings,
  SettingsUpdateRequest,
} from '@/api/types'

export const useProfileStore = defineStore('profile', () => {
  const profile = ref<ProfileData | null>(null)
  const settings = ref<UserSettings | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  const fullName = computed(() => {
    if (!profile.value) return ''
    return [profile.value.first_name, profile.value.last_name].filter(Boolean).join(' ')
  })

  const hasAvatar = computed(() => !!profile.value?.avatar_url)

  async function fetchProfile() {
    loading.value = true
    error.value = null
    try {
      profile.value = await profileApi.get()
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Failed to load profile'
      throw e
    } finally {
      loading.value = false
    }
  }

  async function updateProfile(data: ProfileUpdateRequest): Promise<boolean> {
    loading.value = true
    error.value = null
    try {
      profile.value = await profileApi.update(data)
      const authStore = useAuthStore()
      if (authStore.user) {
        authStore.user.profile = profile.value
      }
      return true
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Failed to update profile'
      return false
    } finally {
      loading.value = false
    }
  }

  async function uploadAvatar(file: File): Promise<boolean> {
    loading.value = true
    error.value = null
    try {
      const response = await profileApi.uploadAvatar(file)
      if (profile.value) {
        profile.value.avatar_url = response.avatar_url
      }
      return true
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Failed to upload avatar'
      return false
    } finally {
      loading.value = false
    }
  }

  async function fetchSettings() {
    loading.value = true
    error.value = null
    try {
      settings.value = await settingsApi.get()
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Failed to load settings'
      throw e
    } finally {
      loading.value = false
    }
  }

  async function updateSettings(data: SettingsUpdateRequest): Promise<boolean> {
    loading.value = true
    error.value = null
    try {
      settings.value = await settingsApi.update(data)
      return true
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Failed to update settings'
      return false
    } finally {
      loading.value = false
    }
  }

  return {
    profile,
    settings,
    loading,
    error,
    fullName,
    hasAvatar,
    fetchProfile,
    updateProfile,
    uploadAvatar,
    fetchSettings,
    updateSettings,
  }
})
