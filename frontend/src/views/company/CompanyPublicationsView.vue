<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- CompanyPublicationsView
// =============================================================================
//
// The Publications tab of the project account: the three things the project
// publishes on its own, without an approval -- posts, the roadmap and
// documents. Each line opens the screen that edits it. "View on the store"
// opens the project's own page the way a buyer sees it, in a new tab.
// =============================================================================

import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ChevronRight, ExternalLink, FileText, Map as MapIcon, Newspaper } from 'lucide-vue-next'

import { CButton } from '@/components/ui'
import { useCompanyProfileStore } from '@/stores/companyProfile'

const { t } = useI18n()
const router = useRouter()
const profileStore = useCompanyProfileStore()

const companyId = computed<string | null>(() => profileStore.profile?.id ?? null)

function viewOnStore(): void {
  if (!companyId.value) return
  const href = router.resolve({
    name: 'public-company-overview',
    params: { id: companyId.value },
  }).href
  window.open(href, '_blank', 'noopener')
}

onMounted(() => {
  void profileStore.loadIfMissing()
})
</script>

<template>
  <div class="cpub">
    <div class="cpub__header">
      <h1 class="cpub__title">
        {{ t('comp.publications.title') }}
      </h1>
      <p class="cpub__subtitle">
        {{ t('comp.publications.subtitle') }}
      </p>
    </div>

    <div class="cpub__actions">
      <CButton variant="outline" size="sm" :disabled="!companyId" @click="viewOnStore">
        <ExternalLink :size="16" />
        {{ t('comp.publications.viewOnStore') }}
      </CButton>
    </div>

    <section class="cpub__section">
      <RouterLink to="/company/publications/posts" class="cpub__row">
        <span class="cpub__row-icon"><Newspaper :size="18" /></span>
        <span class="cpub__row-body">
          <span class="cpub__row-title">{{ t('comp.publications.posts.title') }}</span>
          <span class="cpub__row-desc">{{ t('comp.publications.posts.desc') }}</span>
        </span>
        <ChevronRight :size="16" />
      </RouterLink>
      <RouterLink to="/company/publications/roadmap" class="cpub__row">
        <span class="cpub__row-icon"><MapIcon :size="18" /></span>
        <span class="cpub__row-body">
          <span class="cpub__row-title">{{ t('comp.publications.roadmap.title') }}</span>
          <span class="cpub__row-desc">{{ t('comp.publications.roadmap.desc') }}</span>
        </span>
        <ChevronRight :size="16" />
      </RouterLink>
      <RouterLink to="/company/publications/documents" class="cpub__row">
        <span class="cpub__row-icon"><FileText :size="18" /></span>
        <span class="cpub__row-body">
          <span class="cpub__row-title">{{ t('comp.publications.documents.title') }}</span>
          <span class="cpub__row-desc">{{ t('comp.publications.documents.desc') }}</span>
        </span>
        <ChevronRight :size="16" />
      </RouterLink>
    </section>

    <p class="cpub__hint">
      {{ t('comp.publications.hint') }}
    </p>
  </div>
</template>

<style scoped>
.cpub {
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}
.cpub__title {
  font-size: var(--fs-xl);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}
.cpub__subtitle {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  margin: var(--space-1) 0 0;
}
.cpub__actions {
  display: flex;
}
.cpub__section {
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  background: var(--bg-surface);
  overflow: hidden;
}
.cpub__row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  min-height: var(--size-3xl);
  border-bottom: 1px solid var(--border-default);
  color: var(--text-primary);
  text-decoration: none;
  transition: background 0.15s;
}
.cpub__row:last-child {
  border-bottom: none;
}
.cpub__row:hover {
  background: var(--bg-subtle);
}
.cpub__row-icon {
  display: inline-flex;
  color: var(--primary);
}
.cpub__row-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.cpub__row-title {
  font-size: var(--fs-sm);
  font-weight: 600;
}
.cpub__row-desc {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
}
.cpub__hint {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
  margin: 0;
}
</style>
