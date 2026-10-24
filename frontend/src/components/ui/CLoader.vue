<script setup lang="ts">
// Spinner loader, on the design system's Loader (K20). The system has two
// sizes: a size of 24 or less is its small one, anything larger its default.
//
// `centered` is K20's centred loader for a section or a page that waits: a block
// with the ring and its status text under it, visible. `extent="page"` gives it a
// page's height; a section wait leaves `extent` unset. The bare form (a spinner
// beside a button or in a line) is unchanged and ignores `extent`.

import { useI18n } from 'vue-i18n'

withDefaults(
  defineProps<{
    size?: number
    centered?: boolean
    extent?: 'page'
    /** The centred form's visible text, saying what loads (K20); common.loading when unset. */
    text?: string
  }>(),
  { size: 32 },
)

const { t } = useI18n()
</script>

<template>
  <div
    v-if="centered"
    class="ds-loader ds-loader--centered"
    role="status"
    :data-extent="extent === 'page' ? 'page' : undefined"
  >
    <span class="ds-loader__ring" aria-hidden="true" />
    <span>{{ text ?? t('common.loading') }}</span>
  </div>
  <span v-else class="ds-loader" role="status" :data-size="size <= 24 ? 'sm' : undefined">
    <span class="ds-loader__ring" aria-hidden="true" />
    <span class="ds-sr-only">{{ t('common.loading') }}</span>
  </span>
</template>
