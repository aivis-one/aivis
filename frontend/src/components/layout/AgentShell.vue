<script setup lang="ts">
// Agent shell — layout wrapper for all /agent/* routes.
// Agent has access to all investor screens too (via routing).

import CHeader from '@/components/layout/CHeader.vue'
import CTabBar from '@/components/layout/CTabBar.vue'
import CSideNav from '@/components/layout/CSideNav.vue'
import CToast from '@/components/ui/CToast.vue'
import { AGENT_TABS } from '@/router/tabs'
</script>

<template>
  <div class="shell shell--tabbed">
    <CHeader />
    <div class="shell__body">
      <CSideNav :items="AGENT_TABS" />
      <main class="shell__content">
        <div class="shell__measure">
          <RouterView />
        </div>
      </main>
    </div>
    <CTabBar :items="AGENT_TABS" />
    <CToast />
  </div>
</template>
