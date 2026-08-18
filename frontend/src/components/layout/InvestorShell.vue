<script setup lang="ts">
// Investor shell — layout wrapper for all /investor/* routes.
// CHeader + content area + CTabBar(INVESTOR_TABS).

import CHeader from '@/components/layout/CHeader.vue'
import CTabBar from '@/components/layout/CTabBar.vue'
import CToast from '@/components/ui/CToast.vue'
import { INVESTOR_TABS } from '@/router/tabs'
</script>

<template>
  <div class="shell">
    <CHeader />
    <main class="shell__content">
      <RouterView />
    </main>
    <CTabBar :items="INVESTOR_TABS" />
    <CToast />
  </div>
</template>

<style scoped>
.shell {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  min-height: 100dvh;
  background: var(--bg-page);
}
.shell__content {
  flex: 1;
  overflow-y: auto;
}
</style>
