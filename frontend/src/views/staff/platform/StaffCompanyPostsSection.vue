<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- StaffCompanyPostsSection (iter 2.7 Block C)
// =============================================================================
//
// Company-scoped post management. Thin wrapper over the shared
// PostListEditor with fixedOwner={type:'company', id:companyId}: the
// list is scoped to this company and the editor hides the owner picker,
// always authoring company posts for this id.
//
// companyId comes from the parent route params (the detail view renders
// this section inside its <router-view>). content_manage gate is
// resolved here and passed as canEdit (FP-23) -- identical contract to
// StaffNewsView, just with the owner fixed.
// =============================================================================

import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useStaffPermissions } from '@/composables/useStaffPermissions'
import PostListEditor from '@/components/staff/PostListEditor.vue'

const route = useRoute()
const { canDo } = useStaffPermissions()
const canManageContent = canDo('content_manage')

const companyId = computed<string>(() => {
  const raw = route.params.id
  return typeof raw === 'string' ? raw : ''
})

// fixedOwner forces company ownership + hides the picker in the editor.
const fixedOwner = computed<{ type: 'company'; id: string }>(() => ({
  type: 'company',
  id: companyId.value,
}))
</script>

<template>
  <div class="scps">
    <PostListEditor
      :fixed-owner="fixedOwner"
      :can-edit="canManageContent"
    />
  </div>
</template>

<style scoped>
.scps { padding: var(--space-4); }
</style>
