<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- PublicCompanyOverviewView (iter 2.6 batch 3, R1 §1.6.1
//                                                 + iter 2.6 batch 4 §7.2
//                                                 + iter 2.6 batch 5 products)
// =============================================================================
//
// Anonymous storefront company profile. Public counterpart to the
// investor-side /investor/companies/:id. Differences with the
// investor view:
//
//   1. NO `<CHeader>` inside the view. The shell carries the only
//      header for the public flow. Investor-side renders its own
//      view-scoped <CHeader> with title + back; we keep the surface
//      clean for the marketing context.
//   2. NO sticky CTA / `.co__cta`. Purchase action lives on
//      PublicProductDetailView (iter 2.6 Batch 6), not here. The
//      visitor scrolls through the overview, reads the pitch, taps
//      a product card to commit. CompanyOverview's job is to inform,
//      not to sell.
//   3. Products section is wired via <PublicProductsSection> (Batch 5)
//      -- teaser only (first page), with a "Register to see all" CTA
//      that branches on auth state. Self-hiding contract, no v-if
//      needed.
//   4. Documents section is wired via <PublicAttachmentsSection>
//      (Batch 4) -- self-hiding contract, no v-if needed.
//   5. NO back button. Browser back covers the list <-> overview
//      navigation; a deep-linked visitor simply closes the tab.
//
// LAYOUT ORDER (R1 §1.6.1).
//   Hero -> Stats -> Roadmap -> Products -> Documents.
//   Each non-hero/stats section self-hides when empty, so a company
//   with no roadmap / no products / no documents collapses gracefully
//   to just hero + stats.
//
// DATA SOURCE.
//   Local state via getCompany(id) -- single round-trip to
//   `/api/v1/public/companies/{id}`, returns a
//   PublicCompanyDetailResponse with stats and roadmap inline. No
//   store -- there's no shared data with other views and no
//   pagination. Same shape as the investor view, same epoch-free
//   simplicity (one in-flight fetch at a time, watch-on-id covers
//   :id swaps).
//
// 404 BEHAVIOUR.
//   Backend returns 404 for non-active (hidden / archived) companies.
//   We detect ApiResponseError status 404 and render a "company not
//   found" empty state. Other ApiResponseError statuses (5xx, network)
//   flip `errored` and render the retry path.
//
// IN-PLACE :id SWAP.
//   Vue Router reuses the component instance across param changes
//   when navigating from /public/companies/A to /public/companies/B.
//   The watch on route.params.id covers that case -- without it the
//   user would see A's content frozen while B's id is in the URL.
//
// ROADMAP NAVIGATION FROM HERE.
//   product-click  -> push to public-product-detail (Batch 6 stub
//                     until then; navigation no-ops cleanly).
//   external-click -> window.open with noopener + noreferrer.
//   post-click     -> no-op (public posts view doesn't exist yet,
//                     mirrors the investor-side handler).
// =============================================================================

import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { safeNavigate } from '@/composables/safeNavigate'
import { useI18n } from 'vue-i18n'
import { Building } from 'lucide-vue-next'

import { CButton, CEmptyState, CLoader, CStatCard } from '@/components/ui'
import PublicAttachmentsSection from '@/components/shared/PublicAttachmentsSection.vue'
import PublicProductsSection from '@/components/shared/PublicProductsSection.vue'
import RoadmapTimeline from '@/components/shared/RoadmapTimeline.vue'
import { ApiResponseError } from '@/api/client'
import { getCompany } from '@/api/companies'
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

// ---------------------------------------------------------------------------
// Cover style
// ---------------------------------------------------------------------------

const coverImage = computed<string | null>(() => {
  const co = data.value
  if (!co) return null
  return resolveCoverImage(co)
})

// ---------------------------------------------------------------------------
// Stats display
// ---------------------------------------------------------------------------

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
  if (v > 0) return `+${v}%`
  return `${v}%`
})

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

function onRoadmapProductClick(productId: string): void {
  // Anonymous storefront stays on /public/* routes throughout. The
  // target view is a stub until Batch 6 -- navigation succeeds, the
  // stub renders, real content lands then.
  void safeNavigate(
    router.push({
      name: 'public-product-detail',
      params: { id: productId },
    }),
    '[PublicCompanyOverviewView] to product',
  )
}

function onRoadmapExternalClick(url: string): void {
  // noopener+noreferrer prevents the opened tab from accessing
  // window.opener (security baseline for any third-party URL).
  window.open(url, '_blank', 'noopener,noreferrer')
}

function onRoadmapPostClick(_postId: string): void {
  // No-op placeholder, same as the investor-side handler. Public
  // posts view doesn't exist yet; argument prefixed with underscore
  // to satisfy TS6133.
}
</script>

<template>
  <div class="co">
    <!-- Initial loading -->
    <div v-if="loading" class="co__center">
      <CLoader :size="32" />
    </div>

    <!-- 404: company doesn't exist or is non-active. -->
    <div v-else-if="notFound" class="co__center">
      <CEmptyState :title="t('public.companyOverview.notFound')" />
    </div>

    <!-- Other error: 5xx, network. -->
    <div v-else-if="errored" class="co__center">
      <CEmptyState :title="t('public.companyOverview.errorTitle')" />
      <CButton variant="primary" @click="onRetry">
        {{ t('public.companyOverview.errorRetry') }}
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
            <h1 class="co__hero-name">
              {{ data.name }}
            </h1>
            <p v-if="data.description" class="co__hero-description">
              {{ data.description }}
            </p>
          </div>
        </section>

        <!-- Stats -->
        <section class="co__stats">
          <CStatCard
            :value="poolTotalDisplay"
            :label="t('public.companyOverview.stats.poolTotalOptions')"
          />
          <CStatCard :value="soldDisplay" :label="t('public.companyOverview.stats.optionsSold')" />
          <CStatCard
            :value="soldPercentDisplay"
            :label="t('public.companyOverview.stats.optionsSoldPercent')"
          />
          <CStatCard
            :value="priceGrowthDisplay"
            :label="t('public.companyOverview.stats.priceGrowth90d')"
            :change="priceGrowthDir ? priceGrowthDisplay : undefined"
            :change-dir="priceGrowthDir"
          />
        </section>

        <!-- Roadmap (hidden if empty per R1 §6.1) -->
        <section v-if="hasRoadmap" class="co__section">
          <h2 class="co__section-title">
            {{ t('public.companyOverview.sectionRoadmap') }}
          </h2>
          <RoadmapTimeline
            :items="data.roadmap ?? []"
            @product-click="onRoadmapProductClick"
            @external-click="onRoadmapExternalClick"
            @post-click="onRoadmapPostClick"
          />
        </section>

        <!--
          Public products teaser (iter 2.6 Batch 5, R1 §1.6.1).
          Component self-hides when the company has no products after
          a successful fetch -- no v-if guard here.
        -->
        <PublicProductsSection :company-id="companyId" />

        <!--
          Public attachments section (iter 2.6 Batch 4, R2 §7.2).
          Component self-hides when the list is empty after a successful
          fetch -- no v-if guard here. The auth-flow CompanyOverviewView
          uses the same self-hide contract for its AttachmentsSection.
        -->
        <PublicAttachmentsSection :company-id="companyId" />

        <!--
          No sticky CTA -- purchase lives on product detail (Batch 6).
        -->
      </main>
    </template>
  </div>
</template>

<style scoped>
.co {
  display: flex;
  flex-direction: column;
}

.co__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-4);
  min-height: var(--center-lg);
  padding: var(--space-4);
}

.co__main {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--space-7);
  padding: var(--space-4);
  /* No bottom padding for a sticky/floating CTA -- the public view
     does not have one. The investor side reserves space for both
     a floating .co__cta and the CTabBar; the public shell has neither,
     so the natural bottom padding from .co__main's last child is
     enough. */
  padding-bottom: var(--space-7);
}

/* ---------- Hero ---------- */

.co__hero {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
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
  background-image: linear-gradient(135deg, var(--bg-subtle) 0%, var(--bg-surface) 100%);
}

.co__hero-body {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.co__hero-status {
  align-self: flex-start;
  padding: var(--space-1) var(--space-2);
  font-size: var(--fs-xs);
  font-weight: 500;
  color: var(--success);
  background: var(--success-subtle);
  border-radius: var(--radius-pill);
}

.co__hero-name {
  margin: 0;
  font-size: var(--fs-h3);
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.25;
}

.co__hero-description {
  margin: 0;
  font-size: var(--fs-sm);
  line-height: 1.5;
  color: var(--text-secondary);
  white-space: pre-line;
}

/* ---------- Stats grid ---------- */

.co__stats {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-2);
}

@media (min-width: 640px) {
  .co__stats {
    grid-template-columns: repeat(4, 1fr);
  }
}

/* ---------- Generic section ---------- */

.co__section {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.co__section-title {
  margin: 0;
  font-size: var(--fs-h4);
  font-weight: 700;
  color: var(--text-primary);
}

/* TILE CEILING — a grid authored `repeat(N, 1fr)` keeps N columns at every
   width, so on a 1016px desktop it stretches its contents to fill: measured,
   a stat tile reached 316px and an action button 497px. Past a point the extra
   room should be whitespace, not wider furniture.

   The COLUMN COUNT IS DELIBERATELY UNCHANGED. Only the ceiling is added, so
   nothing reflows and no set of related figures can wrap into a ragged 2+1.
   An earlier attempt used auto-fit and did exactly that: the cap, not a lack
   of room, was what pushed the third tile onto its own line. Mobile-first, so
   this is a min-width and the phone is untouched. */
@media (min-width: 820px) {
  .co__stats {
    max-width: calc(2 * var(--tile-max));
  }
}
</style>
