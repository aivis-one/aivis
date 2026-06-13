<script setup lang="ts">
// =============================================================================
// CBSHOME Frontend -- AgentSettingsView (Task 3 Block D, Phase F6.2)
// =============================================================================
//
// Reached from the More tab (AgentMoreView -> Settings tile). Replaces
// the F6.2 stub. Kept deliberately thin (decision in chat):
//   1. Profile card -- avatar / name / email / role badge. READ-ONLY,
//      same scope as InvestorSettingsView (no name/phone/locale edit).
//   2. Payout details -- preview (JSON) + add/edit via a bottom-sheet
//      JSON editor (GET/PUT /users/me/payout-details). This is the
//      payout home for the agent: AgentBalanceView only reads it as a
//      gate and links here (decision B). Editor pattern lifted from
//      CompanyBalanceView.
//   3. Sign out -- authStore.logout then /login, with a double-click
//      guard.
//
// DELIBERATELY ABSENT.
//   - Agent-application section: the user is already an agent, so the
//     investor "become an agent" state machine is meaningless here.
//   - Theme / marketing toggles: out of this thin scope (decided in
//     chat); they remain investor-side until an agent need appears.
//
// FP notes:
//   FP-19 -- shell owns the header; inline sett__page-header h1.
//   FP-20 -- /agent/settings is a SUB-ROUTE (not in AGENT_TABS), so a
//            CBackLink is mandatory -- consistent with ReferralsView /
//            LeaderboardView. goBack is history-aware, falling through
//            to the More tab on a cold deep-link.
//   FP-18 -- the back fallback navigates via safeNavigate (router.back
//            is neither push nor replace, so it stays bare).
//   FP-15 -- role badge rendered via tOrRaw.
// =============================================================================

import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ChevronRight, CreditCard, LogOut, Pencil } from 'lucide-vue-next'

import {
  CAvatar,
  CBackLink,
  CBottomSheet,
  CButton,
  CLoader,
} from '@/components/ui'
import { useAuthStore } from '@/stores/auth'
import { getPayoutDetails, updatePayoutDetails } from '@/api/users'
import { useToast } from '@/composables/useToast'
import { safeNavigate } from '@/composables/safeNavigate'
import { tOrRaw } from '@/utils/i18n'

const router = useRouter()
const { t } = useI18n()
const authStore = useAuthStore()
const { showToast } = useToast()

// ---------------------------------------------------------------------------
// Profile read-outs (derived from authStore.user)
// ---------------------------------------------------------------------------

function _profile(): Record<string, unknown> {
  const p = authStore.user?.profile
  return p && typeof p === 'object' ? (p as Record<string, unknown>) : {}
}

const fullName = computed<string>(() => {
  const p = _profile()
  const first = typeof p.first_name === 'string' ? p.first_name : ''
  const last = typeof p.last_name === 'string' ? p.last_name : ''
  const name = [first, last].filter(Boolean).join(' ').trim()
  return name || t('agent.settings.unnamed')
})

const email = computed<string>(() => authStore.user?.email ?? '')

const roleLabel = computed<string>(() => {
  const role = authStore.user?.role ?? 'agent'
  return tOrRaw(t, `agent.settings.role.${role}`, role)
})

const avatarUrl = computed<string | undefined>(() => {
  const v = _profile().avatar_url
  return typeof v === 'string' && v.length > 0 ? v : undefined
})

// ---------------------------------------------------------------------------
// Payout details
// ---------------------------------------------------------------------------

const payoutDetails = ref<Record<string, unknown> | null>(null)
const payoutLoading = ref(false)
const payoutLoaded = ref(false)
const payoutErrored = ref(false)
const payoutEpoch = ref(0)

async function fetchPayoutDetails(): Promise<void> {
  const epoch = ++payoutEpoch.value
  payoutLoading.value = true
  payoutErrored.value = false
  try {
    const resp = await getPayoutDetails()
    if (epoch !== payoutEpoch.value) return
    payoutDetails.value = resp.payout_details ?? null
    payoutLoaded.value = true
  } catch {
    if (epoch === payoutEpoch.value) payoutErrored.value = true
  } finally {
    if (epoch === payoutEpoch.value) payoutLoading.value = false
  }
}

const hasPayoutDetails = computed(() => {
  const d = payoutDetails.value
  return !!d && Object.keys(d).length > 0
})

const payoutDetailsJson = computed(() =>
  payoutDetails.value ? JSON.stringify(payoutDetails.value, null, 2) : '',
)

// -- Payout edit sheet --
const payoutSheetOpen = ref(false)
const payoutEditInput = ref('')
const payoutSubmitting = ref(false)
const payoutError = ref('')

const payoutValidation = computed<true | 'json' | 'object' | null>(() => {
  const raw = payoutEditInput.value.trim()
  if (!raw) return null
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return 'json'
  }
  if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
    return 'object'
  }
  return true
})

const payoutValidationKey = computed<string | null>(() => {
  const v = payoutValidation.value
  if (v === 'json') return 'agent.settings.payout.form.errorJson'
  if (v === 'object') return 'agent.settings.payout.form.errorObject'
  return null
})

const canSubmitPayout = computed(() => {
  if (payoutSubmitting.value) return false
  return payoutValidation.value === true
})

function openPayoutSheet(): void {
  payoutEditInput.value = hasPayoutDetails.value
    ? JSON.stringify(payoutDetails.value, null, 2)
    : ''
  payoutError.value = ''
  payoutSheetOpen.value = true
}

function closePayoutSheet(): void {
  payoutSheetOpen.value = false
}

async function submitPayout(): Promise<void> {
  if (!canSubmitPayout.value) return
  const parsed = JSON.parse(payoutEditInput.value) as Record<string, unknown>
  payoutSubmitting.value = true
  payoutError.value = ''
  try {
    await updatePayoutDetails(parsed)
    showToast(t('agent.settings.payout.form.successToast'), 'success')
    closePayoutSheet()
    await fetchPayoutDetails()
  } catch (err) {
    payoutError.value =
      err instanceof Error && err.message
        ? err.message
        : t('agent.settings.payout.form.error')
  } finally {
    payoutSubmitting.value = false
  }
}

watch(payoutSheetOpen, (open) => {
  if (!open) {
    payoutEditInput.value = ''
    payoutError.value = ''
  }
})

// ---------------------------------------------------------------------------
// Navigation + logout
// ---------------------------------------------------------------------------

function goBack(): void {
  // History-aware (the More tab in the wired flow); cold deep-link
  // falls through to More. router.back() is neither push nor replace,
  // so it does not need safeNavigate; the fallback push does (FP-18).
  if (window.history.state?.back) {
    router.back()
    return
  }
  void safeNavigate(
    router.push({ name: 'agent-more' }),
    '[AgentSettingsView] back fallback to agent-more',
  )
}

const loggingOut = ref(false)

async function handleLogout(): Promise<void> {
  if (loggingOut.value) return
  loggingOut.value = true
  try {
    await authStore.logout()
  } finally {
    // Auth state is cleared regardless; a benign NavigationFailure on
    // push is bounced to /login by the guard anyway.
    void safeNavigate(router.push('/login'), '[AgentSettingsView] to login')
  }
}

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

onMounted(() => {
  void fetchPayoutDetails()
})
</script>

<template>
  <div class="sett">
    <!-- Page header (FP-19 inline; FP-20 sub-route back-link) -->
    <div class="sett__page-header">
      <CBackLink :label="t('agent.settings.backLink')" @click="goBack" />
      <h1 class="sett__page-title">{{ t('agent.settings.title') }}</h1>
      <p class="sett__page-subtitle">{{ t('agent.settings.subtitle') }}</p>
    </div>

    <!-- Profile card (read-only) -->
    <section class="sett__profile">
      <CAvatar :url="avatarUrl" :name="fullName" :size="72" />
      <div class="sett__name">{{ fullName }}</div>
      <div v-if="email" class="sett__email">{{ email }}</div>
      <div class="sett__role-badge">{{ roleLabel }}</div>
    </section>

    <!-- Payout details -->
    <section class="sett__section">
      <div class="sett__section-title">
        {{ t('agent.settings.payout.title') }}
      </div>
      <p class="sett__section-desc">{{ t('agent.settings.payout.desc') }}</p>

      <div v-if="payoutLoading && !payoutLoaded" class="sett__center">
        <CLoader :size="20" />
      </div>

      <template v-else-if="payoutErrored">
        <p class="sett__empty">{{ t('agent.settings.payout.loadError') }}</p>
        <div class="sett__cta-row">
          <CButton variant="outline" size="sm" @click="fetchPayoutDetails">
            {{ t('agent.settings.payout.retry') }}
          </CButton>
        </div>
      </template>

      <template v-else>
        <p v-if="!hasPayoutDetails" class="sett__empty">
          {{ t('agent.settings.payout.empty') }}
        </p>
        <pre v-else class="sett__json">{{ payoutDetailsJson }}</pre>

        <div class="sett__cta-row">
          <CButton variant="outline" size="sm" @click="openPayoutSheet">
            <component :is="hasPayoutDetails ? Pencil : CreditCard" :size="14" />
            {{
              hasPayoutDetails
                ? t('agent.settings.payout.editButton')
                : t('agent.settings.payout.addButton')
            }}
            <ChevronRight :size="14" />
          </CButton>
        </div>
      </template>
    </section>

    <!-- Account / sign out -->
    <section class="sett__section">
      <div class="sett__section-title">
        {{ t('agent.settings.actions.title') }}
      </div>
      <button
        type="button"
        class="sett__row sett__row--clickable"
        :class="{ 'sett__row--disabled': loggingOut }"
        :disabled="loggingOut"
        @click="handleLogout"
      >
        <span class="sett__row-label sett__row-label--danger">
          <LogOut :size="16" />
          {{ t('agent.settings.actions.logout') }}
        </span>
        <ChevronRight :size="16" />
      </button>
    </section>

    <!-- Payout edit sheet -->
    <CBottomSheet
      :open="payoutSheetOpen"
      :title="t('agent.settings.payout.form.title')"
      @close="closePayoutSheet"
    >
      <form class="sett__form" @submit.prevent="submitPayout">
        <label class="sett__field">
          <span class="sett__field-label">
            {{ t('agent.settings.payout.form.label') }}
          </span>
          <textarea
            v-model="payoutEditInput"
            class="sett__textarea"
            rows="8"
            spellcheck="false"
            :placeholder="t('agent.settings.payout.form.placeholder')"
            :disabled="payoutSubmitting"
          ></textarea>
          <span class="sett__field-hint">
            {{ t('agent.settings.payout.form.hint') }}
          </span>
        </label>

        <p
          v-if="payoutValidationKey"
          class="sett__form-error sett__form-error--soft"
        >
          {{ t(payoutValidationKey) }}
        </p>

        <p v-if="payoutError" class="sett__form-error">{{ payoutError }}</p>

        <div class="sett__form-actions">
          <CButton
            variant="outline"
            type="button"
            :disabled="payoutSubmitting"
            @click="closePayoutSheet"
          >
            {{ t('agent.settings.payout.form.cancel') }}
          </CButton>
          <CButton
            variant="primary"
            type="submit"
            :disabled="!canSubmitPayout"
            :loading="payoutSubmitting"
          >
            {{ t('agent.settings.payout.form.submit') }}
          </CButton>
        </div>
      </form>
    </CBottomSheet>
  </div>
</template>

<style scoped>
.sett {
  display: flex;
  flex-direction: column;
  padding-bottom: 24px;
}

.sett__page-header {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 16px 16px 0;
}
.sett__page-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--text);
  margin: 8px 0 0;
}
.sett__page-subtitle {
  font-size: 14px;
  color: var(--text-secondary);
  margin: 0;
}

.sett__center {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}

/* Profile card */
.sett__profile {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 20px 16px 24px;
  gap: 6px;
}
.sett__name {
  font-size: 18px;
  font-weight: 700;
  color: var(--text);
  margin-top: 6px;
}
.sett__email {
  font-size: 13px;
  color: var(--text-secondary);
}
.sett__role-badge {
  display: inline-block;
  margin-top: 6px;
  font-size: 11px;
  font-weight: 600;
  padding: 4px 10px;
  border-radius: var(--radius-sm);
  background: var(--bg-elevated);
  color: var(--primary);
  text-transform: capitalize;
}

/* Section */
.sett__section {
  padding: 0 16px;
  margin-bottom: 20px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.sett__section-title {
  font-size: 12px;
  font-weight: 700;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.12em;
  padding: 0 4px;
}
.sett__section-desc {
  font-size: 12px;
  color: var(--text-secondary);
  margin: 0;
  padding: 0 4px;
}

.sett__empty {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0;
  padding: 16px;
  border-radius: var(--radius);
  background: var(--bg-elevated, var(--bg));
  border: 1px dashed var(--border);
  text-align: center;
}

.sett__json {
  margin: 0;
  padding: 12px 14px;
  background: var(--bg-subtle, var(--bg));
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
  color: var(--text-secondary);
  overflow-x: auto;
  white-space: pre;
  line-height: 1.5;
}

.sett__cta-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

/* Row (clickable button) */
.sett__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  min-height: 48px;
  width: 100%;
  background: var(--bg-elevated, var(--bg));
  font: inherit;
  color: inherit;
  text-align: left;
  cursor: pointer;
  transition: background 0.15s;
}
.sett__row--clickable:hover {
  background: var(--bg-subtle);
}
.sett__row--disabled {
  opacity: 0.6;
  pointer-events: none;
}
.sett__row-label {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: var(--text);
}
.sett__row-label--danger {
  color: var(--danger, #dc2626);
  font-weight: 600;
}

/* Payout form */
.sett__form { display: flex; flex-direction: column; gap: 14px; }
.sett__field { display: flex; flex-direction: column; gap: 6px; }
.sett__field-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.sett__field-hint {
  font-size: 11px;
  color: var(--text-tertiary);
  line-height: 1.4;
}
.sett__textarea {
  width: 100%;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: var(--bg);
  color: var(--text);
  font-size: 13px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  line-height: 1.5;
  resize: vertical;
  min-height: 160px;
  transition: border-color 0.15s;
}
.sett__textarea:focus { outline: none; border-color: var(--primary); }
.sett__textarea:disabled { opacity: 0.6; cursor: not-allowed; }

.sett__form-error {
  margin: 0;
  padding: 8px 12px;
  border-radius: var(--radius-sm);
  font-size: 12px;
  background: var(--danger-dim, rgba(220, 38, 38, 0.08));
  border: 1px solid var(--danger, #dc2626);
  color: var(--danger, #dc2626);
}
.sett__form-error--soft {
  background: transparent;
  border: 1px solid var(--warning, var(--border));
  color: var(--warning, var(--text-secondary));
}

.sett__form-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  margin-top: 4px;
}
</style>
