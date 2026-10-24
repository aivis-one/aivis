<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- StaffNewsView (iter 2.7 Block B)
// =============================================================================
//
// Platform-wide post management. Thin wrapper over the shared
// PostListEditor with no fixedOwner -- the list shows every post
// (platform + company) and the editor exposes the owner picker so
// staff can author either kind.
//
// The content_manage gate is resolved here once via useStaffPermissions
// and handed to the editor as `canEdit` (FP-23). A staffer without the
// permission still sees the read-only list.
// =============================================================================

import { useI18n } from 'vue-i18n'
import { useStaffPermissions } from '@/composables/useStaffPermissions'
import PostListEditor from '@/components/staff/PostListEditor.vue'
import { useScreenHeader } from '@/components/layout/screenHeader'

const { t } = useI18n()
const { canDo } = useStaffPermissions()
const canManageContent = canDo('content_manage')

// The frame's header carries the section's title.
useScreenHeader({ title: () => t('staff.platform.news.title') })
</script>

<template>
  <PostListEditor :can-edit="canManageContent" />
</template>
