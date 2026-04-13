<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
</script>

<template>
  <div class="home">
    <div class="home-logo">
      <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
        <rect width="100" height="100" rx="16" fill="var(--o-primary)" />
        <text
          x="50"
          y="72"
          font-size="60"
          font-weight="800"
          font-family="Arial"
          fill="white"
          text-anchor="middle"
        >
          C
        </text>
      </svg>
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
  background: var(--bg);
  gap: var(--space-md);
}

.home-logo svg {
  width: 80px;
  height: 80px;
}

.home-title {
  font-size: 28px;
  font-weight: 800;
  color: var(--text);
  letter-spacing: -0.5px;
}

.home-version {
  font-size: 14px;
  color: var(--text-tertiary);
}
</style>
