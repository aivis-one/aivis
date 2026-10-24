<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- TwoFactorSection (TASK-38)
// =============================================================================
//
// Shared across InvestorSettingsView /
// CompanySettingsView's Actions section, same drop-in-row pattern as
// ActiveSessionsSection.vue / DeactivateAccountSection.vue.
// Backend: auth/router.py "Two-Factor Authentication
// (TOTP)" section + users/service.py's setup_totp/confirm_totp_setup/
// disable_totp -- see those module notes for the full storage shape
// and verification logic. Staff has no Settings/Actions screen (same
// scope note prior TASK-38 batches left for the other shared
// sections), so this component is not wired there.
//
// TWO ENTRY STATES, keyed off authStore.user.two_factor_enabled (a
// UserResponse field derived server-side from
// credentials.totp.enabled -- see users/models.py's two_factor_enabled
// property):
//   NOT enabled -> the ENABLE flow: current password -> QR code + raw
//     secret (manual-entry fallback) + a live code to confirm -> backup
//     codes shown ONCE.
//   Enabled -> the DISABLE flow: current password + a live code (or an
//     unused backup code) -> 2FA off.
//
// QR RENDERING reuses the `qrcode` package already used by
// InvestorDepositView.vue for the crypto deposit address -- same
// `QRCode.toString(..., { type: 'svg' })` call shape, same forced
// light palette (scanners need high contrast regardless of app theme).
//
// BACKUP CODES ARE SHOWN EXACTLY ONCE. confirmTwoFactor()'s response
// is the ONLY time these plaintext codes ever exist outside the user's
// own record of them -- the backend stores only their argon2 hashes
// (see TwoFactorConfirmResponse's docstring). The 'codes' step below is
// therefore NOT a toast and NOT auto-dismissed: it stays open with an
// explicit "I've saved these" confirmation step and a copy-to-clipboard
// affordance, mirroring the "save this now" discipline the backend
// docstring calls for.
//
// ERROR MAPPING mirrors DeactivateAccountSection.vue's
// shape (403 incorrect_password vs. other-403-pass-through for the
// avatar-guard message, 429 shared rate-limit copy, 400 per-step key).
// =============================================================================

import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { AlertTriangle, ChevronRight, Copy, Shield, ShieldCheck } from '@/components/ui/icons'
import QRCode from 'qrcode'

import { CBadge, CButton, CInput, CModal } from '@/components/ui'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/composables/useToast'
import { setupTwoFactor, confirmTwoFactor, disableTwoFactor } from '@/api/auth'
import { ApiResponseError, ApiNetworkError, ApiTimeoutError } from '@/api/client'

const props = defineProps<{
  /** i18n prefix, e.g. "inv.settings.actions" -- keys read from `${tPrefix}.twoFactor.*`. */
  tPrefix: string
}>()

const { t } = useI18n()
const authStore = useAuthStore()
const { showToast } = useToast()

type Step = 'password' | 'qr' | 'codes' | 'disable'

const open = ref(false)
const step = ref<Step>('password')
const loading = ref(false)
const error = ref('')

const isEnabled = computed<boolean>(() => Boolean(authStore.user?.two_factor_enabled))

// -- Enable flow state --
const currentPassword = ref('')
const secret = ref('')
const provisioningUri = ref('')
// The QR as an image (a data address), drawn on the invoice block's white pad (K43).
const qrSrc = ref<string | null>(null)
const setupCode = ref('')
const backupCodes = ref<string[]>([])

// -- Disable flow state --
const disablePassword = ref('')
const disableCode = ref('')

function tk(key: string): string {
  return t(`${props.tPrefix}.twoFactor.${key}`)
}

function reset(): void {
  step.value = isEnabled.value ? 'disable' : 'password'
  loading.value = false
  error.value = ''
  currentPassword.value = ''
  secret.value = ''
  provisioningUri.value = ''
  qrSrc.value = null
  setupCode.value = ''
  backupCodes.value = []
  disablePassword.value = ''
  disableCode.value = ''
}

function openFlow(): void {
  reset()
  open.value = true
}

function close(): void {
  if (loading.value) return
  // The backup-codes step is a deliberate exception: closing away from
  // it without the explicit "I've saved these" button is exactly the
  // "toast that vanishes" outcome the module note warns against, so
  // the CModal's own close (backdrop/Escape) is ignored while codes
  // are on screen -- only the button below can dismiss that step.
  if (step.value === 'codes') return
  open.value = false
}

function mapError(err: unknown, badRequestKey: string | null = null): string {
  if (err instanceof ApiResponseError) {
    // Same discipline as DeactivateAccountSection.vue:
    // match the backend's exact, stable "Incorrect password" text rather
    // than mapping every 403 to that meaning -- forbid_avatar("manage_2fa")
    // also answers 403, with a different message, and blanket-mapping
    // would misleadingly tell an avataring staff member their password
    // was wrong.
    if (err.status === 403 && err.detail === 'Incorrect password') {
      return tk('errorIncorrectPassword')
    }
    if (err.status === 403 && err.detail) {
      return err.detail
    }
    if (err.status === 429) {
      return t('auth.error.rateLimited')
    }
    if (err.status === 400 && badRequestKey) {
      return tk(badRequestKey)
    }
    return err.detail || tk('errorGeneric')
  }
  if (err instanceof ApiNetworkError) return t('auth.error.networkError')
  if (err instanceof ApiTimeoutError) return t('auth.error.timeout')
  return tk('errorGeneric')
}

async function generateQr(uri: string): Promise<string | null> {
  try {
    const svg = await QRCode.toString(uri, {
      type: 'svg',
      margin: 0,
      // Forced light palette -- same reasoning as InvestorDepositView's
      // deposit-address QR: camera/authenticator-app scanners need high
      // contrast regardless of the host UI theme (K43: dark on white). The
      // library takes colour strings and cannot read a token.
      color: { dark: '#000000', light: '#ffffff' },
      errorCorrectionLevel: 'M',
    })
    return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`
  } catch {
    return null
  }
}

// ---------------------------------------------------------------------------
// Enable flow
// ---------------------------------------------------------------------------

const stepTitle = computed<string>(() => {
  if (step.value === 'password') return tk('setupTitle')
  if (step.value === 'qr') return tk('qrTitle')
  if (step.value === 'codes') return tk('codesTitle')
  return tk('disableTitle')
})

const canSubmitPassword = computed(() => currentPassword.value.length > 0)

async function submitPassword(): Promise<void> {
  if (!canSubmitPassword.value || loading.value) return
  error.value = ''
  loading.value = true
  try {
    const resp = await setupTwoFactor({ current_password: currentPassword.value })
    secret.value = resp.secret
    provisioningUri.value = resp.provisioning_uri
    qrSrc.value = await generateQr(resp.provisioning_uri)
    step.value = 'qr'
  } catch (err) {
    error.value = mapError(err)
  } finally {
    loading.value = false
  }
}

const canSubmitSetupCode = computed(() => /^\d{6}$/.test(setupCode.value))

async function submitSetupCode(): Promise<void> {
  if (!canSubmitSetupCode.value || loading.value) return
  error.value = ''
  loading.value = true
  try {
    const resp = await confirmTwoFactor({ code: setupCode.value })
    backupCodes.value = resp.backup_codes
    await authStore.fetchMe()
    step.value = 'codes'
  } catch (err) {
    error.value = mapError(err, 'errorCode')
  } finally {
    loading.value = false
  }
}

// The manual-entry code is a copyable value (K53); a failed copy is told by a toast.
async function copySecret(): Promise<void> {
  try {
    await navigator.clipboard.writeText(secret.value)
  } catch {
    showToast(tk('copyFailed'), 'error')
  }
}

async function copyBackupCodes(): Promise<void> {
  try {
    await navigator.clipboard.writeText(backupCodes.value.join('\n'))
    showToast(tk('codesCopied'), 'success')
  } catch {
    showToast(tk('copyFailed'), 'error')
  }
}

function finishEnableFlow(): void {
  open.value = false
  showToast(tk('enabledToast'), 'success')
}

// ---------------------------------------------------------------------------
// Disable flow
// ---------------------------------------------------------------------------

const canSubmitDisable = computed(
  () => disablePassword.value.length > 0 && disableCode.value.trim().length >= 6,
)

async function submitDisable(): Promise<void> {
  if (!canSubmitDisable.value || loading.value) return
  error.value = ''
  loading.value = true
  try {
    await disableTwoFactor({
      current_password: disablePassword.value,
      code: disableCode.value.trim(),
    })
    await authStore.fetchMe()
    open.value = false
    showToast(tk('disabledToast'), 'success')
  } catch (err) {
    error.value = mapError(err, 'errorDisableCode')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <!-- The settings row that opens the flow (K23) -->
  <ul class="ds-rows">
    <li class="ds-row">
      <span class="ds-row__lead">
        <ShieldCheck v-if="isEnabled" size="sm" />
        <Shield v-else size="sm" />
      </span>
      <span class="ds-row__body">
        <button type="button" class="ds-row__link" @click="openFlow">
          <span class="ds-row__title">{{ isEnabled ? tk('ctaManage') : tk('ctaEnable') }}</span>
        </button>
      </span>
      <span class="ds-row__trail">
        <CBadge v-if="isEnabled" variant="success" :text="tk('statusEnabled')" />
        <ChevronRight size="sm" />
      </span>
    </li>
  </ul>

  <CModal :open="open" :title="stepTitle" @close="close">
    <!-- ENABLE: step 1 -- current password -->
    <template v-if="step === 'password'">
      <p class="ds-dialog__text">
        {{ tk('setupIntro') }}
      </p>

      <CInput
        v-model="currentPassword"
        :label="tk('passwordLabel')"
        type="password"
        autocomplete="current-password"
        :placeholder="tk('passwordPlaceholder')"
        :disabled="loading"
        @keydown.enter="submitPassword"
      />

      <div v-if="error" class="ds-alert ds-alert--danger" role="alert">
        <span class="ds-alert__icon" aria-hidden="true"><AlertTriangle size="sm" /></span>
        <div class="ds-alert__content">
          <p class="ds-alert__text">{{ error }}</p>
        </div>
      </div>

      <div class="ds-dialog__actions">
        <CButton variant="outline" size="sm" inline :disabled="loading" @click="close">
          {{ tk('cancelBtn') }}
        </CButton>
        <CButton
          variant="primary"
          size="sm"
          inline
          :loading="loading"
          :disabled="!canSubmitPassword"
          @click="submitPassword"
        >
          {{ tk('continueBtn') }}
        </CButton>
      </div>
    </template>

    <!-- ENABLE: step 2 -- QR + secret + confirm code. The QR stands on the invoice
         block's white pad (K43), the secret is a copyable value (K53). -->
    <template v-else-if="step === 'qr'">
      <p class="ds-dialog__text">
        {{ tk('qrSubtitle') }}
      </p>

      <div v-if="qrSrc" class="ds-invoice">
        <div class="ds-invoice__qr">
          <img :src="qrSrc" :alt="tk('qrTitle')" />
        </div>
      </div>

      <div class="ds-copy">
        <span class="ds-field__label">{{ tk('secretLabel') }}</span>
        <div class="ds-copy__box">
          <p class="ds-copy__value">{{ secret }}</p>
          <button
            type="button"
            class="ds-button ds-button--ghost ds-button--icon ds-copy__button"
            data-size="sm"
            :aria-label="tk('secretLabel')"
            @click="copySecret"
          >
            <Copy size="sm" />
          </button>
        </div>
      </div>

      <CInput
        v-model="setupCode"
        :label="tk('codeLabel')"
        type="text"
        inputmode="numeric"
        autocomplete="one-time-code"
        maxlength="6"
        :placeholder="tk('codePlaceholder')"
        :disabled="loading"
        @keydown.enter="submitSetupCode"
      />

      <div v-if="error" class="ds-alert ds-alert--danger" role="alert">
        <span class="ds-alert__icon" aria-hidden="true"><AlertTriangle size="sm" /></span>
        <div class="ds-alert__content">
          <p class="ds-alert__text">{{ error }}</p>
        </div>
      </div>

      <div class="ds-dialog__actions">
        <CButton variant="outline" size="sm" inline :disabled="loading" @click="close">
          {{ tk('cancelBtn') }}
        </CButton>
        <CButton
          variant="primary"
          size="sm"
          inline
          :loading="loading"
          :disabled="!canSubmitSetupCode"
          @click="submitSetupCode"
        >
          {{ tk('confirmBtn') }}
        </CButton>
      </div>
    </template>

    <!-- ENABLE: step 3 -- backup codes, shown once -->
    <template v-else-if="step === 'codes'">
      <div class="ds-alert ds-alert--warning" role="alert">
        <span class="ds-alert__icon" aria-hidden="true"><AlertTriangle size="sm" /></span>
        <div class="ds-alert__content">
          <p class="ds-alert__text">{{ tk('codesWarning') }}</p>
        </div>
      </div>

      <div class="ds-card ds-card--flat" data-size="sm">
        <ul class="tfs__codes-list">
          <li v-for="c in backupCodes" :key="c" class="tfs__codes-item">
            {{ c }}
          </li>
        </ul>
      </div>

      <div>
        <CButton variant="outline" size="sm" inline @click="copyBackupCodes">
          <Copy size="sm" />
          {{ tk('copyAllBtn') }}
        </CButton>
      </div>

      <CButton variant="primary" size="sm" @click="finishEnableFlow">
        {{ tk('savedBtn') }}
      </CButton>
    </template>

    <!-- DISABLE -->
    <template v-else>
      <p class="ds-dialog__text">
        {{ tk('disableSubtitle') }}
      </p>

      <CInput
        v-model="disablePassword"
        :label="tk('passwordLabel')"
        type="password"
        autocomplete="current-password"
        :placeholder="tk('passwordPlaceholder')"
        :disabled="loading"
      />

      <CInput
        v-model="disableCode"
        :label="tk('disableCodeLabel')"
        type="text"
        autocomplete="one-time-code"
        :placeholder="tk('disableCodePlaceholder')"
        :disabled="loading"
        @keydown.enter="submitDisable"
      />

      <div v-if="error" class="ds-alert ds-alert--danger" role="alert">
        <span class="ds-alert__icon" aria-hidden="true"><AlertTriangle size="sm" /></span>
        <div class="ds-alert__content">
          <p class="ds-alert__text">{{ error }}</p>
        </div>
      </div>

      <div class="ds-dialog__actions">
        <CButton variant="outline" size="sm" inline :disabled="loading" @click="close">
          {{ tk('cancelBtn') }}
        </CButton>
        <CButton
          variant="danger"
          size="sm"
          inline
          :loading="loading"
          :disabled="!canSubmitDisable"
          @click="submitDisable"
        >
          {{ tk('disableBtn') }}
        </CButton>
      </div>
    </template>
  </CModal>
</template>

<style scoped>
/* The backup codes: two columns of codes in the mono face, set from tokens (the
   system has no list of codes; NEED). */
.tfs__codes-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--space-2);
}
.tfs__codes-item {
  font-family: var(--font-mono);
  font-size: var(--fs-sm);
  color: var(--text-primary);
  user-select: all;
}
</style>
