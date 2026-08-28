<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- InvestorSettingsView (Phase F4.4 B5 + B5-post + B6)
// =============================================================================
//
// Reached via the More tab (tab bar -> /investor/more -> Settings tile).
// Not itself a tab -- the tab bar's "More" slot points at MoreView.
// InvestorShell already renders CHeader for every /investor/* route, so
// this view MUST NOT add its own. The B5 revision shipped a nested
// <CHeader> which doubled the top bar once MoreView started linking
// here in B6; fixed in B6 by dropping that nested header and using the
// inline page-header pattern from MarketView / TransactionsView (<h1>
// + <p>).
//
// SECTIONS.
//   1. Profile card -- avatar (via CAvatar, URL from profile.avatar_url
//      with initials fallback), full name, email, role badge. Avatar,
//      email and role stay READ-ONLY here.
//   2. Profile details -- phone, country and language, plus an edit
//      pencil that opens the profile form modal (TASK-38 item 3).
//
//      TASK-38 UPDATE (supersedes the old F4.4 B5 ruling below): name /
//      phone / country / language are now self-service editable. The old
//      scope note read "personal data ... is NOT editable from Settings
//      ... locale is locked at registration and the Settings page cannot
//      change it" -- that was a frontend-only gap, not a backend
//      constraint: PATCH /api/v1/users/me already accepted `profile`
//      (first_name/last_name/phone/country, TD-024 whitelist in
//      users/service.py) and `language` (a plain, NOT NULL User column)
//      for every role. This view now exposes the missing editor. See the
//      "Profile: self-service edit" block below for the diff-and-submit
//      logic -- same shape as CompanySettingsView's TASK-30 W1 pattern.
//
//      Saving a language change ALSO calls the shared `setLocale()` (the
//      same function CAppControls' header picker uses) right after a
//      successful PATCH, so the current tab's UI switches immediately
//      instead of only taking effect on the next login -- keeping the
//      persisted `user.language` and the live session locale in sync
//      rather than leaving a saved-but-invisible change (see CAppControls'
//      own header comment: "the locale was set exclusively from
//      `user.language` at login").
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
  Pencil,
  RefreshCw,
  Shield,
  Sun,
  UserPlus,
} from 'lucide-vue-next'

import { CAvatar, CButton, CInput, CLoader, CModal, CSelect } from '@/components/ui'
import EmailChangeSection from '@/components/shared/EmailChangeSection.vue'
import ActiveSessionsSection from '@/components/shared/ActiveSessionsSection.vue'
import DeactivateAccountSection from '@/components/shared/DeactivateAccountSection.vue'
import { useAuthStore } from '@/stores/auth'
import { updateMe } from '@/api/users'
import { getMyAgentApplications, submitAgentApplication } from '@/api/agent-apps'
import { useTheme, type ThemeMode } from '@/composables/useTheme'
import { useToast } from '@/composables/useToast'
import { safeNavigate } from '@/composables/safeNavigate'
import { tOrRaw } from '@/utils/i18n'
import { setLocale } from '@/i18n'
import { SUPPORTED_LOCALES } from '@/i18n/locales.config'
import { COUNTRIES } from '@/utils/countries'
import { ApiResponseError } from '@/api/client'
import type { AgentApplicationResponse, UserUpdate } from '@/api/types'

const { t } = useI18n()
const router = useRouter()
const authStore = useAuthStore()
const { showToast } = useToast()

// ---------------------------------------------------------------------------
// Profile read-outs (all derived from authStore.user)
// ---------------------------------------------------------------------------

function _profile(): Record<string, unknown> {
  const p = authStore.user?.profile
  return p && typeof p === 'object' ? (p as Record<string, unknown>) : {}
}

const firstName = computed<string>(() => {
  const v = _profile().first_name
  return typeof v === 'string' ? v : ''
})

const lastName = computed<string>(() => {
  const v = _profile().last_name
  return typeof v === 'string' ? v : ''
})

const fullName = computed<string>(() => {
  const name = [firstName.value, lastName.value].filter(Boolean).join(' ').trim()
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

const countryLabel = computed<string>(() => {
  const code = country.value
  if (!code) return t('inv.settings.profile.notSet')
  return COUNTRIES.find((c) => c.value === code)?.label ?? code
})

const phoneDisplay = computed<string>(() => phone.value || t('inv.settings.profile.notSet'))

const currentLanguage = computed<string>(() => authStore.user?.language ?? '')

const languageLabel = computed<string>(() => {
  const code = currentLanguage.value
  return SUPPORTED_LOCALES.find((l) => l.code === code)?.label ?? code
})

// ---------------------------------------------------------------------------
// Profile: self-service edit (TASK-38 item 3)
// ---------------------------------------------------------------------------
//
// Covers name/phone/country/language -- the fields the F4.4 B5 scope note
// used to call out as read-only. Same diff-and-submit discipline as
// CompanySettingsView's TASK-30 W1 profile editor: drafts seeded from the
// loaded profile on open, submit sends only fields that actually changed
// (omitted = untouched, backend's exclude_unset leaves it alone), response
// re-synced into the auth store on success.
//
// Language options offer the FULL SUPPORTED_LOCALES set (including the
// still-partial de/ar translations), not just the complete en/ru pair --
// deliberately, for consistency with the two pickers that already offer
// all four with no restriction: CAppControls' header picker and this same
// user's own OnboardingProfileView language step (i.e. a user who
// registered with de/ar could otherwise never select it again here). No
// file in this codebase documents de/ar as excluded from user selection;
// restricting only this picker would introduce a new inconsistency rather
// than fix one.

const showEditProfile = ref(false)
const savingProfile = ref(false)

const draftFirstName = ref('')
const draftLastName = ref('')
const draftPhone = ref('')
const draftCountry = ref('')
const draftLanguage = ref('')

function openEditProfile(): void {
  draftFirstName.value = firstName.value
  draftLastName.value = lastName.value
  draftPhone.value = phone.value
  draftCountry.value = country.value
  draftLanguage.value = currentLanguage.value
  showEditProfile.value = true
}

function closeEditProfile(): void {
  showEditProfile.value = false
}

const trimmedFirstName = computed<string>(() => draftFirstName.value.trim())
const trimmedLastName = computed<string>(() => draftLastName.value.trim())
const trimmedPhone = computed<string>(() => draftPhone.value.trim())

// first_name/last_name/country: backend applies no length/format
// validation beyond the profile-keys whitelist (any string is accepted),
// but leaving them non-empty mirrors what OnboardingProfileView already
// required at initial setup -- not a stricter rule, the SAME one, just
// re-applied to editing. Phone stays optional, also matching onboarding.
const firstNameValid = computed<boolean>(() => trimmedFirstName.value.length > 0)
const lastNameValid = computed<boolean>(() => trimmedLastName.value.length > 0)
const countryValid = computed<boolean>(() => draftCountry.value.length > 0)

const canSubmitProfile = computed<boolean>(
  () => firstNameValid.value && lastNameValid.value && countryValid.value,
)

const countryOptions = COUNTRIES
const languageOptions = SUPPORTED_LOCALES.map((l) => ({ value: l.code, label: l.label }))

function buildProfileUpdateBody(): UserUpdate {
  const body: UserUpdate = {}
  const profileUpdates: Record<string, unknown> = {}

  if (trimmedFirstName.value !== firstName.value) {
    profileUpdates.first_name = trimmedFirstName.value
  }
  if (trimmedLastName.value !== lastName.value) {
    profileUpdates.last_name = trimmedLastName.value
  }
  if (trimmedPhone.value !== phone.value) {
    // Clearing an existing phone sends an explicit null (JSONB merge
    // semantics: omitted key = untouched, present null = cleared) --
    // same rule CompanySettingsView's media-URL fields use.
    profileUpdates.phone = trimmedPhone.value ? trimmedPhone.value : null
  }
  if (draftCountry.value !== country.value) {
    profileUpdates.country = draftCountry.value
  }

  if (Object.keys(profileUpdates).length > 0) {
    body.profile = profileUpdates
  }

  if (draftLanguage.value && draftLanguage.value !== currentLanguage.value) {
    body.language = draftLanguage.value
  }

  return body
}

async function handleSaveProfile(): Promise<void> {
  if (!canSubmitProfile.value) return

  const body = buildProfileUpdateBody()
  // Nothing changed -- close without a redundant PATCH.
  if (Object.keys(body).length === 0) {
    showEditProfile.value = false
    return
  }

  const newLanguage = body.language
  savingProfile.value = true
  try {
    await updateMe(body)
    await authStore.fetchMe()
    // Persisted (user.language) and live session locale are two separate
    // mechanisms -- see the header comment. Switch the active session
    // right away so the change is visible now, not only on next login.
    if (newLanguage) {
      await setLocale(newLanguage)
    }
    showEditProfile.value = false
    showToast(t('inv.settings.profile.editSuccess'), 'success')
  } catch (err) {
    const message =
      err instanceof ApiResponseError && err.detail
        ? err.detail
        : t('inv.settings.profile.editError')
    showToast(message, 'error')
  } finally {
    savingProfile.value = false
  }
}

// ---------------------------------------------------------------------------
// Theme (3-state chips)
// ---------------------------------------------------------------------------

const { current: themeCurrent, set: setTheme } = useTheme()

const THEME_MODES: readonly ThemeMode[] = ['auto', 'light', 'dark'] as const

// ---------------------------------------------------------------------------
// Marketing consent
// ---------------------------------------------------------------------------

const marketingConsent = ref<boolean>(Boolean(_profile().marketing_consent))
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
  // Sprint 4.4: typed compare via authStore.role (UserRole | null).
  // A typo in the literal becomes a compile-time error rather than
  // a silent runtime miss.
  () => authStore.role === 'investor',
)
const kycApproved = computed<boolean>(
  // Sprint 4.4: typed compare via authStore.kycStatus (KycStatus | null).
  () => authStore.kycStatus === 'approved',
)

const agentApps = ref<AgentApplicationResponse[]>([])
const agentLoading = ref<boolean>(false)
const agentLoadErrored = ref<boolean>(false)
const agentSubmitting = ref<boolean>(false)

// Newest-first per backend contract (get_my_applications orders by
// created_at DESC), so items[0] is always "the latest".
const latestApp = computed<AgentApplicationResponse | null>(() => agentApps.value[0] ?? null)

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
  void safeNavigate(router.push('/onboarding/kyc'), '[InvestorSettingsView] to KYC onboarding')
}

function goDocs(): void {
  void safeNavigate(
    router.push({ name: 'investor-docs' }),
    '[InvestorSettingsView] to investor docs',
  )
}

const loggingOut = ref<boolean>(false)

async function handleLogout(): Promise<void> {
  if (loggingOut.value) return
  loggingOut.value = true
  try {
    await authStore.logout()
  } finally {
    // Auth state already cleared. If push gets rejected by a benign
    // NavigationFailure type, the next route guard will bounce the
    // tokenless user to /login anyway -- no toast needed.
    void safeNavigate(router.push('/login'), '[InvestorSettingsView] to login')
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
    <!-- Inline page header, no CHeader (shell renders it). -->
    <div class="sett__header">
      <h1 class="sett__page-title">
        {{ t('inv.settings.title') }}
      </h1>
      <p class="sett__page-subtitle">
        {{ t('inv.settings.subtitle') }}
      </p>
    </div>

    <!-- Profile card -->
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

    <!-- Profile details -- phone/country/language, edit pencil opens the
         profile form modal (TASK-38 item 3). -->
    <section class="sett__section">
      <div class="sett__section-title sett__section-title--row">
        <span>{{ t('inv.settings.profile.title') }}</span>
        <button
          type="button"
          class="sett__edit-btn"
          :aria-label="t('common.edit')"
          @click="openEditProfile"
        >
          <Pencil :size="14" />
        </button>
      </div>
      <div class="sett__row">
        <span class="sett__row-label">
          {{ t('inv.settings.profile.phone') }}
        </span>
        <span class="sett__row-value">{{ phoneDisplay }}</span>
      </div>
      <div class="sett__row">
        <span class="sett__row-label">
          {{ t('inv.settings.profile.country') }}
        </span>
        <span class="sett__row-value">{{ countryLabel }}</span>
      </div>
      <div class="sett__row">
        <span class="sett__row-label">
          {{ t('inv.settings.profile.language') }}
        </span>
        <span class="sett__row-value">{{ languageLabel }}</span>
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
            <Monitor v-if="mode === 'auto'" :size="16" />
            <Sun v-else-if="mode === 'light'" :size="16" />
            <Moon v-else :size="16" />
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
        <CButton variant="primary" :loading="agentSubmitting" @click="applyForAgent">
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

      <button type="button" class="sett__row sett__row--clickable" @click="goDocs">
        <span class="sett__row-label sett__row-label--accent">
          <FileText :size="16" />
          {{ t('inv.settings.actions.docs') }}
        </span>
        <ChevronRight :size="16" />
      </button>

      <EmailChangeSection tPrefix="inv.settings.actions" />
      <ActiveSessionsSection tPrefix="inv.settings.actions" />
      <DeactivateAccountSection tPrefix="inv.settings.actions" />

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

    <!-- Profile edit modal (TASK-38 item 3): first/last name, phone,
         country, language. -->
    <CModal :open="showEditProfile" @close="closeEditProfile">
      <h3 class="sett__modal-title">
        {{ t('inv.settings.profile.editTitle') }}
      </h3>

      <div class="sett__modal-row">
        <CInput
          v-model="draftFirstName"
          class="sett__modal-col"
          :label="t('inv.settings.profile.firstName')"
          :error="!firstNameValid ? t('inv.settings.profile.requiredError') : ''"
        />
        <CInput
          v-model="draftLastName"
          class="sett__modal-col"
          :label="t('inv.settings.profile.lastName')"
          :error="!lastNameValid ? t('inv.settings.profile.requiredError') : ''"
        />
      </div>

      <CInput
        v-model="draftPhone"
        :label="t('inv.settings.profile.phone')"
        type="tel"
        placeholder="+49 XXX XXXXXXXX"
        autocomplete="tel"
      />

      <CSelect
        v-model="draftCountry"
        :label="t('inv.settings.profile.country')"
        :options="countryOptions"
        placeholder="—"
        :error="!countryValid ? t('inv.settings.profile.requiredError') : ''"
      />

      <CSelect
        v-model="draftLanguage"
        :label="t('inv.settings.profile.language')"
        :options="languageOptions"
      />

      <div class="sett__modal-actions">
        <CButton variant="outline" size="sm" @click="closeEditProfile">
          {{ t('common.cancel') }}
        </CButton>
        <CButton
          variant="primary"
          size="sm"
          :loading="savingProfile"
          :disabled="!canSubmitProfile"
          @click="handleSaveProfile"
        >
          {{ t('common.save') }}
        </CButton>
      </div>
    </CModal>
  </div>
</template>

<style scoped>
.sett {
  display: flex;
  flex-direction: column;
  padding-bottom: var(--space-5);
}

/* Inline page header -- MarketView pattern */
.sett__header {
  padding: var(--space-4) var(--space-4) 0;
}
.sett__page-title {
  font-size: var(--fs-lg);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 var(--space-1);
}
.sett__page-subtitle {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  margin: 0 0 var(--space-4);
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
}
.sett__section-title {
  font-size: var(--fs-xs);
  font-weight: 700;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.12em;
  margin-bottom: var(--space-2);
  padding: 0 var(--space-1);
}
.sett__section-title--row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.sett__edit-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: var(--size-md);
  height: var(--size-sm);
  padding: 0;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: var(--radius-sm);
  transition:
    color 0.2s,
    background 0.2s;
}
.sett__edit-btn:hover {
  color: var(--primary);
  background: var(--bg-subtle);
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
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--border-default);
  min-height: var(--size-3xl);
}
.sett__row:last-child {
  border-bottom: none;
}
button.sett__row {
  width: 100%;
  background: transparent;
  border: 0;
  border-bottom: 1px solid var(--border-default);
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
  gap: var(--space-2);
  font-size: var(--fs-sm);
  color: var(--text-primary);
}
.sett__row-label--accent {
  color: var(--primary);
  font-weight: 600;
}
.sett__row-label--muted {
  color: var(--text-secondary);
}
.sett__row-label--danger {
  color: var(--danger);
  font-weight: 600;
}
.sett__row-value {
  font-size: var(--fs-sm);
  color: var(--text-tertiary);
  text-align: right;
}

/* Theme chips */
.sett__chips {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
}
.sett__chip {
  /* A5: pointer target floor. */
  min-height: var(--tap-min);
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-default);
  background: var(--bg-page);
  color: var(--text-secondary);
  font-size: var(--fs-xs);
  font-weight: 600;
  cursor: pointer;
  font-family: inherit;
  transition:
    border-color 0.15s,
    color 0.15s,
    background 0.15s;
}
.sett__chip:hover {
  border-color: var(--primary-hover);
  color: var(--text-primary);
}
.sett__chip--active {
  background: var(--primary);
  border-color: var(--primary);
  color: var(--on-primary);
}

/* Toggle switch. The track is tokenised and the knob was a raw #fff, so the
   track followed the theme and the knob could not: measured 1.57:1 knob-vs-track
   in LIGHT against 11.6:1 in dark, i.e. the affordance was carried by its drop
   shadow alone. Both sides now read --toggle-* and the pair is 4.57:1 in BOTH
   themes. See variables.css for the values and for what moves on screen. */
.sett__toggle {
  width: var(--size-2xl);
  height: var(--size-xs);
  background: var(--toggle-track);
  border-radius: var(--radius-md);
  position: relative;
  cursor: pointer;
  transition:
    background 0.2s,
    opacity 0.2s;
  border: none;
  padding: 0;
  flex-shrink: 0;
}

/* A5: the PAINTED box stays this size on purpose; the HIT AREA is expanded past
   it with a centred overlay. Growing the box itself would move the text this
   control sits inside or beside. max() so an already-large box never shrinks. */
.sett__toggle::before {
  content: '';
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  width: max(100%, var(--tap-min));
  height: max(100%, var(--tap-min));
}
.sett__toggle::after {
  content: '';
  position: absolute;
  width: var(--size-2xs);
  height: var(--size-2xs);
  background: var(--toggle-knob);
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

/* Profile edit modal (TASK-38 item 3) */
.sett__modal-title {
  font-size: var(--fs-h4);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 var(--space-4);
}
.sett__modal-row {
  display: flex;
  gap: var(--space-3);
}
.sett__modal-col {
  flex: 1;
}
.sett__modal-actions {
  display: flex;
  gap: var(--space-2);
  justify-content: flex-end;
}
</style>
