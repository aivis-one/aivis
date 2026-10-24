<script setup lang="ts">
// Staff avatar mode — start session form + restrictions info.
// On start: composable handles token swap + redirect to target user dashboard.
// Session management (banner, end) handled by App.vue + useAvatar composable.
//
// TASK-30 admin-capability gap: this used to be a bare "enter user ID"
// CInput with no way to discover a target's UUID through the product.
// UserPicker (search by email/name, built for W0's assign flow) is
// reused here -- the same missing primitive, solved once.

import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Ghost, Ban } from '@/components/ui/icons'
import { CButton } from '@/components/ui'
import UserPicker from '@/components/staff/UserPicker.vue'
import { useScreenHeader } from '@/components/layout/screenHeader'
import { useAvatar } from '@/composables/useAvatar'

const { t } = useI18n()
const { loading, startAvatarSession } = useAvatar()

// The frame's header carries the title and the line under it.
useScreenHeader({
  title: () => t('staff.avatar.title'),
  lead: () => t('staff.avatar.subtitle'),
})

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
    <!-- Start form -->
    <div class="staff-avatar__form">
      <UserPicker v-model="targetUserId" :label="t('staff.avatar.enterUserId')" />
      <CButton
        variant="primary"
        size="sm"
        inline
        :loading="loading"
        :disabled="!targetUserId.trim()"
        @click="handleStart"
      >
        <Ghost size="sm" /> {{ t('staff.avatar.start') }}
      </CButton>
    </div>

    <!-- Restrictions (K07 flat card holding K23 rows) -->
    <section class="ds-card ds-card--flat">
      <h2 class="ds-card__title">{{ t('staff.avatar.restrictions') }}</h2>
      <ul class="ds-rows">
        <li v-for="key in restrictions" :key="key" class="ds-row">
          <span class="ds-row__lead" data-tone="danger"><Ban size="sm" /></span>
          <span class="ds-row__body">
            <span class="ds-row__title">{{ t(key) }}</span>
          </span>
        </li>
      </ul>
    </section>
  </div>
</template>

<style scoped>
.staff-avatar {
  display: grid;
  gap: var(--space-5);
}

.staff-avatar__form {
  display: grid;
  justify-items: start;
  gap: var(--space-3);
}
</style>
