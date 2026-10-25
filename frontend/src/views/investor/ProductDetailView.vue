<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- ProductDetailView (Phase F4.1 + F4.1.4 + F4.2 + F4.2.2
//                                          + F4.4 B7 UX)
// =============================================================================
//
// Public product detail screen. Shared across /investor/products/:id
// and /agent/products/:id via role-aware route names.
//
// Fetch strategy:
//   - Local state, no Pinia store. A product detail is a one-shot
//     fetch with no cross-view cache requirements in F4.1.
//
// F4.2 change -- installment plan cards are the CTA.
//   Each installment row is now a tappable card that deep-links
//   into InstallmentView with `?plan=<template_id>`, opening the
//   confirmation flow for that exact plan in one tap. The secondary
//   "Pay in installments" button underneath was removed -- no second
//   selector needed. "Buy now" stays as the primary CTA for users
//   who want the full package up front.
//
// F4.2.2 polish:
//   Plan-config parsing was duplicated between this view and
//   InstallmentView. Extracted to utils/installmentPlans so
//   ProductDetail, InstallmentView, and the upcoming F4.4 Portfolio
//   share one parser with consistent strictness. Bonus extraction
//   here is now `getPlanBonus(plan)` from that module.
//
// F4.1.4 polish (retained):
//   - Formatters moved to utils/format.ts (TD-F04 closed).
//   - Role-aware routing via router/helpers.ts.
//   - The frame's header (K25) holds the product name and the back control;
//     the hero (K47) carries the product and company over the cover photo,
//     its text on the scrim.
//   - Buy CTA label switches to "Sold out" when available <= 0.
//   - Hero fallback stacks icon + text vertically.
//   - Description breaks long unbroken tokens.
//
// F4.4 B7 UX:
//   First stat now anchors on the pack: heading "Price per pack",
//   value = formatPrice(price_per_pack_cents). The small caption under
//   the value carries the per-unit reference price (the price of a part) so
//   the user can still see the underlying share price without making
//   it the headline. The second stat (Packs availability) is unchanged.
//
//   Sprint 4.4 also dropped the `= 0` default on `available_packages`
//   on the backend schema. The `?? 0` fallback here is gone -- a
//   missing populate would be a server bug, not a soft default.
// =============================================================================

import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Building, ShoppingCart } from '@/components/ui/icons'
import { CBadge, CButton, CLoader, CEmptyState, CStatCard } from '@/components/ui'
import { useScreenHeader } from '@/components/layout/screenHeader'
import { getProduct } from '@/api/products'
import { safeNavigate } from '@/composables/safeNavigate'
import { isAgentShell } from '@/router/helpers'
import { useAuthStore } from '@/stores/auth'
import { showKycPrompt } from '@/composables/useKycPrompt'
import { formatNumber, formatPrice } from '@/utils/format'
import { formatPartPrice } from '@/utils/parts'
import { useSharesPerOption } from '@/composables/useSharesPerOption'
import { getPlanBonus } from '@/utils/installmentPlans'
import type { PublicProductDetailResponse } from '@/api/types'
import { useProductCover } from '@/composables/useThemedLogo'
import { useReloadOnLocale } from '@/composables/useReloadOnLocale'

// Backend currency field is not emitted yet (TD-F03). Keep the
// escape hatch here so the page is correct once it lands.
type ProductWithOptionalCurrency = PublicProductDetailResponse & {
  currency?: string
}

const route = useRoute()
const router = useRouter()
const { t, locale } = useI18n()
const authStore = useAuthStore()

const product = ref<ProductWithOptionalCurrency | null>(null)

// The price of one part: the lot's price over the project's parts per lot; a dash
// while the project's parts per lot is not known (never the lot's price).
const { ensure: ensureParts, partsPerLot } = useSharesPerOption()
watch(
  () => product.value?.company_id,
  (id) => {
    if (id) void ensureParts([id])
  },
  { immediate: true },
)
const partPriceDisplay = computed<string>(() => {
  const p = product.value
  const perLot = p ? partsPerLot(p.company_id) : null
  return p && perLot !== null ? formatPartPrice(p.price_per_unit_cents, perLot, locale.value) : '—'
})
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

// The cover is the product's own picture, else the company's logo for the theme.
const coverSrc = useProductCover(() => product.value)

// F4.4: backend guarantees available_packages is populated; no `?? 0`.
const available = computed<number>(() => {
  const p = product.value
  return p ? p.available_packages : 0
})

function backToMarket(): void {
  // iter 2.6.x hotfix: market routes removed in iter 2.5 batch 9,
  // catalogue moved to *-companies (CompanyListView). Function
  // name kept -- internal label, see `inv.product.backToMarket`
  // i18n key for updated user-facing copy.
  const name = agentShell.value ? 'agent-companies' : 'investor-companies'
  void safeNavigate(router.push({ name }), '[ProductDetailView] to companies list')
}

// The frame's header: the product name and the back control. It prefers
// router.back() so the originating screen (CompanyList / Dashboard CTA /
// etc.) restores its scroll state for free; falls back to the companies
// catalogue when no prior history exists (i.e. the view was opened via a
// deep-linked URL).
useScreenHeader({
  title: () => product.value?.name,
  back: () =>
    window.history.state?.back
      ? true
      : { name: agentShell.value ? 'agent-companies' : 'investor-companies' },
})

function buyNow(): void {
  if (!product.value) return
  // Without a passed verification the press answers with the message first.
  if (authStore.kycStatus !== 'approved') {
    showKycPrompt('purchase')
    return
  }
  const name = agentShell.value ? 'agent-purchase' : 'investor-purchase'
  void safeNavigate(
    router.push({ name, params: { id: product.value.id } }),
    '[ProductDetailView] to purchase',
  )
}

// F4.2 -- plan row. Its link's address is the InstallmentView with the
// selected template pre-chosen; the press goes through the verification
// check first (and does nothing for a sold-out product), then lands directly on
// the confirmation screen.
function planHref(planId: string): string {
  if (!product.value) return ''
  const name = agentShell.value ? 'agent-installment' : 'investor-installment'
  return router.resolve({ name, params: { id: product.value.id }, query: { plan: planId } }).href
}

function openInstallmentPlan(planId: string): void {
  if (!product.value) return
  if (available.value <= 0) return
  if (authStore.kycStatus !== 'approved') {
    showKycPrompt('installment')
    return
  }
  const name = agentShell.value ? 'agent-installment' : 'investor-installment'
  void safeNavigate(
    router.push({
      name,
      params: { id: product.value.id },
      query: { plan: planId },
    }),
    '[ProductDetailView] to installment plan',
  )
}

// H38: project data is in the reader's language -- re-read it on a switch.
useReloadOnLocale(() => loadProduct())

onMounted(loadProduct)
</script>

<template>
  <div class="pd">
    <!-- Loading -->
    <CLoader v-if="loading" centered extent="page" />

    <!-- Not found / error -->
    <CEmptyState
      v-else-if="errored || !product"
      tone="danger"
      :title="t('inv.product.notFound.title')"
      :description="t('inv.product.notFound.desc')"
    >
      <template #actions>
        <CButton variant="outline" size="sm" inline @click="backToMarket">
          {{ t('inv.product.backToMarket') }}
        </CButton>
      </template>
    </CEmptyState>

    <!-- Loaded -->
    <template v-else>
      <!-- Hero (K47): the company and the product name over the photo, or the
           fallback tile with the icon when there is no photo. -->
      <section class="ds-hero" aria-labelledby="pd-hero-title">
        <img v-if="coverSrc" class="ds-hero__image" :src="coverSrc" alt="" />
        <span v-else class="ds-hero__fallback"><Building /></span>
        <div class="ds-hero__content">
          <h2 id="pd-hero-title" class="ds-hero__title">
            {{ product.name }}
          </h2>
          <p class="ds-hero__meta">
            {{ product.company_name }}
          </p>
        </div>
      </section>

      <!-- Stats (K46) -->
      <div class="ds-stats">
        <CStatCard
          :label="t('inv.product.pricePerPack')"
          :value="formatPrice(product.price_per_pack_cents, product.currency)"
          :sub="`${t('buy.partPrice')}: ${partPriceDisplay}`"
        />
        <CStatCard
          :label="t('inv.product.packsAvailability')"
          :value="formatNumber(available, locale)"
          :sub="t('inv.available')"
        />
      </div>

      <!-- Description -->
      <section v-if="product.description" class="ds-card ds-card--flat">
        <div class="ds-card__head">
          <h2 class="ds-card__title">
            {{ t('inv.product.description') }}
          </h2>
        </div>
        <p class="ds-card__body pd__description">
          {{ product.description }}
        </p>
      </section>

      <!-- Installment plans -- each row opens the plan's confirmation (K23) -->
      <section class="ds-card ds-card--flat">
        <div class="ds-card__head">
          <h2 class="ds-card__title">
            {{ t('inv.product.installments') }}
          </h2>
        </div>
        <p v-if="product.installments.length === 0" class="ds-card__body">
          {{ t('inv.product.installmentsEmpty') }}
        </p>
        <ul v-else class="ds-rows">
          <li
            v-for="plan in product.installments"
            :key="plan.id"
            class="ds-row"
            :aria-disabled="available <= 0 ? 'true' : undefined"
          >
            <span class="ds-row__body">
              <a
                v-if="available > 0"
                class="ds-row__link"
                :href="planHref(plan.id)"
                @click.prevent="openInstallmentPlan(plan.id)"
              >
                <span class="ds-row__title">{{ plan.name }}</span>
              </a>
              <span v-else class="ds-row__title">{{ plan.name }}</span>
            </span>
            <span v-if="getPlanBonus(plan) > 0" class="ds-row__trail">
              <CBadge
                variant="success"
                :text="t('inv.product.installmentsBonus', { n: getPlanBonus(plan) })"
              />
            </span>
          </li>
        </ul>
      </section>

      <!-- Primary CTA -- instant purchase. The installment CTA
           lives on the plan rows above (F4.2). -->
      <CButton variant="primary" :disabled="available <= 0" @click="buyNow">
        <ShoppingCart size="sm" />
        {{ available > 0 ? t('inv.product.buy') : t('inv.product.soldOut') }}
      </CButton>
    </template>
  </div>
</template>

<style scoped>
/* The frame's main pads the screen; this column only lays its parts out with the
   same gap the main uses. */
.pd {
  display: grid;
  gap: var(--space-5);
}

/* The description keeps the reader's own line breaks and is capped at the reading
   measure (--maxw-prose is a ceiling: on a phone it does nothing). */
.pd__description {
  white-space: pre-wrap;
  overflow-wrap: break-word;
  max-inline-size: var(--maxw-prose);
}
</style>
