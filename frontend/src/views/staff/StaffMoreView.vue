<script setup lang="ts">
// Staff "More" screen — profile card, tools navigation, system info, logout.
// Matches staff-shell/mockup.html screen-more layout.

import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { FileText, Ghost, LogOut } from 'lucide-vue-next'
import { CAvatar, CBadge } from '@/components/ui'
import { useAuthStore } from '@/stores/auth'
import { safeNavigate } from '@/composables/safeNavigate'

const { t } = useI18n()
const router = useRouter()
const authStore = useAuthStore()

const userName = computed(() => {
  const p = authStore.user?.profile
  if (p && typeof p === 'object') {
    const fn = (p as Record<string, unknown>).first_name
    const ln = (p as Record<string, unknown>).last_name
    if (fn || ln) return `${fn ?? ''} ${ln ?? ''}`.trim()
  }
  return 'Staff'
})

const userEmail = computed(() => authStore.user?.email ?? '')

async function handleLogout(): Promise<void> {
  await authStore.logout()
  void safeNavigate(router.push('/login'), '[StaffMoreView] to login')
}

// Nav-item handlers. Each target gets a dedicated function so future
// per-target guards (role checks, feature flags) attach in one place
// instead of widening a generic `navigate(target)` helper. Matches
// the InvestorDashboardView `goPortfolio/goBalance/...` paradigm.
function goAgentApps(): void {
  void safeNavigate(
    router.push('/staff/agent-apps'),
    '[StaffMoreView] to agent apps',
  )
}

function goAvatar(): void {
  void safeNavigate(router.push('/staff/avatar'), '[StaffMoreView] to avatar')
}
</script>

<template>
  <div class="staff-more">
    <!-- Profile card -->
    <div class="staff-more__profile">
      <CAvatar :name="userName" :size="72" />
      <div class="staff-more__name">{{ userName }}</div>
      <div class="staff-more__email">{{ userEmail }}</div>
      <div class="staff-more__badges">
        <CBadge variant="primary" text="Staff" />
      </div>
    </div>

    <!-- Tools section -->
    <div class="staff-more__section">
      <div class="staff-more__section-label">{{ t('staff.settings.tools') }}</div>

      <div class="staff-more__nav-item" @click="goAgentApps">
        <span class="staff-more__nav-left">
          <FileText :size="16" /> {{ t('staff.agentApps2.title') }}
        </span>
        <span class="staff-more__nav-right">&rarr;</span>
      </div>

      <div class="staff-more__nav-item staff-more__nav-item--accent" @click="goAvatar">
        <span class="staff-more__nav-left">
          <Ghost :size="16" /> Avatar Mode
        </span>
        <span class="staff-more__nav-right">&rarr;</span>
      </div>
    </div>

    <!-- System section -->
    <div class="staff-more__section">
      <div class="staff-more__section-label">{{ t('staff.settings.system') }}</div>

      <div class="staff-more__info-row">
        <span>{{ t('staff.settings.platform') }}</span>
        <span class="staff-more__info-val">v2.4.1</span>
      </div>

      <div class="staff-more__info-row">
        <span>{{ t('staff.settings.language') }}</span>
        <span class="staff-more__info-val">{{ t('staff.settings.langVal') }}</span>
      </div>

      <div class="staff-more__nav-item staff-more__nav-item--danger" @click="handleLogout">
        <span class="staff-more__nav-left">
          <LogOut :size="16" /> {{ t('staff.settings.logout') }}
        </span>
        <span class="staff-more__nav-right">&rarr;</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.staff-more { padding: var(--space-4); }

.staff-more__profile {
  text-align: center; padding: var(--space-4-lg) 0; margin-bottom: var(--space-4);
}
.staff-more__name {
  font-size: var(--fs-h4); font-weight: 700; color: var(--text-primary); margin-top: var(--space-3);
}
.staff-more__email {
  font-size: var(--fs-xs-lg); color: var(--text-secondary); margin-top: var(--space-1);
}
.staff-more__badges {
  display: inline-flex; gap: var(--space-2); margin-top: var(--space-2);
}

.staff-more__section {
  border-top: 1px solid var(--border-default); padding-top: var(--space-4); margin-top: var(--space-4);
}
.staff-more__section-label {
  font-size: var(--fs-xs); font-weight: 700; color: var(--text-tertiary);
  text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: var(--space-3);
}

.staff-more__nav-item {
  display: flex; justify-content: space-between; align-items: center;
  padding: var(--space-4) 0; border-bottom: 1px solid var(--border-default); cursor: pointer;
  font-size: var(--fs-sm); color: var(--text-primary);
}
.staff-more__nav-item:hover { opacity: 0.8; }
.staff-more__nav-item--accent { color: var(--accent); font-weight: 600; }
.staff-more__nav-item--danger { color: var(--danger); border-bottom: none; }
.staff-more__nav-left { display: flex; align-items: center; gap: var(--space-2); }
.staff-more__nav-right { font-size: var(--fs-xs-lg); color: var(--text-tertiary); }

.staff-more__info-row {
  display: flex; justify-content: space-between; padding: var(--space-4) 0;
  border-bottom: 1px solid var(--border-default); font-size: var(--fs-sm); color: var(--text-primary);
}
.staff-more__info-val { font-size: var(--fs-xs-lg); color: var(--text-tertiary); }
</style>
