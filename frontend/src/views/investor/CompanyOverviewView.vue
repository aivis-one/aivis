<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- CompanyOverviewView (iter 2.5 batch 6, R1 §1.3)
// =============================================================================
//
// Investor company profile screen. Sub-route under the Companies tab:
// /investor/companies/:id and /agent/companies/:id (route names added
// in batch 9). Renders:
//   0. The frame's header (K25) with the company name and the back control
//   1. Hero (K47) -- cover + name, then the description
//   2. Stat tiles (K46) -- 4 public metrics from PublicCompanyStatsResponse
//   3. Roadmap timeline -- batch 5 component, hidden when items empty
//   4. Documents section -- batch 6 AttachmentsSection, self-hides when empty
//   5. The frame's action strip (K25) -- "View products" to ProductsByCompanyView
//      (batch 8 + 9)
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
//   A post click opens the post screen (investor-post).
//
// IN-PLACE :id SWAP.
//   Vue Router reuses the component instance across param changes
//   when navigating from /investor/companies/A to /investor/companies/B.
//   The watch on route.params.id covers that case -- without it the
//   user would see A's content frozen while B's id is in the URL.
//
// ACTION STRIP (K25).
//   The "View products" button is the screen's one primary action, drawn by the
//   frame's own piece (ShellAction, `.ds-shell__action`): the last element of the
//   screen, kept above the tab bar on a phone (the bar height and the safe-area
//   inset are the system's), in the flow from 880. The cabinet keeps no
//   fixed-position strip, no z-index and no bar-height token of its own.
// =============================================================================

import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Building } from '@/components/ui/icons'

import { CButton, CEmptyState, CLoader, CStatCard } from '@/components/ui'
import ShellAction from '@/components/layout/ShellAction.vue'
import { useScreenHeader } from '@/components/layout/screenHeader'
import AttachmentsSection from '@/components/shared/AttachmentsSection.vue'
import RoadmapTimeline from '@/components/shared/RoadmapTimeline.vue'
import { ApiResponseError } from '@/api/client'
import { getCompany } from '@/api/companies'
import { safeNavigate } from '@/composables/safeNavigate'
import { isAgentShell } from '@/router/helpers'
import { formatNumber } from '@/utils/format'
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
// Cover
// ---------------------------------------------------------------------------

const coverSrc = computed<string | null>(() => data.value?.cover_url ?? null)

// The frame's header: the company name and the back control. Prefers
// router.back() so the originating screen (most commonly CompanyListView)
// restores scroll/state for free; falls back to the companies list when
// there is no history (deep-link).
useScreenHeader({
  title: () => data.value?.name,
  back: () => (window.history.state?.back ? true : { name: companiesListRouteName.value }),
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

const hasRoadmap = computed<boolean>(() => (data.value?.roadmap?.length ?? 0) > 0)

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

function onRoadmapPostClick(postId: string): void {
  // The post screen sits under the investor shell, which the agent role may
  // also open, so one route serves both shells.
  void safeNavigate(
    router.push({ name: 'investor-post', params: { id: postId } }),
    '[CompanyOverviewView] to post',
  )
}
</script>

<template>
  <div class="co">
    <!-- Initial loading -->
    <CLoader v-if="loading" centered extent="page" />

    <!-- 404: company doesn't exist or is non-active. -->
    <CEmptyState v-else-if="notFound" :title="t('inv.companyOverview.notFound')">
      <template #actions>
        <CButton variant="primary" size="sm" inline @click="goToCompaniesList">
          {{ t('inv.companyOverview.backToList') }}
        </CButton>
      </template>
    </CEmptyState>

    <!-- Other error: 5xx, network. -->
    <CEmptyState v-else-if="errored" tone="danger" :title="t('inv.companyOverview.errorTitle')">
      <template #actions>
        <CButton variant="primary" size="sm" inline @click="onRetry">
          {{ t('inv.companyOverview.errorRetry') }}
        </CButton>
      </template>
    </CEmptyState>

    <!-- Loaded -->
    <template v-else-if="data">
      <!-- Hero (K47): the cover and the company name, then the description -->
      <section class="ds-hero" aria-labelledby="co-hero-name">
        <img v-if="coverSrc" class="ds-hero__image" :src="coverSrc" alt="" />
        <span v-else class="ds-hero__fallback"><Building /></span>
        <div class="ds-hero__content">
          <h2 id="co-hero-name" class="ds-hero__title">
            {{ data.name }}
          </h2>
        </div>
      </section>
      <p v-if="data.description" class="ds-note co__description">
        {{ data.description }}
      </p>

      <!-- Stats (K46) -->
      <section class="ds-stats">
        <CStatCard
          :value="poolTotalDisplay"
          :label="t('inv.companyOverview.stats.poolTotalOptions')"
        />
        <CStatCard :value="soldDisplay" :label="t('inv.companyOverview.stats.optionsSold')" />
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
      <section v-if="hasRoadmap" class="co__section" aria-labelledby="co-roadmap">
        <h2 id="co-roadmap" class="ds-section-title">
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

      <!-- The screen's one primary action (K25 action strip) -->
      <ShellAction>
        <CButton variant="primary" inline @click="goToProducts">
          {{ t('inv.companyOverview.cta.viewProducts') }}
        </CButton>
      </ShellAction>
    </template>
  </div>
</template>

<style scoped>
.co {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

.co__description {
  max-inline-size: var(--maxw-prose);
  /* Full description on overview -- no clamp. */
  white-space: pre-line;
}

.co__section {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}
</style>
