<script setup lang="ts">
// CBS HOME logo — SVG icon + text, configurable height.

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
  <span class="cbs-logo">
    <svg
      class="cbs-logo-icon"
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
    <span v-if="showText" class="cbs-logo-text">CBS HOME</span>
  </span>
</template>

<style scoped>
.cbs-logo {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  text-decoration: none;
}

.cbs-logo-icon {
  flex-shrink: 0;
}

.cbs-logo-text {
  font-size: 16px;
  font-weight: 700;
  color: var(--primary-dark);
  letter-spacing: 0.5px;
}
</style>
