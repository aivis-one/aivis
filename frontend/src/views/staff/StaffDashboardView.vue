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
import { CStatCard, CLoader, CButton, CBadge } from '@/components/ui'
import StaffAlert from '@/components/staff/StaffAlert.vue'
import { useScreenHeader } from '@/components/layout/screenHeader'
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

// The icon part of each queue's tile: an icon of the set in a lead box (K23) whose
// tone is a second sign (the label says the same in words).
const ICONS: Record<QueueKey, { icon: Component; tone: 'warning' | 'success' | 'accent' }> = {
  kyc: { icon: ShieldAlert, tone: 'warning' },
  topups: { icon: CreditCard, tone: 'success' },
  withdrawals: { icon: Banknote, tone: 'success' },
  agentApps: { icon: UserCheck, tone: 'accent' },
  support: { icon: MessageCircle, tone: 'accent' },
}

// The frame's header carries the greeting: the member's name and the panel's name.
useScreenHeader({
  title: () => userName.value,
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
    <div>
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
      <StaffAlert v-if="queues.anyFailed" tone="warning">
        {{ t('staff.home.someFailed') }}
        <template #actions>
          <CButton variant="secondary" size="sm" inline @click="reload">
            {{ t('common.retry') }}
          </CButton>
        </template>
      </StaffAlert>

      <!-- One counter for every queue the member may work (K46) -->
      <div class="ds-stats">
        <CStatCard
          :value="queues.users.status === 'error' ? '—' : String(queues.users.count)"
          :label="t('staff.users.stat')"
          :sub="queues.users.status === 'error' ? t('staff.home.loadFailed') : undefined"
          @click="goUsers"
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
          @click="go(q.path)"
        >
          <template #icon>
            <span class="ds-lead" :data-tone="ICONS[q.key].tone">
              <component :is="ICONS[q.key].icon" />
            </span>
          </template>
        </CStatCard>
      </div>
    </template>
  </div>
</template>

<style scoped>
.staff-dash {
  display: grid;
  gap: var(--space-4);
}

.staff-dash__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-block-size: var(--center-md);
  gap: var(--space-4);
}
</style>
