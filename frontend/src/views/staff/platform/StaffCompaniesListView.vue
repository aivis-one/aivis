<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- StaffCompaniesListView (iter 2.7 Block B)
// =============================================================================
//
// Lists every company (active / hidden / archived) with a status
// filter chip row, a name search, and pagination. Each row navigates
// to the company detail surface (/staff/platform/companies/:id) whose
// section tabs land in Block C.
//
// Source: api/staff-companies.ts::fetchStaffCompanies (company_manage
// gated server-side). This view is read + navigate only for existing
// companies -- editing lives behind the detail sections.
//
// TASK-30 admin-capability gap (W0): the one write action this view
// DOES carry is "Assign" -- promote an existing user to company
// (POST /staff/companies/assign). Before this, there was no functional
// way to produce a working company account through the product at all:
// self-service "company" onboarding set role with no CompanyProfile row
// (see users/schemas.py's _SELECTABLE_ROLES note), and neither company-
// creation endpoint had a frontend entry point. FP-23: gated on
// project_manage AND financial_operations, same combination as the
// price change (this form sets price_per_unit_cents + distribution_config
// too).
//
// Search is debounced (300ms) so each keystroke doesn't fire a request;
// the timer resets page to 1 on a new term.
// =============================================================================

import { ref, onMounted, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Building2 } from 'lucide-vue-next'
import { CBadge, CLoader, CButton, CEmptyState, CInput, CModal, CTextarea } from '@/components/ui'
import { useToast } from '@/composables/useToast'
import { useStaffPermissions } from '@/composables/useStaffPermissions'
import { useAvatar } from '@/composables/useAvatar'
import { safeNavigate } from '@/composables/safeNavigate'
import { ApiResponseError } from '@/api/client'
import { fetchStaffCompanies, assignCompany, createCompany } from '@/api/staff-companies'
import UserPicker from '@/components/staff/UserPicker.vue'
import type { CompanyResponse, UserListItem } from '@/api/types'

const { t } = useI18n()
const { showToast } = useToast()
const router = useRouter()
const { canDo } = useStaffPermissions()
const { startAvatarSession } = useAvatar()

// FP-23: assign AND create both require project_manage AND
// financial_operations, same combination as the price change
// (StaffCompanyPriceSection) -- both forms set price_per_unit_cents +
// distribution_config.
const canManage = canDo('project_manage')
const canFinancial = canDo('financial_operations')
const canManageCompanies = computed<boolean>(() => canManage.value && canFinancial.value)

const items = ref<CompanyResponse[]>([])
const total = ref(0)
const page = ref(1)
const perPage = 20
const statusFilter = ref<'' | 'active' | 'hidden' | 'archived'>('')
const search = ref('')
const loading = ref(true)
const error = ref(false)

// Debounce handle for the search box.
let searchTimer: ReturnType<typeof setTimeout> | null = null

const totalPages = computed(() => Math.ceil(total.value / perPage))

const statusVariant = (s: string) => {
  if (s === 'active') return 'success'
  if (s === 'hidden') return 'warning'
  if (s === 'archived') return 'neutral'
  return 'neutral'
}

function formatPrice(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`
}

async function loadCompanies(): Promise<void> {
  loading.value = true
  error.value = false
  try {
    const resp = await fetchStaffCompanies({
      status: statusFilter.value || undefined,
      search: search.value.trim() || undefined,
      page: page.value,
      per_page: perPage,
    })
    items.value = resp.items
    total.value = resp.total
  } catch {
    error.value = true
    showToast(t('common.error'), 'error')
  } finally {
    loading.value = false
  }
}

function setStatusFilter(s: '' | 'active' | 'hidden' | 'archived'): void {
  statusFilter.value = s
  page.value = 1
}

function openCompany(id: string): void {
  void safeNavigate(
    router.push(`/staff/platform/companies/${id}`),
    `[StaffCompaniesListView] to company ${id}`,
  )
}

// Status chip + page changes reload immediately.
watch([statusFilter, page], () => loadCompanies())

// Search debounce: reset to page 1 and reload 300ms after the last
// keystroke. The watch on `page` above won't double-fire because we
// only assign page.value = 1 when it isn't already 1.
watch(search, () => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    if (page.value !== 1) {
      page.value = 1 // triggers the [statusFilter, page] watcher -> reload
    } else {
      void loadCompanies()
    }
  }, 300)
})

onMounted(loadCompanies)

// ---------------------------------------------------------------------------
// Assign modal (TASK-30 W0)
//
// One form: pick an existing user (UserPicker), enter the commercial
// terms AssignCompanyRequest requires in full (name, price, supply,
// distribution config -- revised ruling 9: no deferred-price state for
// this endpoint, unlike create_company). Optional media/description
// fields are left blank-able; the project fills them in itself later
// via CompanySettingsView once W1 gets its own edit UI.
//
// distribution_config is entered as a company-% number + a comma-
// separated agent-levels list (both in PERCENT, converted to the 0-1
// fractions the backend's validate_distribution_config expects) rather
// than raw JSON -- this is a CREATE-time required field, unlike
// StaffCompanyProfileSection's read-only JSON dump of an existing
// company's config.
// ---------------------------------------------------------------------------

const showAssign = ref(false)
const assigning = ref(false)

const assignUserId = ref('')
const assignSelectedUser = ref<UserListItem | null>(null)
const assignName = ref('')
const assignDescription = ref('')
const assignPriceDollars = ref('')
const assignTotalSupply = ref('')
const assignSharesPerOption = ref('1')
const assignCompanyPct = ref('')
const assignAgentLevels = ref('')

function resetAssignForm(): void {
  assignUserId.value = ''
  assignSelectedUser.value = null
  assignName.value = ''
  assignDescription.value = ''
  assignPriceDollars.value = ''
  assignTotalSupply.value = ''
  assignSharesPerOption.value = '1'
  assignCompanyPct.value = ''
  assignAgentLevels.value = ''
}

function openAssign(): void {
  if (!canManageCompanies.value) {
    console.warn(
      '[StaffCompaniesListView] openAssign blocked: needs project_manage + financial_operations',
    )
    return
  }
  resetAssignForm()
  showAssign.value = true
}

function closeAssign(): void {
  showAssign.value = false
}

function onUserSelected(user: UserListItem | null): void {
  assignSelectedUser.value = user
}

// Price entered in dollars (mirrors StaffCompanyPriceSection), converted
// to integer cents for the wire.
const assignPriceCents = computed<number | null>(() => {
  const dollars = Number(assignPriceDollars.value)
  if (!Number.isFinite(dollars) || dollars <= 0) return null
  return Math.round(dollars * 100)
})

const assignTotalSupplyInt = computed<number | null>(() => {
  const n = Number(assignTotalSupply.value)
  if (!Number.isInteger(n) || n <= 0) return null
  return n
})

const assignSharesPerOptionInt = computed<number | null>(() => {
  const n = Number(assignSharesPerOption.value)
  if (!Number.isInteger(n) || n <= 0) return null
  return n
})

// company_pct: percent input (0, 100) exclusive -> fraction (0, 1) exclusive.
const assignCompanyPctFraction = computed<number | null>(() => {
  const n = Number(assignCompanyPct.value)
  if (!Number.isFinite(n) || n <= 0 || n >= 100) return null
  return n / 100
})

// agent_levels: comma-separated percents -> fractions. Empty input is a
// valid empty array (backend allows agent_levels: []).
const assignAgentLevelsFractions = computed<number[] | null>(() => {
  const raw = assignAgentLevels.value.trim()
  if (!raw) return []
  const parts = raw.split(',').map((p) => p.trim())
  const nums: number[] = []
  for (const p of parts) {
    const n = Number(p)
    if (!Number.isFinite(n) || n <= 0 || n >= 100) return null
    nums.push(n / 100)
  }
  return nums
})

// Mirrors the backend's own invariant (validate_distribution_config):
// company_pct + sum(agent_levels) <= 1.0. Checked client-side to avoid
// an obvious 400, not a substitute for it.
const assignDistributionValid = computed<boolean>(() => {
  const pct = assignCompanyPctFraction.value
  const levels = assignAgentLevelsFractions.value
  if (pct === null || levels === null) return false
  const sum = pct + levels.reduce((a, b) => a + b, 0)
  return sum <= 1.0
})

const canSubmitAssign = computed<boolean>(() => {
  return (
    !!assignUserId.value &&
    !!assignName.value.trim() &&
    assignPriceCents.value !== null &&
    assignTotalSupplyInt.value !== null &&
    assignSharesPerOptionInt.value !== null &&
    assignDistributionValid.value
  )
})

async function handleAssign(): Promise<void> {
  if (!canManageCompanies.value) {
    console.warn(
      '[StaffCompaniesListView] handleAssign blocked: needs project_manage + financial_operations',
    )
    return
  }
  if (!canSubmitAssign.value) return
  const pct = assignCompanyPctFraction.value
  const levels = assignAgentLevelsFractions.value
  if (pct === null || levels === null) return

  assigning.value = true
  try {
    await assignCompany({
      user_id: assignUserId.value,
      name: assignName.value.trim(),
      description: assignDescription.value.trim() || undefined,
      price_per_unit_cents: assignPriceCents.value as number,
      total_supply: assignTotalSupplyInt.value as number,
      shares_per_option: assignSharesPerOptionInt.value as number,
      distribution_config: { company_pct: pct, agent_levels: levels },
    })
    showToast(t('staff.platform.companies.assign.success'), 'success')
    showAssign.value = false
    page.value = 1
    await loadCompanies()
  } catch (e) {
    if (e instanceof ApiResponseError && e.detail) {
      showToast(e.detail, 'error')
    } else {
      showToast(t('common.error'), 'error')
    }
  } finally {
    assigning.value = false
  }
}

// ---------------------------------------------------------------------------
// Create modal (2026-08-30, `№199`)
//
// Mints a BRAND-NEW company: a fresh account (email + password, set by
// admin) plus its profile, in one call -- unlike Assign above, which
// promotes an EXISTING user. Same commercial-terms fields and the same
// company_pct/agent_levels percent-to-fraction handling as Assign.
//
// THE WORKFLOW THIS EXISTS FOR IS "CREATE, THEN IMMEDIATELY ENTER AVATAR
// MODE AS IT" (the owner's own description of how he sets up a
// project): on success this calls useAvatar().startAvatarSession with
// the new account's user_id, which swaps the token and navigates to the
// company dashboard itself -- there is no further click needed. The
// list is reloaded BEFORE that call (not after) so the new company is
// still visible here if the avatar swap itself fails; startAvatarSession
// never rejects (it reports its own error toast and stays on this page
// on failure), so nothing here needs a second catch around it.
// ---------------------------------------------------------------------------

const showCreate = ref(false)
const creating = ref(false)

const createEmail = ref('')
const createPassword = ref('')
const createName = ref('')
const createDescription = ref('')
const createPriceDollars = ref('')
const createTotalSupply = ref('')
const createSharesPerOption = ref('1')
const createCompanyPct = ref('')
const createAgentLevels = ref('')

// Base64url alphabet (64 chars, a power of two) -- `byte & 63` indexes
// it with ZERO modulo bias, unlike `byte % N` for a non-power-of-two N.
const PASSWORD_CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'
const PASSWORD_LENGTH = 20

function generatePassword(): string {
  const bytes = new Uint8Array(PASSWORD_LENGTH)
  crypto.getRandomValues(bytes)
  return Array.from(bytes, (b) => PASSWORD_CHARS[b & 63]).join('')
}

function resetCreateForm(): void {
  createEmail.value = ''
  createPassword.value = generatePassword()
  createName.value = ''
  createDescription.value = ''
  createPriceDollars.value = ''
  createTotalSupply.value = ''
  createSharesPerOption.value = '1'
  createCompanyPct.value = ''
  createAgentLevels.value = ''
}

// Adversarial-review catch (2026-08-30): `handleCreate` awaits
// `createCompany` then forces an avatar-mode navigation via
// `startAvatarSession`. Without a way to tell a STALE in-flight request
// apart from the current one, cancelling the modal (or worse, reopening
// it for a second company) while the first request is still pending let
// the first one complete later and forcibly redirect the admin into
// avatar mode as a company they'd already moved on from -- their
// SECOND form's in-progress input silently discarded. Every open/close
// bumps this token; `handleCreate` compares it after the await to
// decide whether it may still close the modal / force navigation.
let createRequestToken = 0

function openCreate(): void {
  if (!canManageCompanies.value) {
    console.warn(
      '[StaffCompaniesListView] openCreate blocked: needs project_manage + financial_operations',
    )
    return
  }
  createRequestToken++
  resetCreateForm()
  showCreate.value = true
}

function closeCreate(): void {
  createRequestToken++
  showCreate.value = false
}

// RFC 5321's actual grammar is far looser than this, but a client-side
// gate only needs to catch an obviously-wrong entry before the real
// validation (Pydantic's EmailStr, server-side) rejects it with a 422 --
// same division of labour as the price/supply numeric guards below.
const createEmailValid = computed<boolean>(() =>
  /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(createEmail.value.trim()),
)

const createPasswordValid = computed<boolean>(
  () => createPassword.value.length >= 8 && createPassword.value.length <= 128,
)

// Price entered in dollars (mirrors Assign), converted to integer cents.
const createPriceCents = computed<number | null>(() => {
  const dollars = Number(createPriceDollars.value)
  if (!Number.isFinite(dollars) || dollars <= 0) return null
  return Math.round(dollars * 100)
})

const createTotalSupplyInt = computed<number | null>(() => {
  const n = Number(createTotalSupply.value)
  if (!Number.isInteger(n) || n <= 0) return null
  return n
})

const createSharesPerOptionInt = computed<number | null>(() => {
  const n = Number(createSharesPerOption.value)
  if (!Number.isInteger(n) || n <= 0) return null
  return n
})

// company_pct: percent input (0, 100) exclusive -> fraction (0, 1) exclusive.
const createCompanyPctFraction = computed<number | null>(() => {
  const n = Number(createCompanyPct.value)
  if (!Number.isFinite(n) || n <= 0 || n >= 100) return null
  return n / 100
})

// agent_levels: comma-separated percents -> fractions. Empty input is a
// valid empty array (backend allows agent_levels: []).
const createAgentLevelsFractions = computed<number[] | null>(() => {
  const raw = createAgentLevels.value.trim()
  if (!raw) return []
  const parts = raw.split(',').map((p) => p.trim())
  const nums: number[] = []
  for (const p of parts) {
    const n = Number(p)
    if (!Number.isFinite(n) || n <= 0 || n >= 100) return null
    nums.push(n / 100)
  }
  return nums
})

// Mirrors the backend's own invariant (validate_distribution_config):
// company_pct + sum(agent_levels) <= 1.0. Checked client-side to avoid
// an obvious 400, not a substitute for it.
const createDistributionValid = computed<boolean>(() => {
  const pct = createCompanyPctFraction.value
  const levels = createAgentLevelsFractions.value
  if (pct === null || levels === null) return false
  const sum = pct + levels.reduce((a, b) => a + b, 0)
  return sum <= 1.0
})

const canSubmitCreate = computed<boolean>(() => {
  return (
    createEmailValid.value &&
    createPasswordValid.value &&
    !!createName.value.trim() &&
    createPriceCents.value !== null &&
    createTotalSupplyInt.value !== null &&
    createSharesPerOptionInt.value !== null &&
    createDistributionValid.value
  )
})

async function handleCreate(): Promise<void> {
  if (!canManageCompanies.value) {
    console.warn(
      '[StaffCompaniesListView] handleCreate blocked: needs project_manage + financial_operations',
    )
    return
  }
  if (!canSubmitCreate.value) return
  const pct = createCompanyPctFraction.value
  const levels = createAgentLevelsFractions.value
  if (pct === null || levels === null) return

  const myToken = ++createRequestToken
  creating.value = true
  try {
    const resp = await createCompany({
      email: createEmail.value.trim(),
      password: createPassword.value,
      name: createName.value.trim(),
      description: createDescription.value.trim() || undefined,
      price_per_unit_cents: createPriceCents.value as number,
      total_supply: createTotalSupplyInt.value as number,
      shares_per_option: createSharesPerOptionInt.value as number,
      distribution_config: { company_pct: pct, agent_levels: levels },
    })
    showToast(t('staff.platform.companies.create.success'), 'success')
    // The company was created either way -- the call can't be un-sent --
    // so the list always reloads to show it. But if the admin closed or
    // reopened the modal while this request was in flight, this is a
    // STALE response: it may not force-close a since-reopened form or
    // force-navigate the admin away from wherever they've since gone.
    const isStale = myToken !== createRequestToken
    if (!isStale) showCreate.value = false
    page.value = 1
    await loadCompanies()
    if (!isStale) await startAvatarSession(resp.user_id)
  } catch (e) {
    if (e instanceof ApiResponseError && e.detail) {
      showToast(e.detail, 'error')
    } else {
      showToast(t('common.error'), 'error')
    }
  } finally {
    if (myToken === createRequestToken) creating.value = false
  }
}
</script>

<template>
  <div class="scl">
    <div class="scl__header">
      <h2 class="scl__title">
        {{ t('staff.platform.companies.title') }}
      </h2>
      <!-- FP-23: Create/Assign CTAs both require project_manage + financial_operations. -->
      <div v-if="canManageCompanies" class="scl__header-actions">
        <CButton variant="primary" size="sm" @click="openCreate">
          {{ t('staff.platform.companies.create.cta') }}
        </CButton>
        <CButton variant="outline" size="sm" @click="openAssign">
          {{ t('staff.platform.companies.assign.cta') }}
        </CButton>
      </div>
    </div>

    <!-- Status filter chips -->
    <div class="scl__filters">
      <button class="filter-chip" :class="{ active: !statusFilter }" @click="setStatusFilter('')">
        {{ t('staff.platform.companies.filterAll') }}
      </button>
      <button
        v-for="s in ['active', 'hidden', 'archived'] as const"
        :key="s"
        class="filter-chip"
        :class="{ active: statusFilter === s }"
        @click="setStatusFilter(s)"
      >
        {{ t(`staff.platform.companies.filter.${s}`) }}
      </button>
    </div>

    <!-- Search -->
    <!-- A4: a placeholder is not an accessible name -- it is a hint, and it
         disappears the moment the user types. The visible design is a bare
         search box, so the name goes on the control rather than into a label. -->
    <CInput
      v-model="search"
      :aria-label="t('staff.platform.companies.searchPlaceholder')"
      :placeholder="t('staff.platform.companies.searchPlaceholder')"
    />

    <!-- Loading -->
    <div v-if="loading" class="scl__center">
      <CLoader :size="32" />
    </div>

    <!-- Error -->
    <div v-else-if="error" class="scl__center">
      <CButton variant="secondary" size="sm" @click="loadCompanies">
        {{ t('common.retry') }}
      </CButton>
    </div>

    <!-- Empty -->
    <CEmptyState v-else-if="!items.length" :title="t('staff.platform.companies.empty')">
      <template #icon>
        <Building2 :size="40" />
      </template>
    </CEmptyState>

    <!-- List -->
    <template v-else>
      <div class="company-list">
        <button
          v-for="c in items"
          :key="c.id"
          type="button"
          class="company-item"
          @click="openCompany(c.id)"
        >
          <div class="company-item__info">
            <div class="company-item__name">
              {{ c.name }}
            </div>
            <div class="company-item__detail">
              {{ formatPrice(c.price_per_unit_cents) }} &bull;
              {{ t('staff.platform.companies.supply', { n: c.total_supply }) }}
            </div>
          </div>
          <CBadge :variant="statusVariant(c.status)" :text="c.status" />
        </button>
      </div>

      <!-- Pagination -->
      <div v-if="totalPages > 1" class="scl__pagination">
        <CButton variant="outline" size="sm" :disabled="page <= 1" @click="page--">
          &larr;
        </CButton>
        <span class="scl__page">{{ page }} / {{ totalPages }}</span>
        <CButton variant="outline" size="sm" :disabled="page >= totalPages" @click="page++">
          &rarr;
        </CButton>
      </div>
    </template>

    <!-- Assign modal (W0) -->
    <CModal :open="showAssign" @close="closeAssign">
      <h3 class="scl__modal-title">
        {{ t('staff.platform.companies.assign.title') }}
      </h3>
      <p class="scl__modal-hint">
        {{ t('staff.platform.companies.assign.hint') }}
      </p>

      <div class="scl__field">
        <label class="scl__field-label">{{ t('staff.platform.companies.assign.fieldUser') }}</label>
        <UserPicker v-model="assignUserId" @select="onUserSelected" />
        <p v-if="assignSelectedUser?.role === 'company'" class="scl__field-error">
          {{ t('staff.platform.companies.assign.alreadyCompanyError') }}
        </p>
      </div>

      <CInput
        v-model="assignName"
        :label="t('staff.platform.companies.assign.fieldName')"
        :placeholder="t('staff.platform.companies.assign.fieldName')"
      />

      <CTextarea
        v-model="assignDescription"
        :label="t('staff.platform.companies.assign.fieldDescription')"
        :rows="3"
      />

      <CInput
        v-model="assignPriceDollars"
        type="number"
        min="0"
        step="0.01"
        :label="t('staff.platform.companies.assign.fieldPrice')"
        placeholder="0.00"
      />

      <CInput
        v-model="assignTotalSupply"
        type="number"
        min="1"
        step="1"
        :label="t('staff.platform.companies.assign.fieldTotalSupply')"
      />

      <CInput
        v-model="assignSharesPerOption"
        type="number"
        min="1"
        step="1"
        :label="t('staff.platform.companies.assign.fieldSharesPerOption')"
      />

      <CInput
        v-model="assignCompanyPct"
        type="number"
        min="0"
        max="100"
        step="0.1"
        :label="t('staff.platform.companies.assign.fieldCompanyPct')"
        placeholder="65"
      />

      <CInput
        v-model="assignAgentLevels"
        :label="t('staff.platform.companies.assign.fieldAgentLevels')"
        placeholder="10, 3, 1"
        :error="
          assignAgentLevelsFractions === null
            ? t('staff.platform.companies.assign.agentLevelsError')
            : !assignDistributionValid
              ? t('staff.platform.companies.assign.distributionSumError')
              : ''
        "
      />

      <div class="scl__modal-actions">
        <CButton variant="outline" size="sm" @click="closeAssign">
          {{ t('common.cancel') }}
        </CButton>
        <CButton
          variant="primary"
          size="sm"
          :loading="assigning"
          :disabled="!canSubmitAssign"
          @click="handleAssign"
        >
          {{ t('common.save') }}
        </CButton>
      </div>
    </CModal>

    <!-- Create modal (2026-08-30, `№199`) -->
    <CModal :open="showCreate" @close="closeCreate">
      <h3 class="scl__modal-title">
        {{ t('staff.platform.companies.create.title') }}
      </h3>
      <p class="scl__modal-hint">
        {{ t('staff.platform.companies.create.hint') }}
      </p>

      <CInput
        v-model="createEmail"
        type="email"
        autocomplete="off"
        :label="t('staff.platform.companies.create.fieldEmail')"
      />

      <div class="scl__password-row">
        <CInput
          v-model="createPassword"
          type="password"
          autocomplete="new-password"
          maxlength="128"
          :label="t('staff.platform.companies.create.fieldPassword')"
        />
        <CButton variant="outline" size="sm" @click="createPassword = generatePassword()">
          {{ t('staff.platform.companies.create.generatePassword') }}
        </CButton>
      </div>

      <CInput
        v-model="createName"
        :label="t('staff.platform.companies.create.fieldName')"
        :placeholder="t('staff.platform.companies.create.fieldName')"
      />

      <CTextarea
        v-model="createDescription"
        :label="t('staff.platform.companies.create.fieldDescription')"
        :rows="3"
      />

      <CInput
        v-model="createPriceDollars"
        type="number"
        min="0"
        step="0.01"
        :label="t('staff.platform.companies.create.fieldPrice')"
        placeholder="0.00"
      />

      <CInput
        v-model="createTotalSupply"
        type="number"
        min="1"
        step="1"
        :label="t('staff.platform.companies.create.fieldTotalSupply')"
      />

      <CInput
        v-model="createSharesPerOption"
        type="number"
        min="1"
        step="1"
        :label="t('staff.platform.companies.create.fieldSharesPerOption')"
      />

      <CInput
        v-model="createCompanyPct"
        type="number"
        min="0"
        max="100"
        step="0.1"
        :label="t('staff.platform.companies.create.fieldCompanyPct')"
        placeholder="65"
      />

      <CInput
        v-model="createAgentLevels"
        :label="t('staff.platform.companies.create.fieldAgentLevels')"
        placeholder="10, 3, 1"
        :error="
          createAgentLevelsFractions === null
            ? t('staff.platform.companies.create.agentLevelsError')
            : !createDistributionValid
              ? t('staff.platform.companies.create.distributionSumError')
              : ''
        "
      />

      <div class="scl__modal-actions">
        <CButton variant="outline" size="sm" @click="closeCreate">
          {{ t('common.cancel') }}
        </CButton>
        <CButton
          variant="primary"
          size="sm"
          :loading="creating"
          :disabled="!canSubmitCreate"
          @click="handleCreate"
        >
          {{ t('common.save') }}
        </CButton>
      </div>
    </CModal>
  </div>
</template>

<style scoped>
.scl {
  padding: var(--space-4);
}
.scl__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  margin-bottom: var(--space-3);
}
.scl__title {
  font-size: var(--fs-h4);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}

/* Assign modal (W0) */
.scl__modal-title {
  font-size: var(--fs-h4);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 var(--space-2);
}
.scl__modal-hint {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  margin: 0 0 var(--space-4);
}
.scl__field {
  margin-bottom: var(--space-4);
}
.scl__field-label {
  display: block;
  font-size: var(--fs-xs);
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: var(--space-2);
}
.scl__field-error {
  font-size: var(--fs-xs);
  color: var(--danger);
  margin: var(--space-2) 0 0;
}
.scl__password-row {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-2);
  margin-bottom: var(--space-4);
}
.scl__header-actions {
  display: flex;
  gap: var(--space-2);
}
.scl__modal-actions {
  display: flex;
  gap: var(--space-2);
  margin-top: var(--space-4);
  justify-content: flex-end;
}

.scl__filters {
  display: flex;
  gap: var(--space-2);
  overflow-x: auto;
  margin-bottom: var(--space-3);
  padding-bottom: var(--space-1);
}
.filter-chip {
  position: relative;
  /* A5: pointer target floor. */
  min-height: var(--tap-min);
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-default);
  background: var(--bg-page);
  color: var(--text-secondary);
  font-size: var(--fs-xs);
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  text-transform: capitalize;
}

/* A5: the PAINTED box stays this size on purpose -- growing it would move the
   text beside it. The HIT AREA is expanded past it with a centred overlay, the
   pattern CInput.vue established and this codebase already uses ten times.
   max() so an already-large box never shrinks. Added 2026-08-25 after the first
   HIT TEST (elementFromPoint) rather than a bounding-box census: a pseudo-element
   is not in getBoundingClientRect(), so no box-based count here could ever see
   an overlay, and every A5 figure this project published measured the wrong
   quantity. */
.filter-chip::after {
  content: '';
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  width: max(100%, var(--tap-min));
  height: max(100%, var(--tap-min));
}
.filter-chip.active {
  background: var(--primary);
  color: var(--on-primary);
  border-color: var(--primary);
}

.scl__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: var(--center-md);
  gap: var(--space-4);
}

.company-list {
  display: flex;
  flex-direction: column;
}
.company-item {
  appearance: none;
  background: none;
  border: none;
  margin: 0;
  padding: 0;
  font: inherit;
  color: inherit;
  text-align: start;
  width: 100%;
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-4) 0;
  border-bottom: 1px solid var(--border-default);
  cursor: pointer;
  transition: background 0.15s;
}
.company-item:hover {
  background: var(--bg-subtle);
}
.company-item__info {
  flex: 1;
  min-width: 0;
}
.company-item__name {
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.company-item__detail {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
  margin-top: var(--space-1);
}

.scl__pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  margin-top: var(--space-4);
}
.scl__page {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
}
</style>
