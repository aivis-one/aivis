<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- ProductCard (Phase F4.1 + F4.1.4 polish + F4.4 B7 UX)
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
// F4.1.4 polish: formatters moved to utils/format.ts (TD-F04 closed).
//
// F4.4 B7 UX:
//   The pack is the unit of purchase, not the share -- B7 wants the
//   storefront to anchor pricing on it. Left meta block now shows
//   `$N / pack` as the primary line, with `$X / unit` below as a
//   reference. The right meta block ("X packs available") is unchanged.
//   `price_per_pack_cents` comes from the backend pre-computed
//   (package_size * price_per_unit_cents) so the client doesn't multiply.
//
//   Sprint 4.4 also dropped the `= 0` default on `available_packages`
//   on the backend schema. The `?? 0` fallback here is gone -- a
//   missing populate would be a server bug, not a soft default.
// =============================================================================

import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Building } from 'lucide-vue-next'
import {
  formatNumber,
  formatPrice,
  resolveCoverImage,
} from '@/utils/format'
import type { PublicProductResponse } from '@/api/types'

// Backend doesn't yet emit `currency` on PublicProductResponse
// (TD-F03). Keep the escape hatch here so the card stays correct
// once it lands.
type ProductWithOptionalCurrency = PublicProductResponse & {
  currency?: string
}

const props = defineProps<{
  product: ProductWithOptionalCurrency
}>()

defineEmits<{ click: [product: PublicProductResponse] }>()

const { t, locale } = useI18n()

const coverImage = computed(() => resolveCoverImage(props.product))

// F4.4: backend now guarantees this field is populated; no `?? 0`.
const available = computed(() => props.product.available_packages)
</script>

<template>
  <div class="product-card" @click="$emit('click', product)">
    <div
      class="product-card__img"
      :class="{ 'product-card__img--fallback': !coverImage }"
      :style="{ backgroundImage: coverImage ?? 'none' }"
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
        <div class="product-card__price-block">
          <span class="product-card__price">
            {{ formatPrice(product.price_per_pack_cents, product.currency) }}
            <span class="product-card__unit">/ {{ t('inv.pack') }}</span>
          </span>
          <span class="product-card__price-secondary">
            {{ formatPrice(product.price_per_unit_cents, product.currency) }}
            / {{ t('inv.unit') }}
          </span>
        </div>
        <span class="product-card__units">
          {{ formatNumber(available, locale) }} {{ t('inv.market.packsAvailable') }}
        </span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.product-card {
  background: var(--bg-page);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  overflow: hidden;
  cursor: pointer;
  transition: transform 0.2s, box-shadow 0.2s;
}
.product-card:hover {
  transform: translateY(-4px);
  box-shadow: var(--shadow-3);
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
  stroke-width: 2;
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
  color: var(--text-primary); margin-bottom: 4px;
}

.product-card__desc {
  font-size: 13px; color: var(--text-secondary);
  margin-bottom: 10px; line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* F4.4 B7: meta is now a 2-column row where the left column is itself
   a 2-line block (pack price + unit price reference). Right column
   ("packs available") stays single-line. align-items shifted from
   baseline to flex-start so the right column anchors to the top of
   the price block, lining up with the bigger pack price. */
.product-card__meta {
  display: flex; justify-content: space-between; align-items: flex-start;
  gap: 8px;
}

.product-card__price-block {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.product-card__price {
  font-size: 18px; font-weight: 700;
  color: var(--primary);
}
.product-card__unit {
  font-size: 12px; font-weight: 500;
  color: var(--text-secondary);
}

/* F4.4 B7: secondary line under the pack price -- the per-unit
   reference. Quiet typography so it does not compete with the
   primary pack price. */
.product-card__price-secondary {
  font-size: 12px;
  color: var(--text-tertiary);
}

.product-card__units {
  font-size: 12px; color: var(--text-tertiary);
  text-align: end;
  white-space: nowrap;
  /* Sprint 4.4: align with the top of the bigger pack price line above
     the secondary reference. align-self trumps the magic-number
     padding-top from the first B7 cut -- it tracks line-height changes
     for free and survives any future font-size tweak on the price. */
  align-self: flex-start;
}
</style>
