<script setup lang="ts">
// Company shell — layout wrapper for all /company/* routes.

import CHeader from '@/components/layout/CHeader.vue'
import CTabBar from '@/components/layout/CTabBar.vue'
import CSideNav from '@/components/layout/CSideNav.vue'
import CToast from '@/components/ui/CToast.vue'
import { COMPANY_TABS } from '@/router/tabs'
</script>

<template>
  <div class="shell shell--tabbed">
    <CHeader />
    <div class="shell__body">
      <CSideNav :items="COMPANY_TABS" />
      <main class="shell__content">
        <div class="shell__measure">
          <RouterView />
        </div>
      </main>
    </div>
    <CTabBar :items="COMPANY_TABS" />
    <CToast />
  </div>
</template>
