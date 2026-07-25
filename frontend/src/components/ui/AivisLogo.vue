<script setup lang="ts">
// AIVIS.ONE logo — SVG icon + text, configurable height.

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
    <svg
      class="aivis-logo-icon"
      viewBox="0 0 100 100"
      xmlns="http://www.w3.org/2000/svg"
      :style="{ width: height + 'px', height: height + 'px' }"
    >
      <rect width="100" height="100" rx="16" fill="var(--accent)" />
      <text
        x="50"
        y="72"
        font-size="60"
        font-weight="800"
        font-family="Montserrat, Arial, sans-serif"
        fill="white"
        text-anchor="middle"
      >
        C
      </text>
    </svg>
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
  color: var(--primary-dark);
  letter-spacing: 0.5px;
}
</style>
