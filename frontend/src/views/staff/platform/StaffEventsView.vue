<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- StaffEventsView (iter 2.7 Block B)
// =============================================================================
//
// Platform event management. Thin wrapper over the shared EventEditor.
// content_manage gate resolved here and passed as `canEdit` (FP-23);
// a staffer without the permission still sees the read-only list with
// its upcoming/past filter.
// =============================================================================

import { useI18n } from 'vue-i18n'
import { useStaffPermissions } from '@/composables/useStaffPermissions'
import EventEditor from '@/components/staff/EventEditor.vue'

const { t } = useI18n()
const { canDo } = useStaffPermissions()
const canManageContent = canDo('content_manage')
</script>

<template>
  <div class="staff-events">
    <h2 class="staff-events__title">{{ t('staff.platform.events.title') }}</h2>
    <EventEditor :can-edit="canManageContent" />
  </div>
</template>

<style scoped>
.staff-events { padding: var(--space-4); }
.staff-events__title {
  font-size: var(--fs-h4); font-weight: 700; color: var(--text-primary); margin: 0 0 var(--space-3);
}
</style>
