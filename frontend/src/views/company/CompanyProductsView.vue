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
//   Product editing happens by the staff. A tap on a card points the user at
//   support.
// =============================================================================

import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { CButton, CEmptyState, CLoader } from '@/components/ui'
import { listMyProducts } from '@/api/products'
import type { OwnProductResponse } from '@/api/products'
import { formatPrice } from '@/utils/format'
import { useToast } from '@/composables/useToast'

const PER_PAGE = 100

const { t } = useI18n()
const { showToast } = useToast()

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

function coverStyle(p: OwnProductResponse): Record<string, string> {
  return p.cover_url ? { backgroundImage: `url("${encodeURI(p.cover_url)}")` } : {}
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

/** Card tap: product editing is staff-only, so the tap points the user at support. */
function onCardClick(): void {
  showToast(t('comp.products.editViaSupport'), 'info')
}
</script>

<template>
  <div class="cprods">
    <div class="cprods__header">
      <h1 class="cprods__title">
        {{ t('comp.products.title') }}
      </h1>
      <p class="cprods__subtitle">
        {{ t('comp.products.subtitle') }}
      </p>
    </div>

    <div v-if="loading && items.length === 0" class="cprods__center">
      <CLoader :size="28" />
    </div>

    <div v-else-if="error !== null" class="cprods__center">
      <CEmptyState :title="t('comp.products.errorTitle')" :description="error" />
      <CButton variant="outline" size="sm" @click="loadAll">
        {{ t('comp.products.errorRetry') }}
      </CButton>
    </div>

    <div v-else-if="isEmpty" class="cprods__center">
      <CEmptyState
        :title="t('comp.products.empty.title')"
        :description="t('comp.products.empty.desc')"
      />
    </div>

    <div v-else class="cprods__grid">
      <button
        v-for="item in items"
        :key="item.id"
        type="button"
        class="cprods__card"
        @click="onCardClick"
      >
        <div class="cprods__cover" :style="coverStyle(item)" />
        <div class="cprods__body">
          <div class="cprods__name">{{ item.name }}</div>
          <div class="cprods__price">{{ packPrice(item) }}</div>
          <span class="cprods__status" :class="`cprods__status--${item.status}`">
            {{ statusLabel(item.status) }}
          </span>
        </div>
      </button>
    </div>
  </div>
</template>

<style scoped>
.cprods {
  padding: var(--space-4);
}

.cprods__header {
  margin-bottom: var(--space-4);
}
.cprods__title {
  font-size: var(--fs-lg);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 var(--space-1);
}
.cprods__subtitle {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  margin: 0;
}

.cprods__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-4);
  min-height: var(--center-md);
  padding: var(--space-5);
  text-align: center;
}

/* Grid mirrors MarketView -- 1 / 2 / 3 columns by viewport width. */
.cprods__grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--space-3);
}
/* B-3.0 2026-08-24: was 520px. Folded onto the declared component threshold 640, which is
   what the two other product grids (.pps__grid, .pbc__grid) already use for two-up. */
@media (min-width: 640px) {
  .cprods__grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
/* B-3.0 2026-08-24: was 900px, the only site in the tree using it. Folded onto 960, which
   is what .pps__grid and .pbc__grid already use for three-up. 900 is now RETIRED. */
@media (min-width: 960px) {
  .cprods__grid {
    grid-template-columns: repeat(3, 1fr);
  }
}

.cprods__sentinel {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-4);
  min-height: var(--size-xl);
}

/* READING MEASURE — descriptive text only. --maxw-prose (680px) is a CEILING,
   so this rule cannot bind until the container is already wider than a
   comfortable line: on a phone it does nothing at all, which is why it needs
   no media query. Measured at 1280 before applying: `event-card__desc` ran to
   932px and `staff-dash__role-count` to 901. Names, figures and table cells
   are deliberately NOT capped — a name is not prose, and capping it would only
   leave dead space in its row. */
.cprods__subtitle {
  max-width: var(--maxw-prose);
}

.cprods__card {
  display: flex;
  flex-direction: column;
  padding: 0;
  text-align: start;
  cursor: pointer;
  overflow: hidden;
  background: var(--bg-secondary);
  color: var(--text-primary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
}
.cprods__cover {
  aspect-ratio: 16 / 9;
  background-color: var(--bg-secondary);
  background-size: cover;
  background-position: center;
}
.cprods__body {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-1);
  padding: var(--space-3);
}
.cprods__name {
  font-weight: 600;
  color: var(--text-primary);
}
.cprods__price {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
}
.cprods__status {
  font-size: var(--fs-xs);
  font-weight: 600;
  padding: 2px var(--space-2);
  border-radius: var(--radius-pill);
  background: var(--bg-secondary);
  color: var(--text-secondary);
}
</style>
