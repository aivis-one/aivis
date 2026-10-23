<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- StaffCompanyPoolSection (a project's pool of parts)
// =============================================================================
//
// The pool is the part of the project's parts that is offered for sale. It is
// read here (how many parts it holds, how many are sold, how many are left)
// and created here when the project has none yet: a project can have products
// only after it has a pool.
//
// In the standard division 25 percent of the parts are for sale, so 25 is what
// the creation form starts with. A pool is created once; this screen has no
// control that makes it larger afterwards -- parts for sale are not added.
//
// GET  /api/v1/staff/companies/{id}/pool   (company_manage)
// POST /api/v1/staff/companies/{id}/pool   (project_manage AND financial_operations)
//
// The pool's percentage is the server's number (Decimal); this screen shows it
// as it came and does no arithmetic on it.
// =============================================================================

import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { CBadge, CButton, CInput, CLoader, CModal } from '@/components/ui'
import { ApiResponseError } from '@/api/client'
import { createStaffCompanyPool, fetchStaffCompanyPool } from '@/api/staff-companies'
import { useStaffPermissions } from '@/composables/useStaffPermissions'
import { useToast } from '@/composables/useToast'
import { formatNumber } from '@/utils/format'
import type { PoolResponse } from '@/api/types'

const { t, locale } = useI18n()
const route = useRoute()
const { showToast } = useToast()
const { canDo } = useStaffPermissions()

// Creating the pool is a financial act: both rights, as the server asks.
const canManage = canDo('project_manage')
const canFinancial = canDo('financial_operations')
const canCreate = computed<boolean>(() => canManage.value && canFinancial.value)

const companyId = computed<string>(() => {
  const raw = route.params.id
  return typeof raw === 'string' ? raw : ''
})

const pool = ref<PoolResponse | null>(null)
const loading = ref(true)
const error = ref(false)

async function load(): Promise<void> {
  const id = companyId.value
  if (!id) return
  loading.value = true
  error.value = false
  try {
    pool.value = await fetchStaffCompanyPool(id)
  } catch {
    error.value = true
  } finally {
    loading.value = false
  }
}

// -- Creating the pool --------------------------------------------------------

const showCreate = ref(false)
const percentDraft = ref('25')
const saving = ref(false)

// A percentage above 0 and up to 100, with up to four decimals (the server's).
const percentValid = computed<boolean>(() => {
  const text = percentDraft.value.trim()
  if (!/^\d{1,3}(\.\d{1,4})?$/.test(text)) return false
  const n = Number(text)
  return n > 0 && n <= 100
})

function openCreate(): void {
  if (!canCreate.value) return
  percentDraft.value = '25'
  showCreate.value = true
}

async function handleCreate(): Promise<void> {
  if (!canCreate.value || !percentValid.value) return
  saving.value = true
  try {
    pool.value = await createStaffCompanyPool(companyId.value, {
      equity_percent: percentDraft.value.trim(),
    })
    showCreate.value = false
    showToast(t('staff.platform.pool.created'), 'success')
  } catch (err) {
    showToast(
      err instanceof ApiResponseError && err.detail ? err.detail : t('common.error'),
      'error',
    )
  } finally {
    saving.value = false
  }
}

watch(companyId, () => void load())
onMounted(load)
</script>

<template>
  <div class="scpool">
    <div v-if="loading" class="scpool__center">
      <CLoader :size="28" />
    </div>

    <div v-else-if="error" class="scpool__center">
      <p class="scpool__error">{{ t('common.error') }}</p>
      <CButton variant="secondary" size="sm" @click="load">
        {{ t('common.retry') }}
      </CButton>
    </div>

    <template v-else-if="pool">
      <p class="scpool__hint">{{ t('staff.platform.pool.hint') }}</p>
      <div class="scpool__row">
        <span class="scpool__label">{{ t('staff.platform.pool.status') }}</span>
        <CBadge
          :variant="pool.status === 'active' ? 'success' : 'neutral'"
          :text="pool.status === 'active' ? t('staff.platform.pool.active') : pool.status"
        />
      </div>
      <div class="scpool__row">
        <span class="scpool__label">{{ t('staff.platform.pool.share') }}</span>
        <span class="scpool__value">{{ pool.equity_percent }}%</span>
      </div>
      <div class="scpool__row">
        <span class="scpool__label">{{ t('staff.platform.pool.total') }}</span>
        <span class="scpool__value">{{ formatNumber(pool.total_options, locale) }}</span>
      </div>
      <div class="scpool__row">
        <span class="scpool__label">{{ t('staff.platform.pool.sold') }}</span>
        <span class="scpool__value">{{ formatNumber(pool.consumed, locale) }}</span>
      </div>
      <div class="scpool__row">
        <span class="scpool__label">{{ t('staff.platform.pool.left') }}</span>
        <span class="scpool__value">{{ formatNumber(pool.remaining, locale) }}</span>
      </div>
      <p class="scpool__note">{{ t('staff.platform.pool.fixedNote') }}</p>
    </template>

    <template v-else>
      <p class="scpool__hint">{{ t('staff.platform.pool.none') }}</p>
      <CButton v-if="canCreate" variant="primary" size="sm" @click="openCreate">
        {{ t('staff.platform.pool.create') }}
      </CButton>
    </template>

    <CModal :open="showCreate" @close="showCreate = false">
      <h3 class="scpool__modal-title">
        {{ t('staff.platform.pool.createTitle') }}
      </h3>
      <p class="scpool__modal-text">
        {{ t('staff.platform.pool.createHint') }}
      </p>
      <CInput
        v-model="percentDraft"
        inputmode="decimal"
        autocomplete="off"
        :label="t('staff.platform.pool.percentLabel')"
        :error="
          percentDraft.trim() !== '' && !percentValid
            ? t('staff.platform.pool.percentError')
            : undefined
        "
      />
      <div class="scpool__modal-actions">
        <CButton variant="outline" size="sm" @click="showCreate = false">
          {{ t('common.cancel') }}
        </CButton>
        <CButton
          variant="primary"
          size="sm"
          :loading="saving"
          :disabled="!percentValid"
          @click="handleCreate"
        >
          {{ t('staff.platform.pool.create') }}
        </CButton>
      </div>
    </CModal>
  </div>
</template>

<style scoped>
.scpool {
  padding: var(--space-4);
}

.scpool__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: var(--center-sm);
  gap: var(--space-3);
}

.scpool__error {
  margin: 0;
  font-size: var(--fs-sm);
  color: var(--danger);
}

.scpool__hint,
.scpool__note {
  margin: 0 0 var(--space-4);
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  max-width: var(--maxw-prose);
}

.scpool__note {
  margin: var(--space-4) 0 0;
  color: var(--text-tertiary);
}

.scpool__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-3) 0;
  border-bottom: 1px solid var(--border-default);
}

.scpool__label {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
}

.scpool__value {
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--text-primary);
}

.scpool__modal-title {
  font-size: var(--fs-h4);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 var(--space-2);
}

.scpool__modal-text {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  margin: 0 0 var(--space-3);
  max-width: var(--maxw-prose);
}

.scpool__modal-actions {
  display: flex;
  gap: var(--space-2);
  margin-top: var(--space-4);
}
</style>
