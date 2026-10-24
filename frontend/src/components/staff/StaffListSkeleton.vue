<script setup lang="ts">
// The wait for a staff list, on the design system's Skeleton (K19): rows of the
// shape of the real rows (a disc, two lines), hidden from assistive technology,
// with one status text for it. The region that will hold the list is busy while
// these stand. A short wait elsewhere on the screen keeps the Loader (K20).

import { useI18n } from 'vue-i18n'

withDefaults(defineProps<{ rows?: number }>(), { rows: 5 })

const { t } = useI18n()
</script>

<template>
  <div class="ds-skeleton-stack" aria-busy="true">
    <span class="ds-sr-only" role="status">{{ t('common.loading') }}</span>
    <div v-for="n in rows" :key="n" class="ds-skeleton-row" aria-hidden="true">
      <span class="ds-skeleton ds-skeleton--avatar" />
      <span class="ds-skeleton-stack">
        <span class="ds-skeleton ds-skeleton--title" />
        <span class="ds-skeleton ds-skeleton--text" />
      </span>
    </div>
  </div>
</template>
