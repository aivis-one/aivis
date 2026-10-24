<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- DeactivateAccountSection (TASK-38)
// =============================================================================
//
// Shared across InvestorSettingsView /
// CompanySettingsView's Actions section, same drop-in-row pattern as
// TwoFactorSection.vue. Backend: users/service.py::deactivate_own_account
// -- soft/reversible (is_active=False + a "self" discriminator so
// login_email() shows honest copy instead of the staff-block
// "suspended" message), current password required, every session
// (including this one) killed server-side.
//
// No reactivate UI in this pass (see users/service.py module note) --
// on success this just signs the browser out locally and returns to
// /login, same as a normal logout. The backend has already killed the
// session by the time this call returns, so treating "success" as
// "assume logged out" is correct even though authStore.logout() itself
// fires one more (now-401) POST /auth/logout -- that call's failure is
// already ignored by authStore.logout()'s own try/catch, matching every
// other call site of that function.
// =============================================================================

import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { AlertTriangle, ChevronRight } from '@/components/ui/icons'

import { CButton, CInput, CModal } from '@/components/ui'
import { useAuthStore } from '@/stores/auth'
import { safeNavigate } from '@/composables/safeNavigate'
import { deactivateAccount } from '@/api/users'
import { ApiResponseError, ApiNetworkError, ApiTimeoutError } from '@/api/client'

const props = defineProps<{
  /** i18n prefix, e.g. "inv.settings.actions" -- keys read from `${tPrefix}.deactivate.*`. */
  tPrefix: string
}>()

const { t } = useI18n()
const authStore = useAuthStore()
const router = useRouter()

const open = ref(false)
const currentPassword = ref('')
const loading = ref(false)
const error = ref('')

function tk(key: string): string {
  return t(`${props.tPrefix}.deactivate.${key}`)
}

function openConfirm(): void {
  open.value = true
  currentPassword.value = ''
  error.value = ''
}

function close(): void {
  if (loading.value) return
  open.value = false
}

function mapError(err: unknown): string {
  if (err instanceof ApiResponseError) {
    // A project on sale cannot deactivate its account: hide or archive the
    // product first. The server answers with a code, not a wording to rely on.
    if (err.code === 'company_has_active_products') {
      return t('comp.settings.actions.deactivate.errorActiveProducts')
    }
    // Two different 403s can reach this flow: _require_current_password's
    // "Incorrect password" AND forbid_avatar("delete_account")'s
    // avatar-mode-blocked message -- match the backend's own exact,
    // stable text rather than mapping every 403 to "wrong password" (an
    // adversarial review caught this misleading a staff member in avatar
    // mode). Same fix in TwoFactorSection.vue.
    if (err.status === 403 && err.detail === 'Incorrect password') {
      return tk('errorIncorrectPassword')
    }
    if (err.status === 403 && err.detail) return err.detail
    if (err.status === 400 && err.detail) return err.detail
    return err.detail || tk('errorGeneric')
  }
  if (err instanceof ApiNetworkError) return t('auth.error.networkError')
  if (err instanceof ApiTimeoutError) return t('auth.error.timeout')
  return tk('errorGeneric')
}

async function confirm(): Promise<void> {
  if (loading.value || currentPassword.value.length === 0) return
  error.value = ''
  loading.value = true
  try {
    await deactivateAccount({ current_password: currentPassword.value })
    // Server already killed every session, this one included -- clear
    // local state and leave. authStore.logout() tolerates its own
    // POST /auth/logout 401ing (the token is already dead) the same
    // way it does for a normal sign-out.
    await authStore.logout()
    void safeNavigate(router.push('/login'), '[DeactivateAccountSection] to login')
  } catch (err) {
    error.value = mapError(err)
    loading.value = false
  }
}
</script>

<template>
  <!-- The settings row that opens the confirmation (K23); the danger tone of its
       lead box is a second sign, the title says the same in words -->
  <ul class="ds-rows">
    <li class="ds-row">
      <span class="ds-row__lead" data-tone="danger"><AlertTriangle size="sm" /></span>
      <span class="ds-row__body">
        <button type="button" class="ds-row__link" @click="openConfirm">
          <span class="ds-row__title">{{ tk('cta') }}</span>
        </button>
      </span>
      <span class="ds-row__trail"><ChevronRight size="sm" /></span>
    </li>
  </ul>

  <CModal :open="open" :title="tk('title')" @close="close">
    <p class="ds-dialog__text">
      {{ tk('warning') }}
    </p>

    <CInput
      v-model="currentPassword"
      :label="tk('passwordLabel')"
      type="password"
      autocomplete="current-password"
      :placeholder="tk('passwordPlaceholder')"
      :disabled="loading"
      @keydown.enter="confirm"
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
        :disabled="currentPassword.length === 0"
        @click="confirm"
      >
        {{ tk('confirmBtn') }}
      </CButton>
    </div>
  </CModal>
</template>
