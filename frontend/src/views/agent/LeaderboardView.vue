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
//   FP-19 -- the frame owns the header (useScreenHeader), no
//            header component here.
//   FP-20 -- /agent/leaderboard is a SUB-ROUTE (not in AGENT_TABS), so
//            a CBackLink is mandatory; goBack is history-aware with a
//            Hub fallback.
//   FP-18 -- the back fallback navigates via safeNavigate (router.back
//            is neither push nor replace, so it stays bare).
//
// ENTRY POINT (open note, Task 3 report).
//   Reached from the Partners tab (AgentPartnersView, the "Rating" row).
// =============================================================================

import { computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'

import { CBadge, CButton, CEmptyState } from '@/components/ui'
import { useScreenHeader } from '@/components/layout/screenHeader'
import StaffListSkeleton from '@/components/staff/StaffListSkeleton.vue'
import { useAgentStore } from '@/stores/agent'
import { formatDate, formatPrice } from '@/utils/format'

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
    !agentStore.leaderboardLoading &&
    !agentStore.leaderboardError &&
    agentStore.leaderboard !== null &&
    entries.value.length === 0,
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

// The frame's header carries the title, the line under it and the way back:
// history-aware (Partners in the wired flow), a cold deep-link falls through to
// Partners (FP-20).
useScreenHeader({
  title: () => t('agent.leaderboard.title'),
  lead: () => t('agent.leaderboard.subtitle'),
  back: () => (window.history.state?.back ? true : { name: 'agent-partners' }),
})

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
  <!-- Loading -->
  <StaffListSkeleton v-if="agentStore.leaderboardLoading && agentStore.leaderboard === null" />

  <!-- Error -->
  <CEmptyState
    v-else-if="agentStore.leaderboardError && agentStore.leaderboard === null"
    tone="danger"
    :title="t('agent.leaderboard.errorTitle')"
  >
    <template #actions>
      <CButton variant="outline" size="sm" inline @click="retry">
        {{ t('common.retry') }}
      </CButton>
    </template>
  </CEmptyState>

  <!-- Empty: no snapshot yet (not an error) -->
  <CEmptyState
    v-else-if="isEmpty"
    :title="t('agent.leaderboard.empty.title')"
    :description="t('agent.leaderboard.empty.desc')"
  />

  <!-- Ranked list -->
  <template v-else-if="agentStore.leaderboard !== null">
    <p v-if="periodStart" class="lb__period">
      {{ periodCaption }}
    </p>

    <ul class="ds-rows">
      <li v-for="entry in entries" :key="entry.agent_id" class="ds-row">
        <span class="ds-row__lead">#{{ entry.rank }}</span>
        <span class="ds-row__body">
          <span class="ds-row__title">{{ entry.agent_name }}</span>
        </span>
        <span class="ds-row__trail">
          <CBadge v-if="entry.is_me" variant="primary" :text="t('agent.leaderboard.you')" />
          <span class="ds-row__value">{{ formatPrice(entry.volume_cents) }}</span>
        </span>
      </li>
    </ul>
  </template>
</template>

<style scoped>
/* The period caption over the list: a quiet line. */
.lb__period {
  margin: 0;
  font-size: var(--fs-xs);
  color: var(--text-secondary);
}
</style>
