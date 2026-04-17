<script setup lang="ts">
// =============================================================================
// CBSHOME Frontend -- ProductDetailView (Phase F4.1 + F4.1.4 polish)
// =============================================================================
//
// Public product detail screen. Shared across /investor/products/:id
// and /agent/products/:id via role-aware route names.
//
// Fetch strategy:
//   - Local state, no Pinia store. A product detail is a one-shot
//     fetch with no cross-view cache requirements in F4.1.
//
// CTAs wire up to F4.2 stubs (PurchaseView, InstallmentView) -- the
// routes exist and the views render placeholders until F4.2 ships.
//
// Installment plans show only the plan name + bonus-units hint here;
// full tranche breakdown lives on the installment flow itself.
//
// F4.1.4 polish:
//   - Formatters moved to utils/format.ts (TD-F04 closed).
//   - Role-aware routing via router/helpers.ts (no more path-match
//     copypasta).
//   - CHeader displays the product name as a title, truncated by
//     the header itself when it doesn't fit.
//   - Buy CTA label switches to "Sold out" when available <= 0 so
//     the disabled state is self-explanatory.
//   - Hero fallback now stacks icon + text vertically instead of
//     overlapping them in the same flex row.
//   - Description breaks long unbroken strings (URLs) inside the box.
// =============================================================================

import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Building, Calendar, ShoppingCart } from 'lucide-vue-next'
import { CButton, CLoader, CEmptyState } from '@/components/ui'
import CHeader from '@/components/layout/CHeader.vue'
import { getProduct } from '@/api/products'
import { isAgentShell } from '@/router/helpers'
import {
  formatNumber,
  formatPrice,
  resolveCoverImage,
} from '@/utils/format'
import type { PublicProductDetailResponse } from '@/api/types'

// Backend currency field is not emitted yet (TD-F03). Keep the
// escape hatch here so the page is correct once it lands.
type ProductWithOptionalCurrency = PublicProductDetailResponse & {
  currency?: string
}

const route = useRoute()
const router = useRouter()
const { t, locale } = useI18n()

const product = ref<ProductWithOptionalCurrency | null>(null)
const loading = ref(true)
const errored = ref(false)

const productId = computed(() => route.params.id as string)
const agentShell = computed(() => isAgentShell(route))

async function loadProduct(): Promise<void> {
  loading.value = true
  errored.value = false
  try {
    product.value = await getProduct(productId.value)
  } catch {
    errored.value = true
    product.value = null
  } finally {
    loading.value = false
  }
}

const coverImage = computed<string | null>(() => {
  const p = product.value
  return p ? resolveCoverImage(p) : null
})

const available = computed<number>(() => {
  const p = product.value
  return p ? p.units - p.sold_units : 0
})

// plan_config is backend JSONB (see schemas.py) -- extract bonus_units
// defensively so a malformed plan doesn't crash the view.
function installmentBonus(config: Record<string, unknown>): number {
  const b = config['bonus_units']
  return typeof b === 'number' ? b : 0
}

function backToMarket(): void {
  const name = agentShell.value ? 'agent-market' : 'investor-market'
  void router.push({ name })
}

function buyNow(): void {
  if (!product.value) return
  const name = agentShell.value ? 'agent-purchase' : 'investor-purchase'
  void router.push({ name, params: { id: product.value.id } })
}

function startInstallment(): void {
  if (!product.value) return
  const name = agentShell.value
    ? 'agent-installment'
    : 'investor-installment'
  void router.push({ name, params: { id: product.value.id } })
}

onMounted(loadProduct)
</script>

<template>
  <div class="pd">
    <CHeader
      :show-back="true"
      :show-logo="false"
      :title="product?.name"
    />

    <!-- Loading -->
    <div v-if="loading" class="pd__center">
      <CLoader :size="28" />
    </div>

    <!-- Not found / error -->
    <div v-else-if="errored || !product" class="pd__center">
      <CEmptyState
        :title="t('inv.product.notFound.title')"
        :description="t('inv.product.notFound.desc')"
      />
      <CButton variant="outline" size="sm" @click="backToMarket">
        {{ t('inv.product.backToMarket') }}
      </CButton>
    </div>

    <!-- Loaded -->
    <template v-else>
      <!-- Hero with cover image -->
      <div
        class="pd__hero"
        :class="{ 'pd__hero--fallback': !coverImage }"
        :style="{ backgroundImage: coverImage ?? 'none' }"
      >
        <Building v-if="!coverImage" :size="64" class="pd__hero-icon" />
        <div class="pd__hero-content">
          <div class="pd__hero-company">{{ product.company_name }}</div>
          <h1 class="pd__hero-title">{{ product.name }}</h1>
        </div>
      </div>

      <div class="pd__body">
        <!-- Stats -->
        <div class="pd__stats">
          <div class="pd__stat">
            <div class="pd__stat-label">
              {{ t('inv.product.priceLabel') }}
            </div>
            <div class="pd__stat-value pd__stat-value--price">
              {{ formatPrice(product.price_per_unit_cents, product.currency) }}
            </div>
            <div class="pd__stat-unit">/ {{ t('inv.unit') }}</div>
          </div>
          <div class="pd__stat">
            <div class="pd__stat-label">
              {{ t('inv.product.availability') }}
            </div>
            <div class="pd__stat-value">
              {{ formatNumber(available, locale) }}
            </div>
            <div class="pd__stat-unit">{{ t('inv.available') }}</div>
          </div>
        </div>

        <!-- Description -->
        <section v-if="product.description" class="pd__section">
          <h2 class="pd__section-title">
            {{ t('inv.product.description') }}
          </h2>
          <p class="pd__description">{{ product.description }}</p>
        </section>

        <!-- Installment plans -->
        <section class="pd__section">
          <h2 class="pd__section-title">
            {{ t('inv.product.installments') }}
          </h2>
          <div
            v-if="product.installments.length === 0"
            class="pd__empty"
          >
            {{ t('inv.product.installmentsEmpty') }}
          </div>
          <ul v-else class="pd__plans">
            <li
              v-for="plan in product.installments"
              :key="plan.id"
              class="pd__plan"
            >
              <span class="pd__plan-name">{{ plan.name }}</span>
              <span
                v-if="installmentBonus(plan.plan_config) > 0"
                class="pd__plan-bonus"
              >
                {{
                  t('inv.product.installmentsBonus', {
                    n: installmentBonus(plan.plan_config),
                  })
                }}
              </span>
            </li>
          </ul>
        </section>

        <!-- CTAs -->
        <div class="pd__actions">
          <CButton
            variant="primary"
            :disabled="available <= 0"
            @click="buyNow"
          >
            <ShoppingCart :size="16" />
            {{
              available > 0
                ? t('inv.product.buy')
                : t('inv.product.soldOut')
            }}
          </CButton>
          <CButton
            v-if="product.installments.length > 0"
            variant="outline"
            :disabled="available <= 0"
            @click="startInstallment"
          >
            <Calendar :size="16" /> {{ t('inv.product.installment') }}
          </CButton>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.pd { display: flex; flex-direction: column; }

.pd__center {
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  gap: 16px;
  min-height: calc(100vh - 120px);
  min-height: calc(100dvh - 120px);
  padding: 24px;
}

/* Hero with cover image */
.pd__hero {
  position: relative;
  height: 220px;
  background-color: var(--bg-subtle);
  background-size: cover;
  background-position: center;
  display: flex; align-items: flex-end; justify-content: flex-start;
  color: #fff;
}
.pd__hero::after {
  content: '';
  position: absolute; inset: 0;
  background: linear-gradient(transparent 30%, rgba(0, 0, 0, 0.75));
  pointer-events: none;
}
.pd__hero--fallback {
  background-color: var(--bg-subtle);
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
}
.pd__hero--fallback::after { display: none; }

.pd__hero-icon {
  position: relative; z-index: 1;
  color: var(--text-tertiary);
  stroke-width: 1.5;
}

.pd__hero-content {
  position: relative; z-index: 2;
  padding: 20px;
  width: 100%;
}
.pd__hero--fallback .pd__hero-content {
  text-align: center;
  color: var(--text);
  padding: 0 20px 20px;
}
.pd__hero-company {
  font-size: 12px; font-weight: 600;
  opacity: 0.85;
  margin-bottom: 4px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.pd__hero-title {
  font-size: 22px; font-weight: 700;
  margin: 0;
  line-height: 1.3;
}

/* Body */
.pd__body {
  padding: 20px;
  display: flex; flex-direction: column;
  gap: 24px;
}

.pd__stats {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.pd__stat {
  padding: 14px;
  background: var(--bg-subtle);
  border-radius: var(--radius-md);
  text-align: center;
}
.pd__stat-label {
  font-size: 11px;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 6px;
}
.pd__stat-value {
  font-size: 18px; font-weight: 700;
  color: var(--text);
}
.pd__stat-value--price { color: var(--primary); }
.pd__stat-unit {
  font-size: 11px;
  color: var(--text-tertiary);
  margin-top: 2px;
}

.pd__section { display: flex; flex-direction: column; gap: 10px; }
.pd__section-title {
  font-size: 14px; font-weight: 700;
  color: var(--text);
  margin: 0;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.pd__description {
  font-size: 14px;
  color: var(--text-secondary);
  line-height: 1.5;
  margin: 0;
  white-space: pre-wrap;
  /* Break long unbroken tokens (URLs, identifiers) instead of
     letting them push the container wider than the viewport. */
  overflow-wrap: break-word;
}

.pd__empty {
  padding: 14px;
  background: var(--bg-subtle);
  border-radius: var(--radius-md);
  font-size: 13px;
  color: var(--text-tertiary);
  text-align: center;
}

.pd__plans {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.pd__plan {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
}
.pd__plan-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
}
.pd__plan-bonus {
  font-size: 12px;
  font-weight: 600;
  color: var(--success);
  white-space: nowrap;
}

.pd__actions {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding-top: 8px;
}
@media (min-width: 520px) {
  .pd__actions { flex-direction: row; }
  .pd__actions > * { flex: 1; }
}
</style>
