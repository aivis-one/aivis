<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
</script>

<template>
  <div class="dashboard">
    <h1>{{ t('nav.home') }}</h1>
    <p class="dashboard__hint">Company Dashboard — S5</p>
  </div>
</template>

<style scoped>
.dashboard {
  padding: var(--space-md);
}

.dashboard h1 {
  font-size: var(--text-2xl);
  font-weight: 700;
  color: var(--text);
  margin-bottom: var(--space-xs);
}

.dashboard__hint {
  font-size: var(--text-caption);
  color: var(--text-tertiary);
}
</style>
