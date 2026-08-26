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
// READ-ONLY POLICY (MVP, revised TASK-30 ruling 10/12).
//   The company does NOT edit most of its profile from this UI; staff
//   does, via the Sprint 4.1 staff endpoints. We render every field as
//   a row, follow up with a static "contact support" hint, and wire
//   one status-changing action. This matches Frontend.md §F5.2: "Note:
//   для редактирования профиля обратитесь в support" for everything
//   EXCEPT status.
//
//   TASK-30 ruling 12 carves out one narrow self-service write: while
//   ACTIVE, the project may withdraw itself (status -> HIDDEN) via
//   PATCH /api/v1/companies/me (api/companies.ts::updateOwnCompany).
//   It may NOT republish itself (HIDDEN -> ACTIVE) or archive itself --
//   both are staff-only, enforced server-side by update_own_company()
//   which 400s any transition other than ACTIVE -> HIDDEN. This view
//   mirrors that asymmetry: a HIDDEN or ARCHIVED company sees status as
//   plain text with a short explanation, never a button that would
//   just 400 when clicked. Other TASK-30 project-editable fields
//   (description / logo_url / cover_url / promo_video_url /
//   presentation_url) are NOT wired to editing here -- out of scope
//   for this pass, still read-only, still covered by the support hint.
//
// SECTIONS, in render order:
//   1. Hero card -- logo + name + status badge.
//   2. Profile -- description, status (label + badge, or a "withdraw"
//      CTA when ACTIVE -- see the Status self-service block below).
//   3. Pricing & supply -- price_per_unit, total_supply,
//      shares_per_option.
//   4. Distribution config -- raw JSON view (<pre>) of the JSONB
//      object. The platform's revenue-split contract changes over
//      time without a frontend release; rendering as JSON keeps the
//      view honest and forward-compatible. Empty `{}` shows the
//      "empty" placeholder line.
//   5. Media -- logo / cover / promo video / presentation as
//      "Open" links. Skipped entirely if every URL is null.
//   6. Edit-via-support hint -- static line above the actions
//      section so the user reads it before reaching for sign-out.
//   7. Actions -- sign-out only. Without this, a company role has
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
  ChevronRight,
  ExternalLink,
  Image as ImageIcon,
  LogOut,
  Layers,
  Map as MapIcon,
  Package,
  Video,
} from 'lucide-vue-next'

import { CButton, CEmptyState, CLoader, CModal } from '@/components/ui'
import { useAuthStore } from '@/stores/auth'
import { useCompanyProfileStore } from '@/stores/companyProfile'
import { safeNavigate } from '@/composables/safeNavigate'
import { useToast } from '@/composables/useToast'
import { formatNumber, formatPrice } from '@/utils/format'
import { tOrRaw } from '@/utils/i18n'
import { updateOwnCompany } from '@/api/companies'
import { ApiResponseError } from '@/api/client'

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
        <div class="cset__section-title">
          {{ t('comp.settings.profile.title') }}
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

      <!-- Static support hint above the action section. Plain text,
           not a toast: the user is not trying to tap anything yet. -->
      <p class="cset__hint">
        {{ t('comp.settings.editViaSupport') }}
      </p>

      <!-- Actions -->
      <section class="cset__section">
        <div class="cset__section-title">
          {{ t('comp.settings.actions.title') }}
        </div>
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
