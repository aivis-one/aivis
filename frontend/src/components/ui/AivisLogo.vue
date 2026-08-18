<script setup lang="ts">
// AIVIS.ONE logo — the real brand mark + text, configurable height.
//
// The mark is /aivis-mark.svg (public/), not an inline SVG: it carries 12
// gradients whose ids would leak into the host document and can collide with
// another inline SVG's ids. As a file its ids are scoped to itself.
//
// It replaced a rounded rect with the letter "C" — the OLD brand's initial,
// still on screen four weeks after the cbshome -> aivis rename (batch 6a).

withDefaults(
  defineProps<{
    height?: number
    showText?: boolean
  }>(),
  {
    height: 28,
    showText: true,
  },
)
</script>

<template>
  <span class="aivis-logo">
    <img
      class="aivis-logo-icon"
      src="/aivis-mark.svg"
      alt="AIVIS"
      :style="{ width: height + 'px', height: height + 'px' }"
    />
    <span v-if="showText" class="aivis-logo-text">AIVIS.ONE</span>
  </span>
</template>

<style scoped>
.aivis-logo {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  text-decoration: none;
}

.aivis-logo-icon {
  flex-shrink: 0;
}

.aivis-logo-text {
  font-size: 16px;
  font-weight: 700;
  color: var(--primary-active);
  letter-spacing: 0.5px;
}
</style>
