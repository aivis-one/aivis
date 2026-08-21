<script setup lang="ts">
// Staff dashboard — platform statistics + quick actions.
// GET /api/v1/staff/dashboard/stats → DashboardStatsResponse.
// Matches staff-shell/mockup.html screen-dashboard layout.

import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Users, ShieldAlert, CreditCard, UserCheck, ShieldCheck, Ghost } from 'lucide-vue-next'
import { CStatCard, CIconBox, CLoader, CButton, CBadge } from '@/components/ui'
import { useToast } from '@/composables/useToast'
import { safeNavigate } from '@/composables/safeNavigate'
import { useAuthStore } from '@/stores/auth'
import { fetchDashboardStats, fetchAgentApplications } from '@/api/admin'
import type { DashboardStatsResponse } from '@/api/types'

const { t } = useI18n()
const router = useRouter()
const authStore = useAuthStore()
const { showToast } = useToast()

const stats = ref<DashboardStatsResponse | null>(null)
const pendingApps = ref(0)
const loading = ref(true)
const error = ref(false)

const userName = computed(() => {
  const p = authStore.user?.profile
  if (p && typeof p === 'object') {
    const fn = (p as Record<string, unknown>).first_name
    const ln = (p as Record<string, unknown>).last_name
    if (fn || ln) return `${fn ?? ''} ${ln ?? ''}`.trim()
  }
  return authStore.user?.email ?? 'Staff'
})

async function loadStats(): Promise<void> {
  loading.value = true
  error.value = false
  try {
    const [statsData, apps] = await Promise.all([
      fetchDashboardStats(),
      fetchAgentApplications().catch(() => []),
    ])
    stats.value = statsData
    pendingApps.value = apps.length
  } catch {
    error.value = true
    showToast(t('common.error'), 'error')
  } finally {
    loading.value = false
  }
}

// Navigation handlers. Eight inline @click="router.push(...)" in the
// template collapsed to five named functions (one per destination):
// `/staff/kyc` is reached from three places, `/staff/payments` from
// two. Each handler owns its own safeNavigate call so future per-target
// guards attach in one place, matching the InvestorDashboardView
// `goPortfolio/goBalance/...` paradigm.
function goUsers(): void {
  void safeNavigate(router.push('/staff/users'), '[StaffDashboardView] to users')
}

function goKyc(): void {
  void safeNavigate(router.push('/staff/kyc'), '[StaffDashboardView] to KYC queue')
}

function goPayments(): void {
  void safeNavigate(
    router.push('/staff/payments'),
    '[StaffDashboardView] to payments',
  )
}

function goAgentApps(): void {
  void safeNavigate(
    router.push('/staff/agent-apps'),
    '[StaffDashboardView] to agent apps',
  )
}

function goAvatar(): void {
  void safeNavigate(router.push('/staff/avatar'), '[StaffDashboardView] to avatar')
}

onMounted(loadStats)
</script>

<template>
  <div class="staff-dash">
    <!-- Greeting -->
    <div class="staff-dash__greeting">
      <span class="staff-dash__label">{{ t('staff.panel') }}</span>
      <h2 class="staff-dash__name">{{ userName }}</h2>
      <CBadge variant="primary" :text="t('staff.badge')" />
    </div>

    <!-- Loading -->
    <div v-if="loading" class="staff-dash__center">
      <CLoader :size="32" />
    </div>

    <!-- Error -->
    <div v-else-if="error" class="staff-dash__center">
      <p class="staff-dash__error">{{ t('common.error') }}</p>
      <CButton variant="secondary" size="sm" @click="loadStats">{{ t('common.retry') }}</CButton>
    </div>

    <!-- Stats -->
    <template v-else-if="stats">
      <!-- Stat cards grid -->
      <div class="stats-grid">
        <CStatCard
          :value="String(stats.total_users)"
          :label="t('staff.users.stat')"
          @click="goUsers"
        >
          <template #icon>
            <CIconBox variant="primary"><Users :size="24" /></CIconBox>
          </template>
        </CStatCard>

        <CStatCard
          :value="String(stats.pending_kyc_count)"
          :label="t('staff.kycQueue')"
          :sub="t('staff.pending')"
          @click="goKyc"
        >
          <template #icon>
            <CIconBox variant="warning"><ShieldAlert :size="24" /></CIconBox>
          </template>
        </CStatCard>

        <CStatCard
          :value="'—'"
          :label="t('staff.payments.stat')"
          :sub="t('staff.awaitingConfirm')"
          @click="goPayments"
        >
          <template #icon>
            <CIconBox variant="success"><CreditCard :size="24" /></CIconBox>
          </template>
        </CStatCard>

        <CStatCard
          :value="String(pendingApps)"
          :label="t('staff.agentApps')"
          :sub="t('staff.new')"
          @click="goAgentApps"
        >
          <template #icon>
            <CIconBox variant="accent"><UserCheck :size="24" /></CIconBox>
          </template>
        </CStatCard>
      </div>

      <!-- KYC alert banner -->
      <div
        tabindex="0"
        role="button"
        @keyup.enter="goKyc"
        @keyup.space.prevent="goKyc" v-if="stats.pending_kyc_count > 0" class="staff-dash__alert" @click="goKyc">
        <ShieldAlert :size="16" />
        <span>{{ stats.pending_kyc_count }} {{ t('staff.pending').toLowerCase() }} KYC</span>
      </div>

      <!-- Role breakdown -->
      <div v-if="Object.keys(stats.users_by_role).length" class="staff-dash__roles">
        <div
          v-for="(count, role) in stats.users_by_role"
          :key="role"
          class="staff-dash__role-chip"
        >
          <span class="staff-dash__role-name">{{ role }}</span>
          <span class="staff-dash__role-count">{{ count }}</span>
        </div>
      </div>

      <!-- Quick actions -->
      <div class="staff-dash__section-title">{{ t('staff.quickActions') }}</div>
      <CButton variant="primary" size="sm" class="staff-dash__action" @click="goKyc">
        <ShieldCheck :size="16" /> {{ t('staff.processKyc') }}
      </CButton>
      <CButton variant="secondary" size="sm" class="staff-dash__action" @click="goPayments">
        <CreditCard :size="16" /> {{ t('staff.checkPayments') }}
      </CButton>
      <CButton variant="secondary" size="sm" class="staff-dash__action" @click="goAvatar">
        <Ghost :size="16" /> Avatar Mode
      </CButton>
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

.staff-dash__alert {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3);
  background: var(--warning-subtle);
  border-radius: var(--radius-md);
  margin-bottom: var(--space-4);
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--warning);
  cursor: pointer;
}

.staff-dash__roles {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin-bottom: var(--space-4-lg);
}

.staff-dash__role-chip {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-sm);
  background: var(--bg-subtle);
  font-size: var(--fs-xs);
  color: var(--text-secondary);
}

.staff-dash__role-name {
  text-transform: capitalize;
  font-weight: 600;
}

.staff-dash__role-count {
  /* Reading measure: this ran to 901px at 1280. See the prose block below. */
  max-width: var(--maxw-prose);
  font-weight: 700;
  color: var(--text-primary);
}

.staff-dash__section-title {
  font-size: var(--fs-sm);
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: var(--space-3);
}

.staff-dash__action {
  margin-bottom: var(--space-2);
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
@media (min-width: 820px) {
  .stats-grid { max-width: calc(2 * var(--tile-max)); }
}
</style>
