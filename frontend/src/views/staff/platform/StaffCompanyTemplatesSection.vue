<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- StaffCompanyTemplatesSection (iter 2.7 Block C / C2)
// =============================================================================
//
// Read-only inspection of the document templates a company renders
// through (R2 §6.3). Lists per-company rows merged with platform-default
// fallbacks; clicking a row opens a modal with the inlined HTML body.
//
// READ-ONLY in MVP. There is no in-app template editor -- uploads happen
// via the MinIO Web UI + reconcile (R2 §4.8). The detail modal therefore
// shows the HTML as source text in a <pre> (not rendered), so staff can
// inspect the actual {{variables}} and markup. The storage_prefix is
// surfaced as a hint for staff who need to jump into MinIO to edit.
//
// FILTERS: kind / language / status chip rows. All bound to backend
// StrEnums (422 on a bad value, which can't happen from fixed chips).
// The list is NOT paginated -- the backend returns a plain array.
//
// is_platform_default badge distinguishes platform fallbacks from
// per-company overrides at a glance.
//
// Permission: the parent route already enforces company_manage (the
// only gate these endpoints need). No edit CTA -> no FP-23 gating here.
// =============================================================================

import { ref, onMounted, computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { CLoader, CBadge, CButton, CEmptyState, CModal } from '@/components/ui'
import {
  fetchStaffCompanyTemplates,
  fetchStaffCompanyTemplate,
} from '@/api/staff-companies'
import type { TemplateResponse, TemplateDetailResponse } from '@/api/types'

const { t } = useI18n()
const route = useRoute()

const companyId = computed<string>(() => {
  const raw = route.params.id
  return typeof raw === 'string' ? raw : ''
})

// -- Filter options + types. Options are the single source of truth;
// the filter refs derive their value type from them so a ref can
// only ever hold '' (no filter) or one of the option literals --
// which is exactly what fetchStaffCompanyTemplates' narrowed params
// accept (so `value || undefined` type-checks).
const KIND_OPTIONS = [
  'purchase_agreement',
  'gift_certificate',
  'installment_subcontract',
  'ownership_certificate',
] as const
const LANGUAGE_OPTIONS = ['en', 'ru', 'de', 'ar'] as const
const STATUS_OPTIONS = ['draft', 'active', 'archived'] as const

type KindFilter = '' | (typeof KIND_OPTIONS)[number]
type LanguageFilter = '' | (typeof LANGUAGE_OPTIONS)[number]
type StatusFilter = '' | (typeof STATUS_OPTIONS)[number]

// '' = no filter.
const kindFilter = ref<KindFilter>('')
const languageFilter = ref<LanguageFilter>('')
const statusFilter = ref<StatusFilter>('')

// -- List state --
const items = ref<TemplateResponse[]>([])
const loading = ref(true)
const error = ref(false)

// -- Detail modal --
const showDetail = ref(false)
const detail = ref<TemplateDetailResponse | null>(null)
const detailLoading = ref(false)
const detailError = ref(false)

const statusVariant = (s: string) => {
  if (s === 'active') return 'success'
  if (s === 'draft') return 'warning'
  if (s === 'archived') return 'neutral'
  return 'neutral'
}

async function loadTemplates(): Promise<void> {
  const id = companyId.value
  if (!id) return
  loading.value = true
  error.value = false
  try {
    items.value = await fetchStaffCompanyTemplates(id, {
      kind: kindFilter.value || undefined,
      language: languageFilter.value || undefined,
      status: statusFilter.value || undefined,
    })
  } catch {
    error.value = true
  } finally {
    loading.value = false
  }
}

async function openDetail(template: TemplateResponse): Promise<void> {
  showDetail.value = true
  detailLoading.value = true
  detailError.value = false
  detail.value = null
  try {
    detail.value = await fetchStaffCompanyTemplate(companyId.value, template.id)
  } catch {
    // 500 here = broken template (MinIO object missing / storage down).
    // Surface a load error rather than an empty body.
    detailError.value = true
  } finally {
    detailLoading.value = false
  }
}

function setKind(v: KindFilter): void { kindFilter.value = v }
function setLanguage(v: LanguageFilter): void { languageFilter.value = v }
function setStatus(v: StatusFilter): void { statusFilter.value = v }

watch([kindFilter, languageFilter, statusFilter], () => loadTemplates())
watch(companyId, () => loadTemplates())
onMounted(loadTemplates)
</script>

<template>
  <div class="sct">
    <!-- Filter chip rows -->
    <div class="sct__filters">
      <div class="sct__filter-row">
        <button class="filter-chip" :class="{ active: !kindFilter }" @click="setKind('')">
          {{ t('staff.platform.templates.allKinds') }}
        </button>
        <button
          v-for="k in KIND_OPTIONS"
          :key="k"
          class="filter-chip"
          :class="{ active: kindFilter === k }"
          @click="setKind(k)"
        >{{ t(`staff.platform.templates.kind.${k}`) }}</button>
      </div>
      <div class="sct__filter-row">
        <button class="filter-chip" :class="{ active: !languageFilter }" @click="setLanguage('')">
          {{ t('staff.platform.templates.allLanguages') }}
        </button>
        <button
          v-for="l in LANGUAGE_OPTIONS"
          :key="l"
          class="filter-chip"
          :class="{ active: languageFilter === l }"
          @click="setLanguage(l)"
        >{{ l.toUpperCase() }}</button>
      </div>
      <div class="sct__filter-row">
        <button class="filter-chip" :class="{ active: !statusFilter }" @click="setStatus('')">
          {{ t('staff.platform.templates.allStatuses') }}
        </button>
        <button
          v-for="s in STATUS_OPTIONS"
          :key="s"
          class="filter-chip"
          :class="{ active: statusFilter === s }"
          @click="setStatus(s)"
        >{{ t(`staff.platform.templates.status.${s}`) }}</button>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="sct__center">
      <CLoader :size="28" />
    </div>

    <!-- Error -->
    <div v-else-if="error" class="sct__center">
      <CButton variant="secondary" size="sm" @click="loadTemplates">
        {{ t('common.retry') }}
      </CButton>
    </div>

    <!-- Empty -->
    <CEmptyState v-else-if="!items.length" :title="t('staff.platform.templates.empty')" />

    <!-- List -->
    <template v-else>
      <div class="tpl-list">
        <div
          v-for="tpl in items"
          :key="tpl.id"
          class="tpl-item"
          @click="openDetail(tpl)"
        >
          <div class="tpl-item__info">
            <div class="tpl-item__top">
              <CBadge :variant="statusVariant(tpl.status)" :text="tpl.status" />
              <CBadge
                v-if="tpl.is_platform_default"
                variant="primary"
                :text="t('staff.platform.templates.platformDefault')"
              />
            </div>
            <div class="tpl-item__title">{{ tpl.title }}</div>
            <div class="tpl-item__meta">
              {{ t(`staff.platform.templates.kind.${tpl.kind}`) }}
              &bull; {{ tpl.language.toUpperCase() }}
              &bull; v{{ tpl.version }}
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- Detail modal -->
    <CModal :open="showDetail" @close="showDetail = false">
      <div v-if="detailLoading" class="sct__center" style="min-height:160px">
        <CLoader :size="24" />
      </div>

      <div v-else-if="detailError" class="sct__center" style="min-height:160px">
        <p class="sct__detail-error">{{ t('staff.platform.templates.detailError') }}</p>
      </div>

      <template v-else-if="detail">
        <h3 class="sct__modal-title">{{ detail.title }}</h3>
        <div class="sct__detail-meta">
          <CBadge :variant="statusVariant(detail.status)" :text="detail.status" />
          <span>{{ t(`staff.platform.templates.kind.${detail.kind}`) }}</span>
          <span>{{ detail.language.toUpperCase() }}</span>
          <span>v{{ detail.version }}</span>
        </div>

        <!-- storage_prefix hint (MinIO deep-link reference) -->
        <div class="sct__storage">
          <span class="sct__storage-label">{{ t('staff.platform.templates.storagePrefix') }}</span>
          <code class="sct__storage-value">{{ detail.storage_prefix }}</code>
        </div>

        <!-- asset_files list (if any) -->
        <div v-if="detail.asset_files.length" class="sct__assets">
          <span class="sct__assets-label">{{ t('staff.platform.templates.assetFiles') }}</span>
          <ul class="sct__assets-list">
            <li v-for="f in detail.asset_files" :key="f">{{ f }}</li>
          </ul>
        </div>

        <!-- HTML body as source text (NOT rendered) -->
        <div class="sct__html">
          <span class="sct__html-label">{{ t('staff.platform.templates.htmlSource') }}</span>
          <pre class="sct__html-pre">{{ detail.html_content }}</pre>
        </div>

        <div class="sct__modal-actions">
          <CButton variant="outline" size="sm" @click="showDetail = false">
            {{ t('common.close') }}
          </CButton>
        </div>
      </template>
    </CModal>
  </div>
</template>

<style scoped>
.sct { padding: var(--space-4); }

.sct__filters { display: flex; flex-direction: column; gap: var(--space-2); margin-bottom: var(--space-4); }
.sct__filter-row { display: flex; gap: var(--space-2); overflow-x: auto; padding-bottom: var(--space-1); }
.filter-chip {
  padding: var(--space-2) var(--space-3); border-radius: var(--radius-sm); border: 1px solid var(--border-default);
  background: var(--bg-page); color: var(--text-secondary); font-size: var(--fs-xs); font-weight: 600;
  cursor: pointer; white-space: nowrap;
}
.filter-chip.active { background: var(--primary); color: var(--on-primary); border-color: var(--primary); }

.sct__center {
  display: flex; flex-direction: column; align-items: center;
  justify-content: center; min-height: var(--center-sm); gap: var(--space-4);
}
.sct__detail-error { font-size: var(--fs-sm); color: var(--danger); text-align: center; }

.tpl-list { display: flex; flex-direction: column; }
.tpl-item {
  display: flex; align-items: center; gap: var(--space-3); padding: var(--space-4) 0;
  border-bottom: 1px solid var(--border-default); cursor: pointer; transition: background 0.15s;
}
.tpl-item:hover { background: var(--bg-subtle); }
.tpl-item__info { flex: 1; min-width: 0; }
.tpl-item__top { display: flex; gap: var(--space-2); flex-wrap: wrap; margin-bottom: var(--space-2); }
.tpl-item__title {
  font-size: var(--fs-sm); font-weight: 600; color: var(--text-primary);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.tpl-item__meta { font-size: var(--fs-xs); color: var(--text-tertiary); margin-top: var(--space-1); }

.sct__modal-title { font-size: var(--fs-h4); font-weight: 700; color: var(--text-primary); margin: 0 0 var(--space-2); }
.sct__detail-meta {
  display: flex; align-items: center; gap: var(--space-2); flex-wrap: wrap;
  font-size: var(--fs-xs); color: var(--text-secondary); margin-bottom: var(--space-4);
}

.sct__storage, .sct__assets { margin-bottom: var(--space-4); }
.sct__storage-label, .sct__assets-label, .sct__html-label {
  display: block; font-size: var(--fs-xs); font-weight: 600; color: var(--text-secondary);
  text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: var(--space-2);
}
.sct__storage-value {
  font-size: var(--fs-xs); font-family: var(--font-mono); color: var(--text-primary);
  background: var(--bg-subtle); padding: var(--space-1) var(--space-2); border-radius: var(--radius-sm);
  word-break: break-all;
}
.sct__assets-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: var(--space-1); }
.sct__assets-list li { font-size: var(--fs-xs); font-family: var(--font-mono); color: var(--text-secondary); }

.sct__html { margin-bottom: var(--space-2); }
.sct__html-pre {
  font-size: var(--fs-xs); font-family: var(--font-mono); color: var(--text-primary);
  background: var(--bg-subtle); border-radius: var(--radius-sm);
  padding: var(--space-3); overflow: auto; max-height: 360px; margin: 0;
  white-space: pre-wrap; word-break: break-word;
}

.sct__modal-actions { display: flex; gap: var(--space-2); margin-top: var(--space-4); justify-content: flex-end; }
</style>
