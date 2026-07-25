<script setup lang="ts">
// Full-screen loading view displayed during auth initialization.

import { useI18n } from 'vue-i18n'
import AivisLogo from '@/components/ui/AivisLogo.vue'

const { t } = useI18n()
</script>

<template>
  <div class="loading-view">
    <AivisLogo :height="64" />
    <div class="loading-spinner" />
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
  background: var(--bg);
  gap: var(--space-md, 16px);
}

.loading-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--border);
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin-top: 24px;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.loading-text {
  font-size: 14px;
  color: var(--text-tertiary);
  margin-top: 8px;
}
</style>
