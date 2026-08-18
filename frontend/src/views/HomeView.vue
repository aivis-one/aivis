<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
</script>

<template>
  <div class="home">
    <div class="home-logo">
      <img src="/aivis-mark.svg" alt="AIVIS" />
    </div>
    <h1 class="home-title">{{ t('app.name') }}</h1>
    <p class="home-version">v0.1.0</p>
  </div>
</template>

<style scoped>
.home {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  min-height: 100dvh;
  background: var(--bg-page);
  gap: var(--space-4);
}

.home-logo img {
  width: 80px;
  height: 80px;
}

.home-title {
  font-size: 28px;
  font-weight: 800;
  color: var(--text-primary);
  letter-spacing: -0.5px;
}

.home-version {
  font-size: 14px;
  color: var(--text-tertiary);
}
</style>
