<script setup lang="ts">
import { onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import CButton from '@/components/ui/CButton.vue'
import CSkeleton from '@/components/ui/CSkeleton.vue'
import { useKycStore } from '@/stores/kyc'
import { useAuthStore } from '@/stores/auth'
import { getKycStatusColor } from '@/utils/display'

const { t } = useI18n()
const router = useRouter()
const kycStore = useKycStore()
const authStore = useAuthStore()

onMounted(async () => {
  await kycStore.fetchStatus()
  if (kycStore.status === 'none') {
    const role = authStore.userRole ?? 'investor'
    router.replace(`/${role}/kyc/form`)
  }
})

function goToForm() {
  const role = authStore.userRole ?? 'investor'
  router.push(`/${role}/kyc/form`)
}
</script>

<template>
  <div class="kyc-status">
    <h1 class="kyc-status__title">{{ t('kyc.status.title') }}</h1>

    <CSkeleton v-if="kycStore.loading && !kycStore.submission" variant="card" />

    <template v-else-if="kycStore.submission">
      <div class="kyc-status__badge" :style="{ color: getKycStatusColor(kycStore.status) }">
        {{ kycStore.status }}
      </div>

      <!-- Timeline -->
      <ol class="kyc-status__timeline">
        <li class="kyc-status__timeline-item kyc-status__timeline-item--done">
          <span class="kyc-status__timeline-dot" />
          <div>
            <span class="kyc-status__timeline-label">{{ t('kyc.status.timeline_submitted') }}</span>
            <span class="kyc-status__timeline-date">{{ kycStore.submission.submitted_at }}</span>
          </div>
        </li>
        <li
          :class="[
            'kyc-status__timeline-item',
            {
              'kyc-status__timeline-item--done': kycStore.isApproved || kycStore.isRejected,
              'kyc-status__timeline-item--active': kycStore.isPending,
            },
          ]"
        >
          <span class="kyc-status__timeline-dot" />
          <div>
            <span class="kyc-status__timeline-label">{{ t('kyc.status.timeline_review') }}</span>
          </div>
        </li>
        <li
          v-if="kycStore.isApproved"
          class="kyc-status__timeline-item kyc-status__timeline-item--done kyc-status__timeline-item--success"
        >
          <span class="kyc-status__timeline-dot" />
          <div>
            <span class="kyc-status__timeline-label">{{ t('kyc.status.timeline_approved') }}</span>
            <span class="kyc-status__timeline-date">
              {{ t('kyc.status.verified_on') }} {{ kycStore.submission.reviewed_at }}
            </span>
          </div>
        </li>
        <li
          v-if="kycStore.isRejected"
          class="kyc-status__timeline-item kyc-status__timeline-item--done kyc-status__timeline-item--error"
        >
          <span class="kyc-status__timeline-dot" />
          <div>
            <span class="kyc-status__timeline-label">{{ t('kyc.status.timeline_rejected') }}</span>
          </div>
        </li>
      </ol>

      <!-- Rejection details -->
      <div
        v-if="kycStore.isRejected && kycStore.submission.rejection_reason"
        class="kyc-status__rejection"
      >
        <p class="kyc-status__rejection-label">{{ t('kyc.status.rejection_reason') }}</p>
        <p class="kyc-status__rejection-text">{{ kycStore.submission.rejection_reason }}</p>
        <CButton variant="primary" @click="goToForm">{{ t('kyc.status.resubmit') }}</CButton>
      </div>
    </template>
  </div>
</template>

<style scoped>
.kyc-status {
  padding: var(--space-md);
  display: flex;
  flex-direction: column;
  gap: var(--space-lg);
}

.kyc-status__title {
  font-size: var(--text-2xl);
  font-weight: 700;
  color: var(--text);
}

.kyc-status__badge {
  font-size: var(--text-lg);
  font-weight: 700;
  text-transform: uppercase;
}

.kyc-status__timeline {
  display: flex;
  flex-direction: column;
  gap: 0;
  list-style: none;
  padding-inline-start: 0;
}

.kyc-status__timeline-item {
  display: flex;
  align-items: flex-start;
  gap: var(--space-sm);
  padding: var(--space-sm) 0;
  padding-inline-start: var(--space-md);
  border-inline-start: 2px solid var(--border);
  position: relative;
}

.kyc-status__timeline-dot {
  position: absolute;
  inset-inline-start: -5px;
  top: var(--space-sm);
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--border);
}

.kyc-status__timeline-item--done .kyc-status__timeline-dot {
  background: var(--primary);
}

.kyc-status__timeline-item--active .kyc-status__timeline-dot {
  background: var(--warning);
}

.kyc-status__timeline-item--success .kyc-status__timeline-dot {
  background: var(--success);
}

.kyc-status__timeline-item--error .kyc-status__timeline-dot {
  background: var(--error);
}

.kyc-status__timeline-label {
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text);
  display: block;
}

.kyc-status__timeline-date {
  font-size: var(--text-sm);
  color: var(--text-tertiary);
  display: block;
}

.kyc-status__rejection {
  padding: var(--space-md);
  background: var(--error-dim);
  border-radius: var(--radius-lg);
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.kyc-status__rejection-label {
  font-size: var(--text-caption);
  font-weight: 600;
  color: var(--error);
}

.kyc-status__rejection-text {
  font-size: var(--text-base);
  color: var(--text);
}
</style>
