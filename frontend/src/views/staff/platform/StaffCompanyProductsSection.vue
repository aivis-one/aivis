<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- StaffCompanyProductsSection (a project's products)
// =============================================================================
//
// The products on sale of one project, with the two things a staff member does
// to them: create a product (a package of a fixed number of parts at the
// project's price of a part) and change an existing product's text (name,
// description, cover). A product can be created only after the project has a
// pool of parts for sale (the Parts section).
//
// WHAT THE LIST SHOWS. The storefront's list of the project's active products
// is the only list there is for staff; a product that is hidden or archived is
// not in it. For that reason the screen has no control that takes a product off
// sale: it would drop out of the only list the screen has. The project's own
// account shows its products in every status.
//
// GET  /api/v1/public/products?company_id=   (the storefront's list)
// POST /api/v1/staff/products                (project_manage AND financial_operations)
// PATCH /api/v1/staff/products/{id}          (project_manage)
// =============================================================================

import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Package } from 'lucide-vue-next'
import { CButton, CEmptyState, CInput, CLoader, CModal, CTextarea } from '@/components/ui'
import { ApiResponseError } from '@/api/client'
import { listProducts } from '@/api/products'
import { createStaffProduct, updateStaffProduct } from '@/api/staff-products'
import type { StaffUpdateProductRequest } from '@/api/staff-products'
import { useStaffPermissions } from '@/composables/useStaffPermissions'
import { useToast } from '@/composables/useToast'
import { formatNumber, formatPrice } from '@/utils/format'
import type { PublicProductResponse } from '@/api/types'

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

const items = ref<PublicProductResponse[]>([])
const loading = ref(true)
const error = ref(false)

async function load(): Promise<void> {
  const id = companyId.value
  if (!id) return
  loading.value = true
  error.value = false
  try {
    items.value = (await listProducts({ company_id: id, per_page: 100 })).items
  } catch {
    error.value = true
  } finally {
    loading.value = false
  }
}

function serverReason(err: unknown): string {
  return err instanceof ApiResponseError && err.detail ? err.detail : t('common.error')
}

// -- The form (create and edit) -------------------------------------------------

const showForm = ref(false)
const editing = ref<PublicProductResponse | null>(null)
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

function openEdit(product: PublicProductResponse): void {
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
    <p class="scprod__hint">{{ t('staff.platform.products.hint') }}</p>

    <div v-if="canCreate" class="scprod__toolbar">
      <CButton variant="primary" size="sm" @click="openCreate">
        {{ t('staff.platform.products.create') }}
      </CButton>
    </div>

    <div v-if="loading" class="scprod__center">
      <CLoader :size="28" />
    </div>

    <div v-else-if="error" class="scprod__center">
      <p class="scprod__error">{{ t('common.error') }}</p>
      <CButton variant="secondary" size="sm" @click="load">
        {{ t('common.retry') }}
      </CButton>
    </div>

    <CEmptyState v-else-if="!items.length" :title="t('staff.platform.products.empty')">
      <template #icon>
        <Package :size="40" />
      </template>
    </CEmptyState>

    <ul v-else class="scprod__list">
      <li v-for="p in items" :key="p.id" class="scprod__item">
        <div class="scprod__info">
          <div class="scprod__name">{{ p.name }}</div>
          <div v-if="p.description" class="scprod__desc">{{ p.description }}</div>
          <div class="scprod__meta">
            {{
              t('staff.platform.products.meta', {
                size: formatNumber(p.package_size, locale),
                price: formatPrice(p.price_per_unit_cents, 'USD'),
                left: formatNumber(p.available_packages, locale),
              })
            }}
          </div>
        </div>
        <CButton v-if="canEdit" variant="outline" size="sm" @click="openEdit(p)">
          {{ t('common.edit') }}
        </CButton>
      </li>
    </ul>

    <CModal :open="showForm" @close="showForm = false">
      <h3 class="scprod__modal-title">
        {{
          editing
            ? t('staff.platform.products.editTitle')
            : t('staff.platform.products.createTitle')
        }}
      </h3>
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
        <p class="scprod__modal-note">{{ t('staff.platform.products.packageSizeNote') }}</p>
      </template>
      <div class="scprod__modal-actions">
        <CButton variant="outline" size="sm" @click="showForm = false">
          {{ t('common.cancel') }}
        </CButton>
        <CButton
          variant="primary"
          size="sm"
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
  padding: var(--space-4);
}

.scprod__hint {
  margin: 0 0 var(--space-3);
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  max-width: var(--maxw-prose);
}

.scprod__toolbar {
  margin-bottom: var(--space-4);
}

.scprod__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: var(--center-sm);
  gap: var(--space-3);
}

.scprod__error {
  margin: 0;
  font-size: var(--fs-sm);
  color: var(--danger);
}

.scprod__list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.scprod__item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-4) 0;
  border-bottom: 1px solid var(--border-default);
}

.scprod__info {
  flex: 1;
  min-width: 0;
}

.scprod__name {
  font-size: var(--fs-sm);
  font-weight: 700;
  color: var(--text-primary);
}

.scprod__desc {
  margin-top: var(--space-1);
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  max-width: var(--maxw-prose);
}

.scprod__meta {
  margin-top: var(--space-1);
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
}

.scprod__modal-title {
  font-size: var(--fs-h4);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 var(--space-3);
}

.scprod__modal-note {
  margin: 0 0 var(--space-3);
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
}

.scprod__modal-actions {
  display: flex;
  gap: var(--space-2);
  margin-top: var(--space-4);
}
</style>
