<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- CompanyProductsView
// =============================================================================
//
// "Products" tab inside CompanyShell. Shows ALL products of the signed-in
// project, whatever their status (active, hidden, archived): the owner sees
// what the store hides. The status is shown on every card.
//
// DATA SOURCE.
//   GET /api/v1/company/products (listMyProducts) -- the caller's own products,
//   every status, scoped server-side to the caller's own project. All pages are
//   read (100 per page) and shown together.
//
// READ-ONLY.
//   Product editing happens by the staff. A line above the cards points the user
//   at support.
// =============================================================================

import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { Package } from '@/components/ui/icons'
import { CAlert, CBadge, CButton, CEmptyState } from '@/components/ui'
import { useScreenHeader } from '@/components/layout/screenHeader'
import { listMyProducts } from '@/api/products'
import type { OwnProductResponse } from '@/api/products'
import { formatPrice } from '@/utils/format'

const PER_PAGE = 100

const { t } = useI18n()

// The frame's header carries the title and the line under it.
useScreenHeader({
  title: () => t('comp.products.title'),
  lead: () => t('comp.products.subtitle'),
})

const items = ref<OwnProductResponse[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

const isEmpty = computed<boolean>(
  () => !loading.value && error.value === null && items.value.length === 0,
)

function statusLabel(status: string): string {
  return ['active', 'hidden', 'archived'].includes(status)
    ? t(`comp.products.status.${status}`)
    : status
}

function packPrice(p: OwnProductResponse): string {
  return formatPrice(p.price_per_unit_cents * p.package_size)
}

/** A product's status as a badge: on sale is green, hidden amber, archived plain. */
function statusVariant(status: string): 'success' | 'warning' | 'neutral' {
  if (status === 'active') return 'success'
  if (status === 'hidden') return 'warning'
  return 'neutral'
}

/** Reads every page of the project's own products. Also the Retry action. */
async function loadAll(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const all: OwnProductResponse[] = []
    let page = 1
    for (;;) {
      const res = await listMyProducts({ page, per_page: PER_PAGE })
      all.push(...res.items)
      if (res.items.length === 0 || all.length >= res.total) break
      page += 1
    }
    items.value = all
  } catch {
    error.value = t('comp.products.errorTitle')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void loadAll()
})
</script>

<template>
  <div v-if="loading && items.length === 0" class="cprods__grid" aria-busy="true">
    <span class="ds-sr-only" role="status">{{ t('common.loading') }}</span>
    <div v-for="n in 3" :key="n" class="ds-card ds-card--media" aria-hidden="true">
      <span class="ds-skeleton ds-skeleton--block" />
      <div class="ds-card__content">
        <span class="ds-skeleton-stack">
          <span class="ds-skeleton ds-skeleton--title" />
          <span class="ds-skeleton ds-skeleton--text" />
        </span>
      </div>
    </div>
  </div>

  <CEmptyState
    v-else-if="error !== null"
    tone="danger"
    :title="t('comp.products.errorTitle')"
    :description="error"
  >
    <template #actions>
      <CButton variant="outline" size="sm" inline @click="loadAll">
        {{ t('comp.products.errorRetry') }}
      </CButton>
    </template>
  </CEmptyState>

  <CEmptyState
    v-else-if="isEmpty"
    :title="t('comp.products.empty.title')"
    :description="t('comp.products.empty.desc')"
  />

  <template v-else>
    <!-- Product editing is staff-only: the line that was a toast on a tap stands above the cards -->
    <CAlert tone="info">{{ t('comp.products.editViaSupport') }}</CAlert>

    <!-- The project's products as the system's media cards (K07) -->
    <div class="cprods__grid">
      <article v-for="item in items" :key="item.id" class="ds-card ds-card--media">
        <div class="ds-card__media" :class="{ 'ds-card__media--fallback': !item.cover_url }">
          <img v-if="item.cover_url" :src="item.cover_url" alt="" />
          <Package v-else />
        </div>
        <div class="ds-card__content">
          <h2 class="ds-card__title">{{ item.name }}</h2>
          <p class="ds-card__price">
            <span class="ds-card__price-figure">{{ packPrice(item) }}</span>
            <span class="ds-card__price-unit">/ {{ t('inv.pack') }}</span>
          </p>
          <div>
            <CBadge :variant="statusVariant(item.status)" :text="statusLabel(item.status)" />
          </div>
        </div>
      </article>
    </div>
  </template>
</template>

<style scoped>
/* The grid of cards: as many columns as hold the system's tile width. */
.cprods__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(var(--tile-max), 1fr));
  gap: var(--space-3);
}
</style>
