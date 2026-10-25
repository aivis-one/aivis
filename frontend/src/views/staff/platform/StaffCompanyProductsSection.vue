<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- StaffCompanyProductsSection (a project's products)
// =============================================================================
//
// The products of one project in EVERY status (active, hidden, archived), with
// what a staff member does to them: create a product (a package of a fixed
// number of parts at the project's price of a part), change an existing
// product's text (name, description), its cover (a file) and move it between
// statuses -- Hide, Archive and Return. A product can be created only after the project has
// a pool of parts for sale (the Parts section).
//
// Only the moves the server allows are offered: an active product can be hidden
// or archived, a hidden one returned or archived, an archived one stays.
//
// GET   /api/v1/staff/companies/{id}/products  (company_manage; every status, paged)
// POST  /api/v1/staff/products                 (project_manage AND financial_operations)
// PATCH /api/v1/staff/products/{id}            (project_manage)
// PATCH /api/v1/staff/products/{id}/status     (project_manage)
// PUT|DELETE /api/v1/staff/companies/{id}/products/{productId}/cover (project_manage)
//
// LANGUAGES (H38 P-132). Name and description are edited in every language of
// the interface (LocalizedTextFields), English required; the cover per version
// (MediaLanguageSelect): the common file or one language's variant. The edit
// form starts from the product's base and translations, never from the
// displayed texts, which are in the reader's language.
//
// THE COVER IS A FILE (H36 P-131). It is uploaded and removed at once from the
// edit form, not by its Save, and only for a product that exists: on create
// there is no product to attach it to yet, so the form says so.
// =============================================================================

import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Package } from '@/components/ui/icons'
import { CBadge, CButton, CEmptyState, CInput, CModal } from '@/components/ui'
import CActionMenu from '@/components/ui/CActionMenu.vue'
import type { ActionMenuItem } from '@/components/ui/CActionMenu.vue'
import CAlert from '@/components/ui/CAlert.vue'
import CListSkeleton from '@/components/ui/CListSkeleton.vue'
import CPager from '@/components/ui/CPager.vue'
import { useUrlPage } from '@/components/ui/useUrlPage'
import { ApiResponseError } from '@/api/client'
import {
  allowedProductStatuses,
  createStaffProduct,
  fetchStaffCompanyProducts,
  updateStaffProduct,
  updateStaffProductStatus,
} from '@/api/staff-products'
import type { StaffProductStatus, StaffUpdateProductRequest } from '@/api/staff-products'
import { MEDIA_LIMITS, deleteStaffProductCover, uploadStaffProductCover } from '@/api/media'
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
import { useStaffPermissions } from '@/composables/useStaffPermissions'
import { useToast } from '@/composables/useToast'
import { tOrRaw } from '@/utils/i18n'
import { formatNumber, formatPrice } from '@/utils/format'
import type { ProductResponse } from '@/api/generated'
import { useReloadOnLocale } from '@/composables/useReloadOnLocale'

const { t, locale } = useI18n()
const route = useRoute()
const { showToast } = useToast()
const { canDo } = useStaffPermissions()

const canEdit = canDo('project_manage')
const canFinancial = canDo('financial_operations')
const canCreate = computed<boolean>(() => canEdit.value && canFinancial.value)

const companyId = computed<string>(() => {
  const raw = route.params.id
  return typeof raw === 'string' ? raw : ''
})

const items = ref<ProductResponse[]>([])
const total = ref(0)
const page = useUrlPage()
const perPage = 20
const loading = ref(true)
const error = ref(false)

const totalPages = computed(() => Math.ceil(total.value / perPage))

async function load(): Promise<void> {
  const id = companyId.value
  if (!id) return
  loading.value = true
  error.value = false
  try {
    const resp = await fetchStaffCompanyProducts(id, { page: page.value, per_page: perPage })
    items.value = resp.items
    total.value = resp.total
  } catch {
    error.value = true
  } finally {
    loading.value = false
  }
}

function goToPage(n: number): void {
  page.value = n
  void load()
}

function serverReason(err: unknown): string {
  return err instanceof ApiResponseError && err.detail ? err.detail : t('common.error')
}

// -- Status: Hide, Archive, Return ------------------------------------------------

function statusLabel(status: string): string {
  return tOrRaw(t, `comp.products.status.${status}`, status)
}

function statusVariant(status: string): 'success' | 'warning' | 'neutral' {
  if (status === 'active') return 'success'
  if (status === 'hidden') return 'warning'
  return 'neutral'
}

/** The moves offered on a product: the server's table, and only for a member who may change a status. */
function movesOf(product: ProductResponse): StaffProductStatus[] {
  return canEdit.value ? allowedProductStatuses(product.status) : []
}

function moveKey(to: StaffProductStatus): string {
  if (to === 'hidden') return 'staff.platform.products.hide'
  if (to === 'archived') return 'staff.platform.products.archive'
  return 'staff.platform.products.return'
}

/** The acts of a product's row, in one Action menu (K26): its moves, then Edit. */
function rowActions(product: ProductResponse): ActionMenuItem[] {
  const items: ActionMenuItem[] = movesOf(product).map((to) => ({
    value: to,
    label: t(moveKey(to)),
    danger: to === 'archived',
    disabled: movingId.value === product.id,
  }))
  if (canEdit.value) items.push({ value: 'edit', label: t('common.edit') })
  return items
}

function onRowAction(product: ProductResponse, value: string): void {
  if (value === 'edit') openEdit(product)
  else requestMove(product, value as StaffProductStatus)
}

const movingId = ref<string | null>(null)
const archiveTarget = ref<ProductResponse | null>(null)

async function applyMove(product: ProductResponse, to: StaffProductStatus): Promise<void> {
  if (movingId.value) return
  movingId.value = product.id
  try {
    await updateStaffProductStatus(product.id, to)
    showToast(t('staff.platform.products.statusChanged'), 'success')
    archiveTarget.value = null
    await load()
  } catch (err) {
    showToast(serverReason(err), 'error')
  } finally {
    movingId.value = null
  }
}

function requestMove(product: ProductResponse, to: StaffProductStatus): void {
  // Archiving is final, so it asks first; hiding and returning are undone by each other.
  if (to === 'archived') {
    archiveTarget.value = product
    return
  }
  void applyMove(product, to)
}

// -- The form (create and edit) -------------------------------------------------

const showForm = ref(false)
const editing = ref<ProductResponse | null>(null)
const saving = ref(false)

const TEXT_FIELDS = ['name', 'description'] as const
const draftTexts = ref<TextDraft>(emptyDraft(TEXT_FIELDS))
const textFields = computed<LocalizedField[]>(() => [
  { key: 'name', label: t('staff.platform.products.fieldName'), maxlength: 500 },
  {
    key: 'description',
    label: t('staff.platform.products.fieldDescription'),
    multiline: true,
    maxlength: 5000,
  },
])
const draftPackageSize = ref('')

const trimmedName = computed(() => baseText(draftTexts.value, 'name').trim())

// A whole number of parts, at least one; fixed after creation.
const packageSize = computed<number | null>(() => {
  const text = draftPackageSize.value.trim()
  if (!/^\d+$/.test(text)) return null
  const n = Number(text)
  return Number.isSafeInteger(n) && n >= 1 ? n : null
})

const canSubmit = computed<boolean>(() => {
  if (trimmedName.value === '') return false
  return editing.value !== null || packageSize.value !== null
})

function openCreate(): void {
  if (!canCreate.value) return
  editing.value = null
  draftTexts.value = emptyDraft(TEXT_FIELDS)
  draftPackageSize.value = ''
  showForm.value = true
}

function openEdit(product: ProductResponse): void {
  if (!canEdit.value) return
  editing.value = product
  draftTexts.value = makeDraft(TEXT_FIELDS, product.base, product.translations)
  coverLanguage.value = BASE_LANGUAGE
  coverVariants.value = product.image_variants
  showForm.value = true
}

async function handleSave(): Promise<void> {
  if (!canSubmit.value) return
  saving.value = true
  try {
    const current = editing.value
    if (current) {
      // Only what changed travels (an omitted field is kept, null clears).
      const body: StaffUpdateProductRequest = {}
      // Compared with the English base, not the displayed (reader's) texts.
      if (trimmedName.value !== current.base.name) body.name = trimmedName.value
      const description = baseText(draftTexts.value, 'description').trim()
      if (description !== (current.base.description ?? '')) body.description = description || null
      const translations = translationsFromDraft(
        draftTexts.value,
        TEXT_FIELDS,
        current.translations,
      )
      if (!sameTranslations(translations, current.translations)) body.translations = translations
      if (Object.keys(body).length > 0) await updateStaffProduct(current.id, body)
      showToast(t('staff.platform.products.updated'), 'success')
    } else if (packageSize.value !== null) {
      const description = baseText(draftTexts.value, 'description').trim()
      await createStaffProduct({
        company_id: companyId.value,
        name: trimmedName.value,
        description: description || null,
        translations: translationsFromDraft(draftTexts.value, TEXT_FIELDS, {}),
        package_size: packageSize.value,
      })
      showToast(t('staff.platform.products.created'), 'success')
    }
    showForm.value = false
    await load()
  } catch (err) {
    showToast(serverReason(err), 'error')
  } finally {
    saving.value = false
  }
}

// -- The cover (H36): a file, immediate, edit only --------------------------------

// The covers of the product being edited, per language ("en" = the common
// file); follow the uploads and removals so the form shows the truth without
// waiting for the list. coverLanguage picks the version edited.
const coverVariants = ref<unknown>(null)
const coverLanguage = ref<string>(BASE_LANGUAGE)
const coverUrl = computed<string | null>(() =>
  imageIn(coverVariants.value, coverLanguage.value, 'cover_url'),
)
const coverBusy = ref(false)

async function onCoverSelect(file: File): Promise<void> {
  const current = editing.value
  if (!canEdit.value || !current || coverBusy.value) return
  coverBusy.value = true
  try {
    const updated = await uploadStaffProductCover(
      companyId.value,
      current.id,
      file,
      variantLanguage(coverLanguage.value),
    )
    coverVariants.value = updated.image_variants
    showToast(t('common.media.uploaded'), 'success')
    await load()
  } catch (err) {
    showToast(serverReason(err), 'error')
  } finally {
    coverBusy.value = false
  }
}

async function onCoverRemove(): Promise<void> {
  const current = editing.value
  if (!canEdit.value || !current || coverBusy.value) return
  coverBusy.value = true
  try {
    await deleteStaffProductCover(companyId.value, current.id, variantLanguage(coverLanguage.value))
    dropCover()
    showToast(t('common.media.removed'), 'success')
    await load()
  } catch (err) {
    // 404: the cover was already gone.
    if (err instanceof ApiResponseError && err.status === 404) {
      dropCover()
      await load()
    } else {
      showToast(serverReason(err), 'error')
    }
  } finally {
    coverBusy.value = false
  }
}

// The removed version leaves the form at once; the list reload brings the rest.
function dropCover(): void {
  const variants = { ...((coverVariants.value ?? {}) as Record<string, unknown>) }
  delete variants[coverLanguage.value]
  coverVariants.value = variants
}

watch(companyId, () => void load())
// H38: project data is in the reader's language -- re-read it on a switch.
useReloadOnLocale(() => load())

onMounted(load)
</script>

<template>
  <div class="scprod">
    <CAlert tone="info">
      {{ t('staff.platform.products.hint') }}
    </CAlert>

    <div v-if="canCreate" class="scprod__toolbar">
      <CButton variant="primary" size="sm" inline @click="openCreate">
        {{ t('staff.platform.products.create') }}
      </CButton>
    </div>

    <CListSkeleton v-if="loading" />

    <CEmptyState v-else-if="error" tone="danger" :title="t('common.error')">
      <template #actions>
        <CButton variant="secondary" size="sm" inline @click="load">
          {{ t('common.retry') }}
        </CButton>
      </template>
    </CEmptyState>

    <CEmptyState v-else-if="!items.length" :title="t('staff.platform.products.empty')">
      <template #icon>
        <Package />
      </template>
    </CEmptyState>

    <!-- The products (K23 rows) -->
    <ul v-else class="ds-rows scprod__list">
      <li v-for="p in items" :key="p.id" class="ds-row scprod__item">
        <span class="ds-row__lead"><Package size="sm" /></span>
        <span class="ds-row__body">
          <span class="ds-row__title">{{ p.name }}</span>
          <span v-if="p.description" class="ds-row__meta">{{ p.description }}</span>
          <span class="ds-row__meta">
            {{
              t('staff.platform.products.meta', {
                size: formatNumber(p.package_size, locale),
                price: formatPrice(p.price_per_unit_cents, 'USD'),
              })
            }}
          </span>
        </span>
        <span class="ds-row__trail">
          <CBadge :variant="statusVariant(p.status)" :text="statusLabel(p.status)" />
          <CActionMenu
            v-if="rowActions(p).length > 1"
            :label="t('common.actions', { title: p.name })"
            icon-key="more"
            icon-only
            align="end"
            :items="rowActions(p)"
            @select="(value) => onRowAction(p, value)"
          />
          <button
            v-else-if="canEdit"
            type="button"
            class="ds-button ds-button--secondary"
            data-size="sm"
            @click="openEdit(p)"
          >
            <span>{{ t('common.edit') }}</span>
          </button>
        </span>
      </li>
    </ul>

    <!-- Pagination (K17) -->
    <CPager
      v-if="!loading && !error"
      :page="page"
      :total-pages="totalPages"
      @update:page="goToPage"
    />

    <CModal
      :open="archiveTarget !== null"
      :title="t('staff.platform.products.archiveTitle')"
      @close="archiveTarget = null"
    >
      <p class="ds-dialog__text">{{ t('staff.platform.products.archiveBody') }}</p>
      <div class="ds-dialog__actions">
        <CButton variant="outline" size="sm" inline @click="archiveTarget = null">
          {{ t('common.cancel') }}
        </CButton>
        <CButton
          variant="primary"
          size="sm"
          inline
          :loading="movingId !== null"
          @click="archiveTarget && applyMove(archiveTarget, 'archived')"
        >
          {{ t('staff.platform.products.archive') }}
        </CButton>
      </div>
    </CModal>

    <CModal
      :open="showForm"
      :title="
        editing ? t('staff.platform.products.editTitle') : t('staff.platform.products.createTitle')
      "
      @close="showForm = false"
    >
      <LocalizedTextFields v-model="draftTexts" :fields="textFields" />
      <MediaLanguageSelect v-if="editing" v-model="coverLanguage" />
      <MediaImageField
        v-if="editing"
        :label="t('staff.platform.products.fieldCover')"
        :url="coverUrl"
        :max-bytes="MEDIA_LIMITS.productCover"
        :busy="coverBusy"
        :disabled="!canEdit"
        @select="onCoverSelect"
        @remove="onCoverRemove"
      />
      <div v-else class="ds-field">
        <span class="ds-field__label">{{ t('staff.platform.products.fieldCover') }}</span>
        <p class="ds-field__hint">{{ t('staff.platform.products.coverAfterCreate') }}</p>
      </div>
      <template v-if="!editing">
        <CInput
          v-model="draftPackageSize"
          inputmode="numeric"
          autocomplete="off"
          :label="t('staff.platform.products.fieldPackageSize')"
          :hint="t('staff.platform.products.packageSizeNote')"
          :error="
            draftPackageSize.trim() !== '' && packageSize === null
              ? t('staff.platform.products.packageSizeError')
              : undefined
          "
        />
      </template>
      <div class="ds-dialog__actions">
        <CButton variant="outline" size="sm" inline @click="showForm = false">
          {{ t('common.cancel') }}
        </CButton>
        <CButton
          variant="primary"
          size="sm"
          inline
          :loading="saving"
          :disabled="!canSubmit"
          @click="handleSave"
        >
          {{ t('common.save') }}
        </CButton>
      </div>
    </CModal>
  </div>
</template>

<style scoped>
.scprod {
  display: grid;
  gap: var(--space-3);
  align-content: start;
}

.scprod__toolbar {
  display: flex;
}
</style>
