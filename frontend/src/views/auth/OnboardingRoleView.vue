<script setup lang="ts">
// Stub — will be replaced with full implementation in F2.3.

import { useI18n } from 'vue-i18n'

const { t } = useI18n()
</script>

<template>
  <div class="onboarding-stub">
    <h1 class="onboarding-stub__title">{{ t('auth.role.title') }}</h1>
    <p class="onboarding-stub__subtitle">{{ t('auth.role.subtitle') }}</p>
    <div class="onboarding-stub__placeholder">F2.3</div>
  </div>
</template>

<style scoped>
.onboarding-stub {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  min-height: 100dvh;
  background: var(--bg);
  padding: 24px;
  text-align: center;
}

.onboarding-stub__title {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 8px;
}

.onboarding-stub__subtitle {
  font-size: 14px;
  color: var(--text-secondary);
  margin: 0 0 32px;
  max-width: 320px;
}

.onboarding-stub__placeholder {
  padding: 8px 16px;
  border-radius: var(--radius-sm, 6px);
  background: var(--bg-secondary, var(--surface));
  color: var(--text-tertiary);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.05em;
}
</style>
