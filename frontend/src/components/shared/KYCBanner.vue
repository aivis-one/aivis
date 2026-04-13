<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import CButton from '@/components/ui/CButton.vue'
import type { KycStatus } from '@/api/types'

defineProps<{
  status: KycStatus
  rejectionReason?: string
}>()

const emit = defineEmits<{
  start: []
  resume: []
  view: []
}>()

const { t } = useI18n()
</script>

<template>
  <div :class="['kyc-banner', `kyc-banner--${status}`]">
    <div class="kyc-banner__content">
      <template v-if="status === 'none'">
        <p class="kyc-banner__title">{{ t('kyc.banner.title_none') }}</p>
        <CButton variant="primary" size="sm" @click="emit('start')">
          {{ t('kyc.banner.cta_start') }}
        </CButton>
      </template>

      <template v-else-if="status === 'pending' || status === 'in_review'">
        <p class="kyc-banner__title">{{ t('kyc.banner.title_pending') }}</p>
        <button class="kyc-banner__link" @click="emit('view')">
          {{ t('kyc.banner.cta_view_status') }}
        </button>
      </template>

      <template v-else-if="status === 'approved'">
        <p class="kyc-banner__title kyc-banner__title--success">
          {{ t('kyc.banner.title_approved') }}
        </p>
      </template>

      <template v-else-if="status === 'rejected'">
        <p class="kyc-banner__title">{{ t('kyc.banner.title_rejected') }}</p>
        <p v-if="rejectionReason" class="kyc-banner__reason">{{ rejectionReason }}</p>
        <CButton variant="secondary" size="sm" @click="emit('resume')">
          {{ t('kyc.banner.cta_resubmit') }}
        </CButton>
      </template>
    </div>
  </div>
</template>

<style scoped>
.kyc-banner {
  padding: var(--space-md);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border);
}

.kyc-banner--none {
  background: var(--o-tint-8);
  border-color: var(--accent);
}

.kyc-banner--pending,
.kyc-banner--in_review {
  background: var(--warning-dim);
  border-color: var(--warning);
}

.kyc-banner--approved {
  background: var(--success-dim);
  border-color: var(--success);
}

.kyc-banner--rejected {
  background: var(--error-dim);
  border-color: var(--error);
}

.kyc-banner__content {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.kyc-banner__title {
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text);
}

.kyc-banner__title--success {
  color: var(--success);
}

.kyc-banner__reason {
  font-size: var(--text-caption);
  color: var(--text-secondary);
}

.kyc-banner__link {
  background: none;
  border: none;
  color: var(--primary);
  font-size: var(--text-caption);
  font-weight: 600;
  cursor: pointer;
  padding: 0;
  text-align: start;
}
</style>
