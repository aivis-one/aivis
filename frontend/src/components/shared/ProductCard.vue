<script setup lang="ts">
// =============================================================================
// CBSHOME Frontend -- ProductCard (Phase F4.1)
// =============================================================================
//
// Storefront grid card. Emits @click with the full product so the
// parent view decides navigation (investor vs agent shell).
//
// Cover image fallback chain (F4.1):
//   1. product.cover_url          -- product-level cover if set
//   2. product.company_logo_url   -- company logo as a neutral fallback
//   3. Building icon              -- final fallback (no image)
//
// Money formatting is inline (no shared util yet -- TD: extract to
// utils/format.ts once at least two surfaces need it).
// =============================================================================

import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Building } from 'lucide-vue-next'
import type { PublicProductResponse } from '@/api/types'

const props = defineProps<{
  product: PublicProductResponse
}>()

defineEmits<{ click: [product: PublicProductResponse] }>()

const { t } = useI18n()

const coverImage = computed<string | null>(
  () => props.product.cover_url ?? props.product.company_logo_url ?? null,
)

// Cents -> "$12.34". Simple USD-first formatter; revisit once other
// currencies ship.
function formatCents(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`
}

// Thousands separator with thin space (readable across locales).
function formatUnits(n: number): string {
  return n.toLocaleString('en-US').replace(/,/g, ' ')
}

const available = computed(
  () => props.product.units - props.product.sold_units,
)
</script>

<template>
  <div class="product-card" @click="$emit('click', product)">
    <div
      class="product-card__img"
      :class="{ 'product-card__img--fallback': !coverImage }"
      :style="{
        backgroundImage: coverImage ? `url(${coverImage})` : 'none',
      }"
    >
      <Building
        v-if="!coverImage"
        :size="48"
        class="product-card__icon"
      />
      <span class="product-card__company">{{ product.company_name }}</span>
    </div>
    <div class="product-card__body">
      <div class="product-card__name">{{ product.name }}</div>
      <div v-if="product.description" class="product-card__desc">
        {{ product.description }}
      </div>
      <div class="product-card__meta">
        <span class="product-card__price">
          {{ formatCents(product.price_per_unit_cents) }}
          <span class="product-card__unit">/ {{ t('inv.unit') }}</span>
        </span>
        <span class="product-card__units">
          {{ formatUnits(available) }} {{ t('inv.available') }}
        </span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.product-card {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  overflow: hidden;
  cursor: pointer;
  transition: transform 0.2s, box-shadow 0.2s;
}
.product-card:hover {
  transform: translateY(-4px);
  box-shadow: var(--shadow-lg);
}

.product-card__img {
  height: 120px;
  background-color: var(--bg-subtle);
  background-size: cover;
  background-position: center;
  display: flex; align-items: center; justify-content: center;
  position: relative;
  color: #fff;
}
.product-card__img::after {
  content: '';
  position: absolute; inset: 0;
  background: linear-gradient(transparent 40%, rgba(0, 0, 0, 0.6));
  pointer-events: none;
}
.product-card__img--fallback {
  background-color: var(--bg-subtle);
}
.product-card__img--fallback::after { display: none; }

.product-card__icon {
  position: relative; z-index: 1;
  color: var(--text-tertiary);
  stroke-width: 1.5;
}

.product-card__company {
  position: absolute; top: 8px; left: 8px; z-index: 2;
  font-size: 11px; font-weight: 600;
  padding: 3px 8px;
  border-radius: var(--radius-sm);
  background: rgba(0, 0, 0, 0.45);
  color: #fff;
  max-width: calc(100% - 16px);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}

.product-card__body { padding: 14px; }

.product-card__name {
  font-size: 16px; font-weight: 700;
  color: var(--text); margin-bottom: 4px;
}

.product-card__desc {
  font-size: 13px; color: var(--text-secondary);
  margin-bottom: 10px; line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.product-card__meta {
  display: flex; justify-content: space-between; align-items: baseline;
  gap: 8px;
}

.product-card__price {
  font-size: 18px; font-weight: 700;
  color: var(--primary);
}
.product-card__unit {
  font-size: 12px; font-weight: 500;
  color: var(--text-secondary);
}

.product-card__units {
  font-size: 12px; color: var(--text-tertiary);
  text-align: end;
  white-space: nowrap;
}
</style>
