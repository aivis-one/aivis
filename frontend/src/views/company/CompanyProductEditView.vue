<script setup lang="ts">
// Stub — will be replaced with full implementation in F5.2.
// Product detail (readonly, editing via Staff).

import { useI18n } from 'vue-i18n'

const { t } = useI18n()
</script>

<template>
  <div class="view-stub">
    <h1 class="view-stub__title">
      {{ t('nav.comp.product_edit') }}
    </h1>
    <div class="view-stub__badge">F5.2</div>
  </div>
</template>

<style scoped>
.view-stub {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: calc(100vh - 120px);
  min-height: calc(100dvh - 120px);
  padding: var(--space-5);
  text-align: center;
}

.view-stub__title {
  font-size: var(--fs-lg);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 var(--space-4);
}

.view-stub__badge {
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-sm);
  background: var(--bg-secondary);
  color: var(--text-tertiary);
  font-size: var(--fs-xs);
  font-weight: 600;
  letter-spacing: 0.05em;
}
</style>
