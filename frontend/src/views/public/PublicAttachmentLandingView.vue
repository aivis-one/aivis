<script setup lang="ts">
// =============================================================================
// CBSHOME Frontend -- PublicAttachmentLandingView (iter 2.6, stub for Batch 4)
// =============================================================================
//
// Stub placeholder. See PublicCompanyListView.vue for the why-a-stub
// rationale (Vite/Rollup resolves all dynamic imports at build time).
// Replaced by the real landing view in Batch 4 (R2 §7.2, plan §A5).
// =============================================================================

import { useI18n } from 'vue-i18n'

const { t } = useI18n()
</script>

<template>
  <div class="public-stub">
    <h1 class="public-stub__title">{{ t('public.companyList.empty.title') }}</h1>
    <p class="public-stub__subtitle">
      {{ t('public.companyList.empty.subtitle') }}
    </p>
  </div>
</template>

<style scoped>
.public-stub {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 24px;
  text-align: center;
  gap: 12px;
}

.public-stub__title {
  font-size: 20px;
  font-weight: 700;
  color: var(--text);
  margin: 0;
}

.public-stub__subtitle {
  font-size: 14px;
  color: var(--text-secondary);
  margin: 0;
  max-width: 360px;
  line-height: 1.5;
}
</style>
