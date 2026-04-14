<script setup lang="ts">
// Agent shell — layout wrapper for all /agent/* routes.
// Agent has access to all investor screens too (via routing).

import CHeader from '@/components/layout/CHeader.vue'
import CTabBar from '@/components/layout/CTabBar.vue'
import CToast from '@/components/ui/CToast.vue'
import { AGENT_TABS } from '@/router/tabs'
</script>

<template>
  <div class="shell">
    <CHeader />
    <main class="shell__content">
      <RouterView />
    </main>
    <CTabBar :items="AGENT_TABS" />
    <CToast />
  </div>
</template>

<style scoped>
.shell { display: flex; flex-direction: column; min-height: 100vh; min-height: 100dvh; background: var(--bg); }
.shell__content { flex: 1; overflow-y: auto; }
</style>
