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
// A FAILED READ SHOWS AS A FAILURE. A card whose read failed says so in its
// own words and keeps a dash where the number would be; it never shows a zero
// that would read as "nothing is waiting". One retry button re-reads all.
// =============================================================================

import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Users, ShieldAlert, CreditCard, UserCheck, Banknote, MessageCircle } from '@/components/ui/icons'
import type { Component } from 'vue'
import { CStatCard, CIconBox, CLoader, CButton, CBadge } from '@/components/ui'
import { safeNavigate } from '@/composables/safeNavigate'
import { useStaffRights } from '@/composables/useStaffRights'
import { useAuthStore } from '@/stores/auth'
import { QUEUES, useStaffQueuesStore } from '@/stores/staffQueues'
import type { QueueKey, QueueSpec } from '@/stores/staffQueues'

const { t } = useI18n()
const router = useRouter()
const authStore = useAuthStore()
const queues = useStaffQueuesStore()
const { current } = useStaffRights()

const userName = computed(() => {
  const p = authStore.user?.profile
  if (p && typeof p === 'object') {
    const fn = (p as Record<string, unknown>).first_name
    const ln = (p as Record<string, unknown>).last_name
    if (fn || ln) return `${fn ?? ''} ${ln ?? ''}`.trim()
  }
  return authStore.user?.email ?? t('staff.settings.noName')
})

const ICONS: Record<QueueKey, { icon: Component; variant: 'warning' | 'success' | 'accent' }> = {
  kyc: { icon: ShieldAlert, variant: 'warning' },
  topups: { icon: CreditCard, variant: 'success' },
  withdrawals: { icon: Banknote, variant: 'success' },
  agentApps: { icon: UserCheck, variant: 'accent' },
  support: { icon: MessageCircle, variant: 'accent' },
}

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

function valueOf(key: QueueKey): string {
  const q = queues.queues[key]
  if (q.status === 'error') return '—'
  return q.more ? `${q.count}+` : String(q.count)
}

function subOf(key: QueueKey): string | undefined {
  return queues.queues[key].status === 'error' ? t('staff.home.loadFailed') : undefined
}

function go(path: string): void {
  void safeNavigate(router.push(path), `[StaffDashboardView] to ${path}`)
}

function goUsers(): void {
  go('/staff/users')
}

function reload(): void {
  void queues.loadAll((key) => current().can(key))
}

onMounted(reload)
</script>

<template>
  <div class="staff-dash">
    <!-- Greeting -->
    <div class="staff-dash__greeting">
      <span class="staff-dash__label">{{ t('staff.panel') }}</span>
      <h2 class="staff-dash__name">
        {{ userName }}
      </h2>
      <CBadge
        variant="primary"
        :text="current().admin ? t('staff.settings.roleAdmin') : t('staff.settings.roleStaff')"
      />
    </div>

    <!-- Loading -->
    <div v-if="loading" class="staff-dash__center">
      <CLoader :size="32" />
    </div>

    <template v-else>
      <!-- A failed read is said, once, with the way to read again -->
      <div v-if="queues.anyFailed" class="staff-dash__failed" role="alert">
        <p class="staff-dash__error">
          {{ t('staff.home.someFailed') }}
        </p>
        <CButton variant="secondary" size="sm" @click="reload">
          {{ t('common.retry') }}
        </CButton>
      </div>

      <!-- One counter for every queue the member may work -->
      <div class="stats-grid">
        <CStatCard
          :value="queues.users.status === 'error' ? '—' : String(queues.users.count)"
          :label="t('staff.users.stat')"
          :sub="queues.users.status === 'error' ? t('staff.home.loadFailed') : undefined"
          @click="goUsers"
        >
          <template #icon>
            <CIconBox variant="primary">
              <Users :size="24" />
            </CIconBox>
          </template>
        </CStatCard>

        <CStatCard
          v-for="q in visibleQueues"
          :key="q.key"
          :value="valueOf(q.key)"
          :label="t(q.labelKey)"
          :sub="subOf(q.key)"
          @click="go(q.path)"
        >
          <template #icon>
            <CIconBox :variant="ICONS[q.key].variant">
              <component :is="ICONS[q.key].icon" :size="24" />
            </CIconBox>
          </template>
        </CStatCard>
      </div>
    </template>
  </div>
</template>

<style scoped>
.staff-dash {
  padding: var(--space-4);
}

.staff-dash__greeting {
  margin-bottom: var(--space-4-lg);
}

.staff-dash__label {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
}

.staff-dash__name {
  font-size: var(--fs-lg);
  font-weight: 700;
  color: var(--text-primary);
  margin: var(--space-1) 0 var(--space-2);
}

.stats-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
}

.stats-grid .c-stat {
  cursor: pointer;
}

.staff-dash__failed {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-3);
  background: var(--warning-subtle);
  border-radius: var(--radius-md);
  margin-bottom: var(--space-4);
}

.staff-dash__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: var(--center-md);
  gap: var(--space-4);
}

.staff-dash__error {
  margin: 0;
  font-size: var(--fs-sm);
  color: var(--danger);
}

/* TILE CEILING — a grid authored `repeat(N, 1fr)` keeps N columns at every
   width, so on a 1016px desktop it stretches its contents to fill: measured,
   a stat tile reached 316px and an action button 497px. Past a point the extra
   room should be whitespace, not wider furniture.

   The COLUMN COUNT IS DELIBERATELY UNCHANGED. Only the ceiling is added, so
   nothing reflows and no set of related figures can wrap into a ragged 2+1.
   An earlier attempt used auto-fit and did exactly that: the cap, not a lack
   of room, was what pushed the third tile onto its own line. Mobile-first, so
   this is a min-width and the phone is untouched. */
@media (min-width: 880px) {
  .stats-grid {
    max-width: calc(2 * var(--tile-max));
  }
}
</style>
