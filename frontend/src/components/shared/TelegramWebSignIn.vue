<script setup lang="ts">
// "Continue with Telegram" on the website's login and registration screens
// (H45). Both screens do the same: a known Telegram signs in, an unknown one
// goes through the Telegram entry steps (consent, e-mail, code) and then the
// password screen -- the server decides, by the Mini App's own path.
//
// SHOWN ONLY WHERE IT WORKS: never inside the Telegram Mini App (it signs in
// by initData there), and on the website only when the server says the
// sign-in is on (GET /api/v1/auth/telegram/web -- both keys set on the box).
// Until the answer comes, and when it fails, the button is not there: a
// button that leads to "not configured" is worse than none.
//
// THE PRESS: a fresh mark (platform/webLogin.ts), the start with the referral
// code the visitor came by and the screen's interface language, the mark
// remembered with the state, and the browser handed to Telegram. The return
// lands on TelegramReturnView.
//
// The look is the design system's: ds-button--telegram, block, under the
// screen's own primary button (design-system examples, auth-login).

import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ShieldAlert } from '@/components/ui/icons'
import { ApiResponseError } from '@/api/client'
import { getTelegramWebAvailability, startTelegramWebLogin } from '@/api/auth'
import { platform } from '@/platform'
import { REFERRAL_KEY } from '@/stores/auth'
import { newMark, rememberLoginMark } from '@/platform/webLogin'

const { t, locale } = useI18n()

const available = ref(false)
const busy = ref(false)
const error = ref('')

const LANGUAGES = ['en', 'ru', 'ar', 'de'] as const
type Language = (typeof LANGUAGES)[number]

function screenLanguage(): Language | null {
  const code = String(locale.value).slice(0, 2)
  return (LANGUAGES as readonly string[]).includes(code) ? (code as Language) : null
}

onMounted(async () => {
  if (platform.name === 'telegram') return
  try {
    available.value = (await getTelegramWebAvailability()).available === true
  } catch {
    available.value = false
  }
})

async function start(): Promise<void> {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try {
    const mark = newMark()
    const { url, state } = await startTelegramWebLogin({
      mark,
      referral_code: sessionStorage.getItem(REFERRAL_KEY) || null,
      language: screenLanguage(),
    })
    rememberLoginMark({ state, mark })
    window.location.assign(url)
  } catch (err) {
    busy.value = false
    error.value =
      err instanceof ApiResponseError && err.status === 429
        ? t('auth.error.rateLimited')
        : t('auth.telegramWeb.startFailed')
  }
}
</script>

<template>
  <template v-if="available">
    <button
      type="button"
      class="ds-button ds-button--telegram ds-button--block"
      :aria-busy="busy || undefined"
      :disabled="busy"
      @click="start"
    >
      <span v-if="busy" class="ds-button__spinner" aria-hidden="true" />
      <span>{{ t('auth.telegramWeb.button') }}</span>
    </button>
    <div v-if="error" class="ds-alert ds-alert--danger" role="alert">
      <span class="ds-alert__icon" aria-hidden="true"><ShieldAlert size="sm" /></span>
      <div class="ds-alert__content">
        <p class="ds-alert__text">{{ error }}</p>
      </div>
    </div>
  </template>
</template>
