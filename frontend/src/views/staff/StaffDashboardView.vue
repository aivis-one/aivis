<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- StaffDashboardView (the staff Home)
// =============================================================================
//
// One counter for every queue the member works from -- identity checks,
// top-ups in their hour, withdrawals, integrator applications, support
// requests nobody has taken -- and the number of users. A press on a counter
// opens its queue.
//
// ONLY THE QUEUES THE MEMBER MAY WORK are drawn: a member without the right to
// review payments sees no top-up or withdrawal counter (stores/staffQueues.ts
// does not read them either).
//
// THE ADMINISTRATOR ALSO SEES two figures the statistics carry: the users by role
// and the avatar sessions open now (the same read as the user count).
//
// A FAILED READ SHOWS AS A FAILURE. A card whose read failed says so in its
// own words and keeps a dash where the number would be; it never shows a zero
// that would read as "nothing is waiting". One retry button re-reads all.
// =============================================================================

import { computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  Users,
  ShieldAlert,
  CreditCard,
  UserCheck,
  Banknote,
  MessageCircle,
  Ghost,
} from '@/components/ui/icons'
import type { Component } from 'vue'
import { CStatCard, CLoader, CButton, CBadge } from '@/components/ui'
import CAlert from '@/components/ui/CAlert.vue'
import { useScreenHeader } from '@/components/layout/screenHeader'
import { useStaffRights } from '@/composables/useStaffRights'
import { tOrRaw } from '@/utils/i18n'
import { QUEUES, useStaffQueuesStore } from '@/stores/staffQueues'
import type { QueueKey, QueueSpec } from '@/stores/staffQueues'

const { t } = useI18n()
const queues = useStaffQueuesStore()
const { current } = useStaffRights()

// The icon part of each queue's tile: an icon of the set in a lead box (K23) whose
// tone is a second sign (the label says the same in words).
const ICONS: Record<QueueKey, { icon: Component; tone: 'warning' | 'success' | 'accent' }> = {
  kyc: { icon: ShieldAlert, tone: 'warning' },
  topups: { icon: CreditCard, tone: 'success' },
  withdrawals: { icon: Banknote, tone: 'success' },
  agentApps: { icon: UserCheck, tone: 'accent' },
  support: { icon: MessageCircle, tone: 'accent' },
}

// The frame's header carries the tab's name (no greeting) and the panel's name.
useScreenHeader({
  title: () => t('tab.staff.home'),
  lead: () => t('staff.panel'),
})

/** The queues the member may work, in the Home's order. */
const visibleQueues = computed<QueueSpec[]>(() => {
  const rights = current()
  return QUEUES.filter((q) => !q.permission || rights.can(q.permission))
})

const loading = computed<boolean>(
  () =>
    queues.users.status === 'loading' ||
    visibleQueues.value.some((q) => queues.queues[q.key].status === 'loading'),
)

// The roles in the order the user list's chips show them, then any other the server sends.
const ROLE_ORDER = ['investor', 'agent', 'company', 'staff', 'platform']

/** The users by role, drawn for the administrator once the statistics were read. */
const roleTiles = computed(() => {
  if (!current().admin || queues.overview.status !== 'ready') return []
  const byRole = queues.overview.byRole
  const known = ROLE_ORDER.filter((role) => role in byRole)
  const others = Object.keys(byRole)
    .filter((role) => !ROLE_ORDER.includes(role))
    .sort()
  return [...known, ...others].map((role) => ({
    role,
    label: tOrRaw(t, `staff.roles.${role}`, role),
    value: String(byRole[role]),
  }))
})
const showOverview = computed(() => current().admin && queues.overview.status === 'ready')

function valueOf(key: QueueKey): string {
  const q = queues.queues[key]
  if (q.status === 'error') return '—'
  return q.more ? `${q.count}+` : String(q.count)
}

function subOf(key: QueueKey): string | undefined {
  return queues.queues[key].status === 'error' ? t('staff.home.loadFailed') : undefined
}

function reload(): void {
  void queues.loadAll((key) => current().can(key))
}

onMounted(reload)
</script>

<template>
  <div class="staff-dash">
    <div>
      <CBadge
        variant="primary"
        :text="current().admin ? t('staff.settings.roleAdmin') : t('staff.settings.roleStaff')"
      />
    </div>

    <!-- Loading -->
    <CLoader v-if="loading" centered extent="page" />

    <template v-else>
      <!-- A failed read is said, once, with the way to read again -->
      <CAlert v-if="queues.anyFailed" tone="warning">
        {{ t('staff.home.someFailed') }}
        <template #actions>
          <CButton variant="secondary" size="sm" inline @click="reload">
            {{ t('common.retry') }}
          </CButton>
        </template>
      </CAlert>

      <!-- One counter for every queue the member may work (K46) -->
      <div class="ds-stats">
        <CStatCard
          :value="queues.users.status === 'error' ? '—' : String(queues.users.count)"
          :label="t('staff.users.stat')"
          :sub="queues.users.status === 'error' ? t('staff.home.loadFailed') : undefined"
          to="/staff/users"
        >
          <template #icon>
            <span class="ds-lead"><Users /></span>
          </template>
        </CStatCard>

        <CStatCard
          v-for="q in visibleQueues"
          :key="q.key"
          :value="valueOf(q.key)"
          :label="t(q.labelKey)"
          :sub="subOf(q.key)"
          :to="q.path"
        >
          <template #icon>
            <span class="ds-lead" :data-tone="ICONS[q.key].tone">
              <component :is="ICONS[q.key].icon" />
            </span>
          </template>
        </CStatCard>
      </div>

      <!-- The administrator's figures: users by role, avatar sessions open now -->
      <section
        v-if="showOverview"
        class="staff-dash__overview"
        :aria-label="t('staff.home.byRole')"
      >
        <h2 class="ds-section-title">{{ t('staff.home.byRole') }}</h2>
        <div class="ds-stats">
          <CStatCard
            v-for="tile in roleTiles"
            :key="tile.role"
            :value="tile.value"
            :label="tile.label"
          >
            <template #icon>
              <span class="ds-lead"><Users /></span>
            </template>
          </CStatCard>
          <CStatCard
            :value="String(queues.overview.avatarSessions)"
            :label="t('staff.home.avatarSessions')"
          >
            <template #icon>
              <span class="ds-lead" data-tone="accent"><Ghost /></span>
            </template>
          </CStatCard>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.staff-dash {
  display: grid;
  gap: var(--space-4);
}

.staff-dash__overview {
  display: grid;
  gap: var(--space-3);
}
</style>
