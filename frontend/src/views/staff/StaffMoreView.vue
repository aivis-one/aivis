<script setup lang="ts">
// Staff "More" screen — profile card, tools navigation, system info, logout.
// Matches staff-shell/mockup.html screen-more layout.

import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Shield, FileText, Ghost, LogOut } from 'lucide-vue-next'
import { CAvatar, CBadge } from '@/components/ui'
import { useAuthStore } from '@/stores/auth'

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
  router.push('/login')
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
        <CBadge variant="primary">
          <Shield :size="10" style="vertical-align:-1px" /> Staff
        </CBadge>
      </div>
    </div>

    <!-- Tools section -->
    <div class="staff-more__section">
      <div class="staff-more__section-label">{{ t('staff.settings.tools') }}</div>

      <div class="staff-more__nav-item" @click="router.push('/staff/agent-apps')">
        <span class="staff-more__nav-left">
          <FileText :size="14" /> {{ t('staff.agentApps2.title') }}
        </span>
        <span class="staff-more__nav-right">&rarr;</span>
      </div>

      <div class="staff-more__nav-item staff-more__nav-item--accent" @click="router.push('/staff/avatar')">
        <span class="staff-more__nav-left">
          <Ghost :size="14" /> Avatar Mode
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
          <LogOut :size="14" /> {{ t('staff.settings.logout') }}
        </span>
        <span class="staff-more__nav-right">&rarr;</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.staff-more { padding: 16px; }

.staff-more__profile {
  text-align: center; padding: 20px 0; margin-bottom: 16px;
}
.staff-more__name {
  font-size: 18px; font-weight: 700; color: var(--text); margin-top: 12px;
}
.staff-more__email {
  font-size: 13px; color: var(--text-secondary); margin-top: 4px;
}
.staff-more__badges {
  display: inline-flex; gap: 8px; margin-top: 8px;
}

.staff-more__section {
  border-top: 1px solid var(--border); padding-top: 16px; margin-top: 16px;
}
.staff-more__section-label {
  font-size: 12px; font-weight: 700; color: var(--text-tertiary);
  text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 12px;
}

.staff-more__nav-item {
  display: flex; justify-content: space-between; align-items: center;
  padding: 14px 0; border-bottom: 1px solid var(--border); cursor: pointer;
  font-size: 14px; color: var(--text);
}
.staff-more__nav-item:hover { opacity: 0.8; }
.staff-more__nav-item--accent { color: var(--accent); font-weight: 600; }
.staff-more__nav-item--danger { color: var(--danger); border-bottom: none; }
.staff-more__nav-left { display: flex; align-items: center; gap: 8px; }
.staff-more__nav-right { font-size: 13px; color: var(--text-tertiary); }

.staff-more__info-row {
  display: flex; justify-content: space-between; padding: 14px 0;
  border-bottom: 1px solid var(--border); font-size: 14px; color: var(--text);
}
.staff-more__info-val { font-size: 13px; color: var(--text-tertiary); }
</style>
