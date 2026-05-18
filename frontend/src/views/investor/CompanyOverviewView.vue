<script setup lang="ts">
// =============================================================================
// CBSHOME Frontend -- CompanyOverviewView (iter 2.5 batch 6, R1 §1.3)
// =============================================================================
//
// Investor company profile screen. Sub-route under the Companies tab:
// /investor/companies/:id and /agent/companies/:id (route names added
// in batch 9). Renders:
//   1. Hero -- cover + name + status chip + description
//   2. Stats card -- 4 public metrics from PublicCompanyStatsResponse
//   3. Roadmap timeline -- batch 5 component, hidden when items empty
//   4. Documents section -- batch 6 AttachmentsSection, self-hides when empty
//   5. Sticky CTA -- "View products" to ProductsByCompanyView (batch 8 + 9)
//
// DATA SOURCE.
//   Local state, not a store. Single round-trip via getCompany(id),
//   which returns a PublicCompanyDetailResponse carrying stats and
//   roadmap inline (R1 §1.6 backend contract). Adding a store would
//   buy nothing -- there's no shared data with other views, no
//   pagination, no infinite-scroll. The view manages its own loading
//   / errored / data refs and reloads on route :id swap.
//
// 404 BEHAVIOUR.
//   Backend returns 404 for non-active (hidden / archived) companies.
//   We detect ApiResponseError with status 404 and render a
//   "company not found" empty state with a back-to-list CTA instead
//   of the generic error banner. Other ApiResponseError statuses
//   (5xx, network) flip the `errored` flag and render the retry path.
//
// ROUTING -- ROUTE NAMES NOT YET DEFINED.
//   Three forward navigations from this view (RoadmapTimeline product
//   click, RoadmapTimeline external click, sticky CTA "View products")
//   target route names that land in batches 8 / 9:
//     - investor-product-detail / agent-product-detail   (EXISTS, batch 1 routes)
//     - investor-company-products / agent-company-products (BATCH 9)
//   External clicks bypass the router entirely (window.open).
//   Post clicks are a no-op placeholder until the post-view route
//   ships (deferred to iter 2.6 or later).
//
// IN-PLACE :id SWAP.
//   Vue Router reuses the component instance across param changes
//   when navigating from /investor/companies/A to /investor/companies/B.
//   The watch on route.params.id covers that case -- without it the
//   user would see A's content frozen while B's id is in the URL.
//
// FLOATING CTA (iter 2.5 cta-fix2).
//   The "View products" button is pinned to the viewport above the
//   CTabBar via position:fixed -- always visible, regardless of scroll
//   position or content length. The earlier sticky-bottom approach
//   only engaged when content was tall enough to scroll, leaving the
//   CTA hidden below the tab bar on short pages (the bug iter 2.5
//   shipped with). The token --tab-bar-height (variables.css) is the
//   anchor: when the bar's height changes, the CTA follows.
//   .co__main carries enough bottom padding to clear the floating
//   CTA + tab bar + safe-area inset so the last section never sits
//   behind the button on scroll-end.
// =============================================================================

import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Building } from 'lucide-vue-next'

import { CButton, CEmptyState, CLoader, CStatCard } from '@/components/ui'
import CHeader from '@/components/layout/CHeader.vue'
import AttachmentsSection from '@/components/shared/AttachmentsSection.vue'
import RoadmapTimeline from '@/components/shared/RoadmapTimeline.vue'
import { ApiResponseError } from '@/api/client'
import { getCompany } from '@/api/companies'
import { safeNavigate } from '@/composables/safeNavigate'
import { isAgentShell } from '@/router/helpers'
import { formatNumber, resolveCoverImage } from '@/utils/format'
import type { PublicCompanyDetailResponse } from '@/api/types'

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()

const data = ref<PublicCompanyDetailResponse | null>(null)
const loading = ref<boolean>(true)
const errored = ref<boolean>(false)
const notFound = ref<boolean>(false)

const companyId = computed<string>(() => route.params.id as string)

// Role-aware destination route names. The first three exist today; the
// company-products one lands in batch 9. Until then, router.push with
// an unresolved name emits a runtime warning and silently no-ops.
const productDetailRouteName = computed<string>(() =>
  isAgentShell(route) ? 'agent-product-detail' : 'investor-product-detail',
)
const companyProductsRouteName = computed<string>(() =>
  isAgentShell(route) ? 'agent-company-products' : 'investor-company-products',
)
const companiesListRouteName = computed<string>(() =>
  isAgentShell(route) ? 'agent-companies' : 'investor-companies',
)

// ---------------------------------------------------------------------------
// Cover style
// ---------------------------------------------------------------------------

const coverImage = computed<string | null>(() => {
  const co = data.value
  if (!co) return null
  // PublicCompanyDetailResponse carries `cover_url` directly; the
  // company_logo_url shadow inside resolveCoverImage is also honoured
  // as the natural second-stage fallback (a company without a hero
  // cover but with a logo gets the logo instead of the icon).
  return resolveCoverImage(co)
})

// ---------------------------------------------------------------------------
// Stats display
// ---------------------------------------------------------------------------
//
// PublicCompanyStatsResponse fields (R1 §1.6 + §5 backend):
//   pool_total_options       int
//   options_sold             int
//   options_sold_percent     int (0..100, server-computed)
//   price_growth_90d_percent int (signed, server-computed)
//
// We render the four as 2x2 CStatCard tiles. The percent fields are
// emitted by the backend as integers (R1 §1.6); we format with the
// locale-aware number formatter and append '%' as a unit suffix.

const stats = computed(() => data.value?.stats)

const poolTotalDisplay = computed<string>(() =>
  stats.value ? formatNumber(stats.value.pool_total_options, locale.value) : '—',
)
const soldDisplay = computed<string>(() =>
  stats.value ? formatNumber(stats.value.options_sold, locale.value) : '—',
)
const soldPercentDisplay = computed<string>(() =>
  stats.value ? `${stats.value.options_sold_percent}%` : '—',
)
const priceGrowthDisplay = computed<string>(() => {
  if (!stats.value) return '—'
  const v = stats.value.price_growth_90d_percent
  // Signed display: explicit + sign for positive values, locale-correct
  // negative sign comes from String(). 0% reads as "0%" (no sign).
  if (v > 0) return `+${v}%`
  return `${v}%`
})

// Conditional class for price-growth tile: success/danger to highlight
// direction. CStatCard doesn't support arbitrary value-color via prop;
// we hint via the `changeDir` mechanism instead.
const priceGrowthDir = computed<'up' | 'down' | undefined>(() => {
  if (!stats.value) return undefined
  const v = stats.value.price_growth_90d_percent
  if (v > 0) return 'up'
  if (v < 0) return 'down'
  return undefined
})

// ---------------------------------------------------------------------------
// Roadmap visibility (R1 §6.1)
// ---------------------------------------------------------------------------

const hasRoadmap = computed<boolean>(
  () => (data.value?.roadmap?.length ?? 0) > 0,
)

// ---------------------------------------------------------------------------
// Load + lifecycle
// ---------------------------------------------------------------------------

async function loadCompany(id: string): Promise<void> {
  loading.value = true
  errored.value = false
  notFound.value = false
  // Clear the previous payload so the user doesn't see company A's
  // hero while company B is loading.
  data.value = null
  try {
    data.value = await getCompany(id)
  } catch (err) {
    if (err instanceof ApiResponseError && err.status === 404) {
      notFound.value = true
    } else {
      errored.value = true
    }
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void loadCompany(companyId.value)
})

watch(
  () => route.params.id,
  (next) => {
    if (typeof next !== 'string') return
    void loadCompany(next)
  },
)

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

function onRetry(): void {
  void loadCompany(companyId.value)
}

function goToCompaniesList(): void {
  void safeNavigate(
    router.push({ name: companiesListRouteName.value }),
    '[CompanyOverviewView] to companies list',
  )
}

function goToProducts(): void {
  void safeNavigate(
    router.push({
      name: companyProductsRouteName.value,
      params: { id: companyId.value },
    }),
    '[CompanyOverviewView] to company products',
  )
}

function onRoadmapProductClick(productId: string): void {
  void safeNavigate(
    router.push({
      name: productDetailRouteName.value,
      params: { id: productId },
    }),
    '[CompanyOverviewView] to product detail',
  )
}

function onRoadmapExternalClick(url: string): void {
  // Use noopener+noreferrer to prevent the opened tab from accessing
  // window.opener (security baseline for any third-party URL).
  window.open(url, '_blank', 'noopener,noreferrer')
}

function onRoadmapPostClick(_postId: string): void {
  // No-op placeholder. The investor-side post view doesn't exist yet
  // (deferred to iter 2.6 or later). Once it lands, push to its
  // route name here. Suppressed argument is intentional -- TS6133
  // is satisfied via the underscore prefix.
}
</script>

<template>
  <div class="co">
    <CHeader
      :title="data?.name ?? t('inv.companyOverview.notFound')"
      :show-back="true"
      :show-logo="false"
    />

    <!-- Initial loading -->
    <div v-if="loading" class="co__center">
      <CLoader :size="32" />
    </div>

    <!-- 404: company doesn't exist or is non-active. -->
    <div v-else-if="notFound" class="co__center">
      <CEmptyState :title="t('inv.companyOverview.notFound')" />
      <CButton variant="primary" @click="goToCompaniesList">
        {{ t('inv.companyOverview.backToList') }}
      </CButton>
    </div>

    <!-- Other error: 5xx, network. -->
    <div v-else-if="errored" class="co__center">
      <CEmptyState :title="t('inv.companyOverview.errorTitle')" />
      <CButton variant="primary" @click="onRetry">
        {{ t('inv.companyOverview.errorRetry') }}
      </CButton>
    </div>

    <!-- Loaded -->
    <template v-else-if="data">
      <main class="co__main">
        <!-- Hero -->
        <section class="co__hero">
          <div
            class="co__hero-cover"
            :class="{ 'co__hero-cover--fallback': !coverImage }"
            :style="{ backgroundImage: coverImage ?? undefined }"
          >
            <Building v-if="!coverImage" :size="56" />
          </div>
          <div class="co__hero-body">
            <span class="co__hero-status">
              {{ t('common.statusActive') }}
            </span>
            <h1 class="co__hero-name">{{ data.name }}</h1>
            <p v-if="data.description" class="co__hero-description">
              {{ data.description }}
            </p>
          </div>
        </section>

        <!-- Stats -->
        <section class="co__stats">
          <CStatCard
            :value="poolTotalDisplay"
            :label="t('inv.companyOverview.stats.poolTotalOptions')"
          />
          <CStatCard
            :value="soldDisplay"
            :label="t('inv.companyOverview.stats.optionsSold')"
          />
          <CStatCard
            :value="soldPercentDisplay"
            :label="t('inv.companyOverview.stats.optionsSoldPercent')"
          />
          <CStatCard
            :value="priceGrowthDisplay"
            :label="t('inv.companyOverview.stats.priceGrowth90d')"
            :change="priceGrowthDir ? priceGrowthDisplay : undefined"
            :change-dir="priceGrowthDir"
          />
        </section>

        <!-- Roadmap (hidden if empty per R1 §6.1) -->
        <section v-if="hasRoadmap" class="co__section">
          <h2 class="co__section-title">
            {{ t('inv.companyOverview.sectionRoadmap') }}
          </h2>
          <RoadmapTimeline
            :items="data.roadmap ?? []"
            @product-click="onRoadmapProductClick"
            @external-click="onRoadmapExternalClick"
            @post-click="onRoadmapPostClick"
          />
        </section>

        <!-- Documents: self-hides when zero rows after fetch. -->
        <AttachmentsSection :company-id="companyId" />
      </main>

      <!-- Sticky CTA -->
      <div class="co__cta">
        <CButton variant="primary" @click="goToProducts">
          {{ t('inv.companyOverview.cta.viewProducts') }}
        </CButton>
      </div>
    </template>
  </div>
</template>

<style scoped>
.co {
  display: flex;
  flex-direction: column;
  /* No min-height: the view sits inside .shell__content (flex:1,
     overflow-y:auto) which already takes the available viewport
     space; an extra 100vh would push .co bottom past the viewport
     and cause unnecessary scroll-room below content. */
}

.co__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-md);
  min-height: 320px;
  padding: var(--space-md);
}

.co__main {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--space-xl);
  padding: var(--space-md);
  /* Bottom padding must clear two stacked layers above the content:
     the floating .co__cta (--cta-bar-height, pinned via min-height
     down in the .co__cta block) and the CTabBar (--tab-bar-height
     + safe-area-inset-bottom). Without this, the last section sits
     behind the CTA when the user scrolls to the end. The extra
     --space-xl is breathing room so the last item doesn't visually
     kiss the CTA shadow. */
  padding-bottom: calc(
    var(--space-xl)
    + var(--cta-bar-height)
    + var(--tab-bar-height)
    + env(safe-area-inset-bottom, 0px)
  );
}

/* ---------- Hero ---------- */

.co__hero {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.co__hero-cover {
  width: 100%;
  aspect-ratio: 16 / 9;
  border-radius: var(--radius-md);
  background-size: cover;
  background-position: center;
  background-color: var(--bg-subtle);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-tertiary);
}

.co__hero-cover--fallback {
  background-image: linear-gradient(
    135deg,
    var(--bg-subtle) 0%,
    var(--bg-elevated) 100%
  );
}

.co__hero-body {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.co__hero-status {
  align-self: flex-start;
  padding: 2px var(--space-sm);
  font-size: 11px;
  font-weight: 500;
  color: var(--success);
  background: var(--success-dim);
  border-radius: var(--radius-full);
}

.co__hero-name {
  margin: 0;
  font-size: 24px;
  font-weight: 700;
  color: var(--text);
  line-height: 1.25;
}

.co__hero-description {
  margin: 0;
  font-size: 14px;
  line-height: 1.5;
  color: var(--text-secondary);
  /* Full description on overview -- no clamp. */
  white-space: pre-line;
}

/* ---------- Stats grid ---------- */

.co__stats {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-sm);
}

/* On tablet+ widen to 4 columns for a single-row layout. */
@media (min-width: 640px) {
  .co__stats {
    grid-template-columns: repeat(4, 1fr);
  }
}

/* ---------- Generic section ---------- */

.co__section {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.co__section-title {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  color: var(--text);
}

/* ---------- Floating CTA ----------
   Always visible, pinned above the CTabBar. position:fixed (not
   sticky) keeps the button on screen regardless of scroll position
   or content length -- sticky would only engage once the user
   scrolled past the bottom of .co, which on short pages never
   happens and left the CTA hidden below the tab bar (the bug that
   spawned this rewrite).

   Horizontal: --space-md from each edge matches .co__main's inline
   padding, so the button aligns with the content column.

   z-index: 100 puts the CTA on the same plane as CTabBar. They don't
   overlap geometrically (CTA bottom == tab-bar top), but matching the
   z-index protects against future transitions or modals that might
   otherwise sneak between them. */
.co__cta {
  position: fixed;
  left: var(--space-md);
  right: var(--space-md);
  bottom: calc(
    var(--tab-bar-height)
    + env(safe-area-inset-bottom, 0px)
    + var(--space-sm)
  );
  /* min-height (not height) pins the visible strip to --cta-bar-height
     so the token is the real source of truth that .co__main's
     padding-bottom relies on. min-height (rather than height) keeps
     room for the button to grow if the inner label wraps under an
     extreme translation -- the layout above adapts via calc, the CTA
     itself never crops content. */
  min-height: var(--cta-bar-height);
  box-sizing: border-box;
  display: flex;
  align-items: center;
  z-index: 100;
  padding: var(--space-sm);
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
}

.co__cta :deep(.c-button) {
  width: 100%;
}
</style>
