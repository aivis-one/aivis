<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- StaffCompanyProfileSection (iter 2.7 Block C)
// =============================================================================
//
// Project profile: a staff member reads it and changes its NAME,
// DESCRIPTION and LINKS (promo video, presentation), its PICTURES (logo,
// dark logo, cover -- files, H36), plus
// (TASK-30 ruling 12) a status control. Reads the project from the shared
// STAFF_COMPANY_KEY context (PERF-40-01) -- the parent detail view already
// loaded it for the header, so this section does not fire its own detail GET.
// Renders name, description, status, cover, the price of a part, the parts in
// total, and the division of the parts.
//
// THE DIVISION OF THE PARTS IS FIXED -- 25 percent for sale, 10 to the index,
// 14 to the bonus fund, 51 to the reserve -- and is shown as a read-only table
// that nothing on this screen writes. The server would accept a new division in
// the update; the screen does not offer one.
//
// STATUS CONTROL (TASK-30 ruling 12).
//   Unlike everything else on this surface, `status` now has a real
//   mutating control: PATCH /api/v1/staff/companies/{id} (update_company()
//   server-side), gated on project_manage -- the same permission that
//   gates the roadmap and attachment writes on the sibling sections
//   (StaffCompanyRoadmapSection, StaffCompanyDocumentsSection). Unlike
//   the price change (FP-23, gated on project_manage AND
//   financial_operations because it also touches distribution_config's
//   sibling money fields), status is project_manage alone --
//   update_company_endpoint only requires financial_operations when
//   `distribution_config` is present in the body, which it never is
//   here.
//
//   Staff is NOT restricted to one direction (unlike the project's own
//   ACTIVE -> HIDDEN-only self-service in CompanySettingsView): the
//   server validates against VALID_COMPANY_STATUS_TRANSITIONS (hidden
//   -> {active, archived}, active -> {hidden, archived}, archived -> {}
//   terminal). STATUS_TRANSITIONS below mirrors that table client-side
//   so the edit control only ever offers a legal target -- when the
//   current status is 'archived' there are none, so the edit CTA does
//   not render at all rather than opening a modal with an empty select.
//
// PICTURES (H36 P-131). The logo, the logo for the dark theme and the cover
// are files in our storage, uploaded and removed at once through
// PUT|DELETE /api/v1/staff/companies/{id}/media/{slot} (project_manage), not
// through the profile form's Save. After each, the shared context reloads so
// every section sees the new links.
//
// LANGUAGES (H38 P-132). The name and the description are edited in every
// language of the interface (LocalizedTextFields): English is the base and
// required, the others are translations. The screen shows the texts in
// the reader's language, as every screen does. The pictures are edited per
// version (MediaLanguageSelect): the common file, or one language's
// variant -- the links come from the response's image_variants, so a
// Russian-speaking editor sees the common file as the common file.
//
// FP-25 self-hide: optional fields (description, cover) are omitted from
// the render when absent rather than showing empty rows.
// =============================================================================

import { inject, computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ExternalLink } from '@/components/ui/icons'
import { CLoader, CBadge, CButton, CEmptyState, CModal, CSelect, CInput } from '@/components/ui'
import { useToast } from '@/composables/useToast'
import { useStaffPermissions } from '@/composables/useStaffPermissions'
import { updateStaffCompany } from '@/api/staff-companies'
import { MEDIA_LIMITS, deleteStaffCompanyMedia, uploadStaffCompanyMedia } from '@/api/media'
import type { CompanyMediaSlot } from '@/api/media'
import MediaImageField from '@/components/shared/MediaImageField.vue'
import MediaLanguageSelect from '@/components/shared/MediaLanguageSelect.vue'
import LocalizedTextFields from '@/components/shared/LocalizedTextFields.vue'
import type { LocalizedField } from '@/components/shared/LocalizedTextFields.vue'
import {
  BASE_LANGUAGE,
  baseText,
  emptyDraft,
  imageIn,
  makeDraft,
  sameTranslations,
  translationsFromDraft,
  variantLanguage,
} from '@/utils/projectTexts'
import type { TextDraft } from '@/utils/projectTexts'
import { ApiResponseError } from '@/api/client'
import type { UpdateCompanyRequest } from '@/api/types'
import { STAFF_COMPANY_KEY } from './staffCompanyContext'

const { t } = useI18n()
const { showToast } = useToast()
const route = useRoute()
const { canDo } = useStaffPermissions()

// project_manage only -- see STATUS CONTROL note above for why this
// does NOT also require financial_operations the way price does.
const canEditStatus = canDo('project_manage')

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

// ---------------------------------------------------------------------------
// Status control (TASK-30 ruling 12)
// ---------------------------------------------------------------------------

const companyId = computed<string>(() => {
  const raw = route.params.id
  return typeof raw === 'string' ? raw : ''
})

// Mirrors backend/app/modules/companies/constants.py
// VALID_COMPANY_STATUS_TRANSITIONS -- kept in sync manually (small,
// stable table); the server is still the enforced source of truth,
// this only decides what the select offers.
const STATUS_TRANSITIONS: Record<string, string[]> = {
  hidden: ['active', 'archived'],
  active: ['hidden', 'archived'],
  archived: [],
}

function statusValueLabel(s: string): string {
  return t(`staff.platform.profile.statusValues.${s}`)
}

const availableTargets = computed<string[]>(() => {
  const current = company.value?.status
  if (!current) return []
  return STATUS_TRANSITIONS[current] ?? []
})

// The edit CTA only renders when there IS a legal target -- 'archived'
// is terminal, so a company in that state shows the badge with no
// button at all rather than an edit modal with an empty select.
const canShowStatusEdit = computed<boolean>(
  () => canEditStatus.value && availableTargets.value.length > 0,
)

const statusOptions = computed<{ value: string; label: string }[]>(() =>
  availableTargets.value.map((s) => ({ value: s, label: statusValueLabel(s) })),
)

const showStatusEdit = ref(false)
const statusDraft = ref('')
const savingStatus = ref(false)

function openStatusEdit(): void {
  if (!canShowStatusEdit.value) {
    console.warn(
      '[StaffCompanyProfileSection] openStatusEdit blocked: missing project_manage or no legal transition from the current status',
    )
    return
  }
  statusDraft.value = availableTargets.value[0] ?? ''
  showStatusEdit.value = true
}

async function handleStatusSave(): Promise<void> {
  if (!canEditStatus.value) {
    console.warn('[StaffCompanyProfileSection] handleStatusSave blocked: missing project_manage')
    return
  }
  const id = companyId.value
  const next = statusDraft.value
  if (!id || !next) return

  savingStatus.value = true
  try {
    await updateStaffCompany(id, { status: next })
    showStatusEdit.value = false
    showToast(t('staff.platform.profile.statusUpdated'), 'success')
    // Re-pull the detail through the shared context so every section
    // (this one included) sees the new status -- same pattern the
    // roadmap section uses after a mutation.
    await ctx?.reload()
  } catch (err) {
    const message = err instanceof ApiResponseError ? err.detail : t('common.error')
    showToast(message, 'error')
  } finally {
    savingStatus.value = false
  }
}

// ---------------------------------------------------------------------------
// Profile control: name, description, links (project_manage)
// ---------------------------------------------------------------------------

const canEditProfile = canDo('project_manage')

// The fixed division of the parts, in percent; shown, never edited.
const DISTRIBUTION_ROWS: readonly { key: string; percent: number }[] = [
  { key: 'sale', percent: 25 },
  { key: 'index', percent: 10 },
  { key: 'bonus', percent: 14 },
  { key: 'reserve', percent: 51 },
]

const showProfileEdit = ref(false)
const savingProfile = ref(false)
const TEXT_FIELDS = ['name', 'description'] as const
const draftTexts = ref<TextDraft>(emptyDraft(TEXT_FIELDS))
const textFields = computed<LocalizedField[]>(() => [
  { key: 'name', label: t('staff.platform.profile.name'), maxlength: 500 },
  {
    key: 'description',
    label: t('staff.platform.profile.description'),
    multiline: true,
    rows: 4,
    maxlength: 5000,
  },
])
const draftPromo = ref('')
const draftPresentation = ref('')

function openProfileEdit(): void {
  if (!canEditProfile.value || !company.value) return
  const c = company.value
  draftTexts.value = makeDraft(TEXT_FIELDS, c.base, c.translations)
  draftPromo.value = c.promo_video_url ?? ''
  draftPresentation.value = c.presentation_url ?? ''
  showProfileEdit.value = true
}

const canSaveProfile = computed<boolean>(() => baseText(draftTexts.value, 'name').trim().length > 0)

// Only the fields that changed travel (an omitted field is kept, null clears).
function profileChanges(): UpdateCompanyRequest {
  const c = company.value
  const body: UpdateCompanyRequest = {}
  if (!c) return body
  // The English base is compared with the base, not with the displayed
  // name -- that one is in the reader's language.
  const name = baseText(draftTexts.value, 'name').trim()
  if (name !== c.base.name) body.name = name
  const text = (value: string): string | null => value.trim() || null
  const description = text(baseText(draftTexts.value, 'description'))
  if (description !== (c.base.description ?? null)) body.description = description
  const translations = translationsFromDraft(draftTexts.value, TEXT_FIELDS, c.translations)
  if (!sameTranslations(translations, c.translations)) body.translations = translations
  if (text(draftPromo.value) !== (c.promo_video_url ?? null)) {
    body.promo_video_url = text(draftPromo.value)
  }
  if (text(draftPresentation.value) !== (c.presentation_url ?? null)) {
    body.presentation_url = text(draftPresentation.value)
  }
  return body
}

async function handleProfileSave(): Promise<void> {
  if (!canEditProfile.value || !canSaveProfile.value) return
  const id = companyId.value
  const body = profileChanges()
  if (!id) return
  if (Object.keys(body).length === 0) {
    showProfileEdit.value = false
    return
  }
  savingProfile.value = true
  try {
    await updateStaffCompany(id, body)
    showProfileEdit.value = false
    showToast(t('staff.platform.profile.profileUpdated'), 'success')
    await ctx?.reload()
  } catch (err) {
    const message = err instanceof ApiResponseError && err.detail ? err.detail : t('common.error')
    showToast(message, 'error')
  } finally {
    savingProfile.value = false
  }
}

// ---------------------------------------------------------------------------
// Pictures: logo, dark logo, cover (H36 P-131, project_manage)
// ---------------------------------------------------------------------------

interface MediaSlotView {
  slot: CompanyMediaSlot
  label: string
  url: string | null
}

// The version of the pictures being edited: the common file or a variant.
const mediaLanguage = ref<string>(BASE_LANGUAGE)

const mediaSlots = computed<MediaSlotView[]>(() => {
  const v = company.value?.image_variants
  const lang = mediaLanguage.value
  return [
    {
      slot: 'logo',
      label: t('staff.platform.profile.media.logo'),
      url: imageIn(v, lang, 'logo_url'),
    },
    {
      slot: 'logo-dark',
      label: t('staff.platform.profile.media.logoDark'),
      url: imageIn(v, lang, 'logo_dark_url'),
    },
    {
      slot: 'cover',
      label: t('staff.platform.profile.media.cover'),
      url: imageIn(v, lang, 'cover_url'),
    },
  ]
})

const mediaBusy = ref<CompanyMediaSlot | null>(null)

async function onMediaSelect(slot: CompanyMediaSlot, file: File): Promise<void> {
  if (!canEditProfile.value || !companyId.value || mediaBusy.value) return
  mediaBusy.value = slot
  try {
    await uploadStaffCompanyMedia(companyId.value, slot, file, variantLanguage(mediaLanguage.value))
    showToast(t('common.media.uploaded'), 'success')
    await ctx?.reload()
  } catch (err) {
    const message = err instanceof ApiResponseError && err.detail ? err.detail : t('common.error')
    showToast(message, 'error')
  } finally {
    mediaBusy.value = null
  }
}

async function onMediaRemove(slot: CompanyMediaSlot): Promise<void> {
  if (!canEditProfile.value || !companyId.value || mediaBusy.value) return
  mediaBusy.value = slot
  try {
    await deleteStaffCompanyMedia(companyId.value, slot, variantLanguage(mediaLanguage.value))
    showToast(t('common.media.removed'), 'success')
    await ctx?.reload()
  } catch (err) {
    // 404: the picture was already gone -- the reload shows the truth.
    if (err instanceof ApiResponseError && err.status === 404) {
      await ctx?.reload()
    } else {
      showToast(t('common.error'), 'error')
    }
  } finally {
    mediaBusy.value = null
  }
}

function formatPrice(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`
}

// No local fetch -- the parent detail view owns the company load and
// provides it via STAFF_COMPANY_KEY. The retry button calls ctx.reload.
</script>

<template>
  <div class="scp">
    <!-- Loading -->
    <CLoader v-if="loading" centered />

    <!-- Error -->
    <CEmptyState v-else-if="error" tone="danger" :title="t('common.error')">
      <template #actions>
        <CButton variant="secondary" size="sm" inline @click="reload">
          {{ t('common.retry') }}
        </CButton>
      </template>
    </CEmptyState>

    <!-- Loaded -->
    <template v-else-if="company">
      <!-- Cover (FP-25 self-hide when absent): the media card's cover (K07) -->
      <article v-if="company.cover_url" class="ds-card ds-card--media">
        <div class="ds-card__media">
          <img :src="company.cover_url" :alt="company.name" />
        </div>
      </article>

      <!-- Name and status, each with its edit (K23 rows) -->
      <ul class="ds-rows">
        <li class="ds-row">
          <span class="ds-row__body">
            <span class="ds-row__meta">{{ t('staff.platform.profile.name') }}</span>
            <span class="ds-row__title">{{ company.name }}</span>
          </span>
          <span v-if="canEditProfile" class="ds-row__trail">
            <CButton variant="outline" size="sm" inline @click="openProfileEdit">
              {{ t('staff.platform.profile.profileEditCta') }}
            </CButton>
          </span>
        </li>
        <li class="ds-row">
          <span class="ds-row__body">
            <span class="ds-row__meta">{{ t('staff.platform.profile.status') }}</span>
            <span>
              <CBadge
                :variant="statusVariant(company.status)"
                :text="statusValueLabel(company.status)"
              />
            </span>
          </span>
          <span v-if="canShowStatusEdit" class="ds-row__trail">
            <CButton variant="outline" size="sm" inline @click="openStatusEdit">
              {{ t('staff.platform.profile.statusEditCta') }}
            </CButton>
          </span>
        </li>
      </ul>

      <!-- Price of a part, parts (K49) -->
      <dl class="ds-kv">
        <div class="ds-kv__row">
          <dt>{{ t('staff.platform.profile.price') }}</dt>
          <dd>{{ formatPrice(company.price_per_unit_cents) }}</dd>
        </div>
        <div class="ds-kv__row">
          <dt>{{ t('staff.platform.profile.totalSupply') }}</dt>
          <dd>{{ company.total_supply.toLocaleString() }}</dd>
        </div>
      </dl>

      <!-- Description (FP-25 self-hide when absent) -->
      <section v-if="company.description" class="scp__section">
        <h2 class="ds-section-title">
          {{ t('staff.platform.profile.description') }}
        </h2>
        <p class="scp__description">
          {{ company.description }}
        </p>
      </section>

      <!-- Pictures (H36): the logo, the dark logo and the cover, as files (K30) -->
      <section class="scp__section">
        <h2 class="ds-section-title">
          {{ t('staff.platform.profile.media.title') }}
        </h2>
        <MediaLanguageSelect v-model="mediaLanguage" />
        <MediaImageField
          v-for="m in mediaSlots"
          :key="m.slot"
          :label="m.label"
          :url="m.url"
          :max-bytes="MEDIA_LIMITS[m.slot]"
          :busy="mediaBusy === m.slot"
          :disabled="!canEditProfile || (mediaBusy !== null && mediaBusy !== m.slot)"
          @select="(file) => onMediaSelect(m.slot, file)"
          @remove="onMediaRemove(m.slot)"
        />
      </section>

      <!-- External links (FP-25 self-hide each when absent): K23 rows that open the link -->
      <section v-if="company.promo_video_url || company.presentation_url" class="scp__section">
        <h2 class="ds-section-title">
          {{ t('staff.platform.profile.links') }}
        </h2>
        <ul class="ds-rows">
          <li v-if="company.promo_video_url" class="ds-row">
            <span class="ds-row__lead"><ExternalLink size="sm" /></span>
            <span class="ds-row__body">
              <a
                class="ds-row__link"
                :href="company.promo_video_url"
                target="_blank"
                rel="noopener"
              >
                <span class="ds-row__title">{{ t('staff.platform.profile.promoVideoUrl') }}</span>
              </a>
            </span>
          </li>
          <li v-if="company.presentation_url" class="ds-row">
            <span class="ds-row__lead"><ExternalLink size="sm" /></span>
            <span class="ds-row__body">
              <a
                class="ds-row__link"
                :href="company.presentation_url"
                target="_blank"
                rel="noopener"
              >
                <span class="ds-row__title">{{ t('staff.platform.profile.presentationUrl') }}</span>
              </a>
            </span>
          </li>
        </ul>
      </section>

      <!-- The division of the parts: fixed, read only (K49) -->
      <section class="scp__section">
        <h2 class="ds-section-title">
          {{ t('staff.platform.profile.distribution.title') }}
        </h2>
        <dl class="ds-kv">
          <div v-for="row in DISTRIBUTION_ROWS" :key="row.key" class="ds-kv__row">
            <dt>{{ t(`staff.platform.profile.distribution.rows.${row.key}`) }}</dt>
            <dd>{{ row.percent }}%</dd>
          </div>
        </dl>
        <p class="scp__description">
          {{ t('staff.platform.profile.distribution.hint') }}
        </p>
      </section>
    </template>

    <!-- Defensive empty (company null but no error/loading -- shouldn't happen) -->
    <CEmptyState v-else :title="t('common.noResults')" />

    <!-- Profile edit modal: name, description, links (project_manage-gated) -->
    <CModal
      :open="showProfileEdit"
      :title="t('staff.platform.profile.profileEditTitle')"
      @close="showProfileEdit = false"
    >
      <LocalizedTextFields v-model="draftTexts" :fields="textFields" />
      <CInput
        v-model="draftPromo"
        :label="t('staff.platform.profile.promoVideoUrl')"
        :placeholder="t('staff.platform.urlPlaceholder')"
      />
      <CInput
        v-model="draftPresentation"
        :label="t('staff.platform.profile.presentationUrl')"
        :placeholder="t('staff.platform.urlPlaceholder')"
      />
      <p class="ds-field__hint">{{ t('staff.platform.profile.profileEditHint') }}</p>
      <div class="ds-dialog__actions">
        <CButton variant="outline" size="sm" inline @click="showProfileEdit = false">
          {{ t('common.cancel') }}
        </CButton>
        <CButton
          variant="primary"
          size="sm"
          inline
          :loading="savingProfile"
          :disabled="!canSaveProfile"
          @click="handleProfileSave"
        >
          {{ t('common.save') }}
        </CButton>
      </div>
    </CModal>

    <!-- Status edit modal (project_manage-gated) -->
    <CModal
      :open="showStatusEdit"
      :title="t('staff.platform.profile.statusEditTitle')"
      @close="showStatusEdit = false"
    >
      <p class="ds-dialog__text">
        {{ t('staff.platform.profile.statusEditHint') }}
      </p>
      <CSelect
        v-model="statusDraft"
        :label="t('staff.platform.profile.status')"
        :options="statusOptions"
      />
      <div class="ds-dialog__actions">
        <CButton variant="outline" size="sm" inline @click="showStatusEdit = false">
          {{ t('common.cancel') }}
        </CButton>
        <CButton
          variant="primary"
          size="sm"
          inline
          :loading="savingStatus"
          :disabled="!statusDraft"
          @click="handleStatusSave"
        >
          {{ t('common.save') }}
        </CButton>
      </div>
    </CModal>
  </div>
</template>

<style scoped>
.scp {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: var(--space-5);
  align-content: start;
}

.scp__section {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: var(--space-3);
}
.scp__description {
  margin: 0;
  font-size: var(--fs-sm);
  line-height: var(--lh-normal);
  color: var(--text-secondary);
  white-space: pre-wrap;
  max-inline-size: var(--maxw-prose);
}
</style>
