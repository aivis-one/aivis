<script setup lang="ts">
// Spinner loader with configurable size.

withDefaults(defineProps<{ size?: number }>(), { size: 32 })
</script>

<template>
  <div class="c-loader" :style="{ width: size + 'px', height: size + 'px' }" />
</template>

<style scoped>
.c-loader {
  border: 3px solid var(--border-default);
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: c-spin 0.8s linear infinite;
}
@keyframes c-spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
