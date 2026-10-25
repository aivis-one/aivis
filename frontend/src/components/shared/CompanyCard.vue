<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- CompanyCard (iter 2.5 batch 5, R1 §1.2)
// =============================================================================
//
// Grid card for the Investor Companies tab (CompanyListView). Also
// reused in iter 2.6 on the public landing page -- both surfaces show
// the same denormalised list item shape, so the card is shared via
// components/shared and the parent decides where the link leads.
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
// CALL TO ACTION.
//   One card per project, and its one link is the call to action "View the
//   project" (K07's call-to-action form): a link to the project page, given as
//   `to` by the parent, which resolves the route for its shell. The card holds
//   no other link, and the hit area stretches over the whole card.
//
// DESCRIPTION CLAMP.
//   The description is cut at the second line with the system's clamp
//   (`.ds-clamp`); the call to action sits at the foot of the content, so the
//   buttons of a grid stand level whatever the length of the description.
// =============================================================================

import { computed } from 'vue'
import { RouterLink, type RouteLocationRaw } from 'vue-router'
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
  /** The project page the call to action leads to. */
  to: RouteLocationRaw
}>()

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
        <h3 class="ds-card__title">{{ company.name }}</h3>
        <CBadge variant="success" :text="t('common.statusActive')" />
      </div>

      <p class="ds-card__body ds-clamp">
        {{ company.description ?? '' }}
      </p>

      <div class="ds-card__action">
        <RouterLink class="ds-button ds-button--primary ds-button--block ds-card__link" :to="to">
          {{ t('buy.viewProject') }}
          <span class="ds-sr-only">{{ company.name }}</span>
        </RouterLink>
      </div>
    </div>
  </article>
</template>
