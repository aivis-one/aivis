<script setup lang="ts">
// Avatar — shows photo if url provided, otherwise initials from name.

import { computed } from 'vue'

const props = withDefaults(
  defineProps<{ name?: string; url?: string; size?: number }>(),
  { size: 40 },
)

const initials = computed(() => {
  if (!props.name) return '?'
  return props.name
    .split(' ')
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? '')
    .join('')
})
</script>

<template>
  <img v-if="url" class="c-avatar" :src="url" :alt="name ?? ''" :style="{ width: size + 'px', height: size + 'px' }" />
  <div v-else class="c-avatar c-avatar--initials" :style="{ width: size + 'px', height: size + 'px', fontSize: size * 0.4 + 'px' }">
    {{ initials }}
  </div>
</template>

<style scoped>
.c-avatar {
  border-radius: 50%; object-fit: cover; flex-shrink: 0;
  border: 2px solid var(--primary-hover);
}
.c-avatar--initials {
  background: var(--primary); color: var(--on-primary);
  display: flex; align-items: center; justify-content: center;
  font-weight: 700; border: none;
}
</style>
