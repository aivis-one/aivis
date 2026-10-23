<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const baseUrl = import.meta.env.BASE_URL
</script>

<template>
  <div class="home">
    <div class="home-logo">
      <img :src="`${baseUrl}aivis-mark.svg`" alt="AIVIS" />
    </div>
    <h1 class="home-title">
      {{ t('app.name') }}
    </h1>
    <p class="home-version">v0.1.0</p>
  </div>
</template>

<style scoped>
.home {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-block-size: 100vh;
  min-block-size: 100dvh;
  background: var(--bg-page);
  gap: var(--space-4);
}

.home-logo img {
  inline-size: 80px;
  block-size: 80px;
}

.home-title {
  font-size: var(--fs-2xl);
  font-weight: 800;
  color: var(--text-primary);
  letter-spacing: var(--tracking-tight);
}

.home-version {
  font-size: var(--fs-sm);
  color: var(--text-tertiary);
}
</style>
