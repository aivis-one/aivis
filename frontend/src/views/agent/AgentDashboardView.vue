<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- AgentDashboardView (Task 2 Block C, Phase F6.1)
// =============================================================================
//
// Replaces the F2.2 stub. The agent's landing screen (/agent redirects
// here): four widgets + quick actions.
//
// WIDGETS AND THEIR SOURCES:
//   Commission this month -- stores/agent.ts monthCommissionCents
//       (server-side month-to-date aggregate from
//       GET /agent/commissions/summary; exact, no client-side sum).
//   Leaderboard rank      -- stores/agent.ts myRank (is_me entry of
//       GET /agent/leaderboard); renders an em-dash when the agent is
//       outside the snapshot top or no snapshot exists yet.
//   Passive balance       -- existing stores/dashboard.ts
//       (GET /dashboard/summary). Commissions land on the passive
//       ledger, so passive_balance IS the agent's earnings balance.
//       No duplication: one endpoint, one store.
//   Registrations         -- stats.total_registrations from
//       GET /referrals/stats/me. The label is deliberately the honest
//       "Registrations" -- NOT a vague "referrals" that would imply
//       the full downline (downline-by-level is Task 2b backend +
//       Task 3 frontend).
//
// FP notes:
//   FP-18 -- both quick actions navigate via safeNavigate.
//   FP-19 -- no CHeader render; inline dash__header h1 owns the title.
//   FP-23 -- meta.roles already gates /agent/*; the defensive check
//            here only suppresses agent-only fetches if a non-agent
//            ever lands via a future regression (renders nothing
//            harmful either way -- widgets fall back to error states).
//   FP-25 -- widgets self-degrade to compact error text, no skeleton
//            scaffolding for missing data.
// =============================================================================

import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Gem, Link2, Trophy, UserPlus, Wallet } from 'lucide-vue-next'

import { CLoader } from '@/components/ui'
import { useAgentStore } from '@/stores/agent'
import { useAuthStore } from '@/stores/auth'
import { useDashboardStore } from '@/stores/dashboard'
import { safeNavigate } from '@/composables/safeNavigate'
import { formatNumber, formatPrice } from '@/utils/format'

const router = useRouter()
const { t, locale } = useI18n()
const agentStore = useAgentStore()
const authStore = useAuthStore()
const dashboardStore = useDashboardStore()

// FP-23: defensive role check. meta.roles on /agent/* already blocks
// non-agents at the router; this only prevents firing agent-only
// endpoints should that guard ever regress.
const isAgent = computed(() => authStore.user?.role === 'agent')

// ---------------------------------------------------------------------------
// Widget view-models
// ---------------------------------------------------------------------------

const rankDisplay = computed<string>(() =>
  agentStore.myRank !== null
    ? `#${agentStore.myRank}`
    : t('agent.dashboard.widgets.rankNone'),
)

const balanceConfirmed = computed<number>(
  () => dashboardStore.passiveBalance.confirmed,
)
const balanceFrozen = computed<number>(
  () => dashboardStore.passiveBalance.frozen,
)

// ---------------------------------------------------------------------------
// Quick actions (FP-18: safeNavigate only)
// ---------------------------------------------------------------------------

function goHub(): void {
  void safeNavigate(
    router.push({ name: 'agent-hub' }),
    '[AgentDashboardView] to agent-hub',
  )
}

function goCommissions(): void {
  void safeNavigate(
    router.push({ name: 'agent-commissions' }),
    '[AgentDashboardView] to agent-commissions',
  )
}

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

onMounted(() => {
  if (!isAgent.value) return
  // Four independent never-throw probes -- one widget failing must
  // not blank the others (same philosophy as InvestorDashboardView).
  void agentStore.fetchCommissionSummary()
  void agentStore.fetchLeaderboard()
  void agentStore.fetchStats()
  void dashboardStore.refresh()
})
</script>

<template>
  <div class="dash">
    <!-- Screen title (FP-19: shell owns CHeader, view owns the h1) -->
    <div class="dash__header">
      <h1 class="dash__title">{{ t('agent.dashboard.title') }}</h1>
      <p class="dash__subtitle">{{ t('agent.dashboard.subtitle') }}</p>
    </div>

    <!-- Widget grid -->
    <div class="dash__widgets">
      <!-- Commission this month -->
      <div class="dash__widget">
        <div class="dash__widget-icon dash__widget-icon--accent">
          <Gem :size="16" />
        </div>
        <div v-if="agentStore.commissionSummaryLoading" class="dash__widget-loader">
          <CLoader :size="16" />
        </div>
        <template v-else>
          <div class="dash__widget-value">
            <template v-if="agentStore.commissionSummaryError">—</template>
            <template v-else>
              {{ formatPrice(agentStore.monthCommissionCents) }}
            </template>
          </div>
          <div class="dash__widget-label">
            {{
              agentStore.commissionSummaryError
                ? t('agent.dashboard.errors.commission')
                : t('agent.dashboard.widgets.monthCommission')
            }}
          </div>
        </template>
      </div>

      <!-- Leaderboard rank -->
      <div class="dash__widget">
        <div class="dash__widget-icon dash__widget-icon--gold">
          <Trophy :size="16" />
        </div>
        <div v-if="agentStore.leaderboardLoading" class="dash__widget-loader">
          <CLoader :size="16" />
        </div>
        <template v-else>
          <div class="dash__widget-value">
            <template v-if="agentStore.leaderboardError">—</template>
            <template v-else>{{ rankDisplay }}</template>
          </div>
          <div class="dash__widget-label">
            {{
              agentStore.leaderboardError
                ? t('agent.dashboard.errors.rank')
                : t('agent.dashboard.widgets.rank')
            }}
          </div>
        </template>
      </div>

      <!-- Passive balance -->
      <div class="dash__widget">
        <div class="dash__widget-icon dash__widget-icon--primary">
          <Wallet :size="16" />
        </div>
        <div v-if="dashboardStore.loading" class="dash__widget-loader">
          <CLoader :size="16" />
        </div>
        <template v-else>
          <div class="dash__widget-value">
            <template v-if="dashboardStore.error">—</template>
            <template v-else>{{ formatPrice(balanceConfirmed) }}</template>
          </div>
          <div class="dash__widget-label">
            {{
              dashboardStore.error
                ? t('agent.dashboard.errors.balance')
                : t('agent.dashboard.widgets.balance')
            }}
            <span
              v-if="!dashboardStore.error && balanceFrozen > 0"
              class="dash__widget-sub"
            >
              +{{ formatPrice(balanceFrozen) }}
              {{ t('agent.dashboard.widgets.balanceFrozen') }}
            </span>
          </div>
        </template>
      </div>

      <!-- Registrations (honest label -- NOT "referrals"/downline) -->
      <div class="dash__widget">
        <div class="dash__widget-icon dash__widget-icon--teal">
          <UserPlus :size="16" />
        </div>
        <div v-if="agentStore.statsLoading" class="dash__widget-loader">
          <CLoader :size="16" />
        </div>
        <template v-else>
          <div class="dash__widget-value">
            <template v-if="agentStore.statsError || !agentStore.stats">
              —
            </template>
            <template v-else>
              {{
                formatNumber(agentStore.stats.total_registrations, locale)
              }}
            </template>
          </div>
          <div class="dash__widget-label">
            {{
              agentStore.statsError
                ? t('agent.dashboard.errors.registrations')
                : t('agent.dashboard.widgets.registrations')
            }}
          </div>
        </template>
      </div>
    </div>

    <!-- Quick actions -->
    <section class="dash__actions">
      <h2 class="dash__actions-title">
        {{ t('agent.dashboard.actions.title') }}
      </h2>
      <div class="dash__actions-row">
        <button type="button" class="dash__action" @click="goHub">
          <Link2 :size="16" />
          <span>{{ t('agent.dashboard.actions.createLink') }}</span>
        </button>
        <button type="button" class="dash__action" @click="goCommissions">
          <Gem :size="16" />
          <span>{{ t('agent.dashboard.actions.myCommissions') }}</span>
        </button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.dash {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.dash__header {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.dash__title {
  font-size: var(--fs-xl);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}

.dash__subtitle {
  font-size: var(--fs-xs-lg);
  color: var(--text-secondary);
  margin: 0;
}

/* -- Widgets -- */

.dash__widgets {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}

.dash__widget {
  background: var(--surface);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-height: 92px;
}

.dash__widget-icon {
  width: 28px;
  height: 28px;
  border-radius: var(--radius-sm);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-surface);
}

.dash__widget-icon--accent {
  color: var(--accent);
}

.dash__widget-icon--gold {
  color: var(--warning);
}

.dash__widget-icon--primary {
  color: var(--primary);
}

.dash__widget-icon--teal {
  color: var(--success);
}

.dash__widget-loader {
  display: flex;
  align-items: center;
  flex: 1;
}

.dash__widget-value {
  font-size: var(--fs-h4);
  font-weight: 700;
  color: var(--text-primary);
}

.dash__widget-label {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
}

.dash__widget-sub {
  color: var(--text-tertiary);
}

/* -- Quick actions -- */

.dash__actions-title {
  font-size: var(--fs-sm);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 10px;
}

.dash__actions-row {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}

.dash__action {
  background: var(--surface);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  padding: 14px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
  font-size: var(--fs-xs-lg);
  font-weight: 600;
  color: var(--text-primary);
  cursor: pointer;
}

.dash__action:active {
  background: var(--bg-surface);
}
</style>
