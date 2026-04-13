<script setup lang="ts">
defineProps<{
  modelValue?: string
  type?: string
  placeholder?: string
  label?: string
  error?: string
  disabled?: boolean
}>()

defineEmits<{
  'update:modelValue': [value: string]
}>()
</script>

<template>
  <div class="c-input" :class="{ 'c-input--error': error, 'c-input--disabled': disabled }">
    <label v-if="label" class="c-input__label">{{ label }}</label>
    <input
      :type="type ?? 'text'"
      :value="modelValue"
      :placeholder="placeholder"
      :disabled="disabled"
      class="c-input__field"
      @input="$emit('update:modelValue', ($event.target as HTMLInputElement).value)"
    />
    <span v-if="error" class="c-input__error">{{ error }}</span>
  </div>
</template>

<style scoped>
.c-input {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}

.c-input__label {
  font-size: var(--text-caption);
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.c-input__field {
  padding: var(--space-sm) var(--space-md);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--bg);
  color: var(--text);
  font-size: var(--text-md);
  font-family: var(--font);
  transition:
    border-color 0.2s,
    box-shadow 0.2s;
}

.c-input__field::placeholder {
  color: var(--text-tertiary);
}

.c-input__field:focus {
  outline: none;
  border-color: var(--primary);
  box-shadow: var(--shadow-focus);
}

.c-input--error .c-input__field {
  border-color: var(--error);
}

.c-input__error {
  font-size: var(--text-sm);
  color: var(--error);
}

.c-input--disabled .c-input__field {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
