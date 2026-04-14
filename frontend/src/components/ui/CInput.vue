<script setup lang="ts">
// Text input with label, error state, and optional password toggle.

import { ref } from 'vue'
import { Eye, EyeOff } from 'lucide-vue-next'

const props = withDefaults(
  defineProps<{
    modelValue?: string
    label?: string
    placeholder?: string
    error?: string
    type?: string
    autocomplete?: string
  }>(),
  { modelValue: '', type: 'text' },
)

const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const showPassword = ref(false)
const isPassword = props.type === 'password'

function onInput(e: Event): void {
  emit('update:modelValue', (e.target as HTMLInputElement).value)
}
</script>

<template>
  <div class="c-input-group">
    <label v-if="label" class="c-input-label">{{ label }}</label>
    <div class="c-input-wrapper">
      <input
        class="c-input"
        :class="{ 'c-input--error': !!error }"
        :type="isPassword && showPassword ? 'text' : type"
        :value="modelValue"
        :placeholder="placeholder"
        :autocomplete="autocomplete"
        @input="onInput"
      />
      <button
        v-if="isPassword"
        type="button"
        class="c-input-toggle"
        @click="showPassword = !showPassword"
      >
        <EyeOff v-if="showPassword" :size="20" />
        <Eye v-else :size="20" />
      </button>
    </div>
    <div v-if="error" class="c-input-error">{{ error }}</div>
  </div>
</template>

<style scoped>
.c-input-group { margin-bottom: 16px; }

.c-input-label {
  display: block;
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
  margin-bottom: 6px;
}

.c-input {
  width: 100%;
  padding: 14px 16px;
  border: 2px solid var(--border);
  border-radius: var(--radius-md);
  font-size: 15px;
  font-family: inherit;
  background: var(--bg);
  color: var(--text);
  transition: border-color 0.2s, box-shadow 0.2s;
}

.c-input:focus {
  outline: none;
  border-color: var(--primary);
  box-shadow: var(--shadow-focus);
}

.c-input::placeholder { color: var(--text-tertiary); }

.c-input--error {
  border-color: var(--danger);
  animation: c-shake 0.3s ease;
}

.c-input-wrapper { position: relative; }
.c-input-wrapper .c-input { padding-right: 48px; }

.c-input-toggle {
  position: absolute;
  right: 12px;
  top: 50%;
  transform: translateY(-50%);
  padding: 4px;
  color: var(--text-tertiary);
  background: none;
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
}

.c-input-error {
  font-size: 12px;
  color: var(--danger);
  margin-top: 4px;
}

@keyframes c-shake {
  0%, 100% { transform: translateX(0); }
  25% { transform: translateX(-4px); }
  75% { transform: translateX(4px); }
}
</style>
