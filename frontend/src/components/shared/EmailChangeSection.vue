<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- EmailChangeSection (TASK-38)
// =============================================================================
//
// Shared across InvestorSettingsView / AgentSettingsView /
// CompanySettingsView's Actions section (each role gets one drop-in
// row instead of tripling the wizard logic three times). Backend:
// users/schemas.py + users/router.py "Email change" sections --
// three-step flow: current password + new email -> 6-digit code sent
// to the NEW address -> confirm. The active login email is untouched
// until the code is confirmed.
//
// i18n: every string is read from `${props.tPrefix}.emailChange.*` so
// each role keeps its own translated copy (matching the existing
// per-role `${ns}.actions.logout` convention -- this repo does not
// have a shared "common" settings-string namespace).
//
// ERROR MAPPING mirrors PasswordResetConfirmView.vue's branch shape
// (400/403/409/429/network/timeout), plus the two codes this flow adds
// beyond password reset: 403 incorrect_password (step 1 only) and 409
// email-already-taken (step 1 only, race-checked again at step 2).
//
// On successful confirm, authStore.fetchMe() re-syncs the auth store's
// cached email -- the caller's session token itself is untouched (this
// is NOT a password reset; nothing gets invalidated).
// =============================================================================

import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ChevronRight, Mail } from 'lucide-vue-next'

import { CButton, CInput, CModal } from '@/components/ui'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/composables/useToast'
import { requestEmailChange, resendEmailChangeCode, confirmEmailChange } from '@/api/users'
import { ApiResponseError, ApiNetworkError, ApiTimeoutError } from '@/api/client'

const props = defineProps<{
  /** i18n prefix, e.g. "inv.settings.actions" -- keys read from `${tPrefix}.emailChange.*`. */
  tPrefix: string
}>()

const { t } = useI18n()
const authStore = useAuthStore()
const { showToast } = useToast()

type Step = 'password' | 'code'

const open = ref(false)
const step = ref<Step>('password')
const currentPassword = ref('')
const newEmail = ref('')
const code = ref('')
const loading = ref(false)
const resending = ref(false)
const error = ref('')

// The email a code was actually sent to -- captured at the moment
// step 1 succeeds, so the "we sent a code to X" copy in step 2 cannot
// drift from what the backend actually emailed even if the user
// edited the field after submitting (they can't, the field is gone by
// then, but this keeps the two in lockstep by construction rather than
// by "the field still happens to hold the right value").
const sentTo = ref('')

function tk(key: string, params?: Record<string, unknown>): string {
  return params
    ? t(`${props.tPrefix}.emailChange.${key}`, params)
    : t(`${props.tPrefix}.emailChange.${key}`)
}

function openFlow(): void {
  open.value = true
  step.value = 'password'
  currentPassword.value = ''
  newEmail.value = ''
  code.value = ''
  error.value = ''
  sentTo.value = ''
}

function close(): void {
  if (loading.value) return
  open.value = false
}

function mapError(err: unknown, codeErrorKey: string | null = null): string {
  if (err instanceof ApiResponseError) {
    // Two different 403s can reach this flow: _require_current_password's
    // "Incorrect password" (users/service.py) AND forbid_avatar's
    // avatar-mode-blocked message (auth/avatar_guard.py) on the request
    // step. Blanket-mapping every 403 to "incorrect password" (an
    // adversarial review caught this) told a staff member in avatar mode
    // their password was wrong when the real reason was avatar mode --
    // ApiResponseError has no separate machine-readable `code` field
    // (only `status`/`detail`), so this matches the backend's own exact,
    // stable message text rather than assuming every 403 here means one
    // thing. Same fix applied in DeactivateAccountSection.vue.
    if (err.status === 403 && err.detail === 'Incorrect password') {
      return tk('errorIncorrectPassword')
    }
    if (err.status === 403 && err.detail) {
      return err.detail
    }
    if (err.status === 409) {
      return tk('errorEmailTaken')
    }
    if (err.status === 429) {
      return t('auth.error.rateLimited')
    }
    if (err.status === 400 && codeErrorKey) {
      return tk(codeErrorKey)
    }
    return err.detail || tk('errorGeneric')
  }
  if (err instanceof ApiNetworkError) return t('auth.error.networkError')
  if (err instanceof ApiTimeoutError) return t('auth.error.timeout')
  return tk('errorGeneric')
}

const canSubmitPassword = computed(
  () => currentPassword.value.length > 0 && newEmail.value.trim().length > 0,
)

async function submitPassword(): Promise<void> {
  if (!canSubmitPassword.value || loading.value) return
  error.value = ''
  loading.value = true
  try {
    await requestEmailChange({
      current_password: currentPassword.value,
      new_email: newEmail.value.trim(),
    })
    sentTo.value = newEmail.value.trim()
    step.value = 'code'
  } catch (err) {
    error.value = mapError(err)
  } finally {
    loading.value = false
  }
}

async function resend(): Promise<void> {
  if (resending.value) return
  error.value = ''
  resending.value = true
  try {
    await resendEmailChangeCode()
    showToast(tk('resendSuccess'), 'success')
  } catch (err) {
    error.value = mapError(err)
  } finally {
    resending.value = false
  }
}

const canSubmitCode = computed(() => /^\d{6}$/.test(code.value))

async function submitCode(): Promise<void> {
  if (!canSubmitCode.value || loading.value) return
  error.value = ''
  loading.value = true
  try {
    await confirmEmailChange({ code: code.value })
    // Session stays valid -- just re-sync the cached user (email
    // changed, everything else about the session is untouched).
    await authStore.fetchMe()
    open.value = false
    showToast(tk('successToast'), 'success')
  } catch (err) {
    error.value = mapError(err, 'errorCode')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <button type="button" class="ecs__row" @click="openFlow">
    <span class="ecs__row-label">
      <Mail :size="16" />
      {{ tk('cta') }}
    </span>
    <ChevronRight :size="16" />
  </button>

  <CModal :open="open" @close="close">
    <template v-if="step === 'password'">
      <h3 class="ecs__title">
        {{ tk('title') }}
      </h3>

      <CInput
        v-model="currentPassword"
        :label="tk('passwordLabel')"
        type="password"
        autocomplete="current-password"
        :placeholder="tk('passwordPlaceholder')"
        :disabled="loading"
        @keydown.enter="submitPassword"
      />
      <CInput
        v-model="newEmail"
        :label="tk('newEmailLabel')"
        type="email"
        autocomplete="email"
        :placeholder="tk('newEmailPlaceholder')"
        :disabled="loading"
        @keydown.enter="submitPassword"
      />

      <p v-if="error" class="ecs__error">
        {{ error }}
      </p>

      <div class="ecs__actions">
        <CButton variant="outline" size="sm" :disabled="loading" @click="close">
          {{ tk('cancelBtn') }}
        </CButton>
        <CButton
          variant="primary"
          size="sm"
          :loading="loading"
          :disabled="!canSubmitPassword"
          @click="submitPassword"
        >
          {{ tk('continueBtn') }}
        </CButton>
      </div>
    </template>

    <template v-else>
      <h3 class="ecs__title">
        {{ tk('codeTitle') }}
      </h3>
      <p class="ecs__subtitle">
        {{ tk('codeSubtitle', { email: sentTo }) }}
      </p>

      <CInput
        v-model="code"
        :label="tk('codeLabel')"
        type="text"
        inputmode="numeric"
        autocomplete="one-time-code"
        maxlength="6"
        :placeholder="tk('codePlaceholder')"
        :disabled="loading"
        @keydown.enter="submitCode"
      />

      <p v-if="error" class="ecs__error">
        {{ error }}
      </p>

      <div class="ecs__actions">
        <button type="button" class="ecs__resend" :disabled="resending" @click="resend">
          {{ tk('resendBtn') }}
        </button>
      </div>

      <div class="ecs__actions">
        <CButton variant="outline" size="sm" :disabled="loading" @click="close">
          {{ tk('cancelBtn') }}
        </CButton>
        <CButton
          variant="primary"
          size="sm"
          :loading="loading"
          :disabled="!canSubmitCode"
          @click="submitCode"
        >
          {{ tk('confirmBtn') }}
        </CButton>
      </div>
    </template>
  </CModal>
</template>

<style scoped>
.ecs__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--border-default);
  min-height: var(--size-3xl);
  width: 100%;
  background: transparent;
  border-left: 0;
  border-right: 0;
  border-top: 0;
  font: inherit;
  color: inherit;
  text-align: left;
  cursor: pointer;
  transition: background 0.15s;
}
.ecs__row:hover {
  background: var(--bg-subtle);
}
.ecs__row-label {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--primary);
}

.ecs__title {
  font-size: var(--fs-h4);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 var(--space-2);
}
.ecs__subtitle {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  margin: 0 0 var(--space-4);
  line-height: 1.5;
  word-break: break-word;
}

.ecs__error {
  margin: var(--space-2) 0 0;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-sm);
  font-size: var(--fs-xs);
  background: var(--danger-subtle);
  border: 1px solid var(--danger);
  color: var(--danger);
}

.ecs__actions {
  display: flex;
  gap: var(--space-2);
  justify-content: flex-end;
  margin-top: var(--space-4);
}

.ecs__resend {
  background: transparent;
  border: none;
  padding: 0;
  color: var(--primary);
  font-size: var(--fs-xs);
  font-weight: 600;
  cursor: pointer;
  font-family: inherit;
}
.ecs__resend:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
