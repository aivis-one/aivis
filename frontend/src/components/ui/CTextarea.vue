<script setup lang="ts">
import { useId } from 'vue'
// Multi-line text input with label and error state.

withDefaults(
  defineProps<{
    modelValue?: string
    label?: string
    placeholder?: string
    error?: string
    rows?: number
  }>(),
  { modelValue: '', rows: 4 },
)

const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

function onInput(e: Event): void {
  emit('update:modelValue', (e.target as HTMLTextAreaElement).value)
}

// A4: a visible label is not an accessible name unless it is ASSOCIATED. This
// carried <label> with no `for` and the control with no `id`, so a screen
// reader saw an unlabelled field beside some loose text. useId() (Vue 3.5)
// pairs them and stays unique across every instance on the page.
const fieldId = useId()
</script>

<template>
  <div class="c-input-group">
    <label v-if="label" :for="fieldId" class="c-input-label">{{ label }}</label>
    <textarea
      :id="fieldId"
      class="c-textarea"
      :class="{ 'c-textarea--error': !!error }"
      :value="modelValue"
      :placeholder="placeholder"
      :rows="rows"
      @input="onInput"
    />
    <div v-if="error" class="c-input-error">{{ error }}</div>
  </div>
</template>

<style scoped>
.c-input-group { margin-bottom: var(--space-4); }
.c-input-label { display: block; font-size: var(--fs-xs-lg); font-weight: 600; color: var(--text-primary); margin-bottom: var(--space-2); }

.c-textarea {
  width: 100%; padding: var(--space-4) var(--space-4); border: 2px solid var(--border-default);
  border-radius: var(--radius-md); font-size: var(--fs-sm); font-family: inherit;
  background: var(--bg-page); color: var(--text-primary); resize: vertical;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.c-textarea:focus { outline: none; border-color: var(--primary); box-shadow: var(--shadow-focus); }
.c-textarea::placeholder { color: var(--text-tertiary); }
.c-textarea--error { border-color: var(--danger); }
.c-input-error { font-size: var(--fs-xs); color: var(--danger); margin-top: var(--space-1); }
</style>
