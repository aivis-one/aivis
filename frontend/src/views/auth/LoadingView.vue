<script setup lang="ts">
// Full-screen loading view displayed during auth initialization.

import { useI18n } from 'vue-i18n'
import AivisLogo from '@/components/ui/AivisLogo.vue'
import CLoader from '@/components/ui/CLoader.vue'

const { t } = useI18n()
</script>

<template>
  <div class="loading-view">
    <AivisLogo :height="64" />
    <CLoader class="loading-spinner" />
    <p class="loading-text">{{ t('common.loading') }}</p>
  </div>
</template>

<style scoped>
.loading-view {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  min-height: 100dvh;
  background: var(--bg-page);
  gap: var(--space-4);
}

.loading-spinner {
  margin-top: var(--space-5);
}

.loading-text {
  font-size: var(--fs-sm);
  color: var(--text-tertiary);
  margin-top: var(--space-2);
}
</style>
