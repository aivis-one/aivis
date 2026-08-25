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

const { t } = useI18n()
const { canDo } = useStaffPermissions()
const canManageContent = canDo('content_manage')
</script>

<template>
  <div class="staff-news">
    <h2 class="staff-news__title">
      {{ t('staff.platform.news.title') }}
    </h2>
    <PostListEditor :can-edit="canManageContent" />
  </div>
</template>

<style scoped>
.staff-news {
  padding: var(--space-4);
}
.staff-news__title {
  font-size: var(--fs-h4);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 var(--space-3);
}
</style>
