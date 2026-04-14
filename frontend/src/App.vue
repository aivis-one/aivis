<script setup lang="ts">
// Root component — auth gate.
//
// Flow:
//   !isReady           → LoadingView
//   !isAuthenticated    → LoginView or RegisterView (standalone)
//                       → LoadingView (telegram, auto-login in progress)
//   isAuthenticated     → <RouterView /> (main app)

import { ref, onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { useAuth } from '@/composables/useAuth'
import LoadingView from '@/views/auth/LoadingView.vue'
import LoginView from '@/views/auth/LoginView.vue'
import RegisterView from '@/views/auth/RegisterView.vue'

const authStore = useAuthStore()
const { initAuth, isReady, isStandalone } = useAuth()

const authView = ref<'login' | 'register'>('login')

onMounted(() => {
  initAuth()
})
</script>

<template>
  <!-- Phase 1: auth initialization in progress -->
  <LoadingView v-if="!isReady" />

  <!-- Phase 2: not authenticated -->
  <template v-else-if="!authStore.isAuthenticated">
    <!-- Telegram: still loading (auto-login failed or in progress) -->
    <LoadingView v-if="!isStandalone" />

    <!-- Standalone: show login or register form -->
    <RegisterView
      v-else-if="authView === 'register'"
      @go-login="authView = 'login'"
    />
    <LoginView v-else @go-register="authView = 'register'" />
  </template>

  <!-- Phase 3: authenticated — main application -->
  <RouterView v-else />
</template>
