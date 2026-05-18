<script setup lang="ts">
// =============================================================================
// CBSHOME Frontend -- CompanySettingsView (Phase F5.2 B5)
// =============================================================================
//
// Settings tab inside CompanyShell. Read-only render of CompanyResponse
// (the staff-side profile served by GET /companies/me, Sprint 4.5).
//
// CompanyShell renders the global CHeader and CTabBar -- this view has
// only inline content with an <h1> + <p> page header, mirroring
// InvestorSettingsView and the F5.1 dashboard.
//
// READ-ONLY POLICY (MVP).
//   The company itself does NOT edit its profile from this UI; staff
//   does, via the Sprint 4.1 staff endpoints. We render every field
//   as a row, follow up with a static "contact support" hint, and
//   wire only one action -- sign out. This matches Frontend.md §F5.2:
//   "Note: для редактирования профиля обратитесь в support".
//
// SECTIONS, in render order:
//   1. Hero card -- logo + name + status badge.
//   2. Profile -- description, status (label + badge).
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
import {
  isNavigationFailure,
  NavigationFailureType,
  useRouter,
} from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  ChevronRight,
  ExternalLink,
  Image as ImageIcon,
  LogOut,
  Layers,
  Package,
  Video,
} from 'lucide-vue-next'

import { CButton, CEmptyState, CLoader } from '@/components/ui'
import { useAuthStore } from '@/stores/auth'
import { useCompanyProfileStore } from '@/stores/companyProfile'
import { formatNumber, formatPrice } from '@/utils/format'
import { tOrRaw } from '@/utils/i18n'

const { t, locale } = useI18n()
const router = useRouter()
const authStore = useAuthStore()
const profileStore = useCompanyProfileStore()

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
    // tokenless user to /login anyway -- no toast needed. We only
    // log real failures (unknown route, thrown guard, ...).
    router
      .push('/login')
      .catch((err: unknown) => {
        if (
          isNavigationFailure(err, NavigationFailureType.duplicated)
          || isNavigationFailure(err, NavigationFailureType.cancelled)
          || isNavigationFailure(err, NavigationFailureType.aborted)
        ) {
          return
        }
        console.error('[CompanySettingsView] navigation to login failed:', err)
      })
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
      <h1 class="cset__page-title">{{ t('comp.settings.title') }}</h1>
      <p class="cset__page-subtitle">{{ t('comp.settings.subtitle') }}</p>
    </div>

    <!-- Initial loading -->
    <div v-if="initialLoading" class="cset__center">
      <CLoader :size="28" />
    </div>

    <!-- Error -->
    <div v-else-if="hasError" class="cset__center">
      <CEmptyState
        :title="t('comp.settings.errorTitle')"
        :description="profileStore.error ?? ''"
      />
      <CButton variant="outline" size="sm" @click="loadProfile">
        {{ t('comp.settings.errorRetry') }}
      </CButton>
    </div>

    <!-- Loaded -->
    <template v-else-if="profile">
      <!-- Hero card -->
      <section class="cset__hero">
        <div class="cset__hero-logo">
          <img
            v-if="logoUrl"
            :src="logoUrl"
            :alt="companyName"
            class="cset__hero-logo-img"
          />
          <div v-else class="cset__hero-logo-fallback">
            {{ initials }}
          </div>
        </div>
        <div class="cset__hero-text">
          <div class="cset__hero-name">{{ companyName }}</div>
          <span
            class="cset__status-badge"
            :class="statusBadgeClass"
          >
            {{ statusLabel }}
          </span>
        </div>
      </section>

      <!-- Profile -->
      <section
        v-if="profile.description || status"
        class="cset__section"
      >
        <div class="cset__section-title">
          {{ t('comp.settings.profile.title') }}
        </div>
        <div v-if="profile.description" class="cset__row cset__row--block">
          <span class="cset__row-label">
            {{ t('comp.settings.profile.description') }}
          </span>
          <p class="cset__row-multiline">{{ profile.description }}</p>
        </div>
        <div v-if="status" class="cset__row">
          <span class="cset__row-label">
            {{ t('comp.settings.profile.status') }}
          </span>
          <span class="cset__row-value">{{ statusLabel }}</span>
        </div>
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
            <ExternalLink :size="14" />
          </span>
        </a>
      </section>

      <!-- Static support hint above the action section. Plain text,
           not a toast: the user is not trying to tap anything yet. -->
      <p class="cset__hint">{{ t('comp.settings.editViaSupport') }}</p>

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
    </template>
  </div>
</template>

<style scoped>
.cset {
  display: flex;
  flex-direction: column;
  padding-bottom: 24px;
}

/* Header */
.cset__header { padding: 16px 16px 0; }
.cset__page-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--text);
  margin: 0 0 4px;
}
.cset__page-subtitle {
  font-size: 14px;
  color: var(--text-secondary);
  margin: 0 0 16px;
}

/* Whole-screen states (loading / error) */
.cset__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  min-height: calc(100vh - 280px);
  min-height: calc(100dvh - 280px);
  padding: 24px;
  text-align: center;
}

/* Hero card */
.cset__hero {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 16px;
  margin: 0 16px 16px;
  border-radius: var(--radius);
  background: var(--bg-elevated, var(--bg));
  border: 1px solid var(--border);
}
.cset__hero-logo {
  width: 56px;
  height: 56px;
  border-radius: var(--radius-sm);
  overflow: hidden;
  flex-shrink: 0;
  background: var(--bg);
  border: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: center;
}
.cset__hero-logo-img { width: 100%; height: 100%; object-fit: cover; }
.cset__hero-logo-fallback {
  font-size: 20px;
  font-weight: 700;
  color: var(--primary);
  letter-spacing: 0.5px;
}
.cset__hero-text {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}
.cset__hero-name {
  font-size: 18px;
  font-weight: 700;
  color: var(--text);
  word-break: break-word;
}

/* Status badge */
.cset__status-badge {
  display: inline-block;
  align-self: flex-start;
  font-size: 11px;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: var(--radius-sm);
  text-transform: capitalize;
}
.cset__status--success {
  background: var(--bg-elevated, var(--bg));
  color: var(--success, var(--primary));
  border: 1px solid var(--success, var(--primary));
}
.cset__status--warning {
  background: var(--bg-elevated, var(--bg));
  color: var(--warning, var(--text-secondary));
  border: 1px solid var(--warning, var(--border));
}
.cset__status--neutral {
  background: var(--bg-elevated, var(--bg));
  color: var(--text-secondary);
  border: 1px solid var(--border);
}

/* Section */
.cset__section { padding: 0 16px; margin-bottom: 20px; }
.cset__section-title {
  font-size: 12px;
  font-weight: 700;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.12em;
  margin-bottom: 8px;
  padding: 0 4px;
}

/* Row -- shared between <div> and <a>/<button> variants */
.cset__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--border);
  min-height: 48px;
}
.cset__row:last-child { border-bottom: none; }
a.cset__row,
button.cset__row {
  width: 100%;
  background: transparent;
  border: 0;
  border-bottom: 1px solid var(--border);
  font: inherit;
  color: inherit;
  text-align: left;
  cursor: pointer;
  text-decoration: none;
}
a.cset__row:last-child,
button.cset__row:last-child { border-bottom: none; }

.cset__row--block {
  flex-wrap: wrap;
  align-items: stretch;
  flex-direction: column;
}
.cset__row--clickable { transition: background 0.15s; }
.cset__row--clickable:hover { background: var(--bg-subtle, var(--bg-elevated)); }
.cset__row--disabled {
  opacity: 0.6;
  pointer-events: none;
}

.cset__row-label {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: var(--text);
}
.cset__row-label--accent {
  color: var(--primary);
  font-weight: 600;
}
.cset__row-label--muted {
  color: var(--text-secondary);
}
.cset__row-label--danger {
  color: var(--danger, #DC2626);
  font-weight: 600;
}
.cset__row-value {
  font-size: 13px;
  color: var(--text-tertiary);
  text-align: right;
  word-break: break-word;
}
.cset__row-multiline {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 4px 0 0;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
}

/* JSON view -- monospace, scrollable on overflow */
.cset__json {
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

/* Static support hint */
.cset__hint {
  font-size: 12px;
  color: var(--text-tertiary);
  margin: 0 16px 16px;
  padding: 0 4px;
  font-style: italic;
}
</style>
