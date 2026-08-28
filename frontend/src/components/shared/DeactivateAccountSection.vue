<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- DeactivateAccountSection (TASK-38)
// =============================================================================
//
// Shared across InvestorSettingsView / AgentSettingsView /
// CompanySettingsView's Actions section, same drop-in-row pattern as
// EmailChangeSection.vue. Backend: users/service.py::deactivate_own_account
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
import { AlertTriangle, ChevronRight } from 'lucide-vue-next'

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
    // Two different 403s can reach this flow: _require_current_password's
    // "Incorrect password" AND forbid_avatar("delete_account")'s
    // avatar-mode-blocked message -- match the backend's own exact,
    // stable text rather than mapping every 403 to "wrong password" (an
    // adversarial review caught this misleading a staff member in avatar
    // mode). Same fix in EmailChangeSection.vue.
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
  <button type="button" class="das__row" @click="openConfirm">
    <span class="das__row-label">
      <AlertTriangle :size="16" />
      {{ tk('cta') }}
    </span>
    <ChevronRight :size="16" />
  </button>

  <CModal :open="open" @close="close">
    <h3 class="das__title">
      {{ tk('title') }}
    </h3>
    <p class="das__warning">
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

    <p v-if="error" class="das__error">
      {{ error }}
    </p>

    <div class="das__actions">
      <CButton variant="outline" size="sm" :disabled="loading" @click="close">
        {{ tk('cancelBtn') }}
      </CButton>
      <CButton
        variant="danger"
        size="sm"
        :loading="loading"
        :disabled="currentPassword.length === 0"
        @click="confirm"
      >
        {{ tk('confirmBtn') }}
      </CButton>
    </div>
  </CModal>
</template>

<style scoped>
.das__row {
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
.das__row:hover {
  background: var(--bg-subtle);
}
.das__row:last-child {
  border-bottom: none;
}
.das__row-label {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--danger);
}

.das__title {
  font-size: var(--fs-h4);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 var(--space-2);
}
.das__warning {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  margin: 0 0 var(--space-4);
  line-height: 1.5;
}

.das__error {
  margin: var(--space-2) 0 0;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-sm);
  font-size: var(--fs-xs);
  background: var(--danger-subtle);
  border: 1px solid var(--danger);
  color: var(--danger);
}

.das__actions {
  display: flex;
  gap: var(--space-2);
  justify-content: flex-end;
  margin-top: var(--space-4);
}
</style>
