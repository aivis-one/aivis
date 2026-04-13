<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import CButton from '@/components/ui/CButton.vue'
import CCard from '@/components/ui/CCard.vue'

withDefaults(
  defineProps<{
    message?: string
    retryable?: boolean
  }>(),
  {
    message: '',
    retryable: true,
  },
)

defineEmits<{
  retry: []
}>()

const { t } = useI18n()
</script>

<template>
  <CCard class="c-network-error">
    <div class="c-network-error__icon">!</div>
    <p class="c-network-error__message">{{ message || t('errors.network') }}</p>
    <CButton v-if="retryable" variant="secondary" size="sm" @click="$emit('retry')">
      {{ t('errors.retry') }}
    </CButton>
  </CCard>
</template>

<style scoped>
.c-network-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-md);
  text-align: center;
  padding: var(--space-xl) var(--space-md);
}

.c-network-error__icon {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: var(--error-dim);
  color: var(--error);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-2xl);
  font-weight: 700;
}

.c-network-error__message {
  font-size: var(--text-base);
  color: var(--text-secondary);
  max-width: 300px;
}
</style>
