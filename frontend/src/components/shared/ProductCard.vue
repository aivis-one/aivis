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
//   storefront to anchor pricing on it. The card's price line (K07) shows
//   `$N / pack` as the figure, and its reference line under it says
//   `$X / unit` and how many packs are available.
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
      <p class="ds-card__price">
        <span class="ds-card__price-figure">{{
          formatPrice(product.price_per_pack_cents, product.currency)
        }}</span>
        <span class="ds-card__price-unit">/ {{ t('inv.pack') }}</span>
      </p>
      <p class="ds-card__price-ref">
        {{ formatPrice(product.price_per_unit_cents, product.currency) }} / {{ t('inv.unit') }} ·
        {{ formatNumber(available, locale) }} {{ t('inv.market.packsAvailable') }}
      </p>
    </div>
  </article>
</template>

<style scoped>
/* The card, its cover, the chip on the photo, the title link and the price line
   are the system's media card (K07). What is left is the description's clamp. */
.product-card__desc {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  max-inline-size: var(--maxw-prose);
}
</style>
