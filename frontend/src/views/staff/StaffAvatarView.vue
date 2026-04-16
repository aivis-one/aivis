<script setup lang="ts">
// Staff avatar mode — start session form + restrictions info.
// On start: composable handles token swap + redirect to target user dashboard.
// Session management (banner, end) handled by App.vue + useAvatar composable.

import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Ghost, Ban } from 'lucide-vue-next'
import { CButton, CInput } from '@/components/ui'
import { useAvatar } from '@/composables/useAvatar'

const { t } = useI18n()
const { loading, startAvatarSession } = useAvatar()

const targetUserId = ref('')

const restrictions = [
  'staff.avatar.noPurchase',
  'staff.avatar.noWithdraw',
  'staff.avatar.noPassword',
  'staff.avatar.noDelete',
  'staff.avatar.noKyc',
] as const

async function handleStart(): Promise<void> {
  const uid = targetUserId.value.trim()
  if (!uid) return
  await startAvatarSession(uid)
}
</script>

<template>
  <div class="staff-avatar">
    <!-- Header banner -->
    <div class="avatar-header">
      <div class="avatar-header__title">
        <Ghost :size="20" /> {{ t('staff.avatar.title') }}
      </div>
      <div class="avatar-header__sub">{{ t('staff.avatar.subtitle') }}</div>
    </div>

    <!-- Start form -->
    <div class="avatar-form">
      <CInput
        v-model="targetUserId"
        :label="t('staff.avatar.enterUserId')"
        :placeholder="t('staff.avatar.selectUser')"
      />
      <CButton
        variant="primary" size="sm"
        :loading="loading"
        :disabled="!targetUserId.trim()"
        style="margin-top: 12px"
        @click="handleStart"
      >
        <Ghost :size="14" /> {{ t('staff.avatar.start') }}
      </CButton>
    </div>

    <!-- Restrictions -->
    <div class="avatar-restrictions">
      <div class="avatar-restrictions__title">
        <Ban :size="14" /> {{ t('staff.avatar.restrictions') }}
      </div>
      <ul class="avatar-restrictions__list">
        <li v-for="key in restrictions" :key="key" class="avatar-restrictions__item">
          <Ban :size="14" class="avatar-restrictions__icon" />
          {{ t(key) }}
        </li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.staff-avatar { padding: 16px; }

.avatar-header {
  padding: 20px;
  background: var(--accent);
  color: white;
  border-radius: var(--radius-lg);
  margin-bottom: 20px;
  text-align: center;
}
.avatar-header__title {
  font-size: 18px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}
.avatar-header__sub {
  font-size: 13px;
  opacity: 0.9;
  margin-top: 4px;
}

.avatar-form { margin-bottom: 24px; }

.avatar-restrictions {
  padding: 16px;
  background: var(--bg-subtle);
  border-radius: var(--radius-md);
}
.avatar-restrictions__title {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 12px;
}
.avatar-restrictions__list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.avatar-restrictions__item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  font-size: 13px;
  color: var(--text-secondary);
}
.avatar-restrictions__icon {
  color: var(--danger);
  flex-shrink: 0;
}
</style>
