<script setup lang="ts">
// =============================================================================
// CBSHOME Frontend -- PublicCompanyListView (iter 2.6, stub for Batch 3)
// =============================================================================
//
// Stub placeholder. The router (Batch 2) lazy-imports this file via
//   () => import('@/views/public/PublicCompanyListView.vue')
// so the path must exist on disk at build time -- Vite/Rollup resolves
// every dynamic import target during production build (see
// https://vite.dev/guide/build), and a missing target produces a
// silently-empty chunk that breaks downstream plugins (Workbox in our
// case: "Couldn't find configuration for either precaching or runtime
// caching").
//
// Batch 3 replaces this with the real list view (R1 §1.6.1, plan §B4).
// Until then the visitor sees a "Coming soon" placeholder if they
// open /public/companies. No styling beyond the basics; this should
// never reach a real user (Batch 3 is queued).
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
