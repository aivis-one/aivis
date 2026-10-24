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
import { useScreenHeader } from '@/components/layout/screenHeader'

const { t } = useI18n()
const { canDo } = useStaffPermissions()
const canManageContent = canDo('content_manage')

// The frame's header carries the section's title.
useScreenHeader({ title: () => t('staff.platform.events.title') })
</script>

<template>
  <EventEditor :can-edit="canManageContent" />
</template>
