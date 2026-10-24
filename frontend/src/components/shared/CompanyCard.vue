<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- CompanyCard (iter 2.5 batch 5, R1 §1.2)
// =============================================================================
//
// Grid card for the Investor Companies tab (CompanyListView). Also
// reused in iter 2.6 on the public landing page -- both surfaces show
// the same denormalised list item shape, so the card is shared via
// components/shared and the parent decides what tapping does.
//
// COVER IMAGE.
//   The cover is an <img> that covers the media part of the card (K07); a
//   company without one shows the fallback tile with the building icon.
//
// STATUS CHIP.
//   The public storefront endpoint emits only active companies (the
//   public_router 404s on non-active status -- hidden / archived
//   companies are filtered server-side). The chip therefore renders a
//   single locale string for "Active" without branching on the value.
//   If a future endpoint surface adds richer states (e.g. "Funding
//   open / Closed"), promote `status` to a slot or a prop-driven
//   mapping.
//
// CLICK EMISSION.
//   The card emits @click with the full list-item object. The parent
//   view (CompanyListView, or a future PublicLandingView in 2.6)
//   resolves route name + params based on shell (`isAgentShell`) and
//   navigates. Mirrors the ProductCard contract -- card is
//   navigation-agnostic.
//
// DESCRIPTION CLAMP.
//   3-line clamp via -webkit-line-clamp. Empty description renders a
//   non-breaking placeholder height (via min-height on the slot
//   wrapper) so cards in the grid stay equal-height even when one has
//   a long description and another has none. Without this, an empty
//   description card would shrink and break the grid baseline.
// =============================================================================

import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Building } from '@/components/ui/icons'

import { CBadge } from '@/components/ui'
import type { PublicCompanyListResponse } from '@/api/types'

// Item type derived from the list response. Same approach the
// companyList store takes -- no separate single-item re-export in
// api/types.ts.
type CompanyListItem = PublicCompanyListResponse['items'][number]

const props = defineProps<{
  company: CompanyListItem
}>()

defineEmits<{ click: [company: CompanyListItem] }>()

const { t } = useI18n()

// PublicCompanyResponse exposes `cover_url` and no logo on the list endpoint; the
// cover is a picture that covers the media part of the card (K07), else the
// fallback tile with the icon.
const coverSrc = computed(() => props.company.cover_url ?? null)
</script>

<template>
  <article class="ds-card ds-card--media ds-card--interactive">
    <div class="ds-card__media" :class="{ 'ds-card__media--fallback': !coverSrc }">
      <img v-if="coverSrc" :src="coverSrc" alt="" loading="lazy" />
      <Building v-else />
    </div>

    <div class="ds-card__content">
      <div class="ds-card__head">
        <h3 class="ds-card__title">
          <button type="button" class="ds-card__link" @click="$emit('click', company)">
            {{ company.name }}
          </button>
        </h3>
        <CBadge variant="success" :text="t('common.statusActive')" />
      </div>

      <p class="ds-card__body company-card__description">
        {{ company.description ?? '' }}
      </p>
    </div>
  </article>
</template>

<style scoped>
/* The card, its cover, the title link and the status badge are the system's media
   card (K07) and Badge (K08). What is left is the description's clamp: it reserves
   three lines even when empty so the cards in a grid stay equal-height (a literal
   inside a calc is invisible to a scan, so it is derived from the tokens the text
   is set in). */
.company-card__description {
  min-block-size: calc(var(--fs-sm) * var(--lh-normal) * 3);
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  max-inline-size: var(--maxw-prose);
}
</style>
