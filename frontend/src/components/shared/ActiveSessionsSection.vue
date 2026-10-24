<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- ActiveSessionsSection (TASK-38)
// =============================================================================
//
// Shared across InvestorSettingsView /
// CompanySettingsView's Actions section, same drop-in-row pattern as
// TwoFactorSection.vue / DeactivateAccountSection.vue. Unlike those
// two this is not a wizard -- opening the row fetches and shows a
// LIST (GET /api/v1/auth/sessions), each row revocable individually
// (DELETE /api/v1/auth/sessions/{session_id}) with an inline confirm
// step instead of a nested modal.
//
// session_id is NEVER the bearer token -- see api/auth.ts and
// backend/app/modules/auth/service.py's "PUBLIC SESSION ID" module
// note for the exact non-reversible mechanism. This component never
// receives or handles a raw token; it only ever sees the ids and
// metadata the backend already stripped down to.
//
// The caller's own current session is marked is_current by the
// backend (computed server-side against the Authorization header that
// made the request) and rendered with NO Revoke button -- ending it
// here would be functionally identical to /logout, but there is no
// reason to offer two different controls for the same action in one
// screen. The backend endpoint itself still permits it (see
// auth/router.py's auth_revoke_session docstring) for any other client
// that calls it directly; this UI just never exposes that path.
//
// ERROR MAPPING mirrors DeactivateAccountSection.vue's
// shape for the list fetch (network/timeout -> shared auth.error.*
// strings). Revoke adds its own two backend-specific cases: 404 (the
// session was already gone -- another tab revoked it, or it expired
// between list and click; treated as success, not an error, since the
// end state the user wanted is already true) and 403 (avatar mode,
// forbid_avatar("revoke_session") -- see avatar_guard.py's
// revoke_session note; matched on the backend's exact message text,
// same discipline as the sibling sections' 403-vs-wrong-password fix).
// =============================================================================

import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { AlertTriangle, ChevronRight, Monitor, RefreshCw } from '@/components/ui/icons'

import { CBadge, CButton, CEmptyState, CModal } from '@/components/ui'
import { listSessions, revokeSession } from '@/api/auth'
import { ApiResponseError, ApiNetworkError, ApiTimeoutError } from '@/api/client'
import { useToast } from '@/composables/useToast'
import { formatDateTime } from '@/utils/format'
import { tOrRaw } from '@/utils/i18n'
import type { SessionItemResponse } from '@/api/types'

const props = defineProps<{
  /** i18n prefix, e.g. "inv.settings.actions" -- keys read from `${tPrefix}.sessions.*`. */
  tPrefix: string
}>()

const { t, locale } = useI18n()
const { showToast } = useToast()

const open = ref(false)
const loading = ref(false)
const loadError = ref(false)
const sessions = ref<SessionItemResponse[]>([])

// Per-row revoke state -- session_id of the row currently showing the
// inline confirm step / mid-flight, and the last action error (shown
// under that row only, cleared on the next attempt or on close).
const confirmingId = ref<string | null>(null)
const revokingId = ref<string | null>(null)
const actionError = ref('')

function tk(key: string, params?: Record<string, unknown>): string {
  return params
    ? t(`${props.tPrefix}.sessions.${key}`, params)
    : t(`${props.tPrefix}.sessions.${key}`)
}

function authMethodLabel(method: string): string {
  return tOrRaw(t, `${props.tPrefix}.sessions.authMethod.${method}`, method)
}

async function fetchSessions(): Promise<void> {
  loading.value = true
  loadError.value = false
  try {
    const resp = await listSessions()
    sessions.value = resp.items
  } catch {
    loadError.value = true
  } finally {
    loading.value = false
  }
}

function openSessions(): void {
  open.value = true
  confirmingId.value = null
  actionError.value = ''
  void fetchSessions()
}

function close(): void {
  if (revokingId.value) return
  open.value = false
}

function askRevoke(sessionId: string): void {
  actionError.value = ''
  confirmingId.value = sessionId
}

function cancelRevoke(): void {
  confirmingId.value = null
}

function mapRevokeError(err: unknown): string {
  if (err instanceof ApiResponseError) {
    if (err.status === 403 && err.detail) return err.detail
    if (err.status === 400 && err.detail) return err.detail
    return err.detail || tk('errorGeneric')
  }
  if (err instanceof ApiNetworkError) return t('auth.error.networkError')
  if (err instanceof ApiTimeoutError) return t('auth.error.timeout')
  return tk('errorGeneric')
}

async function confirmRevoke(sessionId: string): Promise<void> {
  if (revokingId.value) return
  actionError.value = ''
  revokingId.value = sessionId
  try {
    await revokeSession(sessionId)
    sessions.value = sessions.value.filter((s) => s.session_id !== sessionId)
    confirmingId.value = null
    showToast(tk('revokeSuccess'), 'success')
  } catch (err) {
    // 404 -- the session was already gone by the time this fired
    // (revoked from another tab, or it just expired). The end state
    // the user wanted (that session is dead) already holds, so this
    // is treated as success rather than surfaced as a failure.
    if (err instanceof ApiResponseError && err.status === 404) {
      sessions.value = sessions.value.filter((s) => s.session_id !== sessionId)
      confirmingId.value = null
      showToast(tk('revokeSuccess'), 'success')
    } else {
      actionError.value = mapRevokeError(err)
    }
  } finally {
    revokingId.value = null
  }
}
</script>

<template>
  <!-- The settings row that opens the window (K23) -->
  <ul class="ds-rows">
    <li class="ds-row">
      <span class="ds-row__lead"><Monitor size="sm" /></span>
      <span class="ds-row__body">
        <button type="button" class="ds-row__link" @click="openSessions">
          <span class="ds-row__title">{{ tk('cta') }}</span>
        </button>
      </span>
      <span class="ds-row__trail"><ChevronRight size="sm" /></span>
    </li>
  </ul>

  <CModal :open="open" :title="tk('title')" @close="close">
    <div v-if="loading" aria-busy="true">
      <span class="ds-sr-only" role="status">{{ t('common.loading') }}</span>
      <div class="ds-rows" aria-hidden="true">
        <div v-for="n in 3" :key="n" class="ds-skeleton-row">
          <span class="ds-skeleton ds-skeleton--avatar" /><span class="ds-skeleton-stack"
            ><span class="ds-skeleton ds-skeleton--title" /><span
              class="ds-skeleton ds-skeleton--text"
          /></span>
        </div>
      </div>
    </div>

    <CEmptyState v-else-if="loadError" tone="danger" :title="tk('loadError')">
      <template #actions>
        <CButton variant="outline" size="sm" inline @click="fetchSessions">
          <RefreshCw size="sm" />
          {{ tk('retry') }}
        </CButton>
      </template>
    </CEmptyState>

    <ul v-else class="ds-rows">
      <li v-for="item in sessions" :key="item.session_id" class="ds-row">
        <span class="ds-row__body">
          <span class="ds-row__title">{{ authMethodLabel(item.auth_method) }}</span>
          <span v-if="item.ip || item.user_agent" class="ds-row__meta">
            {{ [item.ip, item.user_agent].filter(Boolean).join(' · ') }}
          </span>
          <span class="ds-row__meta">
            {{ tk('createdAt', { date: formatDateTime(item.created_at, locale) }) }}
          </span>
          <span v-if="confirmingId === item.session_id" class="ds-row__meta">
            {{ tk('revokeConfirmTitle') }}
          </span>
        </span>

        <span class="ds-row__trail">
          <CBadge v-if="item.is_current" variant="primary" :text="tk('current')" />
          <template v-else-if="confirmingId === item.session_id">
            <CButton
              variant="outline"
              size="sm"
              inline
              :disabled="revokingId === item.session_id"
              @click="cancelRevoke"
            >
              {{ tk('cancelBtn') }}
            </CButton>
            <CButton
              variant="danger"
              size="sm"
              inline
              :loading="revokingId === item.session_id"
              @click="confirmRevoke(item.session_id)"
            >
              {{ tk('confirmBtn') }}
            </CButton>
          </template>
          <CButton v-else variant="outline" size="sm" inline @click="askRevoke(item.session_id)">
            {{ tk('revokeBtn') }}
          </CButton>
        </span>
      </li>
    </ul>

    <div v-if="actionError" class="ds-alert ds-alert--danger" role="alert">
      <span class="ds-alert__icon" aria-hidden="true"><AlertTriangle size="sm" /></span>
      <div class="ds-alert__content">
        <p class="ds-alert__text">{{ actionError }}</p>
      </div>
    </div>
  </CModal>
</template>
