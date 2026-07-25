<script setup lang="ts">
// App header — sticky top bar from mockups/css/components.css .app-header.
// Shows logo + title on the left, optional back button, right slot.
//
// F4.1.4 polish: left section now truncates long titles with
// ellipsis instead of bleeding into the right slot. Defensive CSS --
// any title passed from any view stays inside the header strip.

import { useRouter } from 'vue-router'
import { ChevronLeft } from 'lucide-vue-next'
import AivisLogo from '@/components/ui/AivisLogo.vue'
import { safeNavigate } from '@/composables/safeNavigate'

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
    void safeNavigate(router.push('/'), '[CHeader] to home')
  }
}
</script>

<template>
  <header class="c-header">
    <div class="c-header__left">
      <button v-if="showBack" class="c-header__back" @click="goBack">
        <ChevronLeft :size="24" />
      </button>
      <AivisLogo v-if="showLogo && !showBack" :height="28" :show-text="false" />
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
  gap: 8px;
}
.c-header__left {
  display: flex; align-items: center; gap: 10px;
  /* Claim the remaining width and allow the title child to shrink
     below its intrinsic content size (needed for ellipsis). */
  flex: 1;
  min-width: 0;
  overflow: hidden;
}
.c-header__title {
  font-size: 16px; font-weight: 700; color: var(--primary-dark);
  /* Truncate long titles with ellipsis rather than push the right
     slot off the edge. */
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.c-header__back {
  background: none; border: none; cursor: pointer; color: var(--text);
  padding: 4px; display: flex; align-items: center; margin-left: -4px;
  flex-shrink: 0;
}
.c-header__right {
  display: flex; align-items: center; gap: 8px;
  /* Right slot must never shrink -- if someone adds action buttons
     they should stay full size; the title absorbs the space loss. */
  flex-shrink: 0;
}
</style>
