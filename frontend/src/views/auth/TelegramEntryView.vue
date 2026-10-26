<script setup lang="ts">
import AuthShell from '@/components/layout/AuthShell.vue'
import { MailCheck } from '@/components/ui/icons'
// The Telegram entry: one screen, three steps, for a person whose Telegram id
// no account holds yet -- in the Mini App and, since H45, after the website
// sign-in through Telegram (TelegramReturnView). On the website the consent
// step offers the way back to sign in, and an expired link says to start
// again there instead of reopening the app.
//   1. Consent -- two ticks, the cabinet's user agreement and the privacy
//      policy, worded as consent to register. The full texts open in the
//      document window. Nothing is sent at this step.
//   2. E-mail -- POST /api/v1/auth/telegram/link/email. The server answers the
//      same way for every address, so this step moves on after any answer and
//      says nothing about whether an account exists.
//   3. Code -- six boxes, POST /api/v1/auth/telegram/link/confirm. When the
//      account has two-factor on, the server answers `second_code_required` and
//      the authenticator field appears. Sending the e-mail again is the resend,
//      under the server's own rate limits.
// The link token lives in the auth store (memory only). On success the store has
// set the session and the person goes where the router sends a signed-in person.

import { ref, computed, nextTick, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { REFERRAL_KEY, useAuthStore } from '@/stores/auth'
import { ApiResponseError, ApiNetworkError, ApiTimeoutError } from '@/api/client'
import { safeNavigate } from '@/composables/safeNavigate'
import AivisLogo from '@/components/ui/AivisLogo.vue'
import { CAlert, CBackLink, CCheckbox, CInput } from '@/components/ui'
import LegalDocModal from '@/components/legal/LegalDocModal.vue'
import { postEntryTarget } from '@/utils/postAuthReturn'
import { platform } from '@/platform'

const router = useRouter()
const { t, locale } = useI18n()
const authStore = useAuthStore()

// The Mini App and the website (H45) run these same steps; only the way out
// of an expired sign-in differs: reopen the app from Telegram, or start again
// from the website's sign-in screen.
const onWebsite = platform.name !== 'telegram'

const CODE_LENGTH = 6
const RESEND_COOLDOWN = 60

type Step = 'consent' | 'email' | 'code'
const step = ref<Step>('consent')

// -- Step 1: consent --
const acceptedTerms = ref(false)
const acceptedPrivacy = ref(false)
const canContinue = computed(() => acceptedTerms.value && acceptedPrivacy.value)

// The texts are the cabinet's own static files, in the language of this screen.
const docLang = computed(() => (locale.value === 'ru' ? 'ru' : 'en'))
function docUrl(type: string): string {
  return `${import.meta.env.BASE_URL}legal/${docLang.value}/${type}.html`
}
const termsUrl = computed(() => docUrl('cabinet_terms'))
const privacyUrl = computed(() => docUrl('privacy_policy'))

// One document window, told which of the two to open.
const openDoc = ref<'cabinet_terms' | 'privacy_policy' | null>(null)
const docTitle = computed(() =>
  openDoc.value === 'privacy_policy'
    ? t('auth.telegramEntry.privacyTitle')
    : t('auth.telegramEntry.termsTitle'),
)

// -- Step 2: e-mail --
const email = ref('')
const codeTtlMinutes = ref(10)

// -- Step 3: code --
const digits = ref<string[]>(Array(CODE_LENGTH).fill(''))
const inputRefs = ref<HTMLInputElement[]>([])
const secondCode = ref('')
const needsSecondCode = ref(false)

const code = computed(() => digits.value.join(''))
const isCodeComplete = computed(() => code.value.length === CODE_LENGTH)

// -- Shared --
const error = ref('')
// The link token is gone (it lives 15 minutes): nothing can continue here.
const expired = ref(false)
// The wait before the code step's resend; a corrected address on the e-mail
// step is sent at once.
const resendCooldown = ref(0)
let cooldownTimer: ReturnType<typeof setInterval> | null = null
// The server's own wait after too many sends (Retry-After): it holds both the
// e-mail step and the resend.
const serverWait = ref(0)
let serverWaitTimer: ReturnType<typeof setInterval> | null = null

onBeforeUnmount(() => {
  if (cooldownTimer) clearInterval(cooldownTimer)
  if (serverWaitTimer) clearInterval(serverWaitTimer)
})

function startCooldown(seconds: number = RESEND_COOLDOWN): void {
  resendCooldown.value = seconds
  if (cooldownTimer) clearInterval(cooldownTimer)
  cooldownTimer = setInterval(() => {
    resendCooldown.value--
    if (resendCooldown.value <= 0 && cooldownTimer) {
      clearInterval(cooldownTimer)
      cooldownTimer = null
    }
  }, 1000)
}

function startServerWait(seconds: number): void {
  serverWait.value = seconds
  if (serverWaitTimer) clearInterval(serverWaitTimer)
  serverWaitTimer = setInterval(() => {
    serverWait.value--
    if (serverWait.value <= 0 && serverWaitTimer) {
      clearInterval(serverWaitTimer)
      serverWaitTimer = null
    }
  }, 1000)
}

/** The text of an error that belongs to no step in particular. */
function commonError(err: unknown): string {
  if (err instanceof ApiResponseError) {
    if (err.status === 429) return t('auth.error.rateLimited')
    return err.detail
  }
  if (err instanceof ApiNetworkError) return t('auth.error.networkError')
  if (err instanceof ApiTimeoutError) return t('auth.error.timeout')
  return t('common.error')
}

/** The link token expired or is unknown: the person has to start again. */
function expire(): void {
  authStore.clearTelegramEntry()
  expired.value = true
}

/** Website only: back to the sign-in screen, where the Telegram button is. */
function toLogin(): void {
  void safeNavigate(router.replace({ name: 'login' }), '[TelegramEntryView] to login')
}

/** Website only, at the consent step: drop this sign-in and go back. The
 *  guard holds a person with a link token on this screen, so the token goes
 *  first. */
function cancelToLogin(): void {
  authStore.clearTelegramEntry()
  toLogin()
}

// ---------------------------------------------------------------------------
// Steps 1 and 2
// ---------------------------------------------------------------------------

function goToEmail(): void {
  if (!canContinue.value) return
  error.value = ''
  step.value = 'email'
}

function goBack(): void {
  error.value = ''
  step.value = step.value === 'code' ? 'email' : 'consent'
}

async function handleSendEmail(resend = false): Promise<void> {
  if (authStore.loading || serverWait.value > 0 || (resend && resendCooldown.value > 0)) return
  error.value = ''
  const address = email.value.trim()
  if (!address) {
    error.value = t('auth.error.fillAllFields')
    return
  }
  try {
    const answer = await authStore.sendTelegramLinkEmail(
      address,
      sessionStorage.getItem(REFERRAL_KEY),
    )
    codeTtlMinutes.value = answer.code_ttl_minutes
    // The answer is the same for every address; the screen moves on whatever
    // the address is.
    digits.value = Array(CODE_LENGTH).fill('')
    secondCode.value = ''
    needsSecondCode.value = false
    step.value = 'code'
    startCooldown()
    await nextTick()
    inputRefs.value[0]?.focus()
  } catch (err) {
    if (err instanceof ApiResponseError) {
      if (err.code === 'link_token_invalid') {
        expire()
        return
      }
      if (err.status === 429) {
        error.value =
          err.code === 'telegram_link_emails_per_day'
            ? t('auth.telegramEntry.emailsPerDay')
            : t('auth.error.rateLimited')
        if (err.retryAfter) startServerWait(err.retryAfter)
        return
      }
    }
    error.value = commonError(err)
  }
}

// ---------------------------------------------------------------------------
// Step 3: the six boxes (same behaviour as the e-mail verification screen)
// ---------------------------------------------------------------------------

function setInputRef(el: unknown, index: number): void {
  if (el instanceof HTMLInputElement) {
    inputRefs.value[index] = el
  }
}

function handleInput(index: number, event: Event): void {
  const target = event.target as HTMLInputElement
  const value = target.value.replace(/\D/g, '')

  // Handle paste of full code.
  if (value.length > 1) {
    const chars = value.slice(0, CODE_LENGTH).split('')
    chars.forEach((ch, i) => {
      if (i < CODE_LENGTH) digits.value[i] = ch
    })
    const focusIndex = Math.min(chars.length, CODE_LENGTH - 1)
    inputRefs.value[focusIndex]?.focus()
    return
  }

  digits.value[index] = value.slice(0, 1)

  // Auto-focus next input.
  if (value && index < CODE_LENGTH - 1) {
    inputRefs.value[index + 1]?.focus()
  }
}

function handleKeydown(index: number, event: KeyboardEvent): void {
  // Backspace: clear current or move to previous.
  if (event.key === 'Backspace') {
    if (!digits.value[index] && index > 0) {
      digits.value[index - 1] = ''
      inputRefs.value[index - 1]?.focus()
      event.preventDefault()
    }
  }
}

async function handleConfirm(): Promise<void> {
  if (!isCodeComplete.value || authStore.loading) return
  if (needsSecondCode.value && !secondCode.value.trim()) {
    error.value = t('auth.error.fillAllFields')
    return
  }
  error.value = ''
  try {
    await authStore.confirmTelegramLink(
      code.value,
      needsSecondCode.value ? secondCode.value.trim() : null,
    )
    // The guard sends a signed-in person where they belong (the documents
    // step for whatever is still unsigned, otherwise the cabinet).
    // safeNavigate is no-throw by contract -- a benign NavigationFailure must
    // not surface as an error after a successful sign-in.
    await safeNavigate(
      router.push(postEntryTarget(authStore.user?.onboarding_step)),
      '[TelegramEntryView] post-confirm to home',
    )
  } catch (err) {
    if (err instanceof ApiResponseError) {
      switch (err.code) {
        case 'link_token_invalid':
          expire()
          return
        case 'second_code_required':
          // Not a wrong try: the account has two-factor on and the same call
          // goes again with the authenticator code.
          needsSecondCode.value = true
          return
        case 'second_code_invalid':
          error.value = t('auth.telegramEntry.secondCodeInvalid')
          secondCode.value = ''
          return
        case 'invalid_code':
          error.value = t('auth.telegramEntry.codeInvalid')
          digits.value = Array(CODE_LENGTH).fill('')
          await nextTick()
          inputRefs.value[0]?.focus()
          return
        case 'code_expired':
        case 'link_code_not_requested':
          error.value = t('auth.telegramEntry.codeExpired')
          return
        case 'telegram_link_locked':
          error.value = t('auth.telegramEntry.locked')
          return
        case 'telegram_conflict':
          error.value = t('auth.telegramEntry.conflict')
          return
        case 'telegram_already_linked':
          expire()
          return
        case 'account_blocked':
        case 'account_self_deactivated':
          error.value = t('auth.telegramEntry.accountInactive')
          return
      }
    }
    error.value = commonError(err)
  }
}
</script>

<template>
  <AuthShell>
    <template #start>
      <AivisLogo :height="28" />
      <CBackLink v-if="step !== 'consent' && !expired" :label="t('auth.back')" @click="goBack" />
      <CBackLink v-else-if="onWebsite && !expired" :label="t('auth.back')" @click="cancelToLogin" />
    </template>

    <!-- The link has expired: nothing here can continue -->
    <template v-if="expired">
      <h1 class="ds-auth__title">
        {{
          t(onWebsite ? 'auth.telegramEntry.expiredTitleWeb' : 'auth.telegramEntry.expiredTitle')
        }}
      </h1>
      <CAlert tone="danger">{{
        t(onWebsite ? 'auth.telegramEntry.expiredWeb' : 'auth.telegramEntry.expired')
      }}</CAlert>
      <div v-if="onWebsite" class="ds-auth__form">
        <button
          type="button"
          class="ds-button ds-button--primary ds-button--block"
          @click="toLogin"
        >
          {{ t('auth.telegramWeb.backToLogin') }}
        </button>
      </div>
    </template>

    <!-- Step 1: consent -->
    <template v-else-if="step === 'consent'">
      <h1 class="ds-auth__title">
        {{ t('auth.telegramEntry.consentTitle') }}
      </h1>
      <p class="ds-auth__subtitle">
        {{ t('auth.telegramEntry.consentSubtitle') }}
      </p>

      <div class="ds-auth__form">
        <CCheckbox v-model="acceptedTerms">
          {{ t('auth.telegramEntry.consentTermsPrefix') }}
          <a
            :href="termsUrl"
            target="_blank"
            rel="noopener"
            @click.prevent="openDoc = 'cabinet_terms'"
            >{{ t('auth.telegramEntry.termsName') }}</a
          >.
        </CCheckbox>

        <CCheckbox v-model="acceptedPrivacy">
          {{ t('auth.telegramEntry.consentPrivacyPrefix') }}
          <a
            :href="privacyUrl"
            target="_blank"
            rel="noopener"
            @click.prevent="openDoc = 'privacy_policy'"
            >{{ t('auth.telegramEntry.privacyName') }}</a
          >.
        </CCheckbox>

        <button
          class="ds-button ds-button--primary ds-button--block"
          type="button"
          :disabled="!canContinue"
          @click="goToEmail"
        >
          <span>{{ t('auth.telegramEntry.continueBtn') }}</span>
        </button>
      </div>
    </template>

    <!-- Step 2: e-mail -->
    <template v-else-if="step === 'email'">
      <div class="ds-auth__icon">
        <MailCheck />
      </div>
      <h1 class="ds-auth__title">
        {{ t('auth.telegramEntry.emailTitle') }}
      </h1>
      <p class="ds-auth__subtitle">
        {{ t('auth.telegramEntry.emailSubtitle') }}
      </p>

      <div class="ds-auth__form">
        <CInput
          v-model="email"
          :label="t('auth.register.email')"
          type="email"
          placeholder="name@example.com"
          autocomplete="email"
          @keydown.enter="handleSendEmail()"
        />

        <CAlert v-if="error" tone="danger">{{ error }}</CAlert>

        <button
          class="ds-button ds-button--primary ds-button--block"
          type="button"
          :aria-busy="authStore.loading || undefined"
          :disabled="authStore.loading || serverWait > 0"
          @click="handleSendEmail()"
        >
          <span v-if="authStore.loading" class="ds-button__spinner" aria-hidden="true" />
          <span>
            {{
              serverWait > 0
                ? t('auth.verify.resendIn', { seconds: serverWait })
                : t('auth.telegramEntry.sendCodeBtn')
            }}
          </span>
        </button>
      </div>
    </template>

    <!-- Step 3: code (and the second code when the server asks) -->
    <template v-else>
      <div class="ds-auth__icon">
        <MailCheck />
      </div>
      <h1 class="ds-auth__title">
        {{ t('auth.verify.title') }}
      </h1>
      <p class="ds-auth__subtitle">
        {{ t('auth.telegramEntry.codeSubtitle', { minutes: codeTtlMinutes }) }}
        <br />
        <strong>{{ email }}</strong>
      </p>

      <div
        class="ds-field ds-otp"
        role="group"
        aria-labelledby="telegram-entry-code-label"
        :aria-busy="authStore.loading || undefined"
      >
        <span id="telegram-entry-code-label" class="ds-field__label">{{
          t('common.codeGroup')
        }}</span>
        <div class="ds-otp__cells">
          <input
            v-for="(_, index) in CODE_LENGTH"
            :key="index"
            :ref="(el) => setInputRef(el, index)"
            type="text"
            inputmode="numeric"
            maxlength="6"
            class="ds-otp__cell"
            :data-filled="!!digits[index]"
            :aria-invalid="error ? 'true' : undefined"
            :autocomplete="index === 0 ? 'one-time-code' : 'off'"
            :aria-label="t('common.codeDigit', { n: index + 1, total: CODE_LENGTH })"
            :value="digits[index]"
            @input="handleInput(index, $event)"
            @keydown="handleKeydown(index, $event)"
            @keydown.enter="handleConfirm"
          />
        </div>
      </div>

      <div class="ds-auth__form">
        <CInput
          v-if="needsSecondCode"
          v-model="secondCode"
          :label="t('auth.telegramEntry.secondCodeLabel')"
          :hint="t('auth.telegramEntry.secondCodeHint')"
          type="text"
          autocomplete="one-time-code"
          :maxlength="20"
          :placeholder="t('auth.login.mfa.codePlaceholder')"
          @keydown.enter="handleConfirm"
        />

        <CAlert v-if="error" tone="danger">{{ error }}</CAlert>

        <button
          class="ds-button ds-button--primary ds-button--block"
          type="button"
          :aria-busy="authStore.loading || undefined"
          :disabled="!isCodeComplete || authStore.loading"
          @click="handleConfirm"
        >
          <span v-if="authStore.loading" class="ds-button__spinner" aria-hidden="true" />
          <span>{{ t('auth.verify.btn') }}</span>
        </button>

        <div class="ds-auth__foot">
          <span>{{ t('auth.verify.noCode') }}</span>
          <button
            v-if="resendCooldown <= 0 && serverWait <= 0"
            type="button"
            class="ds-button ds-button--ghost"
            data-size="sm"
            @click="handleSendEmail(true)"
          >
            {{ t('auth.verify.resend') }}
          </button>
          <span v-else>
            {{ t('auth.verify.resendIn', { seconds: Math.max(resendCooldown, serverWait) }) }}
          </span>
        </div>
      </div>
    </template>

    <!-- Document window -->
    <LegalDocModal
      :open="openDoc !== null"
      :title="docTitle"
      :lang="docLang"
      :type="openDoc ?? ''"
      @close="openDoc = null"
    />
  </AuthShell>
</template>
