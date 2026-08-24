<script setup lang="ts">
// Investor shell — layout wrapper for all /investor/* routes.
// CHeader + content area + CTabBar(INVESTOR_TABS).

import CHeader from '@/components/layout/CHeader.vue'
import CTabBar from '@/components/layout/CTabBar.vue'
import CSideNav from '@/components/layout/CSideNav.vue'
import CToast from '@/components/ui/CToast.vue'
import { INVESTOR_TABS } from '@/router/tabs'
</script>

<template>
  <div class="shell shell--tabbed">
    <CHeader />
    <div class="shell__body">
      <CSideNav :items="INVESTOR_TABS" />
      <main class="shell__content">
        <div class="shell__measure">
          <RouterView />
        </div>
      </main>
    </div>
    <CTabBar :items="INVESTOR_TABS" />
    <CToast />
  </div>
</template>
