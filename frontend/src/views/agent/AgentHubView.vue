<script setup lang="ts">
// Stub — will be replaced with full implementation in F6.1.
// Agent hub — referral links, stats, earnings overview.

import { useI18n } from 'vue-i18n'

const { t } = useI18n()
</script>

<template>
  <div class="view-stub">
    <h1 class="view-stub__title">{{ t('agent.hub.title') }}</h1>
    <div class="view-stub__badge">F6.1</div>
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
  padding: 24px;
  text-align: center;
}

.view-stub__title {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 16px;
}

.view-stub__badge {
  padding: 6px 14px;
  border-radius: var(--radius-sm, 6px);
  background: var(--bg-secondary, var(--surface));
  color: var(--text-tertiary);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.05em;
}
</style>
