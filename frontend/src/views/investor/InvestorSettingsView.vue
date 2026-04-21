<script setup lang="ts">
// =============================================================================
// CBSHOME Frontend -- InvestorSettingsView (Phase F4.4 B5 + B5-post)
// =============================================================================
//
// Top-level tab view mounted at /investor/settings (the InvestorShell
// already paints the tab bar). Uses CHeader with show-back=false and
// show-logo=true so the top strip matches the other top-level tabs
// (Dashboard, Portfolio, Market, Balance).
//
// SECTIONS.
//   1. Profile card -- avatar (via CAvatar, URL from profile.avatar_url
//      with initials fallback), full name, email, role badge. All
//      READ-ONLY. Per F4.4 B5 scope: personal data (name, phone,
//      country, language) is NOT editable from Settings. Any future
//      edit flow lives elsewhere (KYC re-submit, staff avatar mode).
//   2. Profile details -- phone and country, each rendered as a
//      single read-only row. Hidden if both are absent. Language is
//      intentionally omitted: locale is locked at registration and
//      the Settings page cannot change it, so showing it read-only
//      adds noise without action.
//   3. Preferences -- theme selector (3 chips: auto / light / dark,
//      driven by useTheme -- client-only, no backend round-trip) and
//      a marketing consent toggle backed by profile.marketing_consent
//      (PATCH /users/me with optimistic local flip + revert on fail).
//   4. Agent programme -- conditional block, only rendered when the
//      current user is an investor. State machine below.
//   5. Actions -- My Documents shortcut (deep link into
//      InvestorDocsView) and Sign out (authStore.logout then push
//      /login).
//
// AGENT APPLICATION STATE MACHINE.
//   fetched at mount via getMyAgentApplications (newest-first). The
//   latest row drives the section:
//     loading       -- in flight
//     load_error    -- fetch failed (B5-post). Inline retry button.
//                      Without this, a network drop left the user
//                      seeing an active "Apply" while they had a real
//                      pending application server-side; clicking
//                      caused a 409 with a generic toast. Showing the
//                      retry surface keeps the UI honest.
//     kyc_required  -- user.kyc_status != 'approved' (decision Q6 in
//                      chat). Disabled row pointing to /onboarding/kyc.
//     pending       -- latest status = pending. Disabled "under review"
//                      line, no button.
//     cooldown      -- latest status = rejected AND cooldown_until is
//                      in the future. Disabled row with N-days-left
//                      label (ceiling days to avoid "0 days left" on
//                      the last hour).
//     can_reapply   -- latest status = rejected AND cooldown expired.
//                      Active button labelled "Apply again".
//     can_apply     -- no applications on record. Active button labelled
//                      "Become an agent".
//   Approved is unreachable here: approval flips user.role to agent,
//   which removes them from the InvestorShell route guard.
//
// MARKETING CONSENT OPTIMISM.
//   toggleMarketing flips the local ref immediately, fires PATCH
//   /users/me { profile: { marketing_consent: next } }, and on success
//   calls authStore.fetchMe() so any other subscriber of user.profile
//   sees the updated value without waiting for a route change. On
//   failure the local ref reverts and a toast is shown.
//
// B5-post changes.
//   - Clickable rows rendered as <button type="button"> instead of
//     <div> so keyboard / screen-reader users can activate them.
//     Styling nullified with CSS reset (appearance, background,
//     border, font-family, text-align) to keep the visual from B5.
//   - Marketing toggle wears aria-labelledby pointing at its sibling
//     label span, so assistive tech reads "Marketing communications,
//     pressed/not pressed" rather than a bare toggle state.
//   - Dead `if (err instanceof ApiResponseError) ... else ...` branch
//     in applyForAgent removed; both arms showed the same toast.
//   - getMyAgentApplications failure now surfaces `agentLoadErrored`
//     with an inline retry row rather than silently falling through
//     to can_apply.
// =============================================================================

import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  ChevronRight,
  FileText,
  LogOut,
  Monitor,
  Moon,
  RefreshCw,
  Shield,
  Sun,
  UserPlus,
} from 'lucide-vue-next'

import {
  CAvatar,
  CButton,
  CLoader,
} from '@/components/ui'
import CHeader from '@/components/layout/CHeader.vue'
import { useAuthStore } from '@/stores/auth'
import { updateMe } from '@/api/users'
import {
  getMyAgentApplications,
  submitAgentApplication,
} from '@/api/agent-apps'
import { useTheme, type ThemeMode } from '@/composables/useTheme'
import { useToast } from '@/composables/useToast'
import { tOrRaw } from '@/utils/i18n'
import type { AgentApplicationResponse } from '@/api/types'

const { t } = useI18n()
const router = useRouter()
const authStore = useAuthStore()
const { showToast } = useToast()

// ---------------------------------------------------------------------------
// Profile read-outs (all derived from authStore.user)
// ---------------------------------------------------------------------------

function _profile(): Record<string, unknown> {
  const p = authStore.user?.profile
  return (p && typeof p === 'object') ? (p as Record<string, unknown>) : {}
}

const fullName = computed<string>(() => {
  const p = _profile()
  const first = typeof p.first_name === 'string' ? p.first_name : ''
  const last = typeof p.last_name === 'string' ? p.last_name : ''
  const name = [first, last].filter(Boolean).join(' ').trim()
  return name || t('inv.settings.unnamed')
})

const email = computed<string>(() => authStore.user?.email ?? '')

const roleLabel = computed<string>(() => {
  const role = authStore.user?.role ?? 'investor'
  // FP-15: server-driven enum -> tOrRaw with raw fallback.
  return tOrRaw(t, `inv.settings.role.${role}`, role)
})

const avatarUrl = computed<string | undefined>(() => {
  const v = _profile().avatar_url
  return typeof v === 'string' && v.length > 0 ? v : undefined
})

const phone = computed<string>(() => {
  const v = _profile().phone
  return typeof v === 'string' ? v : ''
})

const country = computed<string>(() => {
  const v = _profile().country
  return typeof v === 'string' ? v : ''
})

const hasProfileDetails = computed<boolean>(
  () => phone.value.length > 0 || country.value.length > 0,
)

// ---------------------------------------------------------------------------
// Theme (3-state chips)
// ---------------------------------------------------------------------------

const { current: themeCurrent, set: setTheme } = useTheme()

const THEME_MODES: readonly ThemeMode[] = ['auto', 'light', 'dark'] as const

// ---------------------------------------------------------------------------
// Marketing consent
// ---------------------------------------------------------------------------

const marketingConsent = ref<boolean>(
  Boolean(_profile().marketing_consent),
)
const marketingBusy = ref<boolean>(false)

async function toggleMarketing(): Promise<void> {
  if (marketingBusy.value) return
  const prev = marketingConsent.value
  const next = !prev
  marketingConsent.value = next
  marketingBusy.value = true
  try {
    await updateMe({ profile: { marketing_consent: next } })
    await authStore.fetchMe()
  } catch {
    marketingConsent.value = prev
    showToast(t('inv.settings.prefs.marketingError'), 'error')
  } finally {
    marketingBusy.value = false
  }
}

// ---------------------------------------------------------------------------
// Agent application
// ---------------------------------------------------------------------------

type AgentState =
  | 'loading'
  | 'load_error'
  | 'kyc_required'
  | 'can_apply'
  | 'pending'
  | 'cooldown'
  | 'can_reapply'

const isInvestor = computed<boolean>(
  () => authStore.user?.role === 'investor',
)
const kycApproved = computed<boolean>(
  () => authStore.user?.kyc_status === 'approved',
)

const agentApps = ref<AgentApplicationResponse[]>([])
const agentLoading = ref<boolean>(false)
const agentLoadErrored = ref<boolean>(false)
const agentSubmitting = ref<boolean>(false)

// Newest-first per backend contract (get_my_applications orders by
// created_at DESC), so items[0] is always "the latest".
const latestApp = computed<AgentApplicationResponse | null>(
  () => agentApps.value[0] ?? null,
)

const agentState = computed<AgentState>(() => {
  if (agentLoading.value) return 'loading'
  if (agentLoadErrored.value) return 'load_error'
  if (!kycApproved.value) return 'kyc_required'
  const last = latestApp.value
  if (!last) return 'can_apply'
  if (last.status === 'pending') return 'pending'
  if (last.status === 'rejected') {
    if (last.cooldown_until) {
      const until = new Date(last.cooldown_until).getTime()
      if (!Number.isNaN(until) && Date.now() < until) return 'cooldown'
    }
    return 'can_reapply'
  }
  // Approved is unreachable in an investor shell (role would be
  // agent). Defensive fallback -- treat as can_apply so the button
  // stays visible rather than the UI going silent.
  return 'can_apply'
})

// Ceiling so a user at "22 hours remaining" sees "1 day left", never
// "0 days left".
const cooldownDaysLeft = computed<number>(() => {
  const last = latestApp.value
  if (!last?.cooldown_until) return 0
  const until = new Date(last.cooldown_until).getTime()
  if (Number.isNaN(until)) return 0
  const diff = until - Date.now()
  if (diff <= 0) return 0
  return Math.ceil(diff / (24 * 60 * 60 * 1000))
})

async function fetchAgentApps(): Promise<void> {
  if (!isInvestor.value) return
  agentLoading.value = true
  agentLoadErrored.value = false
  try {
    const resp = await getMyAgentApplications()
    agentApps.value = resp.items
  } catch {
    agentLoadErrored.value = true
  } finally {
    agentLoading.value = false
  }
}

async function applyForAgent(): Promise<void> {
  if (agentSubmitting.value) return
  agentSubmitting.value = true
  try {
    await submitAgentApplication()
    showToast(t('inv.settings.agent.submitSuccess'), 'success')
    await fetchAgentApps()
  } catch {
    // Backend currently surfaces 400 (cooldown / role mismatch) and
    // 409 (pending already exists). The UI has already gated those
    // states, so hitting them means the local state was stale.
    // Single generic toast -- no benefit to narrowing ApiResponseError
    // vs. network error in the UX.
    showToast(t('inv.settings.agent.submitError'), 'error')
  } finally {
    agentSubmitting.value = false
  }
}

// ---------------------------------------------------------------------------
// Navigation helpers
// ---------------------------------------------------------------------------

function goKyc(): void {
  void router.push('/onboarding/kyc')
}

function goDocs(): void {
  void router.push({ name: 'investor-docs' })
}

const loggingOut = ref<boolean>(false)

async function handleLogout(): Promise<void> {
  if (loggingOut.value) return
  loggingOut.value = true
  try {
    await authStore.logout()
  } finally {
    void router.push('/login')
  }
}

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

onMounted(() => {
  void fetchAgentApps()
})
</script>

<template>
  <div class="sett">
    <CHeader
      :show-back="false"
      :show-logo="true"
      :title="t('inv.settings.title')"
    />

    <!-- Profile card -->
    <section class="sett__profile">
      <CAvatar :url="avatarUrl" :name="fullName" :size="72" />
      <div class="sett__name">{{ fullName }}</div>
      <div v-if="email" class="sett__email">{{ email }}</div>
      <div class="sett__role-badge">{{ roleLabel }}</div>
    </section>

    <!-- Profile details (read-only) -->
    <section v-if="hasProfileDetails" class="sett__section">
      <div class="sett__section-title">
        {{ t('inv.settings.profile.title') }}
      </div>
      <div v-if="phone" class="sett__row">
        <span class="sett__row-label">
          {{ t('inv.settings.profile.phone') }}
        </span>
        <span class="sett__row-value">{{ phone }}</span>
      </div>
      <div v-if="country" class="sett__row">
        <span class="sett__row-label">
          {{ t('inv.settings.profile.country') }}
        </span>
        <span class="sett__row-value">{{ country }}</span>
      </div>
    </section>

    <!-- Preferences -->
    <section class="sett__section">
      <div class="sett__section-title">
        {{ t('inv.settings.prefs.title') }}
      </div>

      <!-- Theme chips -->
      <div class="sett__row sett__row--block">
        <span class="sett__row-label">
          {{ t('inv.settings.prefs.theme') }}
        </span>
        <div class="sett__chips">
          <button
            v-for="mode in THEME_MODES"
            :key="mode"
            type="button"
            class="sett__chip"
            :class="{ 'sett__chip--active': themeCurrent === mode }"
            @click="setTheme(mode)"
          >
            <Monitor v-if="mode === 'auto'" :size="14" />
            <Sun v-else-if="mode === 'light'" :size="14" />
            <Moon v-else :size="14" />
            {{ t(`inv.settings.prefs.themeValue.${mode}`) }}
          </button>
        </div>
      </div>

      <!-- Marketing consent -->
      <div class="sett__row">
        <span id="marketing-consent-label" class="sett__row-label">
          {{ t('inv.settings.prefs.marketing') }}
        </span>
        <button
          type="button"
          class="sett__toggle"
          :class="{ 'sett__toggle--active': marketingConsent }"
          :disabled="marketingBusy"
          :aria-pressed="marketingConsent"
          aria-labelledby="marketing-consent-label"
          @click="toggleMarketing"
        />
      </div>
    </section>

    <!-- Agent programme -->
    <section v-if="isInvestor" class="sett__section">
      <div class="sett__section-title">
        {{ t('inv.settings.agent.title') }}
      </div>

      <!-- Loading -->
      <div v-if="agentState === 'loading'" class="sett__center">
        <CLoader :size="20" />
      </div>

      <!-- Load error with retry -->
      <button
        v-else-if="agentState === 'load_error'"
        type="button"
        class="sett__row sett__row--clickable"
        @click="fetchAgentApps"
      >
        <span class="sett__row-label sett__row-label--muted">
          <RefreshCw :size="16" />
          {{ t('inv.settings.agent.loadError') }}
        </span>
        <span class="sett__row-label sett__row-label--accent">
          {{ t('common.retry') }}
        </span>
      </button>

      <!-- KYC required -->
      <button
        v-else-if="agentState === 'kyc_required'"
        type="button"
        class="sett__row sett__row--clickable"
        @click="goKyc"
      >
        <span class="sett__row-label sett__row-label--accent">
          <Shield :size="16" />
          {{ t('inv.settings.agent.kycRequired') }}
        </span>
        <ChevronRight :size="16" />
      </button>

      <!-- Pending review -->
      <div v-else-if="agentState === 'pending'" class="sett__row">
        <span class="sett__row-label sett__row-label--muted">
          <UserPlus :size="16" />
          {{ t('inv.settings.agent.pending') }}
        </span>
      </div>

      <!-- Cooldown active -->
      <div v-else-if="agentState === 'cooldown'" class="sett__row">
        <span class="sett__row-label sett__row-label--muted">
          <UserPlus :size="16" />
          {{ t('inv.settings.agent.cooldown', { days: cooldownDaysLeft }) }}
        </span>
      </div>

      <!-- Can apply / reapply -->
      <div v-else class="sett__row sett__row--block">
        <CButton
          variant="primary"
          size="default"
          :loading="agentSubmitting"
          @click="applyForAgent"
        >
          <UserPlus :size="16" />
          {{
            agentState === 'can_reapply'
              ? t('inv.settings.agent.reapply')
              : t('inv.settings.agent.apply')
          }}
        </CButton>
      </div>
    </section>

    <!-- Actions -->
    <section class="sett__section">
      <div class="sett__section-title">
        {{ t('inv.settings.actions.title') }}
      </div>

      <button
        type="button"
        class="sett__row sett__row--clickable"
        @click="goDocs"
      >
        <span class="sett__row-label sett__row-label--accent">
          <FileText :size="16" />
          {{ t('inv.settings.actions.docs') }}
        </span>
        <ChevronRight :size="16" />
      </button>

      <button
        type="button"
        class="sett__row sett__row--clickable"
        :class="{ 'sett__row--disabled': loggingOut }"
        :disabled="loggingOut"
        @click="handleLogout"
      >
        <span class="sett__row-label sett__row-label--danger">
          <LogOut :size="16" />
          {{ t('inv.settings.actions.logout') }}
        </span>
        <ChevronRight :size="16" />
      </button>
    </section>
  </div>
</template>

<style scoped>
.sett {
  display: flex;
  flex-direction: column;
  padding-bottom: 24px;
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
}
.sett__section-title {
  font-size: 12px;
  font-weight: 700;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.12em;
  margin-bottom: 8px;
  padding: 0 4px;
}

/*
 * Row. Rendered either as <div> (read-only) or <button type="button">
 * (clickable). Shared CSS -- the button variant needs a reset to
 * erase default button chrome (background, border, font, text-align)
 * so the visual stays identical to the div variant from B5.
 */
.sett__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--border);
  min-height: 48px;
}
.sett__row:last-child {
  border-bottom: none;
}
button.sett__row {
  width: 100%;
  background: transparent;
  border: 0;
  border-bottom: 1px solid var(--border);
  font: inherit;
  color: inherit;
  text-align: left;
  cursor: pointer;
}
button.sett__row:last-child {
  border-bottom: none;
}

.sett__row--block {
  flex-wrap: wrap;
  align-items: stretch;
}
.sett__row--clickable {
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
.sett__row-label--accent {
  color: var(--primary);
  font-weight: 600;
}
.sett__row-label--muted {
  color: var(--text-secondary);
}
.sett__row-label--danger {
  color: var(--danger, #DC2626);
  font-weight: 600;
}
.sett__row-value {
  font-size: 13px;
  color: var(--text-tertiary);
  text-align: right;
}

/* Theme chips */
.sett__chips {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.sett__chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 6px 10px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: var(--bg);
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  font-family: inherit;
  transition: border-color 0.15s, color 0.15s, background 0.15s;
}
.sett__chip:hover {
  border-color: var(--primary-light);
  color: var(--text);
}
.sett__chip--active {
  background: var(--primary);
  border-color: var(--primary);
  color: #fff;
}

/* Toggle switch */
.sett__toggle {
  width: 44px;
  height: 24px;
  background: var(--border);
  border-radius: 12px;
  position: relative;
  cursor: pointer;
  transition: background 0.2s, opacity 0.2s;
  border: none;
  padding: 0;
  flex-shrink: 0;
}
.sett__toggle::after {
  content: '';
  position: absolute;
  width: 20px;
  height: 20px;
  background: #fff;
  border-radius: 50%;
  top: 2px;
  left: 2px;
  transition: transform 0.2s;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
}
.sett__toggle--active {
  background: var(--primary);
}
.sett__toggle--active::after {
  transform: translateX(20px);
}
.sett__toggle:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
