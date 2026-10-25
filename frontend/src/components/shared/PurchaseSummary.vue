<script setup lang="ts">
// The summary lines of the Purchase block (K55), shared by the project page, the
// confirmation and the done screen: the portfolio's name with its bonus Badge, the
// count of parts (the bonus parts in the success colour, the sign in the text) and
// the quiet lines -- the price of a part, and on an instalment the money of the
// instalment and the parts by month, marked "no bonus". Parts are lots times the
// parts in a lot; the lot itself is never shown.
//
// A fragment: its parts are children of the block's own `.ds-purchase` stack.
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { CBadge } from '@/components/ui'
import type { PlanConfig } from '@/utils/installmentPlans'
import { formatPartPrice, formatUsd, formatUsdCents, instalmentLines, partsOf } from '@/utils/parts'
import { formatNumber } from '@/utils/format'

const props = defineProps<{
  /** The line over the parts: the project and the portfolio. */
  title: string
  lots: number
  lotPriceCents: number
  sharesPerOption: number
  totalCents: number
  /** The bonus percent of a payment at once (0 when the portfolio has none). */
  bonusPercent: number
  /** The bonus, in lots, a payment at once brings. */
  bonusLots: number
  /** The chosen instalment, or null for a payment at once. */
  plan: PlanConfig | null
  planName?: string
}>()

const { t, locale } = useI18n()

const parts = computed(() => partsOf(props.lots, props.sharesPerOption))
const bonusParts = computed(() => partsOf(props.bonusLots, props.sharesPerOption))
const atOnce = computed(() => props.plan === null)
const showBonus = computed(() => atOnce.value && props.bonusPercent > 0)

const partPrice = computed(() =>
  formatPartPrice(props.lotPriceCents, props.sharesPerOption, locale.value),
)
const total = computed(() => formatUsdCents(props.totalCents, locale.value))

const lines = computed(() => (props.plan ? instalmentLines(props.plan) : null))

const money = computed(() => {
  const l = lines.value
  if (!l) return ''
  const last = formatUsd(l.lastCents, locale.value)
  if (l.eachCents === null) return t('buy.instalmentLast', { count: l.count, last })
  const each = formatUsd(l.eachCents, locale.value)
  return l.eachCents === l.lastCents
    ? t('buy.instalmentEqual', { count: l.count, each })
    : t('buy.instalmentMoney', { count: l.count - 1, each, last })
})
</script>

<template>
  <div class="ds-purchase__head">
    <p class="ds-purchase__title">{{ title }}</p>
    <CBadge
      v-if="showBonus"
      variant="success"
      :text="t('buy.bonusBadge', { n: formatNumber(bonusPercent, locale) })"
    />
  </div>
  <!-- The payment switch stands between the head and the parts (K55's order). -->
  <slot />
  <p class="ds-purchase__parts">
    <template v-if="atOnce">
      {{ t('buy.parts', { n: formatNumber(parts, locale) }) }}
      <span v-if="showBonus && bonusParts > 0" class="ds-purchase__bonus">
        {{ t('buy.bonusParts', { n: formatNumber(bonusParts, locale) }) }}
      </span>
    </template>
    <template v-else>
      {{ t('buy.partsOver', { n: formatNumber(parts, locale), plan: planName ?? '' }) }}
    </template>
  </p>
  <p v-if="atOnce" class="ds-note">
    {{ t('buy.partPriceAtOnce', { price: partPrice, total })
    }}<template v-if="bonusPercent <= 0"> · {{ t('buy.noBonus') }}</template>
  </p>
  <template v-else-if="lines">
    <p class="ds-note">{{ t('buy.partPriceTotal', { price: partPrice, total }) }}</p>
    <p class="ds-note">{{ money }} · {{ t('buy.noBonus') }}</p>
    <p v-if="lines.eachPercent !== null" class="ds-note">
      {{
        t('buy.partsByMonth', {
          each: formatNumber(lines.eachPercent, locale),
          last: formatNumber(lines.lastPercent, locale),
        })
      }}
    </p>
  </template>
</template>
