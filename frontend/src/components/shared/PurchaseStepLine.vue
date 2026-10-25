<script setup lang="ts">
// The step line of the buying path (K32): the dots and the position in words,
// "Step 2 of 3 · Confirmation". The dots are decoration over the words; the list
// carries the position as its name.
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps<{ step: 1 | 2 | 3 }>()

const { t } = useI18n()

const STEP_KEYS = { 1: 'terms', 2: 'confirm', 3: 'done' } as const

const label = computed(() =>
  t('buy.step', { n: props.step, name: t(`buy.steps.${STEP_KEYS[props.step]}`) }),
)
</script>

<template>
  <div class="ds-stepline">
    <ol class="ds-dots" :aria-label="t('buy.stepAria', { n: step })">
      <li
        v-for="n in 3"
        :key="n"
        class="ds-dots__dot"
        :aria-current="n === step ? 'step' : undefined"
      />
    </ol>
    <p class="ds-dots__text">{{ label }}</p>
  </div>
</template>
