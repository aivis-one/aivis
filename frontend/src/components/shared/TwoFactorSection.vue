<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- TwoFactorSection (TASK-38)
// =============================================================================
//
// Shared across InvestorSettingsView / AgentSettingsView /
// CompanySettingsView's Actions section, same drop-in-row pattern as
// EmailChangeSection.vue / ActiveSessionsSection.vue / Deactivate
// AccountSection.vue. Backend: auth/router.py "Two-Factor Authentication
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
// ERROR MAPPING mirrors EmailChangeSection.vue / DeactivateAccountSection.vue's
// shape (403 incorrect_password vs. other-403-pass-through for the
// avatar-guard message, 429 shared rate-limit copy, 400 per-step key).
// =============================================================================

import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ChevronRight, Copy, Shield, ShieldCheck } from 'lucide-vue-next'
import QRCode from 'qrcode'

import { CButton, CInput, CModal } from '@/components/ui'
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
const qrSvg = ref<string | null>(null)
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
  qrSvg.value = null
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
    // Same discipline as EmailChangeSection.vue / DeactivateAccountSection.vue:
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
    return await QRCode.toString(uri, {
      type: 'svg',
      margin: 0,
      width: 220,
      // Forced light palette -- same reasoning as InvestorDepositView's
      // deposit-address QR: camera/authenticator-app scanners need high
      // contrast regardless of the host UI theme.
      color: { dark: '#000000', light: '#ffffff' },
      errorCorrectionLevel: 'M',
    })
  } catch {
    return null
  }
}

// ---------------------------------------------------------------------------
// Enable flow
// ---------------------------------------------------------------------------

const canSubmitPassword = computed(() => currentPassword.value.length > 0)

async function submitPassword(): Promise<void> {
  if (!canSubmitPassword.value || loading.value) return
  error.value = ''
  loading.value = true
  try {
    const resp = await setupTwoFactor({ current_password: currentPassword.value })
    secret.value = resp.secret
    provisioningUri.value = resp.provisioning_uri
    qrSvg.value = await generateQr(resp.provisioning_uri)
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
  <button type="button" class="tfs__row" @click="openFlow">
    <span class="tfs__row-label">
      <ShieldCheck v-if="isEnabled" :size="16" />
      <Shield v-else :size="16" />
      {{ isEnabled ? tk('ctaManage') : tk('ctaEnable') }}
    </span>
    <span class="tfs__row-right">
      <span v-if="isEnabled" class="tfs__status-badge">{{ tk('statusEnabled') }}</span>
      <ChevronRight :size="16" />
    </span>
  </button>

  <CModal :open="open" @close="close">
    <!-- ENABLE: step 1 -- current password -->
    <template v-if="step === 'password'">
      <h3 class="tfs__title">
        {{ tk('setupTitle') }}
      </h3>
      <p class="tfs__subtitle">
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

      <p v-if="error" class="tfs__error">
        {{ error }}
      </p>

      <div class="tfs__actions">
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

    <!-- ENABLE: step 2 -- QR + secret + confirm code -->
    <template v-else-if="step === 'qr'">
      <h3 class="tfs__title">
        {{ tk('qrTitle') }}
      </h3>
      <p class="tfs__subtitle">
        {{ tk('qrSubtitle') }}
      </p>

      <div v-if="qrSvg" class="tfs__qr" v-html="qrSvg" />

      <div class="tfs__secret-block">
        <span class="tfs__secret-label">{{ tk('secretLabel') }}</span>
        <code class="tfs__secret-value">{{ secret }}</code>
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

      <p v-if="error" class="tfs__error">
        {{ error }}
      </p>

      <div class="tfs__actions">
        <CButton variant="outline" size="sm" :disabled="loading" @click="close">
          {{ tk('cancelBtn') }}
        </CButton>
        <CButton
          variant="primary"
          size="sm"
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
      <h3 class="tfs__title">
        {{ tk('codesTitle') }}
      </h3>
      <p class="tfs__warning">
        {{ tk('codesWarning') }}
      </p>

      <ul class="tfs__codes-list">
        <li v-for="c in backupCodes" :key="c" class="tfs__codes-item">
          {{ c }}
        </li>
      </ul>

      <div class="tfs__actions tfs__actions--left">
        <CButton variant="outline" size="sm" inline @click="copyBackupCodes">
          <Copy :size="14" />
          {{ tk('copyAllBtn') }}
        </CButton>
      </div>

      <div class="tfs__actions">
        <CButton variant="primary" size="sm" @click="finishEnableFlow">
          {{ tk('savedBtn') }}
        </CButton>
      </div>
    </template>

    <!-- DISABLE -->
    <template v-else>
      <h3 class="tfs__title">
        {{ tk('disableTitle') }}
      </h3>
      <p class="tfs__subtitle">
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

      <p v-if="error" class="tfs__error">
        {{ error }}
      </p>

      <div class="tfs__actions">
        <CButton variant="outline" size="sm" :disabled="loading" @click="close">
          {{ tk('cancelBtn') }}
        </CButton>
        <CButton
          variant="danger"
          size="sm"
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
.tfs__row {
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
.tfs__row:hover {
  background: var(--bg-subtle);
}
.tfs__row:last-child {
  border-bottom: none;
}
.tfs__row-label {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--primary);
}
.tfs__row-right {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
}
.tfs__status-badge {
  font-size: var(--fs-2xs, 0.6875rem);
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  padding: 2px var(--space-2);
  border-radius: var(--radius-sm);
  background: var(--success-subtle, var(--bg-subtle));
  color: var(--success, var(--text-secondary));
}

.tfs__title {
  font-size: var(--fs-h4);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 var(--space-2);
}
.tfs__subtitle {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  margin: 0 0 var(--space-4);
  line-height: 1.5;
}
.tfs__warning {
  font-size: var(--fs-xs);
  color: var(--danger);
  margin: 0 0 var(--space-4);
  line-height: 1.5;
  font-weight: 600;
}

.tfs__qr {
  display: flex;
  justify-content: center;
  margin: 0 0 var(--space-4);
}
.tfs__qr :deep(svg) {
  width: 180px;
  height: 180px;
  border-radius: var(--radius-sm);
}

.tfs__secret-block {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  margin: 0 0 var(--space-4);
  padding: var(--space-3);
  background: var(--bg-subtle);
  border-radius: var(--radius-sm);
}
.tfs__secret-label {
  font-size: var(--fs-2xs, 0.6875rem);
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-tertiary);
}
.tfs__secret-value {
  font-family: var(--font-mono, monospace);
  font-size: var(--fs-sm);
  color: var(--text-primary);
  word-break: break-all;
  user-select: all;
}

.tfs__codes-list {
  list-style: none;
  margin: 0 0 var(--space-3);
  padding: var(--space-3);
  background: var(--bg-subtle);
  border-radius: var(--radius-sm);
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--space-2);
}
.tfs__codes-item {
  font-family: var(--font-mono, monospace);
  font-size: var(--fs-sm);
  color: var(--text-primary);
  user-select: all;
}

.tfs__error {
  margin: var(--space-2) 0 0;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-sm);
  font-size: var(--fs-xs);
  background: var(--danger-subtle);
  border: 1px solid var(--danger);
  color: var(--danger);
}

.tfs__actions {
  display: flex;
  gap: var(--space-2);
  justify-content: flex-end;
  margin-top: var(--space-4);
}
.tfs__actions--left {
  justify-content: flex-start;
  margin-top: var(--space-2);
}
</style>
