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
//   FP-19 -- shell owns the header; inline comm__header h1, no header
//            component here.
//   FP-25 -- self-hiding empty state, no scaffolding.
//   FP-15 -- type / status / period_type rendered via tOrRaw.
//   No back-link: /agent/commissions is a top-level tab (AGENT_TABS).
//
// PAGINATION.
//   Explicit "Load more" over the store trio (same choice as
//   AgentHubView -- an agent's history is paged, not infinite-scrolled).
// =============================================================================

import { computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'

import { CButton, CEmptyState, CLoader } from '@/components/ui'
import { useAgentStore } from '@/stores/agent'
import { tOrRaw } from '@/utils/i18n'
import { formatDate, formatPrice } from '@/utils/format'

const { t, locale } = useI18n()
const agentStore = useAgentStore()

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

function typeLabel(type: string): string {
  return tOrRaw(t, `agent.commissions.type.${type}`, type)
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
  <div class="comm">
    <!-- Screen title (FP-19: shell owns the header, view owns the h1) -->
    <div class="comm__header">
      <h1 class="comm__title">
        {{ t('agent.commissions.title') }}
      </h1>
      <p class="comm__subtitle">
        {{ t('agent.commissions.subtitle') }}
      </p>
    </div>

    <!-- Loading (first page) -->
    <div
      v-if="agentStore.commissionsLoading && agentStore.commissions.length === 0"
      class="comm__center"
    >
      <CLoader :size="24" />
    </div>

    <!-- Error -->
    <div
      v-else-if="agentStore.commissionsError && agentStore.commissions.length === 0"
      class="comm__center"
    >
      <CEmptyState :title="t('agent.commissions.errorTitle')" />
      <CButton variant="outline" size="sm" @click="retry">
        {{ t('common.retry') }}
      </CButton>
    </div>

    <!-- FP-25: self-hiding empty state -->
    <div v-else-if="commissionsEmpty" class="comm__center">
      <CEmptyState
        :title="t('agent.commissions.empty.title')"
        :description="t('agent.commissions.empty.desc')"
      />
    </div>

    <!-- List -->
    <template v-else>
      <ul class="comm__list">
        <li v-for="entry in agentStore.commissions" :key="entry.id" class="comm__card">
          <div class="comm__row">
            <span class="comm__type">{{ typeLabel(entry.type) }}</span>
            <span class="comm__amount">
              {{ formatPrice(entry.amount_cents) }}
            </span>
          </div>

          <div class="comm__row comm__row--meta">
            <div class="comm__detail">
              <!-- commission: who / what / level -->
              <template v-if="entry.type === 'commission'">
                <span class="comm__detail-main">
                  {{ entry.investor_name || '—' }}
                </span>
                <span class="comm__detail-sub">
                  <span v-if="entry.product_name">{{ entry.product_name }}</span>
                  <span v-if="entry.level != null" class="comm__level">
                    {{ levelLabel(entry.level) }}
                  </span>
                </span>
              </template>
              <!-- volume_bonus: period / rank -->
              <template v-else>
                <span class="comm__detail-main">
                  {{ periodLabel(entry.period_type) }}
                </span>
                <span v-if="entry.rank != null" class="comm__detail-sub">
                  {{ t('agent.commissions.bonus.rankLabel') }}
                  #{{ entry.rank }}
                </span>
              </template>
            </div>

            <div class="comm__meta-right">
              <span class="comm__status" :class="`comm__status--${statusVariant(entry.status)}`">
                {{ statusLabel(entry.status) }}
              </span>
              <span class="comm__date">{{ formatDate(entry.created_at, locale) }}</span>
            </div>
          </div>
        </li>
      </ul>

      <div v-if="agentStore.hasMoreCommissions && !commissionsEmpty" class="comm__more">
        <CButton
          variant="secondary"
          :loading="agentStore.commissionsLoading"
          :disabled="agentStore.commissionsLoading"
          @click="loadMore"
        >
          {{ t('agent.commissions.loadMore') }}
        </CButton>
      </div>

      <p
        v-if="agentStore.commissionsError && agentStore.commissions.length > 0"
        class="comm__loadmore-error"
      >
        {{ t('agent.commissions.loadMoreError') }}
      </p>
    </template>
  </div>
</template>

<style scoped>
.comm {
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.comm__header {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.comm__title {
  font-size: var(--fs-xl);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}

.comm__subtitle {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  margin: 0;
}

.comm__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-5) 0;
}

.comm__loadmore-error {
  margin: var(--space-2) 0 0;
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  text-align: center;
}

/* -- List -- */

.comm__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.comm__card {
  background: var(--surface);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.comm__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}

.comm__row--meta {
  align-items: flex-end;
}

.comm__type {
  font-size: var(--fs-xs);
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.comm__amount {
  font-size: var(--fs-body);
  font-weight: 700;
  color: var(--text-primary);
}

.comm__detail {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
}

.comm__detail-main {
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.comm__detail-sub {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
}

.comm__level {
  font-weight: 700;
  color: var(--text-secondary);
}

.comm__meta-right {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: var(--space-1);
  flex-shrink: 0;
}

.comm__status {
  font-size: var(--fs-xs);
  font-weight: 600;
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-sm);
  background: var(--bg-surface);
  color: var(--text-secondary);
}

.comm__status--success {
  color: var(--success);
}

.comm__status--warning {
  color: var(--warning);
}

.comm__status--danger {
  color: var(--danger);
  background: var(--danger-subtle);
}

.comm__status--neutral {
  color: var(--text-tertiary);
}

.comm__date {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
}

.comm__more {
  display: flex;
  justify-content: center;
  margin-top: var(--space-3);
}

/* READING MEASURE — descriptive text only. --maxw-prose (680px) is a CEILING,
   so this rule cannot bind until the container is already wider than a
   comfortable line: on a phone it does nothing at all, which is why it needs
   no media query. Measured at 1280 before applying: `event-card__desc` ran to
   932px and `staff-dash__role-count` to 901. Names, figures and table cells
   are deliberately NOT capped — a name is not prose, and capping it would only
   leave dead space in its row. */
.comm__subtitle {
  max-width: var(--maxw-prose);
}
</style>
