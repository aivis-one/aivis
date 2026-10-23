<script setup lang="ts">
// The storefront's right slot of the header: Register and Sign in for a visitor,
// the way into the cabinet for a signed-in one. Both carry the current public path
// as ?next= so the sign-in screen sends the visitor back to the same page.

import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { safeNavigate } from '@/composables/safeNavigate'
import { useAuthStore } from '@/stores/auth'
import { getRoleDashboard } from '@/router/guards'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

// The root edge case is excluded: an empty `next` is the safer baseline.
const nextQuery = computed<string | undefined>(() => {
  const path = route.fullPath
  if (!path || path === '/') return undefined
  return path
})

function goToLogin(): void {
  void safeNavigate(
    router.push({
      name: 'login',
      query: nextQuery.value ? { next: nextQuery.value } : undefined,
    }),
    '[PublicHeaderActions] to login',
  )
}

function goToRegister(): void {
  void safeNavigate(
    router.push({
      name: 'register',
      query: nextQuery.value ? { next: nextQuery.value } : undefined,
    }),
    '[PublicHeaderActions] to register',
  )
}

function goToCabinet(): void {
  void safeNavigate(
    router.push(getRoleDashboard(authStore.role)),
    '[PublicHeaderActions] to cabinet',
  )
}
</script>

<template>
  <button
    v-if="authStore.isAuthenticated"
    type="button"
    class="ds-button ds-button--primary"
    data-size="sm"
    @click="goToCabinet"
  >
    {{ t('public.shell.cabinetButton') }}
  </button>
  <template v-else>
    <button
      type="button"
      class="ds-button ds-button--secondary"
      data-size="sm"
      @click="goToRegister"
    >
      {{ t('public.shell.registerButton') }}
    </button>
    <button type="button" class="ds-button ds-button--primary" data-size="sm" @click="goToLogin">
      {{ t('public.shell.loginButton') }}
    </button>
  </template>
</template>
