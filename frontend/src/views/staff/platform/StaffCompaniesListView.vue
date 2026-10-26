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
import { useI18n } from 'vue-i18n'
import { tOrRaw } from '@/utils/i18n'
import {
  AlertTriangle,
  Building2,
  Check,
  ChevronRight,
  Plus,
  UserPlus,
} from '@/components/ui/icons'
import { CBadge, CButton, CEmptyState, CInput, CModal, CTextarea } from '@/components/ui'
import CListSkeleton from '@/components/ui/CListSkeleton.vue'
import CPager from '@/components/ui/CPager.vue'
import { useUrlPage } from '@/components/ui/useUrlPage'
import { useScreenHeader } from '@/components/layout/screenHeader'
import { useToast } from '@/composables/useToast'
import { useStaffPermissions } from '@/composables/useStaffPermissions'
import { useAvatar } from '@/composables/useAvatar'
import { ApiResponseError } from '@/api/client'
import { fetchStaffCompanies, assignCompany, createCompany } from '@/api/staff-companies'
import UserPicker from '@/components/staff/UserPicker.vue'
import type { CompanyResponse, UserListItem } from '@/api/types'
import { useReloadOnLocale } from '@/composables/useReloadOnLocale'
import { passwordWithinRule } from '@/utils/passwordRule'

const { t } = useI18n()
const { showToast } = useToast()
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
const page = useUrlPage()
const perPage = 20
const statusFilter = ref<'' | 'active' | 'hidden' | 'archived'>('')
const search = ref('')
const loading = ref(true)
const error = ref(false)

// The frame's header carries the section's title and its two actions (FP-23: the
// Create and Assign actions both need project_manage + financial_operations).
useScreenHeader({
  title: () => t('staff.platform.companies.title'),
  actions: () =>
    canManageCompanies.value
      ? [
          {
            id: 'create',
            label: t('staff.platform.companies.create.cta'),
            icon: Plus,
            onClick: openCreate,
          },
          {
            id: 'assign',
            label: t('staff.platform.companies.assign.cta'),
            icon: UserPlus,
            onClick: openAssign,
          },
        ]
      : [],
})

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

// H38: project data is in the reader's language -- re-read it on a switch.
useReloadOnLocale(() => loadCompanies())

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
const assignTotalSupply = ref('1000000000')
const assignSharesPerOption = ref('1')
const assignCompanyPct = ref('')
const assignAgentLevels = ref('')

function resetAssignForm(): void {
  assignUserId.value = ''
  assignSelectedUser.value = null
  assignName.value = ''
  assignDescription.value = ''
  assignPriceDollars.value = ''
  assignTotalSupply.value = '1000000000'
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
const createTotalSupply = ref('1000000000')
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
  createTotalSupply.value = '1000000000'
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

const createPasswordValid = computed<boolean>(() => passwordWithinRule(createPassword.value))

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
    <!-- Status filter chips -->
    <div class="ds-chip-row" role="group" :aria-label="t('staff.platform.companies.title')">
      <button
        class="ds-chip"
        :aria-pressed="!statusFilter"
        @click="setStatusFilter('')"
        type="button"
      >
        <Check class="ds-chip__check" size="sm" />
        <span>{{ t('staff.platform.companies.filterAll') }}</span>
      </button>
      <button
        v-for="s in ['active', 'hidden', 'archived'] as const"
        :key="s"
        class="ds-chip"
        :aria-pressed="statusFilter === s"
        @click="setStatusFilter(s)"
        type="button"
      >
        <Check class="ds-chip__check" size="sm" />
        <span>{{ t(`staff.platform.companies.filter.${s}`) }}</span>
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
    <CListSkeleton v-if="loading" />

    <!-- Error -->
    <CEmptyState v-else-if="error" tone="danger" :title="t('common.error')">
      <template #actions>
        <CButton variant="secondary" size="sm" inline @click="loadCompanies">
          {{ t('common.retry') }}
        </CButton>
      </template>
    </CEmptyState>

    <!-- Empty -->
    <CEmptyState v-else-if="!items.length" :title="t('staff.platform.companies.empty')">
      <template #icon>
        <Building2 />
      </template>
    </CEmptyState>

    <!-- List (K23 rows: a row opens the project) -->
    <template v-else>
      <ul class="ds-rows company-list">
        <li v-for="c in items" :key="c.id" class="ds-row">
          <span class="ds-row__lead"><Building2 size="sm" /></span>
          <span class="ds-row__body">
            <RouterLink class="ds-row__link" :to="`/staff/platform/projects/${c.id}`">
              <span class="ds-row__title">{{ c.name }}</span>
            </RouterLink>
            <span class="ds-row__meta">
              {{ formatPrice(c.price_per_unit_cents) }} &bull;
              {{ t('staff.platform.companies.supply', { n: c.total_supply }) }}
            </span>
          </span>
          <span class="ds-row__trail">
            <CBadge
              :variant="statusVariant(c.status)"
              :text="tOrRaw(t, `staff.platform.companies.filter.${c.status}`, c.status)"
            />
            <ChevronRight size="sm" />
          </span>
        </li>
      </ul>

      <!-- Pagination (K17) -->
      <CPager :page="page" :total-pages="totalPages" @update:page="(n: number) => (page = n)" />
    </template>

    <!-- Assign modal (W0) -->
    <CModal
      :open="showAssign"
      :title="t('staff.platform.companies.assign.title')"
      @close="closeAssign"
    >
      <p class="ds-dialog__text">
        {{ t('staff.platform.companies.assign.hint') }}
      </p>

      <div>
        <UserPicker
          v-model="assignUserId"
          :label="t('staff.platform.companies.assign.fieldUser')"
          @select="onUserSelected"
        />
        <p v-if="assignSelectedUser?.role === 'company'" class="ds-field__error">
          <AlertTriangle size="sm" />
          <span>{{ t('staff.platform.companies.assign.alreadyCompanyError') }}</span>
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

      <div class="ds-dialog__actions">
        <CButton variant="outline" size="sm" inline @click="closeAssign">
          {{ t('common.cancel') }}
        </CButton>
        <CButton
          variant="primary"
          size="sm"
          inline
          :loading="assigning"
          :disabled="!canSubmitAssign"
          @click="handleAssign"
        >
          {{ t('common.save') }}
        </CButton>
      </div>
    </CModal>

    <!-- Create modal (2026-08-30, `№199`) -->
    <CModal
      :open="showCreate"
      :title="t('staff.platform.companies.create.title')"
      @close="closeCreate"
    >
      <p class="ds-dialog__text">
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
        <CButton variant="outline" size="sm" inline @click="createPassword = generatePassword()">
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

      <div class="ds-dialog__actions">
        <CButton variant="outline" size="sm" inline @click="closeCreate">
          {{ t('common.cancel') }}
        </CButton>
        <CButton
          variant="primary"
          size="sm"
          inline
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
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: var(--space-3);
  align-content: start;
}

.scl__password-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  justify-items: start;
  gap: var(--space-2);
}
.scl__password-row > :first-child {
  justify-self: stretch;
}
</style>
