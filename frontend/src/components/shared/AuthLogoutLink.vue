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
  <button type="button" class="logout-link" :disabled="busy" @click="signOut">
    {{ t('auth.logout') }}
  </button>
</template>

<style scoped>
.logout-link {
  position: relative;
  background: none;
  border: none;
  padding: 0;
  color: var(--primary);
  font-size: var(--fs-sm);
  font-weight: 600;
  cursor: pointer;
}

/* The painted box keeps its size; the hit area is raised to the tap minimum. */
.logout-link::after {
  content: '';
  position: absolute;
  inset-inline-start: 50%;
  inset-block-start: 50%;
  transform: translate(-50%, -50%);
  inline-size: max(100%, var(--tap-min));
  block-size: max(100%, var(--tap-min));
}

.logout-link:hover:not(:disabled) {
  text-decoration: underline;
}

.logout-link:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
