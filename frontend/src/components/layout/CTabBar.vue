<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useRouter, useRoute } from 'vue-router'
import type { TabConfig } from '@/router/tabs'

defineProps<{
  tabs: TabConfig[]
}>()

const { t } = useI18n()
const router = useRouter()
const route = useRoute()

function isActive(tab: TabConfig): boolean {
  return route.path.startsWith(tab.route)
}

function navigate(tab: TabConfig): void {
  router.push(tab.route)
}
</script>

<template>
  <nav class="c-tabbar">
    <button
      v-for="tab in tabs"
      :key="tab.key"
      :class="['c-tabbar__item', { 'c-tabbar__item--active': isActive(tab) }]"
      @click="navigate(tab)"
    >
      <span class="c-tabbar__icon">{{ tab.icon.charAt(0).toUpperCase() }}</span>
      <span class="c-tabbar__label">{{ t(tab.labelKey) }}</span>
    </button>
  </nav>
</template>

<style scoped>
.c-tabbar {
  position: sticky;
  bottom: 0;
  z-index: 50;
  display: flex;
  align-items: center;
  justify-content: space-around;
  height: 56px;
  background: var(--bg-elevated);
  border-top: 1px solid var(--border);
  padding-bottom: env(safe-area-inset-bottom);
}

.c-tabbar__item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  flex: 1;
  padding: var(--space-xs) 0;
  background: none;
  border: none;
  color: var(--text-tertiary);
  cursor: pointer;
  transition: color 0.2s;
}

.c-tabbar__item--active {
  color: var(--primary);
}

.c-tabbar__icon {
  font-size: var(--text-xl);
  font-weight: 700;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.c-tabbar__label {
  font-size: var(--text-xs);
  font-weight: 500;
}
</style>
