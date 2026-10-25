<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- InvestorSettingsView (Phase F4.4 B5 + B5-post + B6)
// =============================================================================
//
// Reached via the More tab (tab bar -> /investor/more -> Settings tile).
// Not itself a tab -- the tab bar's "More" slot points at MoreView.
// The frame's header (K25) holds the title and the line under it, set here with
// `useScreenHeader`; this view adds no header of its own. Each section is a Card
// (K07): the details a key-value list (K49), the actions Row list rows (K23), the
// marketing consent a Toggle (K06), the theme a Segmented control (K31).
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
//      The e-mail (EmailSection) sits here: an account that signed in
//      without one adds and confirms it, because identity verification
//      starts from a confirmed e-mail.
//   3. Preferences -- theme selector (3 choices: auto / light / dark,
//      driven by useTheme -- client-only, no backend round-trip) and
//      a marketing consent toggle backed by profile.marketing_consent
//      (PATCH /users/me with optimistic local flip + revert on fail).
//   4. "Become an integrator" -- shown to an investor only AFTER the
//      identity verification is passed (before it, the verification row
//      below is the way in). State machine below.
//   5. Actions -- identity verification (its status), Documents, Support
//      and FAQ (they lie inside Settings on a phone), the security group
//      (two-factor, sessions) and notification settings.
//   6. Leaving -- the last card, apart: "Log out of all devices", account
//      deactivation and "Log out".
//
// AGENT APPLICATION STATE MACHINE.
//   TASK-39 item 5: the derivation (loading / load_error / kyc_required /
//   pending / cooldown / can_reapply / can_apply) moved out of this view
//   into composables/useAgentApplicationStatus.ts, which fetches
//   getMyAgentApplications (newest-first) and exposes the same `state` this
//   section always rendered. See that file's header for the full state
//   table. It moved so InvestorMoreView's new "Agent programme" tile (the
//   discoverability entry point the owner asked for) reads the identical
//   state instead of a second hand-rolled copy that could disagree with
//   this one. This view remains the ONLY place that calls
//   submitAgentApplication() -- the composable is read-only.
//     load_error    -- fetch failed (B5-post). Inline retry button.
//                      Without this, a network drop left the user
//                      seeing an active "Apply" while they had a real
//                      pending application server-side; clicking
//                      caused a 409 with a generic toast. Showing the
//                      retry surface keeps the UI honest.
//     kyc_required  -- The "Become an integrator" button greyed; a press
//                      opens the verification prompt.
//     pending       -- The button reads "Application under review"; a press
//                      opens the message about writing to support.
//     cooldown      -- Disabled row with N-days-left label (ceiling days
//                      to avoid "0 days left" on the last hour).
//     can_reapply   -- Active button labelled "Apply again"; a press opens
//                      the application window.
//     can_apply     -- Active button labelled "Become an integrator"; a press
//                      opens the application window.
//
// MARKETING CONSENT OPTIMISM.
//   toggleMarketing flips the local ref immediately, fires PATCH
//   /users/me { profile: { marketing_consent: next } }, and on success
//   calls authStore.fetchMe() so any other subscriber of user.profile
//   sees the updated value without waiting for a route change. On
//   failure the local ref reverts and a toast is shown.
//
// B5-post changes.
//   - Clickable rows are links (the system's Row list, K23) where they open a
//     screen, and keyboard / screen-reader users activate them.
//   - The marketing consent is a native switch (K06) named by its own label, so
//     assistive tech reads "Marketing communications, on/off".
//   - Dead `if (err instanceof ApiResponseError) ... else ...` branch
//     in applyForAgent removed; both arms showed the same toast.
//   - getMyAgentApplications failure surfaces a load_error state with
//     an inline retry row rather than silently falling through to
//     can_apply. (The ref behind it was named `agentLoadErrored` when
//     this note was written; TASK-39 item 5 moved it into
//     useAgentApplicationStatus as `loadErrored` -- no such local
//     exists in this file any more.)
// =============================================================================

import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  AlertTriangle,
  ChevronRight,
  FileText,
  HelpCircle,
  LogOut,
  MessageCircle,
  Monitor,
  Moon,
  Pencil,
  Shield,
  Sun,
  UserPlus,
} from '@/components/ui/icons'

import { CAvatar, CBadge, CButton, CInput, CLoader, CModal, CSelect } from '@/components/ui'
import { useScreenHeader } from '@/components/layout/screenHeader'
import TwoFactorSection from '@/components/shared/TwoFactorSection.vue'
import EmailSection from '@/components/shared/EmailSection.vue'
import ActiveSessionsSection from '@/components/shared/ActiveSessionsSection.vue'
import NotificationPreferencesSection from '@/components/shared/NotificationPreferencesSection.vue'
import DeactivateAccountSection from '@/components/shared/DeactivateAccountSection.vue'
import IntegratorApplicationModal from '@/components/shared/IntegratorApplicationModal.vue'
import { useAuthStore } from '@/stores/auth'
import { useSupportStore } from '@/stores/support'
import { getShell } from '@/router/helpers'
import { updateMe } from '@/api/users'
import { submitAgentApplication } from '@/api/agent-apps'
import { useAgentApplicationStatus } from '@/composables/useAgentApplicationStatus'
import { useTheme, type ThemeMode } from '@/composables/useTheme'
import { useToast } from '@/composables/useToast'
import { showKycPrompt } from '@/composables/useKycPrompt'
import { safeNavigate } from '@/composables/safeNavigate'
import { tOrRaw } from '@/utils/i18n'
import { setLocale } from '@/i18n'
import { SUPPORTED_LOCALES } from '@/i18n/locales.config'
import { COUNTRIES } from '@/utils/countries'
import type { UserUpdate } from '@/api/types'

const { t } = useI18n()
const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const { showToast } = useToast()

useScreenHeader({
  title: () => t('inv.settings.title'),
  lead: () => t('inv.settings.subtitle'),
})

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

const email = computed<string>(() => authStore.user?.email ?? '')

// The heading of the profile card: the name; with no name given, the e-mail; with
// neither, the plain title of the card. It never says the name is missing.
const fullName = computed<string>(() => {
  const name = [firstName.value, lastName.value].filter(Boolean).join(' ').trim()
  return name || email.value || t('inv.settings.profile.title')
})

// The e-mail line under the heading, only when the heading is not already the e-mail.
const showEmailLine = computed<boolean>(
  () => email.value.length > 0 && fullName.value !== email.value,
)

// The verification screen sends a person here to confirm an address that is
// already on the account; with no address yet the field comes first.
const confirmEmail = computed<boolean>(
  () => route.query.confirm_email === '1' && email.value.length > 0,
)

// Taken once when the screen opens: the section must not vanish when an
// address added here makes `email` non-empty before its code is entered.
const showEmailSection = ref<boolean>(!email.value || confirmEmail.value)

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

// The details are incomplete while a name is missing, or there is neither phone nor
// country: the card then offers a visible "Fill in details" button beside the pencil.
const detailsEmpty = computed<boolean>(
  () => !firstName.value || !lastName.value || (!phone.value && !country.value),
)

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
    // A plain sentence, never the server's raw text.
    void err
    showToast(t('inv.settings.profile.editError'), 'error')
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
//
// State derivation (loading/kyc_required/pending/cooldown/can_apply/
// can_reapply) now lives in useAgentApplicationStatus (TASK-39 item 5) so
// InvestorMoreView's new "Agent programme" tile reads the exact same state
// machine instead of a second copy that could drift. This view keeps the
// only submit control -- applyForAgent() is still the SOLE call site of
// submitAgentApplication().

const {
  isInvestor,
  state: agentState,
  cooldownDaysLeft,
  fetch: fetchAgentApps,
} = useAgentApplicationStatus()

const agentSubmitting = ref<boolean>(false)
const agentModalOpen = ref<boolean>(false)
const agentSent = ref<boolean>(false)

// The button is visible to everyone. Without a passed identity verification it
// is greyed and a press opens the verification prompt; after it, a press opens
// the application window (or, once the application is sent, the message about
// writing to support).
function onAgentButton(): void {
  if (agentState.value === 'kyc_required') {
    showKycPrompt('integrator')
    return
  }
  agentModalOpen.value = true
}

async function applyForAgent(): Promise<void> {
  if (agentSubmitting.value) return
  agentSubmitting.value = true
  try {
    await submitAgentApplication()
    agentSent.value = true
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

// The KYC row names where the verification stands.
const kycRowKey = computed<string>(() => {
  const raw = authStore.user?.kyc_status
  if (raw === 'approved') return 'inv.settings.actions.kyc.approved'
  if (raw === 'submitted') return 'inv.settings.actions.kyc.submitted'
  if (raw === 'rejected') return 'inv.settings.actions.kyc.rejected'
  return 'inv.settings.actions.kyc.notStarted'
})

const loggingOutAll = ref<boolean>(false)

// Ends the session on every device. The local session is cleared only after
// the server has ended them all; a failure says so and changes nothing.
async function handleLogoutAll(): Promise<void> {
  if (loggingOutAll.value) return
  loggingOutAll.value = true
  try {
    await authStore.logoutAllDevices()
    void safeNavigate(router.push('/login'), '[InvestorSettingsView] to login')
  } catch {
    showToast(t('inv.settings.actions.logoutAllError'), 'error')
  } finally {
    loggingOutAll.value = false
  }
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

// -- Support row (H40 item 10) ------------------------------------------------
// The row leads to the shell's own support screen -- this view is mounted
// in the buyer's and the integrator's shells -- and shows what is unread in
// the person's conversation. A failed count keeps no badge rather than a
// guessed 0 (support store's `unread` is null until known).
const support = useSupportStore()
const supportRouteName = computed<string>(() =>
  getShell(route) === 'agent' ? 'agent-support' : 'investor-support',
)
const supportUnread = computed<number>(() => support.unread ?? 0)

onMounted(() => {
  void fetchAgentApps()
  void support.fetchUnread()
})
</script>

<template>
  <div class="sett">
    <!-- Profile card -->
    <section class="ds-card sett__profile" aria-labelledby="sett-name">
      <CAvatar :url="avatarUrl" :name="fullName" :size="56" />
      <h2 id="sett-name" class="ds-section-title">
        {{ fullName }}
      </h2>
      <p v-if="showEmailLine" class="ds-note sett__email">
        {{ email }}
      </p>
      <CBadge variant="neutral" :text="roleLabel" />
    </section>

    <!-- Profile details -- phone/country/language, edit pencil opens the
         profile form modal (TASK-38 item 3). -->
    <section class="ds-card" aria-labelledby="sett-profile">
      <header class="ds-card__head">
        <h2 id="sett-profile" class="ds-card__title">
          {{ t('inv.settings.profile.title') }}
        </h2>
        <button
          type="button"
          class="ds-button ds-button--ghost ds-button--icon"
          data-size="sm"
          :aria-label="t('common.edit')"
          @click="openEditProfile"
        >
          <Pencil size="sm" />
        </button>
      </header>
      <dl class="ds-kv">
        <div class="ds-kv__row">
          <dt>{{ t('inv.settings.profile.firstName') }}</dt>
          <dd>{{ firstName || t('inv.settings.profile.notSet') }}</dd>
        </div>
        <div class="ds-kv__row">
          <dt>{{ t('inv.settings.profile.lastName') }}</dt>
          <dd>{{ lastName || t('inv.settings.profile.notSet') }}</dd>
        </div>
        <div class="ds-kv__row">
          <dt>{{ t('inv.settings.profile.phone') }}</dt>
          <dd>{{ phoneDisplay }}</dd>
        </div>
        <div class="ds-kv__row">
          <dt>{{ t('inv.settings.profile.country') }}</dt>
          <dd>{{ countryLabel }}</dd>
        </div>
        <div class="ds-kv__row">
          <dt>{{ t('inv.settings.profile.language') }}</dt>
          <dd>{{ languageLabel }}</dd>
        </div>
      </dl>
      <div v-if="detailsEmpty" class="ds-card__foot">
        <CButton variant="outline" size="sm" inline @click="openEditProfile">
          {{ t('inv.settings.profile.fill') }}
        </CButton>
      </div>
    </section>

    <!-- The e-mail: added and confirmed here when the account has none -->
    <section v-if="showEmailSection || confirmEmail" class="ds-card">
      <EmailSection :confirm="confirmEmail" />
    </section>

    <!-- Actions -->
    <section class="ds-card" aria-labelledby="sett-actions">
      <header class="ds-card__head">
        <h2 id="sett-actions" class="ds-card__title">
          {{ t('inv.settings.actions.title') }}
        </h2>
      </header>

      <ul class="ds-rows">
        <!-- Identity verification, with where it stands -->
        <li class="ds-row">
          <span class="ds-row__lead"><Shield size="sm" /></span>
          <span class="ds-row__body">
            <RouterLink class="ds-row__link" to="/verification">
              <span class="ds-row__title">{{ t('inv.settings.actions.kyc.title') }}</span>
            </RouterLink>
            <span class="ds-row__meta">{{ t(kycRowKey) }}</span>
          </span>
          <span class="ds-row__trail"><ChevronRight size="sm" /></span>
        </li>

        <li class="ds-row">
          <span class="ds-row__lead"><FileText size="sm" /></span>
          <span class="ds-row__body">
            <RouterLink class="ds-row__link" :to="{ name: 'investor-docs' }">
              <span class="ds-row__title">{{ t('inv.settings.actions.docs') }}</span>
            </RouterLink>
          </span>
          <span class="ds-row__trail"><ChevronRight size="sm" /></span>
        </li>

        <li class="ds-row">
          <span class="ds-row__lead"><MessageCircle size="sm" /></span>
          <span class="ds-row__body">
            <RouterLink class="ds-row__link" :to="{ name: supportRouteName }">
              <span class="ds-row__title">{{ t('inv.settings.actions.support') }}</span>
            </RouterLink>
          </span>
          <span class="ds-row__trail">
            <CBadge
              v-if="supportUnread > 0"
              variant="primary"
              :text="String(supportUnread)"
              :aria-label="t('inv.support.unread', { n: supportUnread })"
            />
            <ChevronRight size="sm" />
          </span>
        </li>

        <li class="ds-row">
          <span class="ds-row__lead"><HelpCircle size="sm" /></span>
          <span class="ds-row__body">
            <RouterLink class="ds-row__link" :to="{ name: 'investor-faq' }">
              <span class="ds-row__title">{{ t('inv.settings.actions.faq') }}</span>
            </RouterLink>
          </span>
          <span class="ds-row__trail"><ChevronRight size="sm" /></span>
        </li>
      </ul>

      <!-- Security: two-factor and the active sessions -->
      <TwoFactorSection tPrefix="inv.settings.actions" />
      <ActiveSessionsSection tPrefix="inv.settings.actions" />

      <NotificationPreferencesSection tPrefix="inv.settings.actions" />
    </section>

    <!-- Preferences -->
    <section class="ds-card" aria-labelledby="sett-prefs">
      <header class="ds-card__head">
        <h2 id="sett-prefs" class="ds-card__title">
          {{ t('inv.settings.prefs.title') }}
        </h2>
      </header>

      <!-- Theme (K31) -->
      <div class="ds-field">
        <span class="ds-field__label" aria-hidden="true">
          {{ t('inv.settings.prefs.theme') }}
        </span>
        <fieldset class="ds-segmented">
          <legend class="ds-sr-only">{{ t('inv.settings.prefs.theme') }}</legend>
          <label v-for="mode in THEME_MODES" :key="mode" class="ds-segmented__option">
            <input
              class="ds-segmented__input"
              type="radio"
              name="theme-mode"
              :value="mode"
              :checked="themeCurrent === mode"
              @change="setTheme(mode)"
            />
            <Monitor v-if="mode === 'auto'" size="sm" />
            <Sun v-else-if="mode === 'light'" size="sm" />
            <Moon v-else size="sm" />
            {{ t(`inv.settings.prefs.themeValue.${mode}`) }}
          </label>
        </fieldset>
      </div>

      <!-- Marketing consent: a setting that applies at once is a Toggle (K06) -->
      <label class="ds-toggle">
        <span class="ds-toggle__text">
          <span>{{ t('inv.settings.prefs.marketing') }}</span>
        </span>
        <input
          class="ds-toggle__input"
          type="checkbox"
          role="switch"
          :checked="marketingConsent"
          :disabled="marketingBusy"
          @change="toggleMarketing"
        />
        <span class="ds-toggle__track" aria-hidden="true" />
      </label>
    </section>

    <!-- Become an integrator: visible to every buyer; greyed until the verification is passed -->
    <section v-if="isInvestor" class="ds-card" aria-labelledby="sett-agent">
      <header class="ds-card__head">
        <h2 id="sett-agent" class="ds-card__title">
          {{ t('inv.settings.agent.title') }}
        </h2>
      </header>

      <!-- Loading -->
      <CLoader v-if="agentState === 'loading'" :size="20" />

      <!-- Load error with retry -->
      <div v-else-if="agentState === 'load_error'" class="ds-alert ds-alert--danger" role="alert">
        <span class="ds-alert__icon" aria-hidden="true"><AlertTriangle size="sm" /></span>
        <div class="ds-alert__content">
          <p class="ds-alert__text">{{ t('inv.settings.agent.loadError') }}</p>
          <div class="ds-alert__actions">
            <CButton variant="outline" size="sm" inline @click="fetchAgentApps">
              {{ t('common.retry') }}
            </CButton>
          </div>
        </div>
      </div>

      <!-- Pending review -->
      <CButton v-else-if="agentState === 'pending'" variant="outline" @click="onAgentButton">
        <UserPlus size="sm" />
        {{ t('inv.settings.agent.underReview') }}
      </CButton>

      <!-- Cooldown active -->
      <p v-else-if="agentState === 'cooldown'" class="ds-card__body sett__cooldown">
        <UserPlus size="sm" />
        {{ t('inv.settings.agent.cooldown', { days: cooldownDaysLeft }) }}
      </p>

      <!-- Can apply / reapply -->
      <CButton
        v-else
        :variant="agentState === 'kyc_required' ? 'outline' : 'primary'"
        :aria-disabled="agentState === 'kyc_required' || undefined"
        @click="onAgentButton"
      >
        <UserPlus size="sm" />
        {{
          agentState === 'can_reapply'
            ? t('inv.settings.agent.reapply')
            : t('inv.settings.agent.apply')
        }}
      </CButton>

      <IntegratorApplicationModal
        :open="agentModalOpen"
        :sent="agentSent || agentState === 'pending'"
        :submitting="agentSubmitting"
        @close="agentModalOpen = false"
        @submit="applyForAgent"
      />
    </section>

    <!-- Leaving: sign out (this device, every device) and deactivation, a last card apart -->
    <section class="ds-card" aria-labelledby="sett-leave">
      <header class="ds-card__head">
        <h2 id="sett-leave" class="ds-sr-only">
          {{ t('inv.settings.leave.title') }}
        </h2>
      </header>

      <ul class="ds-rows">
        <li class="ds-row" :aria-disabled="loggingOutAll ? 'true' : undefined">
          <span class="ds-row__lead" data-tone="danger"><LogOut size="sm" /></span>
          <span class="ds-row__body">
            <button
              type="button"
              class="ds-row__link"
              :disabled="loggingOutAll"
              @click="handleLogoutAll"
            >
              <span class="ds-row__title" data-tone="danger">
                {{ t('inv.settings.actions.logoutAll') }}
              </span>
            </button>
          </span>
          <span class="ds-row__trail"><ChevronRight size="sm" /></span>
        </li>
      </ul>

      <DeactivateAccountSection tPrefix="inv.settings.actions" />

      <ul class="ds-rows">
        <li class="ds-row" :aria-disabled="loggingOut ? 'true' : undefined">
          <span class="ds-row__lead" data-tone="danger"><LogOut size="sm" /></span>
          <span class="ds-row__body">
            <button type="button" class="ds-row__link" :disabled="loggingOut" @click="handleLogout">
              <span class="ds-row__title" data-tone="danger">
                {{ t('inv.settings.actions.logout') }}
              </span>
            </button>
          </span>
          <span class="ds-row__trail"><ChevronRight size="sm" /></span>
        </li>
      </ul>
    </section>

    <!-- Profile edit modal (TASK-38 item 3): first/last name, phone,
         country, language. -->
    <CModal
      :open="showEditProfile"
      :title="t('inv.settings.profile.editTitle')"
      @close="closeEditProfile"
    >
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

      <div class="ds-dialog__actions">
        <CButton variant="outline" size="sm" inline @click="closeEditProfile">
          {{ t('common.cancel') }}
        </CButton>
        <CButton
          variant="primary"
          size="sm"
          inline
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
  gap: var(--space-4);
}

/* Profile card: the avatar, the name, the e-mail and the role, centred */
.sett__profile {
  align-items: center;
  text-align: center;
  gap: var(--space-2);
}
/* a long address breaks anywhere rather than widening the card */
.sett__email {
  overflow-wrap: anywhere;
}

/* The cooldown line: an icon and the words */
.sett__cooldown {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin: 0;
}

/* Profile edit modal (TASK-38 item 3) */
.sett__modal-row {
  display: flex;
  gap: var(--space-3);
}
.sett__modal-col {
  flex: 1;
}
</style>
