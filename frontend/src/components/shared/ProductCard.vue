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
import { Building } from '@/components/ui/icons'
import { formatNumber, formatPrice } from '@/utils/format'
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

// The cover is the product's own picture, else the company's logo; either covers
// the media part of the card (K07).
const coverSrc = computed(() => props.product.cover_url ?? props.product.company_logo_url ?? null)

// F4.4: backend now guarantees this field is populated; no `?? 0`.
const available = computed(() => props.product.available_packages)
</script>

<template>
  <article class="ds-card ds-card--media ds-card--interactive">
    <div class="ds-card__media" :class="{ 'ds-card__media--fallback': !coverSrc }" data-size="sm">
      <img v-if="coverSrc" :src="coverSrc" alt="" loading="lazy" />
      <Building v-else />
      <span class="ds-card__tag">{{ product.company_name }}</span>
    </div>
    <div class="ds-card__content">
      <h3 class="ds-card__title">
        <button type="button" class="ds-card__link" @click="$emit('click', product)">
          {{ product.name }}
        </button>
      </h3>
      <p v-if="product.description" class="ds-card__body product-card__desc">
        {{ product.description }}
      </p>
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
  </article>
</template>

<style scoped>
/* The card, its cover, the chip on the photo and the title link are the system's
   media card (K07). What is left is the description's clamp and the price block
   under it: the system has no price line for a card (NEED), so its type is set
   from tokens. */
.product-card__desc {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  max-inline-size: var(--maxw-prose);
}

/* Meta is a 2-column row: the left column is a 2-line block (the pack price and
   the per-unit reference), the right one ("packs available") is one line anchored
   to the top of the price block. */
.product-card__meta {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--space-2);
}

.product-card__price-block {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-inline-size: 0;
}

.product-card__price {
  font-size: var(--fs-h4);
  font-weight: 700;
  color: var(--primary);
}
.product-card__unit {
  font-size: var(--fs-xs);
  font-weight: 500;
  color: var(--text-secondary);
}

/* The per-unit reference under the pack price: quiet type. */
.product-card__price-secondary {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
}

.product-card__units {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
  text-align: end;
  white-space: nowrap;
}
</style>
