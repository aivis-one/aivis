<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- CommissionsView (Task 3 Block C, Phase F6.2)
// =============================================================================
//
// Replaces the F6.2 stub. The agent's commission + volume-bonus
// history, paginated over the store's commissions group
// (fetchCommissionsFirstPage / loadMoreCommissions / hasMoreCommissions,
// GET /agent/commissions/me, limit/offset).
//
// TWO ENTRY TYPES (CommissionEntry.type):
//   "commission"   -- level (L1-L3), investor_name, product_name
//   "volume_bonus" -- period_type, rank
// One adaptive card renders either; the type/status/period strings are
// server-driven enums and go through tOrRaw (FP-15).
//
// STATUS HONESTY (Task 3 §3).
//   /commissions/me does NOT filter by status -- it returns reversed
//   entries too. The status badge is rendered faithfully: reversed maps
//   to a danger "Clawed back" chip. This view does NO client-side
//   summing of amounts -- the dashboard's month figure comes from the
//   server /commissions/summary aggregate (reversed excluded), so there
//   is no place here to silently fold a reversed entry into a total.
//
// FP notes:
//   FP-19 -- the frame owns the header (useScreenHeader), no header
//            component here.
//   FP-25 -- self-hiding empty state, no scaffolding.
//   FP-15 -- type / status / period_type rendered via tOrRaw.
//   A back-link to Partners: the commissions lie inside that tab.
//
// EACH ROW SAYS WHAT IT IS: from whom (the partner's name and short id), how much, for what
// (the purchase and the product bought), at which level; a type the screen does not know is
// named plainly as "Other accrual", never by its raw token.
//
// PAGINATION.
//   Explicit "Load more" over the store trio (an agent's history is paged, not
//   infinite-scrolled).
// =============================================================================

import { computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'

import { Coins, ShieldAlert } from '@/components/ui/icons'
import { CBadge, CButton, CEmptyState } from '@/components/ui'
import { useScreenHeader } from '@/components/layout/screenHeader'
import StaffListSkeleton from '@/components/staff/StaffListSkeleton.vue'
import type { CommissionEntry } from '@/api/types'
import { useAgentStore } from '@/stores/agent'
import { tOrRaw } from '@/utils/i18n'
import { formatDate, formatPrice } from '@/utils/format'

const { t, locale } = useI18n()
const agentStore = useAgentStore()

// The frame's header carries the title, the line under it and the way back to Partners.
useScreenHeader({
  title: () => t('agent.commissions.title'),
  lead: () => t('agent.commissions.subtitle'),
  back: { name: 'agent-partners' },
})

// ---------------------------------------------------------------------------
// Derived
// ---------------------------------------------------------------------------

const commissionsEmpty = computed(
  () =>
    !agentStore.commissionsLoading &&
    !agentStore.commissionsError &&
    agentStore.commissions.length === 0,
)

// ---------------------------------------------------------------------------
// Display helpers (FP-15: server enums via tOrRaw)
// ---------------------------------------------------------------------------

const KNOWN_TYPES: readonly string[] = ['commission', 'volume_bonus']

// A type the screen does not know is named plainly, never by its raw token.
function typeLabel(type: string): string {
  return KNOWN_TYPES.includes(type)
    ? t(`agent.commissions.type.${type}`)
    : t('agent.commissions.type.other')
}

function statusLabel(status: string): string {
  return tOrRaw(t, `agent.commissions.status.${status}`, status)
}

function periodLabel(period: string | null | undefined): string {
  if (!period) return ''
  return tOrRaw(t, `agent.commissions.period.${period}`, period)
}

function levelLabel(level: number | null | undefined): string {
  return level != null ? t('agent.commissions.level', { n: level }) : ''
}

// reversed is the one that must stand out; mirrors the danger mapping
// used by BalanceView / CompanyBalanceView. Unknown statuses -> neutral.
function statusVariant(status: string): 'success' | 'warning' | 'danger' | 'neutral' {
  if (status === 'confirmed') return 'success'
  if (status === 'frozen') return 'warning'
  if (status === 'reversed') return 'danger'
  return 'neutral'
}

// The row's title says from whom (a commission) or for which period (a volume
// bonus); its meta line gathers the type, the product, the references, the level
// (or the rank) and the date.
function entryTitle(entry: CommissionEntry): string {
  if (entry.type === 'commission') {
    return t('agent.commissions.from', { name: entry.investor_name || '—' })
  }
  if (entry.type === 'volume_bonus') return periodLabel(entry.period_type) || typeLabel(entry.type)
  return typeLabel(entry.type)
}

function entryMeta(entry: CommissionEntry): string {
  const parts: string[] = [typeLabel(entry.type)]
  if (entry.type === 'commission') {
    if (entry.product_name) {
      parts.push(t('agent.commissions.forProduct', { product: entry.product_name }))
    }
    if (entry.investor_short_id) {
      parts.push(t('agent.commissions.partnerId', { id: entry.investor_short_id }))
    }
    if (entry.purchase_short_id) {
      parts.push(t('agent.commissions.purchaseRef', { id: entry.purchase_short_id }))
    }
    if (entry.level != null) parts.push(levelLabel(entry.level))
  } else if (entry.type === 'volume_bonus' && entry.rank != null) {
    parts.push(`${t('agent.commissions.bonus.rankLabel')} #${entry.rank}`)
  }
  parts.push(formatDate(entry.created_at, locale.value))
  return parts.join(' · ')
}

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

function retry(): void {
  void agentStore.fetchCommissionsFirstPage()
}

function loadMore(): void {
  void agentStore.loadMoreCommissions()
}

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

onMounted(() => {
  void agentStore.fetchCommissionsFirstPage()
})
</script>

<template>
  <!-- Loading (first page) -->
  <StaffListSkeleton v-if="agentStore.commissionsLoading && agentStore.commissions.length === 0" />

  <!-- Error -->
  <CEmptyState
    v-else-if="agentStore.commissionsError && agentStore.commissions.length === 0"
    tone="danger"
    :title="t('agent.commissions.errorTitle')"
  >
    <template #actions>
      <CButton variant="outline" size="sm" inline @click="retry">
        {{ t('common.retry') }}
      </CButton>
    </template>
  </CEmptyState>

  <!-- FP-25: self-hiding empty state -->
  <CEmptyState
    v-else-if="commissionsEmpty"
    :title="t('agent.commissions.empty.title')"
    :description="t('agent.commissions.empty.desc')"
  />

  <!-- List -->
  <template v-else>
    <ul class="ds-rows">
      <li v-for="entry in agentStore.commissions" :key="entry.id" class="ds-row">
        <span class="ds-row__lead"><Coins size="sm" /></span>
        <span class="ds-row__body">
          <span class="ds-row__title">{{ entryTitle(entry) }}</span>
          <span class="ds-row__meta">{{ entryMeta(entry) }}</span>
        </span>
        <span class="ds-row__trail">
          <span class="ds-row__value">{{ formatPrice(entry.amount_cents) }}</span>
          <CBadge :variant="statusVariant(entry.status)" :text="statusLabel(entry.status)" />
        </span>
      </li>
    </ul>

    <div v-if="agentStore.hasMoreCommissions && !commissionsEmpty">
      <CButton
        variant="secondary"
        inline
        :loading="agentStore.commissionsLoading"
        :disabled="agentStore.commissionsLoading"
        @click="loadMore"
      >
        {{ t('agent.commissions.loadMore') }}
      </CButton>
    </div>

    <div
      v-if="agentStore.commissionsError && agentStore.commissions.length > 0"
      class="ds-alert ds-alert--danger"
      role="alert"
    >
      <span class="ds-alert__icon" aria-hidden="true"><ShieldAlert size="sm" /></span>
      <div class="ds-alert__content">
        <p class="ds-alert__text">{{ t('agent.commissions.loadMoreError') }}</p>
      </div>
    </div>
  </template>
</template>
