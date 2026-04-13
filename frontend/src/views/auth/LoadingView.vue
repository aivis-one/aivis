<script setup lang="ts">
import CbsLogo from '@/components/ui/CbsLogo.vue'
</script>

<template>
  <div class="loading-page">
    <CbsLogo />
    <div class="loading-spinner" />
  </div>
</template>

<style scoped>
.loading-page {
  min-height: 100vh;
  min-height: 100dvh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-lg);
  background: var(--bg);
}

.loading-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--border);
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
