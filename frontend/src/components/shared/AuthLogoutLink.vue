<script setup lang="ts">
// "Sign out" for the entry screens (e-mail code, documents, identity
// verification): a person who started on the wrong account, or who does not
// want to go on, can leave from any of them.

import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { safeNavigate } from '@/composables/safeNavigate'

const { t } = useI18n()
const router = useRouter()
const authStore = useAuthStore()
const busy = ref(false)

async function signOut(): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    await authStore.logout()
  } finally {
    busy.value = false
    void safeNavigate(router.push('/login'), '[AuthLogoutLink] to login')
  }
}
</script>

<template>
  <button
    type="button"
    class="ds-button ds-button--ghost"
    data-size="sm"
    :disabled="busy"
    @click="signOut"
  >
    {{ t('auth.logout') }}
  </button>
</template>
