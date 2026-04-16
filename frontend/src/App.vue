<script setup lang="ts">
// Root component — auth gate + avatar overlay banner.
//
// Flow:
//   !isReady           → LoadingView
//   authError           → Error screen with retry (Telegram failure)
//   !isAuthenticated    → LoginView or RegisterView (standalone)
//   isAuthenticated     → <RouterView /> (main app)
//
// Avatar mode:
//   When staff is operating as another user, a fixed banner is shown
//   at the top of the screen with a "Return to Staff" button.

import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { Ghost, Shield } from 'lucide-vue-next'
import { useAuthStore } from '@/stores/auth'
import { useAuth } from '@/composables/useAuth'
import { useAvatar } from '@/composables/useAvatar'
import LoadingView from '@/views/auth/LoadingView.vue'
import LoginView from '@/views/auth/LoginView.vue'
import RegisterView from '@/views/auth/RegisterView.vue'

const { t } = useI18n()
const authStore = useAuthStore()
const { initAuth, retryAuth, isReady, isStandalone, authError } = useAuth()
const { isAvatarActive, loading: avatarLoading, endAvatarSession } = useAvatar()

const authView = ref<'login' | 'register'>('login')

/** Display name for avatar banner. */
const avatarTargetName = computed(() => {
  const p = authStore.user?.profile
  if (p && typeof p === 'object') {
    const fn = (p as Record<string, unknown>).first_name
    if (fn) return String(fn)
  }
  return authStore.user?.email ?? '…'
})

onMounted(() => {
  initAuth()
})
</script>

<template>
  <!-- Avatar overlay banner — fixed at top, above everything -->
  <div v-if="isAvatarActive && authStore.isAuthenticated" class="avatar-banner">
    <div class="avatar-banner__left">
      <Ghost :size="16" />
      <span class="avatar-banner__text">
        Avatar: {{ avatarTargetName }}
      </span>
    </div>
    <button
      class="avatar-banner__btn"
      :disabled="avatarLoading"
      @click="endAvatarSession"
    >
      <Shield :size="14" />
      {{ t('staff.avatar.return') }}
    </button>
  </div>

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
  <div v-else :class="{ 'app--avatar-active': isAvatarActive }">
    <RouterView />
  </div>
</template>

<style scoped>
/* Avatar overlay banner */
.avatar-banner {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  background: var(--accent);
  color: white;
  font-size: 13px;
  font-weight: 600;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
}

.avatar-banner__left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.avatar-banner__text {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.avatar-banner__btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: white;
  color: var(--accent);
  border: none;
  border-radius: var(--radius-sm, 6px);
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  white-space: nowrap;
  flex-shrink: 0;
}

.avatar-banner__btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.avatar-banner__btn:hover:not(:disabled) {
  opacity: 0.9;
}

/* Push content down when avatar banner is visible */
.app--avatar-active {
  padding-top: 40px;
}

/* Auth error screen */
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
