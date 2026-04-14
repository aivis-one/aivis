<script setup lang="ts">
// App header — sticky top bar from mockups/css/components.css .app-header.
// Shows logo + title on the left, optional back button, right slot.

import { useRouter } from 'vue-router'
import { ChevronLeft } from 'lucide-vue-next'
import CbsLogo from '@/components/ui/CbsLogo.vue'

withDefaults(
  defineProps<{
    title?: string
    showBack?: boolean
    showLogo?: boolean
  }>(),
  { showBack: false, showLogo: true },
)

const router = useRouter()

function goBack(): void {
  if (window.history.length > 1) {
    router.back()
  } else {
    router.push('/')
  }
}
</script>

<template>
  <header class="c-header">
    <div class="c-header__left">
      <button v-if="showBack" class="c-header__back" @click="goBack">
        <ChevronLeft :size="24" />
      </button>
      <CbsLogo v-if="showLogo && !showBack" :height="28" :show-text="false" />
      <span v-if="title" class="c-header__title">{{ title }}</span>
    </div>
    <div class="c-header__right">
      <slot name="right" />
    </div>
  </header>
</template>

<style scoped>
.c-header {
  position: sticky; top: 0; z-index: 100; background: var(--bg);
  padding: 12px 16px; border-bottom: 1px solid var(--border);
  display: flex; align-items: center; justify-content: space-between;
}
.c-header__left { display: flex; align-items: center; gap: 10px; }
.c-header__title { font-size: 16px; font-weight: 700; color: var(--primary-dark); }
.c-header__back {
  background: none; border: none; cursor: pointer; color: var(--text);
  padding: 4px; display: flex; align-items: center; margin-left: -4px;
}
.c-header__right { display: flex; align-items: center; gap: 8px; }
</style>
