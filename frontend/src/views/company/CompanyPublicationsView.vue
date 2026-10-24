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
import {
  ChevronRight,
  ExternalLink,
  FileText,
  Info,
  Map as MapIcon,
  Newspaper,
} from '@/components/ui/icons'

import { CIconBox } from '@/components/ui'
import { useScreenHeader } from '@/components/layout/screenHeader'
import { useCompanyProfileStore } from '@/stores/companyProfile'

const { t } = useI18n()
const router = useRouter()
const profileStore = useCompanyProfileStore()

const companyId = computed<string | null>(() => profileStore.profile?.id ?? null)

// The frame's header carries the title, the line under it and the one action:
// "View on the store" opens the project's page as a buyer sees it, once the
// profile is read.
useScreenHeader({
  title: () => t('comp.publications.title'),
  lead: () => t('comp.publications.subtitle'),
  actions: () =>
    companyId.value
      ? [
          {
            id: 'view-on-store',
            label: t('comp.publications.viewOnStore'),
            icon: ExternalLink,
            onClick: viewOnStore,
          },
        ]
      : [],
})

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
  <nav class="ds-navtiles" :aria-label="t('comp.publications.title')">
    <RouterLink to="/company/publications/posts" class="ds-navtile">
      <CIconBox><Newspaper /></CIconBox>
      <span class="ds-navtile__text">
        <span class="ds-navtile__title">{{ t('comp.publications.posts.title') }}</span>
        <span class="ds-navtile__desc">{{ t('comp.publications.posts.desc') }}</span>
      </span>
      <ChevronRight class="ds-navtile__go" size="sm" />
    </RouterLink>
    <RouterLink to="/company/publications/roadmap" class="ds-navtile">
      <CIconBox><MapIcon /></CIconBox>
      <span class="ds-navtile__text">
        <span class="ds-navtile__title">{{ t('comp.publications.roadmap.title') }}</span>
        <span class="ds-navtile__desc">{{ t('comp.publications.roadmap.desc') }}</span>
      </span>
      <ChevronRight class="ds-navtile__go" size="sm" />
    </RouterLink>
    <RouterLink to="/company/publications/documents" class="ds-navtile">
      <CIconBox><FileText /></CIconBox>
      <span class="ds-navtile__text">
        <span class="ds-navtile__title">{{ t('comp.publications.documents.title') }}</span>
        <span class="ds-navtile__desc">{{ t('comp.publications.documents.desc') }}</span>
      </span>
      <ChevronRight class="ds-navtile__go" size="sm" />
    </RouterLink>
  </nav>

  <div class="ds-alert ds-alert--info" role="status">
    <span class="ds-alert__icon" aria-hidden="true"><Info size="sm" /></span>
    <div class="ds-alert__content">
      <p class="ds-alert__text">{{ t('comp.publications.hint') }}</p>
    </div>
  </div>
</template>
