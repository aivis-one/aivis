<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- StaffCompanyProfileSection (iter 2.7 Block C)
// =============================================================================
//
// Read-only company profile inspection. Reads the company from the
// shared STAFF_COMPANY_KEY context (PERF-40-01) -- the parent detail
// view already loaded it for the header, so this section does not fire
// its own detail GET. Renders name, description, status, cover, price,
// supply, and the raw distribution_config.
//
// Editing is out of MVP scope (R1 §4.3) -- this surface is inspection
// only. distribution_config is shown as pretty-printed JSON rather than
// a structured editor for the same reason.
//
// FP-25 self-hide: optional fields (description, cover) are omitted from
// the render when absent rather than showing empty rows.
// =============================================================================

import { inject, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { CLoader, CBadge, CButton, CEmptyState } from '@/components/ui'
import { STAFF_COMPANY_KEY } from './staffCompanyContext'

const { t } = useI18n()

// PERF-40-01: read the company the parent detail view already loaded
// instead of firing a second GET /staff/companies/{id}. The injection
// is always present in practice -- sections only ever render inside
// StaffCompanyDetailView's <router-view>.
const ctx = inject(STAFF_COMPANY_KEY)

const company = computed(() => ctx?.company.value ?? null)
const loading = computed(() => ctx?.loading.value ?? false)
const error = computed(() => ctx?.error.value ?? false)

function reload(): void {
  void ctx?.reload()
}

const statusVariant = (s: string) => {
  if (s === 'active') return 'success'
  if (s === 'hidden') return 'warning'
  if (s === 'archived') return 'neutral'
  return 'neutral'
}

function formatPrice(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`
}

// Pretty-print distribution_config for read-only inspection. It is a
// free-form JSONB on the backend, so we show it verbatim rather than
// assuming a fixed shape.
const distributionJson = computed<string>(() => {
  if (!company.value) return ''
  return JSON.stringify(company.value.distribution_config, null, 2)
})

// No local fetch -- the parent detail view owns the company load and
// provides it via STAFF_COMPANY_KEY. The retry button calls ctx.reload.
</script>

<template>
  <div class="scp">
    <!-- Loading -->
    <div v-if="loading" class="scp__center">
      <CLoader :size="28" />
    </div>

    <!-- Error -->
    <div v-else-if="error" class="scp__center">
      <CButton variant="secondary" size="sm" @click="reload">
        {{ t('common.retry') }}
      </CButton>
    </div>

    <!-- Loaded -->
    <template v-else-if="company">
      <!-- Cover (FP-25 self-hide when absent) -->
      <div v-if="company.cover_url" class="scp__cover">
        <img :src="company.cover_url" :alt="company.name" class="scp__cover-img" />
      </div>

      <!-- Status + price + supply rows -->
      <div class="scp__row">
        <span class="scp__label">{{ t('staff.platform.profile.status') }}</span>
        <CBadge :variant="statusVariant(company.status)" :text="company.status" />
      </div>
      <div class="scp__row">
        <span class="scp__label">{{ t('staff.platform.profile.price') }}</span>
        <span class="scp__value">{{ formatPrice(company.price_per_unit_cents) }}</span>
      </div>
      <div class="scp__row">
        <span class="scp__label">{{ t('staff.platform.profile.totalSupply') }}</span>
        <span class="scp__value">{{ company.total_supply.toLocaleString() }}</span>
      </div>
      <div class="scp__row">
        <span class="scp__label">{{ t('staff.platform.profile.sharesPerOption') }}</span>
        <span class="scp__value">{{ company.shares_per_option }}</span>
      </div>

      <!-- Description (FP-25 self-hide when absent) -->
      <div v-if="company.description" class="scp__section">
        <h3 class="scp__section-title">{{ t('staff.platform.profile.description') }}</h3>
        <p class="scp__description">{{ company.description }}</p>
      </div>

      <!-- External links (FP-25 self-hide each when absent) -->
      <div
        v-if="company.logo_url || company.promo_video_url || company.presentation_url"
        class="scp__section"
      >
        <h3 class="scp__section-title">{{ t('staff.platform.profile.links') }}</h3>
        <ul class="scp__links">
          <li v-if="company.logo_url">
            <a :href="company.logo_url" target="_blank" rel="noopener">
              {{ t('staff.platform.profile.logoUrl') }}
            </a>
          </li>
          <li v-if="company.promo_video_url">
            <a :href="company.promo_video_url" target="_blank" rel="noopener">
              {{ t('staff.platform.profile.promoVideoUrl') }}
            </a>
          </li>
          <li v-if="company.presentation_url">
            <a :href="company.presentation_url" target="_blank" rel="noopener">
              {{ t('staff.platform.profile.presentationUrl') }}
            </a>
          </li>
        </ul>
      </div>

      <!-- distribution_config (raw JSON inspection) -->
      <div class="scp__section">
        <h3 class="scp__section-title">{{ t('staff.platform.profile.distributionConfig') }}</h3>
        <pre class="scp__json">{{ distributionJson }}</pre>
      </div>
    </template>

    <!-- Defensive empty (company null but no error/loading -- shouldn't happen) -->
    <CEmptyState v-else :title="t('common.noResults')" />
  </div>
</template>

<style scoped>
.scp { padding: var(--space-4); }

.scp__center {
  display: flex; flex-direction: column; align-items: center;
  justify-content: center; min-height: 160px; gap: var(--space-4);
}

.scp__cover { margin-bottom: var(--space-4); }
.scp__cover-img {
  width: 100%; max-height: 180px; object-fit: cover;
  border-radius: var(--radius-md); display: block;
}

.scp__row {
  display: flex; justify-content: space-between; align-items: center;
  padding: var(--space-3) 0; border-bottom: 1px solid var(--border-default);
}
.scp__label { font-size: var(--fs-xs-lg); color: var(--text-secondary); }
.scp__value { font-size: var(--fs-sm); font-weight: 600; color: var(--text-primary); }

.scp__section { margin-top: var(--space-4-lg); }
.scp__section-title {
  font-size: var(--fs-sm); font-weight: 700; color: var(--text-primary); margin: 0 0 var(--space-2);
}
.scp__description {
  font-size: var(--fs-sm); color: var(--text-secondary); line-height: 1.5; margin: 0;
  white-space: pre-wrap;
}
.scp__links { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: var(--space-2); }
.scp__links a { font-size: var(--fs-xs-lg); color: var(--primary); text-decoration: underline; word-break: break-all; }

.scp__json {
  font-size: var(--fs-xs); font-family: monospace; color: var(--text-primary);
  background: var(--bg-subtle); border-radius: var(--radius-sm);
  padding: var(--space-3); overflow-x: auto; margin: 0; white-space: pre;
}
</style>
