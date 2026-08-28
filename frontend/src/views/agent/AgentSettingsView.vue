<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- AgentSettingsView (Task 3 Block D, Phase F6.2)
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

import { CAvatar, CBackLink, CBottomSheet, CButton, CLoader, CTextarea } from '@/components/ui'
import EmailChangeSection from '@/components/shared/EmailChangeSection.vue'
import ActiveSessionsSection from '@/components/shared/ActiveSessionsSection.vue'
import DeactivateAccountSection from '@/components/shared/DeactivateAccountSection.vue'
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

const payoutValidation = computed<true | 'json' | 'object' | 'empty' | null>(() => {
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
  // An empty object would save as "{}" -> hasPayoutDetails reads false
  // afterwards, leaving the withdraw gate stuck on "no payout details"
  // despite a successful save (review §6).
  if (Object.keys(parsed as Record<string, unknown>).length === 0) {
    return 'empty'
  }
  return true
})

const payoutValidationKey = computed<string | null>(() => {
  const v = payoutValidation.value
  if (v === 'json') return 'agent.settings.payout.form.errorJson'
  if (v === 'object') return 'agent.settings.payout.form.errorObject'
  if (v === 'empty') return 'agent.settings.payout.form.errorEmpty'
  return null
})

const canSubmitPayout = computed(() => {
  if (payoutSubmitting.value) return false
  return payoutValidation.value === true
})

function openPayoutSheet(): void {
  payoutEditInput.value = hasPayoutDetails.value ? JSON.stringify(payoutDetails.value, null, 2) : ''
  payoutError.value = ''
  payoutSheetOpen.value = true
}

function closePayoutSheet(): void {
  payoutSheetOpen.value = false
}

async function submitPayout(): Promise<void> {
  if (!canSubmitPayout.value) return
  // canSubmitPayout === true guarantees payoutValidation === true (the
  // input already parsed to a non-empty object), so this cannot throw --
  // kept explicit rather than relying on that invariant silently (2.7).
  let parsed: Record<string, unknown>
  try {
    parsed = JSON.parse(payoutEditInput.value) as Record<string, unknown>
  } catch {
    payoutError.value = t('agent.settings.payout.form.errorJson')
    return
  }
  payoutSubmitting.value = true
  payoutError.value = ''
  try {
    await updatePayoutDetails(parsed)
    showToast(t('agent.settings.payout.form.successToast'), 'success')
    // PUT replaces payout_details wholesale -> the submitted object IS
    // the new server state. Write it locally instead of refetching: a
    // failing refetch here would flip payoutErrored and replace the
    // just-saved details with an error screen right after the success
    // toast (review 2.4).
    payoutDetails.value = parsed
    payoutLoaded.value = true
    payoutErrored.value = false
    closePayoutSheet()
  } catch (err) {
    payoutError.value =
      err instanceof Error && err.message ? err.message : t('agent.settings.payout.form.error')
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
      <h1 class="sett__page-title">
        {{ t('agent.settings.title') }}
      </h1>
      <p class="sett__page-subtitle">
        {{ t('agent.settings.subtitle') }}
      </p>
    </div>

    <!-- Profile card (read-only) -->
    <section class="sett__profile">
      <CAvatar :url="avatarUrl" :name="fullName" :size="72" />
      <div class="sett__name">
        {{ fullName }}
      </div>
      <div v-if="email" class="sett__email">
        {{ email }}
      </div>
      <div class="sett__role-badge">
        {{ roleLabel }}
      </div>
    </section>

    <!-- Payout details -->
    <section class="sett__section">
      <div class="sett__section-title">
        {{ t('agent.settings.payout.title') }}
      </div>
      <p class="sett__section-desc">
        {{ t('agent.settings.payout.desc') }}
      </p>

      <div v-if="payoutLoading && !payoutLoaded" class="sett__center">
        <CLoader :size="20" />
      </div>

      <template v-else-if="payoutErrored">
        <p class="sett__empty">
          {{ t('agent.settings.payout.loadError') }}
        </p>
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
            <component :is="hasPayoutDetails ? Pencil : CreditCard" :size="16" />
            {{
              hasPayoutDetails
                ? t('agent.settings.payout.editButton')
                : t('agent.settings.payout.addButton')
            }}
            <ChevronRight :size="16" />
          </CButton>
        </div>
      </template>
    </section>

    <!-- Account / sign out -->
    <section class="sett__section">
      <div class="sett__section-title">
        {{ t('agent.settings.actions.title') }}
      </div>
      <EmailChangeSection tPrefix="agent.settings.actions" />
      <ActiveSessionsSection tPrefix="agent.settings.actions" />
      <DeactivateAccountSection tPrefix="agent.settings.actions" />
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
          <CTextarea
            v-model="payoutEditInput"
            class="sett__control"
            size="compact"
            mono
            :rows="8"
            spellcheck="false"
            :placeholder="t('agent.settings.payout.form.placeholder')"
            :disabled="payoutSubmitting"
          />
          <span class="sett__field-hint">
            {{ t('agent.settings.payout.form.hint') }}
          </span>
        </label>

        <p v-if="payoutValidationKey" class="sett__form-error sett__form-error--soft">
          {{ t(payoutValidationKey) }}
        </p>

        <p v-if="payoutError" class="sett__form-error">
          {{ payoutError }}
        </p>

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
  padding-bottom: var(--space-5);
}

.sett__page-header {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  padding: var(--space-4) var(--space-4) 0;
}
.sett__page-title {
  font-size: var(--fs-lg);
  font-weight: 700;
  color: var(--text-primary);
  margin: var(--space-2) 0 0;
}
.sett__page-subtitle {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  margin: 0;
}

.sett__center {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-4-lg);
}

/* Profile card */
.sett__profile {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: var(--space-4-lg) var(--space-4) var(--space-5);
  gap: var(--space-2);
}
.sett__name {
  font-size: var(--fs-h4);
  font-weight: 700;
  color: var(--text-primary);
  margin-top: var(--space-2);
}
.sett__email {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
}
.sett__role-badge {
  display: inline-block;
  margin-top: var(--space-2);
  font-size: var(--fs-xs);
  font-weight: 600;
  padding: var(--space-1) var(--space-3);
  border-radius: var(--radius-sm);
  background: var(--bg-surface);
  color: var(--primary);
  text-transform: capitalize;
}

/* Section */
.sett__section {
  padding: 0 var(--space-4);
  margin-bottom: var(--space-4-lg);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.sett__section-title {
  font-size: var(--fs-xs);
  font-weight: 700;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.12em;
  padding: 0 var(--space-1);
}
.sett__section-desc {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  margin: 0;
  padding: 0 var(--space-1);
}

.sett__empty {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  margin: 0;
  padding: var(--space-4);
  border-radius: var(--radius);
  background: var(--bg-surface);
  border: 1px dashed var(--border-default);
  text-align: center;
}

.sett__json {
  margin: 0;
  padding: var(--space-3) var(--space-4);
  background: var(--bg-subtle);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  font-family: var(--font-mono);
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  overflow-x: auto;
  white-space: pre;
  line-height: 1.5;
}

.sett__cta-row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

/* Row (clickable button) */
.sett__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  min-height: var(--size-3xl);
  width: 100%;
  background: var(--bg-surface);
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
  gap: var(--space-2);
  font-size: var(--fs-sm);
  color: var(--text-primary);
}
.sett__row-label--danger {
  color: var(--danger);
  font-weight: 600;
}

/* Payout form */
.sett__form {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}
.sett__field {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
/* See CompanyBalanceView: the flex gap is the field's rhythm. */
.sett__control {
  margin-bottom: 0;
}
.sett__control :deep(.c-textarea) {
  min-height: 160px;
}
.sett__field-label {
  font-size: var(--fs-xs);
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.sett__field-hint {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
  line-height: 1.4;
}

.sett__form-error {
  margin: 0;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-sm);
  font-size: var(--fs-xs);
  background: var(--danger-subtle);
  border: 1px solid var(--danger);
  color: var(--danger);
}
.sett__form-error--soft {
  background: transparent;
  border: 1px solid var(--warning);
  color: var(--warning);
}

.sett__form-actions {
  display: flex;
  gap: var(--space-2);
  justify-content: flex-end;
  margin-top: var(--space-1);
}
</style>
