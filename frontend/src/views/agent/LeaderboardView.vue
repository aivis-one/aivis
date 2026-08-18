<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- LeaderboardView (Task 3 Block C, Phase F6.2)
// =============================================================================
//
// Replaces the F6.2 stub. The agent leaderboard for the current period,
// GET /agent/leaderboard via the store's leaderboard group. Ranked
// rows (rank / agent_name / volume); the caller's own row is
// highlighted from the server is_me flag.
//
// EMPTY STATE.
//   entries is empty until the leaderboard worker takes the first
//   snapshot of the period -- a real, expected state, not an error. It
//   gets its own CEmptyState ("not ready yet"), distinct from the
//   error path.
//
// FP notes:
//   FP-19 -- shell owns the header; inline lb__page-header h1, no
//            header component here.
//   FP-20 -- /agent/leaderboard is a SUB-ROUTE (not in AGENT_TABS), so
//            a CBackLink is mandatory; goBack is history-aware with a
//            Hub fallback.
//   FP-18 -- the back fallback navigates via safeNavigate (router.back
//            is neither push nor replace, so it stays bare).
//
// ENTRY POINT (open note, Task 3 report).
//   Same as ReferralsView: no shipped Hub/Dashboard link points here
//   yet; the entry point is expected from AgentMoreView (Block D).
// =============================================================================

import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'

import { CBackLink, CButton, CEmptyState, CLoader } from '@/components/ui'
import { useAgentStore } from '@/stores/agent'
import { safeNavigate } from '@/composables/safeNavigate'
import { formatDate, formatPrice } from '@/utils/format'

const router = useRouter()
const { t, locale } = useI18n()
const agentStore = useAgentStore()

// ---------------------------------------------------------------------------
// Derived
// ---------------------------------------------------------------------------

const entries = computed(() => agentStore.leaderboard?.entries ?? [])

const periodStart = computed(() => agentStore.leaderboard?.period_start ?? null)

// Loaded payload with zero ranked rows -- the worker has not taken the
// first snapshot of the period yet.
const isEmpty = computed(
  () =>
    !agentStore.leaderboardLoading
    && !agentStore.leaderboardError
    && agentStore.leaderboard !== null
    && entries.value.length === 0,
)

// Period caption -- empty when no snapshot period is known yet (the
// v-if hides the element; the null guard also keeps the shared,
// non-null formatDate happy).
const periodCaption = computed(() =>
  periodStart.value
    ? t('agent.leaderboard.period', {
        date: formatDate(periodStart.value, locale.value),
      })
    : '',
)

// ---------------------------------------------------------------------------
// Navigation
// ---------------------------------------------------------------------------

function goBack(): void {
  // History-aware (More tab in the wired flow); cold deep-link falls
  // through to the Hub. router.back() is neither push nor replace, so
  // it does not need safeNavigate; the fallback push does (FP-18).
  if (window.history.state?.back) {
    router.back()
    return
  }
  void safeNavigate(
    router.push({ name: 'agent-hub' }),
    '[LeaderboardView] back fallback to agent-hub',
  )
}

function retry(): void {
  void agentStore.fetchLeaderboard()
}

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

onMounted(() => {
  void agentStore.fetchLeaderboard()
})
</script>

<template>
  <div class="lb">
    <!-- Page header (FP-19: shell owns the header; FP-20: sub-route back-link) -->
    <div class="lb__page-header">
      <CBackLink :label="t('agent.leaderboard.backLink')" @click="goBack" />
      <h1 class="lb__title">{{ t('agent.leaderboard.title') }}</h1>
      <p class="lb__subtitle">{{ t('agent.leaderboard.subtitle') }}</p>
    </div>

    <!-- Loading -->
    <div
      v-if="agentStore.leaderboardLoading && agentStore.leaderboard === null"
      class="lb__center"
    >
      <CLoader :size="24" />
    </div>

    <!-- Error -->
    <div
      v-else-if="agentStore.leaderboardError && agentStore.leaderboard === null"
      class="lb__center"
    >
      <CEmptyState :title="t('agent.leaderboard.errorTitle')" />
      <CButton variant="outline" size="sm" @click="retry">
        {{ t('common.retry') }}
      </CButton>
    </div>

    <!-- Empty: no snapshot yet (not an error) -->
    <div v-else-if="isEmpty" class="lb__center">
      <CEmptyState
        :title="t('agent.leaderboard.empty.title')"
        :description="t('agent.leaderboard.empty.desc')"
      />
    </div>

    <!-- Ranked list -->
    <template v-else-if="agentStore.leaderboard !== null">
      <p v-if="periodStart" class="lb__period">
        {{ periodCaption }}
      </p>

      <ul class="lb__list">
        <li
          v-for="entry in entries"
          :key="entry.agent_id"
          class="lb__row"
          :class="{ 'lb__row--me': entry.is_me }"
        >
          <span class="lb__rank">#{{ entry.rank }}</span>
          <span class="lb__name">
            <span class="lb__nametext">{{ entry.agent_name }}</span>
            <span v-if="entry.is_me" class="lb__you">
              {{ t('agent.leaderboard.you') }}
            </span>
          </span>
          <span class="lb__volume">{{ formatPrice(entry.volume_cents) }}</span>
        </li>
      </ul>
    </template>
  </div>
</template>

<style scoped>
.lb {
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.lb__page-header {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.lb__title {
  font-size: var(--fs-xl);
  font-weight: 700;
  color: var(--text-primary);
  margin: var(--space-2) 0 0;
}

.lb__subtitle {
  font-size: var(--fs-xs-lg);
  color: var(--text-secondary);
  margin: 0;
}

.lb__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-5) 0;
}

.lb__period {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
  margin: 0;
}

/* -- Ranked list -- */

.lb__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.lb__row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  background: var(--surface);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  padding: var(--space-3) var(--space-4);
}

.lb__row--me {
  border-color: var(--primary);
  background: var(--primary-dim);
}

.lb__rank {
  font-size: var(--fs-sm);
  font-weight: 700;
  color: var(--text-secondary);
  min-width: 36px;
}

.lb__name {
  flex: 1;
  min-width: 0;
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--text-primary);
}

/* The ellipsis belongs to the NAME TEXT, not to the flex container. On the
   container it was inert (text-overflow acts on inline content in a block,
   not on a flex container's anonymous text item) and its overflow:hidden ate
   the adjacent flex-shrink:0 badge instead of trimming the name. */
.lb__nametext {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.lb__you {
  flex-shrink: 0;
  font-size: var(--fs-xs);
  font-weight: 600;
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-sm);
  background: var(--primary);
  color: var(--on-primary);
}

.lb__volume {
  font-size: var(--fs-sm);
  font-weight: 700;
  color: var(--text-primary);
  flex-shrink: 0;
}
</style>
