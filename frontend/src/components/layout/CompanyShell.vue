<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import CHeader from './CHeader.vue'
import CTabBar from './CTabBar.vue'
import { companyTabs } from '@/router/tabs'

const { t } = useI18n()
</script>

<template>
  <div class="shell">
    <CHeader :title="t('app.name')" />
    <main class="shell__content">
      <router-view />
    </main>
    <CTabBar :tabs="companyTabs" />
  </div>
</template>

<style scoped>
.shell {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  min-height: 100dvh;
  background: var(--bg);
}

.shell__content {
  flex: 1;
  overflow-y: auto;
}
</style>
