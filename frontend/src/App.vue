<script setup lang="ts">
// Root component — auth gate.
//
// Flow:
//   !isReady           → LoadingView
//   authError           → Error screen with retry (Telegram failure)
//   !isAuthenticated    → LoginView or RegisterView (standalone)
//   isAuthenticated     → <RouterView /> (main app)

import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { useAuth } from '@/composables/useAuth'
import LoadingView from '@/views/auth/LoadingView.vue'
import LoginView from '@/views/auth/LoginView.vue'
import RegisterView from '@/views/auth/RegisterView.vue'

const { t } = useI18n()
const authStore = useAuthStore()
const { initAuth, retryAuth, isReady, isStandalone, authError } = useAuth()

const authView = ref<'login' | 'register'>('login')

onMounted(() => {
  initAuth()
})
</script>

<template>
  <!-- Phase 1: auth initialization in progress -->
  <LoadingView v-if="!isReady" />

  <!-- Phase 2: auth error (Telegram failure) -->
  <div v-else-if="authError && !isStandalone && !authStore.isAuthenticated" class="auth-error-screen">
    <p class="auth-error-text">{{ authError }}</p>
    <button class="auth-error-retry" @click="retryAuth">{{ t('common.retry') }}</button>
  </div>

  <!-- Phase 3: not authenticated -->
  <template v-else-if="!authStore.isAuthenticated">
    <RegisterView
      v-if="authView === 'register'"
      @go-login="authView = 'login'"
    />
    <LoginView v-else @go-register="authView = 'register'" />
  </template>

  <!-- Phase 4: authenticated — main application -->
  <RouterView v-else />
</template>

<style scoped>
.auth-error-screen {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  min-height: 100dvh;
  background: var(--bg);
  gap: var(--space-md, 16px);
  padding: 24px;
}
.auth-error-text {
  font-size: 14px;
  color: var(--danger);
  text-align: center;
}
.auth-error-retry {
  padding: 12px 24px;
  border-radius: var(--radius-md, 8px);
  background: var(--accent);
  color: white;
  font-weight: 600;
  font-size: 15px;
  border: none;
  cursor: pointer;
}
</style>
