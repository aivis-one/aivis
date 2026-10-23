<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- CompanySettingsView (the project account's Settings tab)
// =============================================================================
//
// Settings tab inside CompanyShell, in the order a project looks for things:
//   1. Hero -- logo, name, status.
//   2. Personal block -- the name, the e-mail and the language of the person
//      who works in the account.
//   3. Profile -- description, status (or the "withdraw" button while the
//      project is on sale), and a pencil that opens the profile and media form.
//   4. Parts -- the price of a part and the parts for sale, READ ONLY. The price
//      of a part is the fair value of the project divided by 1,000,000,000,
//      one for every project; it changes only by a revaluation of the project,
//      never by a hand entry here, and the parts for sale are 25 percent of the
//      parts and never grow. Nothing on this screen writes either figure.
//   5. Distribution -- the fixed division of the parts, a table, read only.
//   6. Documents (the project's legal documents to read), Support, FAQ,
//      Activity (the change log).
//   7. Media links, then the account: two-factor authentication, sessions,
//      notification preferences, deactivation, sign-out.
//
// Posts, the roadmap and documents of the project live on the Publications
// tab; the balance in the top bar opens the balance screen.
//
// A project may withdraw itself from the store (status -> hidden) through
// PATCH /api/v1/companies/me while it is active. It may not republish itself or
// archive itself: both are the administrator's, and this view shows a hidden or
// archived project's status as plain text with a short explanation, never a
// button that would only be refused.
//
// DATA SOURCE. companyProfile.loadIfMissing() -- cache-first. Everything else
// appears only after the profile is non-null; a failed load shows a retry.
// =============================================================================

import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  ChevronRight,
  ExternalLink,
  FileText,
  HelpCircle,
  History,
  Image as ImageIcon,
  LogOut,
  MessageCircle,
  Pencil,
  Video,
} from 'lucide-vue-next'

import { CButton, CEmptyState, CInput, CLoader, CModal, CSelect, CTextarea } from '@/components/ui'
import TwoFactorSection from '@/components/shared/TwoFactorSection.vue'
import ActiveSessionsSection from '@/components/shared/ActiveSessionsSection.vue'
import NotificationPreferencesSection from '@/components/shared/NotificationPreferencesSection.vue'
import DeactivateAccountSection from '@/components/shared/DeactivateAccountSection.vue'
import { useAuthStore } from '@/stores/auth'
import { useCompanyProfileStore } from '@/stores/companyProfile'
import { useCompanyDashboardStore } from '@/stores/companyDashboard'
import { safeNavigate } from '@/composables/safeNavigate'
import { useToast } from '@/composables/useToast'
import { formatNumber, formatPrice } from '@/utils/format'
import { tOrRaw } from '@/utils/i18n'
import { updateOwnCompany } from '@/api/companies'
import { updateMe } from '@/api/users'
import { setLocale } from '@/i18n'
import { SUPPORTED_LOCALES } from '@/i18n/locales.config'
import { ApiResponseError } from '@/api/client'
import type { UpdateOwnCompanyRequest, UserUpdate } from '@/api/types'

const { t, locale } = useI18n()
const router = useRouter()
const authStore = useAuthStore()
const profileStore = useCompanyProfileStore()
const dashboardStore = useCompanyDashboardStore()
const { showToast } = useToast()

// ---------------------------------------------------------------------------
// Derived view state
// ---------------------------------------------------------------------------

const profile = computed(() => profileStore.profile)

const initialLoading = computed<boolean>(() => {
  if (profileStore.error) return false
  return profile.value === null
})

const hasError = computed<boolean>(() => profileStore.error !== null)

// ---------------------------------------------------------------------------
// Hero readouts
// ---------------------------------------------------------------------------

const companyName = computed<string>(() => profile.value?.name ?? '')
const logoUrl = computed<string | null>(() => profile.value?.logo_url ?? null)

/**
 * Initials fallback when logo_url is null. Same rule as the dashboard
 * hero: first letter of up to two whitespace chunks ("Test Company"
 * -> "TC"), uppercase, falls back to "C" on empty name.
 */
const initials = computed<string>(() => {
  const name = companyName.value.trim()
  if (!name) return 'C'
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part.charAt(0).toUpperCase())
    .join('')
})

const status = computed<string>(() => profile.value?.status ?? '')
const statusLabel = computed<string>(() =>
  // FP-15: server-driven enum -> tOrRaw with raw fallback so a future
  // backend status (e.g. "suspended") shows up readable instead of
  // the dotted i18n path.
  tOrRaw(t, `comp.settings.status.${status.value}`, status.value),
)
const statusBadgeClass = computed<string>(() => {
  if (status.value === 'active') return 'cset__status--success'
  if (status.value === 'hidden') return 'cset__status--warning'
  return 'cset__status--neutral'
})

// ---------------------------------------------------------------------------
// Status: self-service withdraw (TASK-30 ruling 12)
// ---------------------------------------------------------------------------
//
// The ONLY status transition a project may make on its own is
// ACTIVE -> HIDDEN ("withdraw"). Publishing (HIDDEN -> ACTIVE) and
// archiving are staff-only actions (done from
// StaffCompanyProfileSection); this view never offers them. The
// server (update_own_company) rejects everything else with a 400
// regardless -- canWithdraw only decides whether the CTA is SHOWN, it
// is not the safety mechanism.
//
// HIDDEN / ARCHIVED render as plain read-only text with a short
// explanation instead of a button that would just 400 if clicked.

const canWithdraw = computed<boolean>(() => status.value === 'active')

const showWithdrawConfirm = ref(false)
const withdrawing = ref(false)

function openWithdrawConfirm(): void {
  if (!canWithdraw.value) {
    console.warn('[CompanySettingsView] openWithdrawConfirm blocked: status is not active')
    return
  }
  showWithdrawConfirm.value = true
}

async function handleWithdraw(): Promise<void> {
  if (!canWithdraw.value) {
    console.warn('[CompanySettingsView] handleWithdraw blocked: status is not active')
    return
  }
  withdrawing.value = true
  try {
    const updated = await updateOwnCompany({ status: 'hidden' })
    profileStore.applyProfile(updated)
    showWithdrawConfirm.value = false
    showToast(t('comp.settings.profile.withdrawSuccess'), 'success')
  } catch (err) {
    // Server-side is the real gate (a stale client could still race
    // an admin's concurrent publish/archive and hit the 400) -- show
    // its message rather than swallowing it as an unhandled rejection.
    const message =
      err instanceof ApiResponseError ? err.detail : t('comp.settings.profile.withdrawError')
    showToast(message, 'error')
  } finally {
    withdrawing.value = false
  }
}

// ---------------------------------------------------------------------------
// Profile: self-service edit (TASK-30 W1)
// ---------------------------------------------------------------------------
//
// One modal covers description + the four media URLs. Submit sends only
// the fields that actually changed, diffed against the loaded profile --
// same exclude_unset contract the roadmap/attachments editors already
// rely on (omit = keep, null = clear). Pricing/supply/distribution and
// status are NOT part of this form -- pricing stays staff-only, status
// has its own dedicated withdraw flow above.

const showEditProfile = ref(false)
const savingProfile = ref(false)

const draftDescription = ref('')
const draftLogoUrl = ref('')
const draftCoverUrl = ref('')
const draftPromoVideoUrl = ref('')
const draftPresentationUrl = ref('')

function openEditProfile(): void {
  const p = profile.value
  if (!p) return
  draftDescription.value = p.description ?? ''
  draftLogoUrl.value = p.logo_url ?? ''
  draftCoverUrl.value = p.cover_url ?? ''
  draftPromoVideoUrl.value = p.promo_video_url ?? ''
  draftPresentationUrl.value = p.presentation_url ?? ''
  showEditProfile.value = true
}

function closeEditProfile(): void {
  showEditProfile.value = false
}

const trimmedDescription = computed<string>(() => draftDescription.value.trim())
const trimmedLogoUrl = computed<string>(() => draftLogoUrl.value.trim())
const trimmedCoverUrl = computed<string>(() => draftCoverUrl.value.trim())
const trimmedPromoVideoUrl = computed<string>(() => draftPromoVideoUrl.value.trim())
const trimmedPresentationUrl = computed<string>(() => draftPresentationUrl.value.trim())

// Every media URL is optional, but if present must be http(s) -- mirror
// the backend validator (and the roadmap section's externalUrlValid
// pattern) so we don't round-trip a guaranteed 422.
function isValidOptionalUrl(v: string): boolean {
  if (!v) return true
  return v.startsWith('http://') || v.startsWith('https://')
}

const logoUrlValid = computed<boolean>(() => isValidOptionalUrl(trimmedLogoUrl.value))
const coverUrlValid = computed<boolean>(() => isValidOptionalUrl(trimmedCoverUrl.value))
const promoVideoUrlValid = computed<boolean>(() => isValidOptionalUrl(trimmedPromoVideoUrl.value))
const presentationUrlValid = computed<boolean>(() =>
  isValidOptionalUrl(trimmedPresentationUrl.value),
)

const canSubmitProfile = computed<boolean>(
  () =>
    logoUrlValid.value &&
    coverUrlValid.value &&
    promoVideoUrlValid.value &&
    presentationUrlValid.value,
)

// Diff against the loaded profile -- send only fields that changed.
// Clearing a field sends explicit null; an untouched field is omitted
// entirely so the backend's exclude_unset PATCH leaves it alone.
function buildProfileUpdateBody(): UpdateOwnCompanyRequest {
  const body: UpdateOwnCompanyRequest = {}
  const p = profile.value
  if (!p) return body

  const origDescription = p.description ?? ''
  if (trimmedDescription.value !== origDescription) {
    body.description = trimmedDescription.value ? trimmedDescription.value : null
  }

  const origLogoUrl = p.logo_url ?? ''
  if (trimmedLogoUrl.value !== origLogoUrl) {
    body.logo_url = trimmedLogoUrl.value ? trimmedLogoUrl.value : null
  }

  const origCoverUrl = p.cover_url ?? ''
  if (trimmedCoverUrl.value !== origCoverUrl) {
    body.cover_url = trimmedCoverUrl.value ? trimmedCoverUrl.value : null
  }

  const origPromoVideoUrl = p.promo_video_url ?? ''
  if (trimmedPromoVideoUrl.value !== origPromoVideoUrl) {
    body.promo_video_url = trimmedPromoVideoUrl.value ? trimmedPromoVideoUrl.value : null
  }

  const origPresentationUrl = p.presentation_url ?? ''
  if (trimmedPresentationUrl.value !== origPresentationUrl) {
    body.presentation_url = trimmedPresentationUrl.value ? trimmedPresentationUrl.value : null
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

  savingProfile.value = true
  try {
    const updated = await updateOwnCompany(body)
    profileStore.applyProfile(updated)
    showEditProfile.value = false
    showToast(t('comp.settings.profile.editSuccess'), 'success')
  } catch (err) {
    const message =
      err instanceof ApiResponseError && err.detail
        ? err.detail
        : t('comp.settings.profile.editError')
    showToast(message, 'error')
  } finally {
    savingProfile.value = false
  }
}

// ---------------------------------------------------------------------------
// Parts -- price and parts for sale, read only
// ---------------------------------------------------------------------------

// The fixed division of the parts, in percent. Shown as a table; the project
// does not edit it.
const DISTRIBUTION_ROWS: readonly { key: string; percent: number }[] = [
  { key: 'sale', percent: 25 },
  { key: 'index', percent: 10 },
  { key: 'bonus', percent: 14 },
  { key: 'reserve', percent: 51 },
]

// ---------------------------------------------------------------------------
// Personal block -- name, e-mail, language
// ---------------------------------------------------------------------------

function userProfile(): Record<string, unknown> {
  const p = authStore.user?.profile
  return p && typeof p === 'object' ? (p as Record<string, unknown>) : {}
}

const firstName = computed<string>(() => {
  const v = userProfile().first_name
  return typeof v === 'string' ? v : ''
})
const lastName = computed<string>(() => {
  const v = userProfile().last_name
  return typeof v === 'string' ? v : ''
})
const personName = computed<string>(() =>
  [firstName.value, lastName.value].filter(Boolean).join(' ').trim(),
)
const personEmail = computed<string>(() => authStore.user?.email ?? '')
const currentLanguage = computed<string>(() => authStore.user?.language ?? '')
const languageLabel = computed<string>(
  () =>
    SUPPORTED_LOCALES.find((l) => l.code === currentLanguage.value)?.label ?? currentLanguage.value,
)
const languageOptions = SUPPORTED_LOCALES.map((l) => ({ value: l.code, label: l.label }))

const showEditPerson = ref(false)
const savingPerson = ref(false)
const draftFirstName = ref('')
const draftLastName = ref('')
const draftLanguage = ref('')

function openEditPerson(): void {
  draftFirstName.value = firstName.value
  draftLastName.value = lastName.value
  draftLanguage.value = currentLanguage.value
  showEditPerson.value = true
}

const canSubmitPerson = computed<boolean>(
  () => (draftFirstName.value.trim().length > 0) === (draftLastName.value.trim().length > 0),
)

async function handleSavePerson(): Promise<void> {
  if (!canSubmitPerson.value) return
  const body: UserUpdate = {}
  const changes: Record<string, unknown> = {}
  if (draftFirstName.value.trim() !== firstName.value)
    changes.first_name = draftFirstName.value.trim()
  if (draftLastName.value.trim() !== lastName.value) changes.last_name = draftLastName.value.trim()
  if (Object.keys(changes).length > 0) body.profile = changes
  const newLanguage =
    draftLanguage.value && draftLanguage.value !== currentLanguage.value ? draftLanguage.value : ''
  if (newLanguage) body.language = newLanguage
  if (Object.keys(body).length === 0) {
    showEditPerson.value = false
    return
  }
  savingPerson.value = true
  try {
    await updateMe(body)
    await authStore.fetchMe()
    if (newLanguage) await setLocale(newLanguage)
    showEditPerson.value = false
    showToast(t('comp.settings.person.editSuccess'), 'success')
  } catch {
    showToast(t('comp.settings.person.editError'), 'error')
  } finally {
    savingPerson.value = false
  }
}

// ---------------------------------------------------------------------------
// Media links -- show the section only if at least one is set
// ---------------------------------------------------------------------------

interface MediaLink {
  key: string
  url: string
  label: string
  icon: typeof ImageIcon
}

const mediaLinks = computed<MediaLink[]>(() => {
  const p = profile.value
  if (!p) return []
  const out: MediaLink[] = []
  if (p.logo_url) {
    out.push({
      key: 'logo',
      url: p.logo_url,
      label: t('comp.settings.links.logo'),
      icon: ImageIcon,
    })
  }
  if (p.cover_url) {
    out.push({
      key: 'cover',
      url: p.cover_url,
      label: t('comp.settings.links.cover'),
      icon: ImageIcon,
    })
  }
  if (p.promo_video_url) {
    out.push({
      key: 'promoVideo',
      url: p.promo_video_url,
      label: t('comp.settings.links.promoVideo'),
      icon: Video,
    })
  }
  if (p.presentation_url) {
    out.push({
      key: 'presentation',
      url: p.presentation_url,
      label: t('comp.settings.links.presentation'),
      icon: ExternalLink,
    })
  }
  return out
})

// ---------------------------------------------------------------------------
// Lifecycle + actions
// ---------------------------------------------------------------------------

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
    void safeNavigate(router.push('/login'), '[CompanySettingsView] to login')
  }
}

async function loadProfile(): Promise<void> {
  await profileStore.loadIfMissing()
  if (dashboardStore.summary === null) void dashboardStore.refresh()
}

onMounted(() => {
  void loadProfile()
})
</script>

<template>
  <div class="cset">
    <!-- Inline page header -->
    <div class="cset__header">
      <h1 class="cset__page-title">
        {{ t('comp.settings.title') }}
      </h1>
      <p class="cset__page-subtitle">
        {{ t('comp.settings.subtitle') }}
      </p>
    </div>

    <!-- Initial loading -->
    <div v-if="initialLoading" class="cset__center">
      <CLoader :size="28" />
    </div>

    <!-- Error -->
    <div v-else-if="hasError" class="cset__center">
      <CEmptyState :title="t('comp.settings.errorTitle')" :description="profileStore.error ?? ''" />
      <CButton variant="outline" size="sm" @click="loadProfile">
        {{ t('comp.settings.errorRetry') }}
      </CButton>
    </div>

    <!-- Loaded -->
    <template v-else-if="profile">
      <!-- Hero card -->
      <section class="cset__hero">
        <div class="cset__hero-logo">
          <img v-if="logoUrl" :src="logoUrl" :alt="companyName" class="cset__hero-logo-img" />
          <div v-else class="cset__hero-logo-fallback">
            {{ initials }}
          </div>
        </div>
        <div class="cset__hero-text">
          <div class="cset__hero-name">
            {{ companyName }}
          </div>
          <span class="cset__status-badge" :class="statusBadgeClass">
            {{ statusLabel }}
          </span>
        </div>
      </section>

      <!-- Personal block -->
      <section class="cset__section">
        <div class="cset__section-title cset__section-title--row">
          <span>{{ t('comp.settings.person.title') }}</span>
          <button
            type="button"
            class="cset__edit-btn"
            :aria-label="t('common.edit')"
            @click="openEditPerson"
          >
            <Pencil :size="14" />
          </button>
        </div>
        <div class="cset__row">
          <span class="cset__row-label">{{ t('comp.settings.person.name') }}</span>
          <span class="cset__row-value">{{ personName || t('comp.settings.person.notSet') }}</span>
        </div>
        <div class="cset__row">
          <span class="cset__row-label">{{ t('comp.settings.person.email') }}</span>
          <span class="cset__row-value">{{ personEmail }}</span>
        </div>
        <div class="cset__row">
          <span class="cset__row-label">{{ t('comp.settings.person.language') }}</span>
          <span class="cset__row-value">{{ languageLabel }}</span>
        </div>
      </section>

      <!-- Profile -->
      <section v-if="profile.description || status" class="cset__section">
        <div class="cset__section-title cset__section-title--row">
          <span>{{ t('comp.settings.profile.title') }}</span>
          <button
            type="button"
            class="cset__edit-btn"
            :aria-label="t('common.edit')"
            @click="openEditProfile"
          >
            <Pencil :size="14" />
          </button>
        </div>
        <div v-if="profile.description" class="cset__row cset__row--block">
          <span class="cset__row-label">
            {{ t('comp.settings.profile.description') }}
          </span>
          <p class="cset__row-multiline">
            {{ profile.description }}
          </p>
        </div>
        <div v-if="status" class="cset__row">
          <span class="cset__row-label">
            {{ t('comp.settings.profile.status') }}
          </span>
          <span v-if="!canWithdraw" class="cset__row-value">{{ statusLabel }}</span>
          <CButton v-else variant="outline" size="sm" @click="openWithdrawConfirm">
            {{ t('comp.settings.profile.withdrawCta') }}
          </CButton>
        </div>
        <!-- Hidden/archived: explain who can undo it, right under the
             status row rather than only inside a modal the user may
             never open. -->
        <p v-if="status === 'hidden'" class="cset__status-hint">
          {{ t('comp.settings.profile.hiddenHint') }}
        </p>
        <p v-else-if="status === 'archived'" class="cset__status-hint">
          {{ t('comp.settings.profile.archivedHint') }}
        </p>
      </section>

      <!-- Parts: the price of a part and the parts for sale, read only -->
      <section class="cset__section">
        <div class="cset__section-title">
          {{ t('comp.settings.parts.title') }}
        </div>
        <div class="cset__row">
          <span class="cset__row-label">{{ t('comp.settings.parts.price') }}</span>
          <span class="cset__row-value">{{ formatPrice(profile.price_per_unit_cents) }}</span>
        </div>
        <p class="cset__status-hint">
          {{ t('comp.settings.parts.priceHint') }}
        </p>
        <div class="cset__row">
          <span class="cset__row-label">{{ t('comp.settings.parts.supply') }}</span>
          <span class="cset__row-value">{{ dashboardStore.summary?.pool ? formatNumber(dashboardStore.summary.pool.total_options, locale) : '—' }}</span>
        </div>
        <p class="cset__status-hint">
          {{ t('comp.settings.parts.supplyHint') }}
        </p>
      </section>

      <!-- Distribution: the fixed division of the parts, read only -->
      <section class="cset__section">
        <div class="cset__section-title">
          {{ t('comp.settings.distribution.title') }}
        </div>
        <div v-for="row in DISTRIBUTION_ROWS" :key="row.key" class="cset__row">
          <span class="cset__row-label">{{ t(`comp.settings.distribution.rows.${row.key}`) }}</span>
          <span class="cset__row-value">{{ row.percent }}%</span>
        </div>
        <p class="cset__status-hint">
          {{ t('comp.settings.distribution.hint') }}
        </p>
      </section>

      <!-- Documents: the project's legal documents to read -->
      <section class="cset__section">
        <div class="cset__section-title">
          {{ t('comp.settings.docs.title') }}
        </div>
        <RouterLink to="/company/docs" class="cset__row cset__row--clickable">
          <span class="cset__row-label">
            <FileText :size="16" />
            {{ t('comp.settings.docs.cta') }}
          </span>
          <ChevronRight :size="16" />
        </RouterLink>
      </section>

      <!-- Support (TASK-39 item 4) -- same "no dead 6th tab-bar slot"
           reasoning as Notifications/Roadmap/Posts/Attachments above:
           CompanyShell has no More tab, so the entry point is a row
           here instead. Measured gap: a company user had no path to
           support anywhere in the product before this. -->
      <section class="cset__section">
        <div class="cset__section-title">
          {{ t('comp.settings.support.title') }}
        </div>
        <RouterLink to="/company/support" class="cset__row cset__row--clickable">
          <span class="cset__row-label">
            <MessageCircle :size="16" />
            {{ t('comp.settings.support.cta') }}
          </span>
          <ChevronRight :size="16" />
        </RouterLink>
      </section>

      <!-- FAQ (TASK-39 item 3) -- same "no dead 6th tab-bar slot"
           reasoning as Notifications/Roadmap/Posts/Attachments/Support
           above: CompanyShell has no More tab, so the entry point is a
           row here instead. This is the company's OWN, SEPARATE FAQ
           (owner ruling) -- not the shared investor/agent one -- see
           CompanyFaqView.vue for the full ruling. -->
      <section class="cset__section">
        <div class="cset__section-title">
          {{ t('comp.settings.faq.title') }}
        </div>
        <RouterLink to="/company/faq" class="cset__row cset__row--clickable">
          <span class="cset__row-label">
            <HelpCircle :size="16" />
            {{ t('comp.settings.faq.cta') }}
          </span>
          <ChevronRight :size="16" />
        </RouterLink>
      </section>

      <!-- Audit feed (TASK-39 item 7) -- same "no dead 6th tab-bar
           slot" reasoning as Notifications/Roadmap/Posts/Attachments/
           Support above: CompanyShell has no More tab, so the entry
           point is a row here instead. Measured gap: the project had
           no way to see its own write history (who changed what and
           when) anywhere in the product before this. -->
      <section class="cset__section">
        <div class="cset__section-title">
          {{ t('comp.settings.audit.title') }}
        </div>
        <RouterLink to="/company/audit" class="cset__row cset__row--clickable">
          <span class="cset__row-label">
            <History :size="16" />
            {{ t('comp.settings.audit.cta') }}
          </span>
          <ChevronRight :size="16" />
        </RouterLink>
      </section>

      <!-- Media links -->
      <section v-if="mediaLinks.length > 0" class="cset__section">
        <div class="cset__section-title">
          {{ t('comp.settings.links.title') }}
        </div>
        <a
          v-for="link in mediaLinks"
          :key="link.key"
          class="cset__row cset__row--clickable"
          :href="link.url"
          target="_blank"
          rel="noopener noreferrer"
        >
          <span class="cset__row-label">
            <component :is="link.icon" :size="16" />
            {{ link.label }}
          </span>
          <span class="cset__row-label cset__row-label--accent">
            {{ t('comp.settings.links.open') }}
            <ExternalLink :size="16" />
          </span>
        </a>
      </section>

      <!-- Actions -->
      <section class="cset__section">
        <div class="cset__section-title">
          {{ t('comp.settings.actions.title') }}
        </div>
        <TwoFactorSection tPrefix="comp.settings.actions" />
        <ActiveSessionsSection tPrefix="comp.settings.actions" />
        <NotificationPreferencesSection tPrefix="comp.settings.actions" />
        <DeactivateAccountSection tPrefix="comp.settings.actions" />
        <button
          type="button"
          class="cset__row cset__row--clickable"
          :class="{ 'cset__row--disabled': loggingOut }"
          :disabled="loggingOut"
          @click="handleLogout"
        >
          <span class="cset__row-label cset__row-label--danger">
            <LogOut :size="16" />
            {{ t('comp.settings.actions.logout') }}
          </span>
          <ChevronRight :size="16" />
        </button>
      </section>

      <!-- Withdraw confirm modal (ACTIVE -> HIDDEN only) -->
      <CModal :open="showWithdrawConfirm" @close="showWithdrawConfirm = false">
        <h3 class="cset__modal-title">
          {{ t('comp.settings.profile.withdrawConfirmTitle') }}
        </h3>
        <p class="cset__modal-hint">
          {{ t('comp.settings.profile.withdrawConfirmBody') }}
        </p>
        <div class="cset__modal-actions">
          <CButton variant="outline" size="sm" @click="showWithdrawConfirm = false">
            {{ t('common.cancel') }}
          </CButton>
          <CButton variant="primary" size="sm" :loading="withdrawing" @click="handleWithdraw">
            {{ t('comp.settings.profile.withdrawConfirmSubmit') }}
          </CButton>
        </div>
      </CModal>

      <!-- Profile edit modal (TASK-30 W1): description + the four media
           URLs. Pricing/supply/distribution/status are NOT here. -->
      <CModal :open="showEditProfile" @close="closeEditProfile">
        <h3 class="cset__modal-title">
          {{ t('comp.settings.profile.editTitle') }}
        </h3>

        <CTextarea
          v-model="draftDescription"
          :label="t('comp.settings.profile.description')"
          :rows="5"
          maxlength="5000"
        />

        <CInput
          v-model="draftLogoUrl"
          :label="t('comp.settings.links.logo')"
          placeholder="https://..."
          maxlength="2000"
          :error="!logoUrlValid ? t('comp.settings.profile.urlFormatError') : ''"
        />

        <CInput
          v-model="draftCoverUrl"
          :label="t('comp.settings.links.cover')"
          placeholder="https://..."
          maxlength="2000"
          :error="!coverUrlValid ? t('comp.settings.profile.urlFormatError') : ''"
        />

        <CInput
          v-model="draftPromoVideoUrl"
          :label="t('comp.settings.links.promoVideo')"
          placeholder="https://..."
          maxlength="2000"
          :error="!promoVideoUrlValid ? t('comp.settings.profile.urlFormatError') : ''"
        />

        <CInput
          v-model="draftPresentationUrl"
          :label="t('comp.settings.links.presentation')"
          placeholder="https://..."
          maxlength="2000"
          :error="!presentationUrlValid ? t('comp.settings.profile.urlFormatError') : ''"
        />

        <div class="cset__modal-actions">
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

      <!-- Personal block edit modal: name and language -->
      <CModal :open="showEditPerson" @close="showEditPerson = false">
        <h3 class="cset__modal-title">
          {{ t('comp.settings.person.editTitle') }}
        </h3>
        <CInput
          v-model="draftFirstName"
          :label="t('comp.settings.person.firstName')"
          maxlength="100"
        />
        <CInput
          v-model="draftLastName"
          :label="t('comp.settings.person.lastName')"
          maxlength="100"
        />
        <CSelect
          v-model="draftLanguage"
          :label="t('comp.settings.person.language')"
          :options="languageOptions"
        />
        <div class="cset__modal-actions">
          <CButton variant="outline" size="sm" @click="showEditPerson = false">
            {{ t('common.cancel') }}
          </CButton>
          <CButton
            variant="primary"
            size="sm"
            :loading="savingPerson"
            :disabled="!canSubmitPerson"
            @click="handleSavePerson"
          >
            {{ t('common.save') }}
          </CButton>
        </div>
      </CModal>
    </template>
  </div>
</template>

<style scoped>
.cset {
  display: flex;
  flex-direction: column;
  padding-bottom: var(--space-5);
}

/* Header */
.cset__header {
  padding: var(--space-4) var(--space-4) 0;
}
.cset__page-title {
  font-size: var(--fs-lg);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 var(--space-1);
}
.cset__page-subtitle {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  margin: 0 0 var(--space-4);
}

/* Whole-screen states (loading / error) */
.cset__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  min-height: calc(100vh - 280px);
  min-height: calc(100dvh - 280px);
  padding: var(--space-5);
  text-align: center;
}

/* Hero card */
.cset__hero {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  padding: var(--space-4);
  margin: 0 var(--space-4) var(--space-4);
  border-radius: var(--radius);
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
}
.cset__hero-logo {
  width: var(--size-4xl);
  height: var(--size-4xl);
  border-radius: var(--radius-sm);
  overflow: hidden;
  flex-shrink: 0;
  background: var(--bg-page);
  border: 1px solid var(--border-default);
  display: flex;
  align-items: center;
  justify-content: center;
}
.cset__hero-logo-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.cset__hero-logo-fallback {
  font-size: var(--fs-lg);
  font-weight: 700;
  color: var(--primary);
  letter-spacing: 0.5px;
}
.cset__hero-text {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  min-width: 0;
}
.cset__hero-name {
  font-size: var(--fs-h4);
  font-weight: 700;
  color: var(--text-primary);
  word-break: break-word;
}

/* Status badge */
.cset__status-badge {
  display: inline-block;
  align-self: flex-start;
  font-size: var(--fs-xs);
  font-weight: 600;
  padding: var(--space-1) var(--space-3);
  border-radius: var(--radius-sm);
  text-transform: capitalize;
}
.cset__status--success {
  background: var(--bg-surface);
  color: var(--success);
  border: 1px solid var(--success);
}
.cset__status--warning {
  background: var(--bg-surface);
  color: var(--warning);
  border: 1px solid var(--warning);
}
.cset__status--neutral {
  background: var(--bg-surface);
  color: var(--text-secondary);
  border: 1px solid var(--border-default);
}

/* Status hint (hidden / archived explanation, under the status row) */
.cset__status-hint {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
  margin: calc(-1 * var(--space-2)) 0 var(--space-2);
  padding: 0 var(--space-1);
}

/* Withdraw confirm modal */
.cset__modal-title {
  font-size: var(--fs-h4);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 var(--space-2);
}
.cset__modal-hint {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  margin: 0 0 var(--space-4);
}
.cset__modal-actions {
  display: flex;
  gap: var(--space-2);
  justify-content: flex-end;
}

/* Section */
.cset__section {
  padding: 0 var(--space-4);
  margin-bottom: var(--space-4-lg);
}
.cset__section-title {
  font-size: var(--fs-xs);
  font-weight: 700;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.12em;
  margin-bottom: var(--space-2);
  padding: 0 var(--space-1);
}
.cset__section-title--row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.cset__edit-btn {
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
.cset__edit-btn:hover {
  color: var(--primary);
  background: var(--bg-subtle);
}

/* Row -- shared between <div> and <a>/<button> variants */
.cset__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--border-default);
  min-height: var(--size-3xl);
}
.cset__row:last-child {
  border-bottom: none;
}
a.cset__row,
button.cset__row {
  width: 100%;
  background: transparent;
  border: 0;
  border-bottom: 1px solid var(--border-default);
  font: inherit;
  color: inherit;
  text-align: left;
  cursor: pointer;
  text-decoration: none;
}
a.cset__row:last-child,
button.cset__row:last-child {
  border-bottom: none;
}

.cset__row--block {
  flex-wrap: wrap;
  align-items: stretch;
  flex-direction: column;
}
.cset__row--clickable {
  transition: background 0.15s;
}
.cset__row--clickable:hover {
  background: var(--bg-subtle);
}
.cset__row--disabled {
  opacity: 0.6;
  pointer-events: none;
}

.cset__row-label {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--fs-sm);
  color: var(--text-primary);
}
.cset__row-label--accent {
  color: var(--primary);
  font-weight: 600;
}
.cset__row-label--muted {
  color: var(--text-secondary);
}
.cset__row-label--danger {
  color: var(--danger);
  font-weight: 600;
}
.cset__row-value {
  font-size: var(--fs-sm);
  color: var(--text-tertiary);
  text-align: right;
  word-break: break-word;
}
.cset__row-multiline {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  margin: var(--space-1) 0 0;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
}

/* JSON view -- monospace, scrollable on overflow */
.cset__json {
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

/* Static support hint */
.cset__hint {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
  margin: 0 var(--space-4) var(--space-4);
  padding: 0 var(--space-1);
  font-style: italic;
}

/* READING MEASURE — descriptive text only. --maxw-prose (680px) is a CEILING,
   so this rule cannot bind until the container is already wider than a
   comfortable line: on a phone it does nothing at all, which is why it needs
   no media query. Measured at 1280 before applying: `event-card__desc` ran to
   932px and `staff-dash__role-count` to 901. Names, figures and table cells
   are deliberately NOT capped — a name is not prose, and capping it would only
   leave dead space in its row. */
.cset__hint {
  max-width: var(--maxw-prose);
}
</style>
