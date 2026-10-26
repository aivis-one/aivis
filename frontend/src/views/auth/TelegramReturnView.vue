<script setup lang="ts">
import AuthShell from '@/components/layout/AuthShell.vue'
// =============================================================================
// TelegramReturnView -- where Telegram sends the browser back (H45)
// =============================================================================
//
// The website sign-in through Telegram (platform/webLogin.ts,
// backend/app/modules/auth/web_login.py) returns here with `code` and `state`,
// or with `error` when the person cancelled on Telegram's page. The screen:
//   1. reads them ONCE and wipes them from the address bar -- a reload would
//      otherwise re-send an already used state and say "expired" every time;
//   2. takes this browser's mark (one-time) and goes on only when the mark
//      was made for this very state: a return link that came from someone
//      else is refused here, without a request (login CSRF);
//   3. completes the sign-in: the store applies the answer exactly as for the
//      Mini App -- a session, the Telegram entry steps (a Telegram nobody
//      holds yet), or the second-code screen -- and the screen leaves for it.
//      The password screen, when due, is the guard's (H44).
// A refusal stays on this screen with its reason and a way back to sign in.
// =============================================================================

import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { ShieldAlert } from '@/components/ui/icons'
import { useAuthStore } from '@/stores/auth'
import { ApiResponseError, ApiNetworkError, ApiTimeoutError } from '@/api/client'
import { safeNavigate } from '@/composables/safeNavigate'
import { takeLoginMark } from '@/platform/webLogin'
import { postEntryTarget } from '@/utils/postAuthReturn'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const error = ref('')

function one(value: unknown): string | null {
  return typeof value === 'string' && value ? value : null
}

function refusal(err: unknown): string {
  if (err instanceof ApiResponseError) {
    switch (err.code) {
      case 'login_expired':
        return t('auth.telegramWeb.expired')
      case 'login_foreign':
        return t('auth.telegramWeb.foreign')
      case 'telegram_failed':
      case 'login_not_configured':
        return t('auth.telegramWeb.failed')
    }
    if (err.status === 429) return t('auth.error.rateLimited')
    return err.detail
  }
  if (err instanceof ApiNetworkError) return t('auth.error.networkError')
  if (err instanceof ApiTimeoutError) return t('auth.error.timeout')
  return t('common.error')
}

onMounted(async () => {
  const code = one(route.query.code)
  const state = one(route.query.state)
  const cancelled = one(route.query.error)
  // Wipe the address: the code and state are spent whatever happens next.
  if (code || state || cancelled) {
    await safeNavigate(
      router.replace({ name: 'telegram-return', query: {} }),
      '[TelegramReturnView] wipe the address',
    )
  }
  const remembered = takeLoginMark()

  if (cancelled) {
    error.value = t('auth.telegramWeb.cancelled')
    return
  }
  if (!code || !state) {
    error.value = t('auth.telegramWeb.expired')
    return
  }
  if (!remembered || remembered.state !== state) {
    error.value = t('auth.telegramWeb.foreign')
    return
  }

  try {
    const result = await authStore.completeTelegramWebLogin(code, state, remembered.mark)
    const target =
      'linkRequired' in result && result.linkRequired
        ? { name: 'telegram-entry' }
        : result.mfaRequired
          ? { name: 'telegram-second-code' }
          : postEntryTarget(authStore.user?.onboarding_step)
    await safeNavigate(router.replace(target), '[TelegramReturnView] after the sign-in')
  } catch (err) {
    error.value = refusal(err)
  }
})

function toLogin(): void {
  void safeNavigate(router.replace({ name: 'login' }), '[TelegramReturnView] to login')
}
</script>

<template>
  <AuthShell>
    <h1 class="ds-auth__title">
      {{ t('auth.telegramWeb.returnTitle') }}
    </h1>

    <template v-if="error">
      <div class="ds-alert ds-alert--danger" role="alert">
        <span class="ds-alert__icon" aria-hidden="true"><ShieldAlert size="sm" /></span>
        <div class="ds-alert__content">
          <p class="ds-alert__text">{{ error }}</p>
        </div>
      </div>
      <div class="ds-auth__form">
        <button
          type="button"
          class="ds-button ds-button--primary ds-button--block"
          @click="toLogin"
        >
          {{ t('auth.telegramWeb.backToLogin') }}
        </button>
      </div>
    </template>

    <p v-else class="ds-auth__subtitle" role="status">
      {{ t('auth.telegramWeb.checking') }}
    </p>
  </AuthShell>
</template>
