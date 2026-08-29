<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- CompanySettingsView (Phase F5.2 B5)
// =============================================================================
//
// Settings tab inside CompanyShell. Read-only render of CompanyResponse
// (the staff-side profile served by GET /companies/me, Sprint 4.5).
//
// CompanyShell renders the global CHeader and CTabBar -- this view has
// only inline content with an <h1> + <p> page header, mirroring
// InvestorSettingsView and the F5.1 dashboard.
//
// READ-ONLY POLICY (MVP, revised TASK-30 ruling 10/12, W1 pass).
//   Pricing & supply (price_per_unit_cents / total_supply /
//   shares_per_option) and the distribution_config JSON stay
//   staff/admin-only by deliberate ruling ("the project describes,
//   the admin owns and prices") -- this view still renders them as
//   plain read-only rows/JSON, backed by a short hint pointing at
//   support, never an edit control.
//
//   TASK-30 ruling 12 carves out one narrow self-service write on
//   STATUS: while ACTIVE, the project may withdraw itself
//   (status -> HIDDEN) via PATCH /api/v1/companies/me
//   (api/companies.ts::updateOwnCompany). It may NOT republish itself
//   (HIDDEN -> ACTIVE) or archive itself -- both are staff-only,
//   enforced server-side by update_own_company() which 400s any
//   transition other than ACTIVE -> HIDDEN. This view mirrors that
//   asymmetry: a HIDDEN or ARCHIVED company sees status as plain text
//   with a short explanation, never a button that would just 400 when
//   clicked.
//
//   W1 UPDATE: the other TASK-30 project-editable fields -- description /
//   logo_url / cover_url / promo_video_url / presentation_url -- WERE
//   flagged above as "not wired to editing here, out of scope for this
//   pass". They now ARE wired: an edit pencil next to the Profile
//   section title opens a form modal covering all five, PATCHes only
//   the fields that actually changed (exclude_unset semantics --
//   omitted fields are left alone server-side), and applies the
//   response back onto the profile store on success. See the "Profile:
//   self-service edit" block below for the diff-and-submit logic.
//
// SECTIONS, in render order:
//   1. Hero card -- logo + name + status badge.
//   2. Profile -- description, status (label + badge, or a "withdraw"
//      CTA when ACTIVE -- see the Status self-service block below),
//      plus an edit pencil that opens the profile/media form modal.
//   3. Pricing & supply -- price_per_unit, total_supply,
//      shares_per_option. Read-only, staff/admin-only.
//   4. Distribution config -- raw JSON view (<pre>) of the JSONB
//      object. The platform's revenue-split contract changes over
//      time without a frontend release; rendering as JSON keeps the
//      view honest and forward-compatible. Empty `{}` shows the
//      "empty" placeholder line. Read-only, staff/admin-only, followed
//      by a short hint that pricing/supply/distribution stay
//      staff-managed.
//   5. Media -- logo / cover / promo video / presentation as
//      "Open" links. Skipped entirely if every URL is null -- these
//      URLs are edited from the same modal as the Profile section
//      (§2), not from a control in this section.
//   6. Actions -- sign-out only. Without this, a company role has
//      no way to leave the session.
//
// FIELDS DELIBERATELY OMITTED.
//   - id / user_id        -- internal UUIDs, no operational use.
//   - created_at          -- noise.
//   - updated_at          -- noise.
//   - currency            -- not on CompanyResponse; formatPrice
//                            falls back to USD (TD-F08a).
//
// DATA SOURCE.
//   companyProfile.loadIfMissing() -- cache-first. The dashboard view
//   (F5.1 B2) typically loads it before the user reaches this tab,
//   in which case onMounted is a no-op. On a hard refresh into
//   /company/settings, the cache is empty and we fetch.
//
// RENDER POLICY.
//   Same all-or-nothing pattern as the dashboard: full-screen loader
//   until profile resolves; full-screen retry on error; everything
//   else only after the profile is non-null. Avoids partial-state
//   confusion.
// =============================================================================

import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  Bell,
  ChevronRight,
  ExternalLink,
  FileText,
  History,
  Image as ImageIcon,
  LogOut,
  Layers,
  Map as MapIcon,
  MessageCircle,
  Newspaper,
  Package,
  Pencil,
  Video,
} from 'lucide-vue-next'

import { CButton, CEmptyState, CInput, CLoader, CModal, CTextarea } from '@/components/ui'
import EmailChangeSection from '@/components/shared/EmailChangeSection.vue'
import TwoFactorSection from '@/components/shared/TwoFactorSection.vue'
import ActiveSessionsSection from '@/components/shared/ActiveSessionsSection.vue'
import NotificationPreferencesSection from '@/components/shared/NotificationPreferencesSection.vue'
import DeactivateAccountSection from '@/components/shared/DeactivateAccountSection.vue'
import { useAuthStore } from '@/stores/auth'
import { useCompanyProfileStore } from '@/stores/companyProfile'
import { safeNavigate } from '@/composables/safeNavigate'
import { useToast } from '@/composables/useToast'
import { formatNumber, formatPrice } from '@/utils/format'
import { tOrRaw } from '@/utils/i18n'
import { updateOwnCompany } from '@/api/companies'
import { ApiResponseError } from '@/api/client'
import type { UpdateOwnCompanyRequest } from '@/api/types'

const { t, locale } = useI18n()
const router = useRouter()
const authStore = useAuthStore()
const profileStore = useCompanyProfileStore()
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
// Distribution config -- JSON view
// ---------------------------------------------------------------------------

const distributionJson = computed<string>(() => {
  const cfg = profile.value?.distribution_config
  if (!cfg) return ''
  // Pretty-print with 2-space indent. Object guaranteed to be plain
  // JSON-able by the backend contract (Record<string, unknown> over
  // the wire as JSONB).
  return JSON.stringify(cfg, null, 2)
})

const hasDistributionConfig = computed<boolean>(() => {
  const cfg = profile.value?.distribution_config
  if (!cfg) return false
  return Object.keys(cfg).length > 0
})

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

      <!-- Notifications (Phase 6, the bell) -- same "no dead 6th tab-bar
           slot" reasoning as the Roadmap/Posts/Attachments rows below:
           COMPANY_TABS has 5 fixed slots, so a route not on the tab bar
           gets a settings row instead. Investor/Agent/StaffMoreView all
           got an equivalent tile added for this same route; this row is
           company's version of the same entry point (an adversarial
           review of the notifications build caught that company had
           been left without one, reachable only via the header bell). -->
      <section class="cset__section">
        <div class="cset__section-title">
          {{ t('comp.settings.notifications.title') }}
        </div>
        <RouterLink to="/company/notifications" class="cset__row cset__row--clickable">
          <span class="cset__row-label">
            <Bell :size="16" />
            {{ t('comp.settings.notifications.cta') }}
          </span>
          <ChevronRight :size="16" />
        </RouterLink>
      </section>

      <!-- Roadmap (TASK-30 self-service, §4) -->
      <section class="cset__section">
        <div class="cset__section-title">
          {{ t('comp.settings.roadmap.title') }}
        </div>
        <RouterLink to="/company/roadmap" class="cset__row cset__row--clickable">
          <span class="cset__row-label">
            <MapIcon :size="16" />
            {{ t('comp.settings.roadmap.cta') }}
          </span>
          <ChevronRight :size="16" />
        </RouterLink>
      </section>

      <!-- Posts (TASK-30 self-service, §4, W4) -->
      <section class="cset__section">
        <div class="cset__section-title">
          {{ t('comp.settings.posts.title') }}
        </div>
        <RouterLink to="/company/posts" class="cset__row cset__row--clickable">
          <span class="cset__row-label">
            <Newspaper :size="16" />
            {{ t('comp.settings.posts.cta') }}
          </span>
          <ChevronRight :size="16" />
        </RouterLink>
      </section>

      <!-- Attachments (TASK-30 self-service, §4) -->
      <section class="cset__section">
        <div class="cset__section-title">
          {{ t('comp.settings.attachments.title') }}
        </div>
        <RouterLink to="/company/attachments" class="cset__row cset__row--clickable">
          <span class="cset__row-label">
            <FileText :size="16" />
            {{ t('comp.settings.attachments.cta') }}
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

      <!-- Pricing & supply -->
      <section class="cset__section">
        <div class="cset__section-title">
          {{ t('comp.settings.pricing.title') }}
        </div>
        <div class="cset__row">
          <span class="cset__row-label">
            <Package :size="16" />
            {{ t('comp.settings.pricing.pricePerUnit') }}
          </span>
          <span class="cset__row-value">
            {{ formatPrice(profile.price_per_unit_cents) }}
          </span>
        </div>
        <div class="cset__row">
          <span class="cset__row-label">
            <Layers :size="16" />
            {{ t('comp.settings.pricing.totalSupply') }}
          </span>
          <span class="cset__row-value">
            {{ formatNumber(profile.total_supply, locale) }}
          </span>
        </div>
        <div class="cset__row">
          <span class="cset__row-label">
            {{ t('comp.settings.pricing.sharesPerOption') }}
          </span>
          <span class="cset__row-value">
            {{ formatNumber(profile.shares_per_option, locale) }}
          </span>
        </div>
      </section>

      <!-- Distribution config -->
      <section class="cset__section">
        <div class="cset__section-title">
          {{ t('comp.settings.distribution.title') }}
        </div>
        <div v-if="!hasDistributionConfig" class="cset__row">
          <span class="cset__row-label cset__row-label--muted">
            {{ t('comp.settings.distribution.empty') }}
          </span>
        </div>
        <pre v-else class="cset__json">{{ distributionJson }}</pre>
      </section>

      <!-- Pricing/supply/distribution stay staff/admin-only (TASK-30
           ruling) -- this replaces the old page-wide "contact support
           to edit" hint now that description/media are self-service. -->
      <p class="cset__hint">
        {{ t('comp.settings.adminManagedHint') }}
      </p>

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
        <EmailChangeSection tPrefix="comp.settings.actions" />
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
