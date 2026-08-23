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
//   resolveCoverImage(source) returns either a ready-to-use
//   `url("...")` string or null. For PublicCompanyResponse the only
//   image field is cover_url (no company_logo_url shadow), so the
//   helper effectively reduces to a single fallback step. Calling it
//   keeps encodeURI hygiene (staff-supplied URLs with stray chars
//   cannot break the inline style) without duplicating the snippet.
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
import { Building } from 'lucide-vue-next'

import { resolveCoverImage } from '@/utils/format'
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

// PublicCompanyResponse exposes `cover_url` but no company_logo
// shadow on the list endpoint, so the second fallback of
// resolveCoverImage is effectively unused. Type assertion is safe --
// the helper does an `??` lookup on both keys, missing keys read as
// undefined and pass through to the null branch.
const coverImage = computed(() =>
  resolveCoverImage({ cover_url: props.company.cover_url }),
)
</script>

<template>
  <button type="button" class="company-card" @click="$emit('click', company)">
    <div
      class="company-card__img"
      :class="{ 'company-card__img--fallback': !coverImage }"
      :style="{ backgroundImage: coverImage ?? undefined }"
    >
      <Building v-if="!coverImage" :size="40" />
    </div>

    <div class="company-card__body">
      <div class="company-card__header">
        <h3 class="company-card__name">{{ company.name }}</h3>
        <span class="company-card__chip">
          {{ t('common.statusActive') }}
        </span>
      </div>

      <p class="company-card__description">
        {{ company.description ?? '' }}
      </p>
    </div>
  </button>
</template>

<style scoped>
.company-card {
  appearance: none; background: none; border: none; margin: 0; padding: 0;
  font: inherit; color: inherit; text-align: start; width: 100%;
  display: flex;
  flex-direction: column;
  background: var(--bg-page);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  overflow: hidden;
  cursor: pointer;
  transition: transform 0.12s ease, box-shadow 0.12s ease;
}

.company-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-2);
}

.company-card:active {
  transform: translateY(0);
}

.company-card__img {
  /* 16:9 keeps the grid baseline predictable across screen sizes. */
  aspect-ratio: 16 / 9;
  width: 100%;
  background-size: cover;
  background-position: center;
  background-color: var(--bg-subtle);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-tertiary);
}

.company-card__img--fallback {
  /* Subtle gradient so the placeholder doesn't read as broken. */
  background-image: linear-gradient(
    135deg,
    var(--bg-subtle) 0%,
    var(--bg-surface) 100%
  );
}

.company-card__body {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-4);
}

.company-card__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-2);
}

.company-card__name {
  flex: 1;
  margin: 0;
  font-size: var(--fs-body);
  font-weight: 600;
  color: var(--text-primary);
  line-height: 1.3;
  /* 2-line clamp for long company names. */
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.company-card__chip {
  flex-shrink: 0;
  padding: var(--space-1) var(--space-2);
  font-size: var(--fs-xs);
  font-weight: 500;
  color: var(--success);
  background: var(--success-subtle);
  border-radius: var(--radius-pill);
  white-space: nowrap;
}

.company-card__description {
  margin: 0;
  font-size: var(--fs-sm);
  line-height: 1.45;
  color: var(--text-secondary);
  /* Reserve 3 lines of height even when empty -- equal-height cards
     in the grid regardless of description fill.
     Derived from the SAME token the text is set in. It read `13px` -- the
     retired step this element no longer uses -- so it reserved 56.55px for
     three lines that occupy 60.9px, and the equal-height guarantee this rule
     exists for did not hold. A literal inside a calc is invisible to a scan
     that looks at font-size declarations. */
  min-height: calc(var(--fs-sm) * 1.45 * 3);
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* READING MEASURE — descriptive text only. --maxw-prose (680px) is a CEILING,
   so this rule cannot bind until the container is already wider than a
   comfortable line: on a phone it does nothing at all, which is why it needs
   no media query. Measured at 1280 before applying: `event-card__desc` ran to
   932px and `staff-dash__role-count` to 901. Names, figures and table cells
   are deliberately NOT capped — a name is not prose, and capping it would only
   leave dead space in its row. */
.company-card__description { max-width: var(--maxw-prose); }
</style>
