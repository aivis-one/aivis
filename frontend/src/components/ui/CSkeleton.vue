<script setup lang="ts">
withDefaults(
  defineProps<{
    variant?: 'card' | 'list' | 'text' | 'avatar'
    lines?: number
    width?: string
    height?: string
  }>(),
  {
    variant: 'text',
    lines: 3,
    width: '100%',
    height: '',
  },
)

const lineWidths = ['100%', '90%', '75%']
</script>

<template>
  <div class="c-skeleton" :style="{ width }" :class="`c-skeleton--${variant}`">
    <!-- Text variant -->
    <template v-if="variant === 'text'">
      <div
        v-for="i in lines"
        :key="i"
        class="c-skeleton__line c-skeleton__shimmer"
        :style="{ width: lineWidths[(i - 1) % lineWidths.length] }"
      />
    </template>

    <!-- Avatar variant -->
    <div
      v-else-if="variant === 'avatar'"
      class="c-skeleton__circle c-skeleton__shimmer"
      :style="{ width: height || '48px', height: height || '48px' }"
    />

    <!-- Card variant -->
    <template v-else-if="variant === 'card'">
      <div class="c-skeleton__line c-skeleton__line--header c-skeleton__shimmer" />
      <div class="c-skeleton__line c-skeleton__shimmer" style="width: 100%" />
      <div class="c-skeleton__line c-skeleton__shimmer" style="width: 90%" />
      <div class="c-skeleton__line c-skeleton__shimmer" style="width: 75%" />
    </template>

    <!-- List variant -->
    <template v-else-if="variant === 'list'">
      <div v-for="i in 3" :key="i" class="c-skeleton__row">
        <div class="c-skeleton__circle c-skeleton__circle--sm c-skeleton__shimmer" />
        <div class="c-skeleton__row-text">
          <div class="c-skeleton__line c-skeleton__shimmer" style="width: 60%" />
          <div
            class="c-skeleton__line c-skeleton__line--short c-skeleton__shimmer"
            style="width: 40%"
          />
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.c-skeleton {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.c-skeleton__shimmer {
  background: var(--bg-elevated);
  background-image: linear-gradient(
    90deg,
    var(--bg-elevated) 0%,
    var(--bg-subtle) 50%,
    var(--bg-elevated) 100%
  );
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
}

.c-skeleton__line {
  height: 14px;
  border-radius: var(--radius-sm);
}

.c-skeleton__line--header {
  height: 20px;
  width: 50%;
  margin-bottom: var(--space-xs);
}

.c-skeleton__line--short {
  height: 12px;
}

.c-skeleton__circle {
  border-radius: 50%;
  flex-shrink: 0;
}

.c-skeleton__circle--sm {
  width: 36px;
  height: 36px;
}

.c-skeleton__row {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}

.c-skeleton__row-text {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}

.c-skeleton--card {
  padding: var(--space-md);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
}

@keyframes shimmer {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}
</style>
