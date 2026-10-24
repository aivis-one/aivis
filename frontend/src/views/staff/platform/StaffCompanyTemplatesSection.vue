<script setup lang="ts">
import { Check } from '@/components/ui/icons'
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
import { tOrRaw } from '@/utils/i18n'
import { CLoader, CBadge, CButton, CEmptyState, CModal } from '@/components/ui'
import CAlert from '@/components/ui/CAlert.vue'
import CListSkeleton from '@/components/ui/CListSkeleton.vue'
import { fetchStaffCompanyTemplates, fetchStaffCompanyTemplate } from '@/api/staff-companies'
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

function setKind(v: KindFilter): void {
  kindFilter.value = v
}
function setLanguage(v: LanguageFilter): void {
  languageFilter.value = v
}
function setStatus(v: StatusFilter): void {
  statusFilter.value = v
}

watch([kindFilter, languageFilter, statusFilter], () => loadTemplates())
watch(companyId, () => loadTemplates())
onMounted(loadTemplates)
</script>

<template>
  <div class="sct">
    <!-- Filter chip rows (K13) -->
    <div class="sct__filters">
      <div class="ds-chip-row" role="group" :aria-label="t('staff.platform.templates.allKinds')">
        <button class="ds-chip" :aria-pressed="!kindFilter" @click="setKind('')" type="button">
          <Check class="ds-chip__check" size="sm" />
          <span>{{ t('staff.platform.templates.allKinds') }}</span>
        </button>
        <button
          v-for="k in KIND_OPTIONS"
          :key="k"
          class="ds-chip"
          :aria-pressed="kindFilter === k"
          @click="setKind(k)"
          type="button"
        >
          <Check class="ds-chip__check" size="sm" />
          <span>{{ t(`staff.platform.templates.kind.${k}`) }}</span>
        </button>
      </div>
      <div
        class="ds-chip-row"
        role="group"
        :aria-label="t('staff.platform.templates.allLanguages')"
      >
        <button
          class="ds-chip"
          :aria-pressed="!languageFilter"
          @click="setLanguage('')"
          type="button"
        >
          <Check class="ds-chip__check" size="sm" />
          <span>{{ t('staff.platform.templates.allLanguages') }}</span>
        </button>
        <button
          v-for="l in LANGUAGE_OPTIONS"
          :key="l"
          class="ds-chip"
          :aria-pressed="languageFilter === l"
          @click="setLanguage(l)"
          type="button"
        >
          <Check class="ds-chip__check" size="sm" />
          <span>{{ l.toUpperCase() }}</span>
        </button>
      </div>
      <div class="ds-chip-row" role="group" :aria-label="t('staff.platform.templates.allStatuses')">
        <button class="ds-chip" :aria-pressed="!statusFilter" @click="setStatus('')" type="button">
          <Check class="ds-chip__check" size="sm" />
          <span>{{ t('staff.platform.templates.allStatuses') }}</span>
        </button>
        <button
          v-for="s in STATUS_OPTIONS"
          :key="s"
          class="ds-chip"
          :aria-pressed="statusFilter === s"
          @click="setStatus(s)"
          type="button"
        >
          <Check class="ds-chip__check" size="sm" />
          <span>{{ t(`staff.platform.templates.status.${s}`) }}</span>
        </button>
      </div>
    </div>

    <!-- Loading -->
    <CListSkeleton v-if="loading" />

    <!-- Error -->
    <CEmptyState v-else-if="error" tone="danger" :title="t('common.error')">
      <template #actions>
        <CButton variant="secondary" size="sm" inline @click="loadTemplates">
          {{ t('common.retry') }}
        </CButton>
      </template>
    </CEmptyState>

    <!-- Empty -->
    <CEmptyState v-else-if="!items.length" :title="t('staff.platform.templates.empty')" />

    <!-- List (K23 rows; a row opens the template's source in place) -->
    <ul v-else class="ds-rows tpl-list">
      <li v-for="tpl in items" :key="tpl.id" class="ds-row">
        <span class="ds-row__body">
          <button type="button" class="ds-row__link tpl-item" @click="openDetail(tpl)">
            <span class="ds-row__title">{{ tpl.title }}</span>
          </button>
          <span class="ds-row__meta">
            {{ t(`staff.platform.templates.kind.${tpl.kind}`) }}
            &bull; {{ tpl.language.toUpperCase() }} &bull; v{{ tpl.version }}
          </span>
        </span>
        <span class="ds-row__trail">
          <CBadge
            :variant="statusVariant(tpl.status)"
            :text="tOrRaw(t, `staff.platform.templates.status.${tpl.status}`, tpl.status)"
          />
          <CBadge
            v-if="tpl.is_platform_default"
            variant="primary"
            :text="t('staff.platform.templates.platformDefault')"
          />
        </span>
      </li>
    </ul>

    <!-- Detail modal -->
    <CModal
      :open="showDetail"
      :title="detail && !detailLoading && !detailError ? detail.title : undefined"
      @close="showDetail = false"
    >
      <div v-if="detailLoading" class="sct__center">
        <CLoader :size="24" />
      </div>

      <CAlert v-else-if="detailError" tone="danger">
        {{ t('staff.platform.templates.detailError') }}
      </CAlert>

      <template v-else-if="detail">
        <div class="sct__detail-meta">
          <CBadge
            :variant="statusVariant(detail.status)"
            :text="tOrRaw(t, `staff.platform.templates.status.${detail.status}`, detail.status)"
          />
          <span>{{ t(`staff.platform.templates.kind.${detail.kind}`) }}</span>
          <span>{{ detail.language.toUpperCase() }}</span>
          <span>v{{ detail.version }}</span>
        </div>

        <!-- storage_prefix hint (MinIO deep-link reference) -->
        <div class="sct__block">
          <span class="sct__label">{{ t('staff.platform.templates.storagePrefix') }}</span>
          <code class="sct__code">{{ detail.storage_prefix }}</code>
        </div>

        <!-- asset_files list (if any) -->
        <div v-if="detail.asset_files.length" class="sct__block">
          <span class="sct__label">{{ t('staff.platform.templates.assetFiles') }}</span>
          <ul class="sct__assets-list">
            <li v-for="f in detail.asset_files" :key="f">
              <code class="sct__code">{{ f }}</code>
            </li>
          </ul>
        </div>

        <!-- HTML body as source text (NOT rendered) -->
        <div class="sct__block">
          <span class="sct__label">{{ t('staff.platform.templates.htmlSource') }}</span>
          <pre class="sct__code sct__html-pre">{{ detail.html_content }}</pre>
        </div>

        <div class="ds-dialog__actions">
          <CButton variant="outline" size="sm" inline @click="showDetail = false">
            {{ t('common.close') }}
          </CButton>
        </div>
      </template>
    </CModal>
  </div>
</template>

<style scoped>
.sct {
  display: grid;
  gap: var(--space-4);
  align-content: start;
}

.sct__filters {
  display: grid;
  gap: var(--space-2);
}

.sct__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-block-size: var(--center-md);
  gap: var(--space-4);
}

/* The row opens the template in place: a button holds the row's one link-part
   (the title), and a button aligns its text to the start by hand. */
.tpl-item {
  text-align: start;
}

.sct__detail-meta {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap;
  font-size: var(--fs-xs);
  color: var(--text-secondary);
}

.sct__block {
  display: grid;
  gap: var(--space-2);
}
.sct__label {
  font-size: var(--fs-xs);
  font-weight: 600;
  letter-spacing: var(--tracking-wide);
  text-transform: uppercase;
  color: var(--text-secondary);
}
.sct__assets-list {
  display: grid;
  gap: var(--space-1);
}

/* Source text, names and paths are read character by character: the mono family (D11). */
.sct__code {
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-sm);
  background: var(--bg-inset);
  font-family: var(--font-mono);
  font-size: var(--fs-xs);
  color: var(--text-primary);
  word-break: break-all;
}
.sct__html-pre {
  margin: 0;
  padding: var(--space-3);
  overflow: auto;
  max-block-size: var(--center-lg);
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
