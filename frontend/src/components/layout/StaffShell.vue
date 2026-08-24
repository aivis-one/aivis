<script setup lang="ts">
// Staff shell — layout wrapper for all /staff/* routes.

import CHeader from '@/components/layout/CHeader.vue'
import CTabBar from '@/components/layout/CTabBar.vue'
import CSideNav from '@/components/layout/CSideNav.vue'
import CToast from '@/components/ui/CToast.vue'
import { STAFF_TABS } from '@/router/tabs'
</script>

<template>
  <div class="shell shell--tabbed">
    <CHeader />
    <div class="shell__body">
      <CSideNav :items="STAFF_TABS" />
      <main class="shell__content">
        <div class="shell__measure">
          <RouterView />
        </div>
      </main>
    </div>
    <CTabBar :items="STAFF_TABS" />
    <CToast />
  </div>
</template>

<style scoped>
/* The ONLY shell rule that is not shared: staff screens cap content at
   --maxw-wide (1240px) where the other four cap at --maxw (1080px).
   ⚠ WHETHER THAT ASYMMETRY IS DELIBERATE IS `B-3.3` AND IT IS THE OWNER'S
   CALL. It is left here, in one place and visible, precisely so that his
   ruling is a one-line change. Everything else lives in styles/shell.css. */
.shell__measure {
  max-width: var(--maxw-wide);
}
</style>
