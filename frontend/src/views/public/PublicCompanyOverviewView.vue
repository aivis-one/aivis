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
//   1. NO header of its own. The frame carries the only header for the
//      public flow; the view hands it the company's name (useScreenHeader).
//      The storefront has no back control: the browser's back covers the
//      list -> overview step.
//
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
//   post-click     -> push to public-post (the post screen under the
//                     storefront shell).
// =============================================================================

import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { safeNavigate } from '@/composables/safeNavigate'
import { useI18n } from 'vue-i18n'
import { Building } from '@/components/ui/icons'

import { CButton, CEmptyState, CStatCard } from '@/components/ui'
import { useScreenHeader } from '@/components/layout/screenHeader'
import PublicAttachmentsSection from '@/components/shared/PublicAttachmentsSection.vue'
import PublicProductsSection from '@/components/shared/PublicProductsSection.vue'
import RoadmapTimeline from '@/components/shared/RoadmapTimeline.vue'
import { ApiResponseError } from '@/api/client'
import { getCompany } from '@/api/companies'
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

// ---------------------------------------------------------------------------
// Cover and header
// ---------------------------------------------------------------------------

// The cover is the company's own picture (the K47 hero); without one, the fallback tile.
const coverSrc = computed<string | null>(() => {
  const co = data.value
  return co?.cover_url ?? null
})

// The frame's header carries the company's name as the title. Called in setup.
useScreenHeader({ title: () => data.value?.name })

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

function onRoadmapPostClick(postId: string): void {
  void safeNavigate(
    router.push({ name: 'public-post', params: { id: postId } }),
    '[PublicCompanyOverviewView] to post',
  )
}
</script>

<template>
  <div class="co">
    <!-- Initial loading -->
    <div v-if="loading" class="ds-loader ds-loader--centered" data-extent="page" role="status">
      <span class="ds-loader__ring" aria-hidden="true" />
      <span>{{ t('common.loading') }}</span>
    </div>

    <!-- 404: company doesn't exist or is non-active. -->
    <CEmptyState v-else-if="notFound" :title="t('public.companyOverview.notFound')" />

    <!-- Other error: 5xx, network. -->
    <CEmptyState v-else-if="errored" tone="danger" :title="t('public.companyOverview.errorTitle')">
      <template #actions>
        <CButton variant="primary" inline @click="onRetry">
          {{ t('public.companyOverview.errorRetry') }}
        </CButton>
      </template>
    </CEmptyState>

    <!-- Loaded -->
    <template v-else-if="data">
      <!-- Hero (K47): the cover with the company's name over it, or the fallback
           tile with the icon when there is no cover. -->
      <section class="ds-hero" aria-labelledby="co-hero-name">
        <img v-if="coverSrc" class="ds-hero__image" :src="coverSrc" alt="" />
        <span v-else class="ds-hero__fallback"><Building /></span>
        <div class="ds-hero__content">
          <h2 id="co-hero-name" class="ds-hero__title">
            {{ data.name }}
          </h2>
        </div>
      </section>

      <section v-if="data.description" class="ds-card ds-card--flat">
        <p class="ds-card__body co__description">
          {{ data.description }}
        </p>
      </section>

      <!-- Stats -->
      <section class="ds-stats">
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
        <h2 class="ds-section-title">
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
    </template>
  </div>
</template>

<style scoped>
/* The frame's main pads the screen; this column lays its parts out with the same gap. */
.co {
  display: grid;
  gap: var(--space-5);
}

/* The company's description keeps the author's line breaks and is capped at the
   reading measure (--maxw-prose is a ceiling: on a phone it does nothing). */
.co__description {
  white-space: pre-line;
  max-inline-size: var(--maxw-prose);
}

/* A section of the screen: its heading (the system's section title), then its content. */
.co__section {
  display: grid;
  gap: var(--space-4);
}
</style>
