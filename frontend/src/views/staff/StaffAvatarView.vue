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
        <Ghost :size="16" /> {{ t('staff.avatar.start') }}
      </CButton>
    </div>

    <!-- Restrictions -->
    <div class="avatar-restrictions">
      <div class="avatar-restrictions__title">
        <Ban :size="16" /> {{ t('staff.avatar.restrictions') }}
      </div>
      <ul class="avatar-restrictions__list">
        <li v-for="key in restrictions" :key="key" class="avatar-restrictions__item">
          <Ban :size="16" class="avatar-restrictions__icon" />
          {{ t(key) }}
        </li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.staff-avatar { padding: var(--space-4); }

.avatar-header {
  padding: var(--space-4-lg);
  background: var(--accent);
  color: var(--on-accent);
  border-radius: var(--radius-lg);
  margin-bottom: var(--space-4-lg);
  text-align: center;
}
.avatar-header__title {
  font-size: var(--fs-h4);
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
}
.avatar-header__sub {
  font-size: var(--fs-xs-lg);
  opacity: 0.9;
  margin-top: var(--space-1);
}

.avatar-form { margin-bottom: var(--space-5); }

.avatar-restrictions {
  padding: var(--space-4);
  background: var(--bg-subtle);
  border-radius: var(--radius-md);
}
.avatar-restrictions__title {
  font-size: var(--fs-xs-lg);
  font-weight: 700;
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-3);
}
.avatar-restrictions__list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.avatar-restrictions__item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) 0;
  font-size: var(--fs-xs-lg);
  color: var(--text-secondary);
}
.avatar-restrictions__icon {
  color: var(--danger);
  flex-shrink: 0;
}

/* READING MEASURE — descriptive text only. --maxw-prose (680px) is a CEILING,
   so this rule cannot bind until the container is already wider than a
   comfortable line: on a phone it does nothing at all, which is why it needs
   no media query. Measured at 1280 before applying: `event-card__desc` ran to
   932px and `staff-dash__role-count` to 901. Names, figures and table cells
   are deliberately NOT capped — a name is not prose, and capping it would only
   leave dead space in its row. */
.avatar-header__sub { max-width: var(--maxw-prose); }
</style>
