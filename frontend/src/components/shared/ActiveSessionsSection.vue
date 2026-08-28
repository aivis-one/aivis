<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- ActiveSessionsSection (TASK-38)
// =============================================================================
//
// Shared across InvestorSettingsView / AgentSettingsView /
// CompanySettingsView's Actions section, same drop-in-row pattern as
// EmailChangeSection.vue / DeactivateAccountSection.vue. Unlike those
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
// ERROR MAPPING mirrors EmailChangeSection.vue / DeactivateAccountSection.vue's
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
import { ChevronRight, Monitor, RefreshCw } from 'lucide-vue-next'

import { CButton, CLoader, CModal } from '@/components/ui'
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
  return params ? t(`${props.tPrefix}.sessions.${key}`, params) : t(`${props.tPrefix}.sessions.${key}`)
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
  <button type="button" class="sas__row" @click="openSessions">
    <span class="sas__row-label">
      <Monitor :size="16" />
      {{ tk('cta') }}
    </span>
    <ChevronRight :size="16" />
  </button>

  <CModal :open="open" @close="close">
    <h3 class="sas__title">
      {{ tk('title') }}
    </h3>

    <div v-if="loading" class="sas__center">
      <CLoader :size="24" />
    </div>

    <div v-else-if="loadError" class="sas__center sas__center--column">
      <p class="sas__load-error">
        {{ tk('loadError') }}
      </p>
      <CButton variant="outline" size="sm" inline @click="fetchSessions">
        <RefreshCw :size="14" />
        {{ tk('retry') }}
      </CButton>
    </div>

    <ul v-else class="sas__list">
      <li v-for="item in sessions" :key="item.session_id" class="sas__item">
        <div class="sas__item-info">
          <span class="sas__item-method">
            <span v-if="item.is_current" class="sas__current-badge">{{ tk('current') }}</span>
            <template v-else>{{ authMethodLabel(item.auth_method) }}</template>
          </span>
          <span v-if="item.ip || item.user_agent" class="sas__item-meta">
            {{ [item.ip, item.user_agent].filter(Boolean).join(' · ') }}
          </span>
          <span class="sas__item-date">
            {{ tk('createdAt', { date: formatDateTime(item.created_at, locale) }) }}
          </span>
        </div>

        <div v-if="!item.is_current" class="sas__item-actions">
          <template v-if="confirmingId === item.session_id">
            <span class="sas__confirm-label">{{ tk('revokeConfirmTitle') }}</span>
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
        </div>
      </li>
    </ul>

    <p v-if="actionError" class="sas__error">
      {{ actionError }}
    </p>
  </CModal>
</template>

<style scoped>
.sas__row {
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
.sas__row:hover {
  background: var(--bg-subtle);
}
.sas__row:last-child {
  border-bottom: none;
}
.sas__row-label {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--primary);
}

.sas__title {
  font-size: var(--fs-h4);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 var(--space-4);
}

.sas__center {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-5) 0;
}
.sas__center--column {
  flex-direction: column;
  gap: var(--space-3);
}
.sas__load-error {
  margin: 0;
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  text-align: center;
}

.sas__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
}
.sas__item {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-3) 0;
  border-bottom: 1px solid var(--border-default);
}
.sas__item:last-child {
  border-bottom: none;
}
.sas__item-info {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}
.sas__item-method {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--text-primary);
}
.sas__current-badge {
  font-size: var(--fs-2xs, 0.6875rem);
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  padding: 2px var(--space-2);
  border-radius: var(--radius-sm);
  background: var(--primary);
  color: var(--on-primary);
}
.sas__item-meta {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  word-break: break-word;
}
.sas__item-date {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
}
.sas__item-actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap;
}
.sas__confirm-label {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  flex: 1 1 100%;
}

.sas__error {
  margin: var(--space-3) 0 0;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-sm);
  font-size: var(--fs-xs);
  background: var(--danger-subtle);
  border: 1px solid var(--danger);
  color: var(--danger);
}
</style>
