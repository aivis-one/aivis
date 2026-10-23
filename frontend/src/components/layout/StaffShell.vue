<script setup lang="ts">
// Staff shell — layout wrapper for all /staff/* routes.

import { computed } from 'vue'
import CHeader from '@/components/layout/CHeader.vue'
import CTabBar from '@/components/layout/CTabBar.vue'
import CSideNav from '@/components/layout/CSideNav.vue'
import CToast from '@/components/ui/CToast.vue'
import { STAFF_TABS } from '@/router/tabs'
import { useStaffRights } from '@/composables/useStaffRights'
import { tabAllowed } from '@/utils/staffRights'

// The tabs the member may use: a tab that opens a hub is drawn only when the
// member has the right to at least one of the hub's sections.
const { current } = useStaffRights()
const tabs = computed(() => {
  const rights = current()
  return STAFF_TABS.filter((tab) => tabAllowed(tab.id, rights))
})
</script>

<template>
  <div class="shell shell--tabbed">
    <CHeader />
    <div class="shell__body">
      <CSideNav :items="tabs" />
      <main class="shell__content">
        <div class="shell__measure">
          <RouterView />
        </div>
      </main>
    </div>
    <CTabBar :items="tabs" />
    <CToast />
  </div>
</template>

<style scoped>
/* The ONLY shell rule that is not shared: staff screens cap content at
   --maxw-wide where the other four cap at --maxw. Staff screens are tables and
   lists, the other four roles are mostly text and cards, and the right width for
   those two things is not the same number. checks/shell_layout.py asserts this
   override still exists, so a refactor cannot fold it into one value silently. */
.shell__measure {
  max-inline-size: var(--maxw-wide);
}
</style>
