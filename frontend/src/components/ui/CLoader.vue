<script setup lang="ts">
// Spinner loader, on the design system's Loader (K20). The system has two
// sizes: a size of 24 or less is its small one, anything larger its default.

import { useI18n } from 'vue-i18n'

withDefaults(defineProps<{ size?: number }>(), { size: 32 })

const { t } = useI18n()
</script>

<template>
  <span class="ds-loader" role="status" :data-size="size <= 24 ? 'sm' : undefined">
    <span class="ds-loader__ring" aria-hidden="true" />
    <span class="ds-sr-only">{{ t('common.loading') }}</span>
  </span>
</template>
