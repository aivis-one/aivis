<script setup lang="ts">
// The banner row of the frame (K25, in the look of the warning Alert, K09): shown
// while staff act as another user, on every screen, with the way back to the staff
// cabinet. It is the first child of the shell grid, above the header.

import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Ghost } from '@/components/ui/icons'
import { useAuthStore } from '@/stores/auth'
import { useAvatar } from '@/composables/useAvatar'

const { t } = useI18n()
const authStore = useAuthStore()
const { isAvatarActive, loading, endAvatarSession } = useAvatar()

/** The name of the user the staff member acts as. */
const targetName = computed(() => {
  const p = authStore.user?.profile
  if (p && typeof p === 'object') {
    const fn = (p as Record<string, unknown>).first_name
    if (fn) return String(fn)
  }
  return authStore.user?.email ?? '…'
})
</script>

<template>
  <div v-if="isAvatarActive && authStore.isAuthenticated" class="ds-shell__banner" role="status">
    <span class="ds-alert__icon" aria-hidden="true"><Ghost size="sm" /></span>
    <span class="ds-shell__banner-text">{{ t('staff.avatar.title') }}: {{ targetName }}</span>
    <button
      type="button"
      class="ds-button ds-button--secondary ds-shell__banner-action"
      data-size="sm"
      :disabled="loading"
      @click="endAvatarSession"
    >
      {{ t('staff.avatar.return') }}
    </button>
  </div>
</template>
