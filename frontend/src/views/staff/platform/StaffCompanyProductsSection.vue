<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- StaffCompanyProductsSection (a project's products)
// =============================================================================
//
// The products of one project in EVERY status (active, hidden, archived), with
// what a staff member does to them: create a product (a package of a fixed
// number of parts at the project's price of a part), change an existing
// product's text (name, description, cover) and move it between statuses --
// Hide, Archive and Return. A product can be created only after the project has
// a pool of parts for sale (the Parts section).
//
// Only the moves the server allows are offered: an active product can be hidden
// or archived, a hidden one returned or archived, an archived one stays.
//
// GET   /api/v1/staff/companies/{id}/products  (company_manage; every status, paged)
// POST  /api/v1/staff/products                 (project_manage AND financial_operations)
// PATCH /api/v1/staff/products/{id}            (project_manage)
// PATCH /api/v1/staff/products/{id}/status     (project_manage)
// =============================================================================

import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Package } from '@/components/ui/icons'
import { CBadge, CButton, CEmptyState, CInput, CModal, CTextarea } from '@/components/ui'
import StaffAlert from '@/components/staff/StaffAlert.vue'
import StaffListSkeleton from '@/components/staff/StaffListSkeleton.vue'
import StaffPager from '@/components/staff/StaffPager.vue'
import { useUrlPage } from '@/components/staff/useUrlPage'
import { ApiResponseError } from '@/api/client'
import {
  allowedProductStatuses,
  createStaffProduct,
  fetchStaffCompanyProducts,
  updateStaffProduct,
  updateStaffProductStatus,
} from '@/api/staff-products'
import type { StaffProductStatus, StaffUpdateProductRequest } from '@/api/staff-products'
import { useStaffPermissions } from '@/composables/useStaffPermissions'
import { useToast } from '@/composables/useToast'
import { tOrRaw } from '@/utils/i18n'
import { formatNumber, formatPrice } from '@/utils/format'
import type { ProductResponse } from '@/api/generated'

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

const draftName = ref('')
const draftDescription = ref('')
const draftCover = ref('')
const draftPackageSize = ref('')

const trimmedName = computed(() => draftName.value.trim())

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
  draftName.value = ''
  draftDescription.value = ''
  draftCover.value = ''
  draftPackageSize.value = ''
  showForm.value = true
}

function openEdit(product: ProductResponse): void {
  if (!canEdit.value) return
  editing.value = product
  draftName.value = product.name
  draftDescription.value = product.description ?? ''
  draftCover.value = product.cover_url ?? ''
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
      if (trimmedName.value !== current.name) body.name = trimmedName.value
      const description = draftDescription.value.trim()
      if (description !== (current.description ?? '')) body.description = description || null
      const cover = draftCover.value.trim()
      if (cover !== (current.cover_url ?? '')) body.cover_url = cover || null
      if (Object.keys(body).length > 0) await updateStaffProduct(current.id, body)
      showToast(t('staff.platform.products.updated'), 'success')
    } else if (packageSize.value !== null) {
      const description = draftDescription.value.trim()
      const cover = draftCover.value.trim()
      await createStaffProduct({
        company_id: companyId.value,
        name: trimmedName.value,
        description: description || null,
        cover_url: cover || null,
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

watch(companyId, () => void load())
onMounted(load)
</script>

<template>
  <div class="scprod">
    <StaffAlert tone="info">
      {{ t('staff.platform.products.hint') }}
    </StaffAlert>

    <div v-if="canCreate" class="scprod__toolbar">
      <CButton variant="primary" size="sm" inline @click="openCreate">
        {{ t('staff.platform.products.create') }}
      </CButton>
    </div>

    <StaffListSkeleton v-if="loading" />

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
        <span class="ds-row__trail scprod__actions">
          <CBadge :variant="statusVariant(p.status)" :text="statusLabel(p.status)" />
          <button
            v-for="to in movesOf(p)"
            :key="to"
            type="button"
            class="ds-button ds-button--secondary"
            data-size="sm"
            :disabled="movingId === p.id"
            @click="requestMove(p, to)"
          >
            <span>{{ t(moveKey(to)) }}</span>
          </button>
          <button
            v-if="canEdit"
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
    <StaffPager
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
      <CInput v-model="draftName" :label="t('staff.platform.products.fieldName')" maxlength="500" />
      <CTextarea
        v-model="draftDescription"
        :label="t('staff.platform.products.fieldDescription')"
        maxlength="5000"
      />
      <CInput
        v-model="draftCover"
        :label="t('staff.platform.products.fieldCover')"
        :placeholder="t('staff.platform.urlPlaceholder')"
        maxlength="2000"
      />
      <template v-if="!editing">
        <CInput
          v-model="draftPackageSize"
          inputmode="numeric"
          autocomplete="off"
          :label="t('staff.platform.products.fieldPackageSize')"
          :error="
            draftPackageSize.trim() !== '' && packageSize === null
              ? t('staff.platform.products.packageSizeError')
              : undefined
          "
        />
        <p class="ds-field__hint">{{ t('staff.platform.products.packageSizeNote') }}</p>
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

/* On a narrow row the trail drops under the text instead of squeezing it: the row wraps, and the
   text keeps a floor of its own width (the system's trail does not shrink). */
.scprod__item {
  flex-wrap: wrap;
}
.scprod__item .ds-row__body {
  flex: 1 1 var(--center-sm);
}
.scprod__actions {
  flex: 0 1 auto;
  flex-wrap: wrap;
  justify-content: flex-end;
  margin-inline-start: auto;
}
</style>
