<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- StaffUsersView (iter 2.7 A3 + A5)
// =============================================================================
//
// Staff user management -- list, role / kyc_status filter, detail modal.
//   GET    /api/v1/staff/users (?role=, ?kyc_status=, ?page=, ?per_page=)
//   GET    /api/v1/staff/users/{id}
//   PATCH  /api/v1/staff/users/{id}/block
//   POST   /api/v1/staff/users (promote to staff, admin only)
//   PATCH  /api/v1/staff/users/{id}/permissions (admin only)
//   POST   /api/v1/staff/kyc/{application_id}/approve  (iter 2.7 A5)
//   POST   /api/v1/staff/kyc/{application_id}/reject   (iter 2.7 A5)
//
// Sprint 4.4 PermissionKey contract:
//   PermissionKey is derived from the backend's UpdatePermissionsRequest
//   and the runtime list ALL_PERMISSION_KEYS is checked both ways at
//   compile time:
//
//     1. `as const satisfies readonly PermissionKey[]`
//        rejects keys in the array that are NOT valid PermissionKey
//        values (typos and removed-on-backend keys).
//
//     2. The `_PermissionKeysExhaustive` assertion below rejects valid
//        PermissionKey values that are MISSING from the array (a new
//        permission added to the backend that this UI forgot). The
//        use-site assignment is what actually fails the build -- a
//        bare type alias is just a tooltip warning.
//
// iter 2.7 A3 + A5 (R1 §3 KYC merge).
//   The old StaffKYCView page was removed in iter 2.7 A2. Its
//   Approve / Reject flow is folded into THIS view's detail modal,
//   plus a new chip row filters the list by kyc_status. The kyc_status
//   query param landed on fetchUsers in A3.
//
//   The detail modal's "KYC Application" section reads three new
//   fields surfaced by the backend mini-iter shipped alongside A5:
//     - latest_application_id      : UUID of the newest KYCApplication
//                                    row, or null if the user has
//                                    never submitted.
//     - latest_application_status  : status of that row.
//     - kyc_applications_history   : up to KYC_HISTORY_LIMIT newest
//                                    rows, newest first. Empty list
//                                    when the user has never submitted.
//
//   The section self-hides (FP-25) when latest_application_id is null:
//     - role=company / role=staff are exempt from KYC by the platform's
//       onboarding flow, so they never have an application row to act
//       on. Showing an empty "no application" block in that case is
//       just noise.
//   When the section IS shown, Approve / Reject are gated FP-23-style:
//     - canDoKycApprove computed from useStaffPermissions wraps both
//       buttons (template guard);
//     - the handlers run a defensive check + console.warn before
//       firing the network call.
//   Buttons are further restricted to status=submitted -- terminal
//   statuses (approved / rejected) leave only the history visible.
// =============================================================================

import { ref, onMounted, computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Clock } from 'lucide-vue-next'
import { CAvatar, CBadge, CLoader, CButton, CModal, CEmptyState, CInput, CCheckbox } from '@/components/ui'
import { useToast } from '@/composables/useToast'
import { useStaffPermissions } from '@/composables/useStaffPermissions'
import {
  fetchUsers,
  fetchUserDetail,
  blockUser,
  createStaff,
  updatePermissions,
  approveKYC,
  rejectKYC,
} from '@/api/admin'
import type {
  UpdatePermissionsRequest,
  UserListItem,
  UserDetailResponse,
} from '@/api/types'

// PermissionKey derived from the backend schema -- single source of
// truth. Required<> strips the `?` so `keyof` returns every permission
// regardless of optional-on-the-wire shape.
type PermissionKey = keyof Required<UpdatePermissionsRequest>

// Full list of permission keys -- ensures UI shows all toggles even if
// backend omits false values. `as const satisfies readonly PermissionKey[]`
// catches typos and removed-on-backend keys at compile time.
//
// content_manage was added to DEFAULT_STAFF_PERMISSIONS in backend
// Sprint 9.1 and finally to UpdatePermissionsRequest in iter 2.7 A6
// (schema-side mini-iter that closed the 9-vs-8 drift). The
// exhaustiveness assertion below now expects nine keys.
const ALL_PERMISSION_KEYS = [
  'avatar_mode',
  'kyc_approve',
  'payment_review',
  'user_block',
  'financial_operations',
  'agent_application_review',
  'translation_edit',
  'company_manage',
  'content_manage',
] as const satisfies readonly PermissionKey[]

// Compile-time exhaustiveness: if the backend adds a new permission to
// UpdatePermissionsRequest and this array forgets it, the assignment
// below fails to typecheck -- the type on the right resolves to the
// error-object literal, which is not assignable to `true`.
type _PermissionKeysExhaustive =
  Exclude<PermissionKey, (typeof ALL_PERMISSION_KEYS)[number]> extends never
    ? true
    : { readonly error: 'ALL_PERMISSION_KEYS missing keys from UpdatePermissionsRequest' }

const _permissionKeysExhaustive: _PermissionKeysExhaustive = true
void _permissionKeysExhaustive

// KYC status filter chip values. Backend ?kyc_status= accepts these
// exact strings (KYCStatus StrEnum, 422 on anything else).
const ALL_KYC_STATUSES = [
  'not_started',
  'submitted',
  'approved',
  'rejected',
] as const
type KYCStatus = (typeof ALL_KYC_STATUSES)[number]

const { t } = useI18n()
const { showToast } = useToast()
const { canDo } = useStaffPermissions()

// iter 2.7 A5: FP-23 template guard for the Approve / Reject buttons
// in the detail modal's KYC section. Reads the effective permission
// merged with defaults on the current staff member.
const canDoKycApprove = canDo('kyc_approve')

// -- List state --
const items = ref<UserListItem[]>([])
const total = ref(0)
const page = ref(1)
const perPage = 20
const roleFilter = ref('')
// The staff dashboard's KYC card and alert banner deep-link here, because
// iter 2.7 A2 removed /staff/kyc and moved the queue into this screen. The
// chip is selected from `?kyc_status=`, VALIDATED against the enum above --
// the backend 422s on anything else, so an unknown value falls back to the
// unfiltered list rather than travelling to the API.
// Assigned during setup, ahead of the watch() below, so arriving with a
// filter costs one request and not two.
const route = useRoute()
const queryKyc = String(route.query.kyc_status ?? '')
const kycStatusFilter = ref<'' | KYCStatus>(
  (ALL_KYC_STATUSES as readonly string[]).includes(queryKyc) ? (queryKyc as KYCStatus) : '',
)
const loading = ref(true)
const error = ref(false)

// -- Detail modal state --
const showDetail = ref(false)
const detailUser = ref<UserDetailResponse | null>(null)
const detailLoading = ref(false)
const actionLoading = ref(false)

// -- Block modal --
const showBlockModal = ref(false)
const blockReason = ref('')

// -- Promote modal --
const showPromoteModal = ref(false)

// -- KYC reject modal (iter 2.7 A5) --
const showKycRejectModal = ref(false)
const kycRejectReason = ref('')
const kycActionLoading = ref(false)

const totalPages = computed(() => Math.ceil(total.value / perPage))

const kycVariant = (status: string) => {
  if (status === 'approved') return 'success'
  if (status === 'submitted') return 'warning'
  if (status === 'rejected') return 'danger'
  return 'neutral'
}

const roleVariant = (role: string) => {
  if (role === 'staff') return 'primary'
  if (role === 'agent') return 'accent'
  if (role === 'company') return 'warning'
  return 'neutral'
}

function fullName(item: { first_name?: string | null; last_name?: string | null }): string {
  const parts = [item.first_name, item.last_name].filter(Boolean)
  return parts.length ? parts.join(' ') : '—'
}

// Pretty-print an ISO datetime. Used for both the registered-at row
// and KYC history timeline. toLocaleDateString matches the existing
// "Registered" row format for visual consistency.
function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString()
}

async function loadUsers(): Promise<void> {
  loading.value = true
  error.value = false
  try {
    const resp = await fetchUsers({
      role: roleFilter.value || undefined,
      kyc_status: kycStatusFilter.value || undefined,
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

async function openDetail(userId: string): Promise<void> {
  showDetail.value = true
  detailLoading.value = true
  detailUser.value = null
  try {
    detailUser.value = await fetchUserDetail(userId)
  } catch {
    showToast(t('common.error'), 'error')
    showDetail.value = false
  } finally {
    detailLoading.value = false
  }
}

// -- Filters --

function setRoleFilter(role: string): void {
  roleFilter.value = role
  page.value = 1
}

function setKycStatusFilter(status: '' | KYCStatus): void {
  kycStatusFilter.value = status
  page.value = 1
}

// -- Actions --

async function handleBlock(): Promise<void> {
  if (!detailUser.value) return
  actionLoading.value = true
  try {
    await blockUser(detailUser.value.id, { reason: blockReason.value || undefined })
    showToast(t('staff.userDetail.unblockNote'), 'success')
    showBlockModal.value = false
    blockReason.value = ''
    showDetail.value = false
    await loadUsers()
  } catch {
    showToast(t('common.error'), 'error')
  } finally {
    actionLoading.value = false
  }
}

async function handlePromote(): Promise<void> {
  if (!detailUser.value) return
  actionLoading.value = true
  try {
    await createStaff({ user_id: detailUser.value.id })
    showToast(t('staff.userDetail.promoted'), 'success')
    showPromoteModal.value = false
    showDetail.value = false
    await loadUsers()
  } catch {
    showToast(t('common.error'), 'error')
  } finally {
    actionLoading.value = false
  }
}

// Takes the NEW value rather than the old one. The raw checkbox reported only
// that it had changed, so the caller passed the CURRENT value and this function
// inverted it; CCheckbox emits the value it moved to, which removes that
// round-trip and the double negation that came with it.
async function setPermission(key: PermissionKey, value: boolean): Promise<void> {
  if (!detailUser.value?.staff_profile) return
  try {
    const updated = await updatePermissions(detailUser.value.staff_profile.id, {
      [key]: value,
    })
    detailUser.value.staff_profile = updated
    showToast(t('staff.userDetail.permissionsUpdated'), 'success')
  } catch {
    showToast(t('common.error'), 'error')
  }
}

// iter 2.7 A5 -- KYC Approve / Reject from the detail modal.
//
// Both handlers carry a defensive permission check (FP-23 belt-and-
// braces) -- the template hides the buttons via canDoKycApprove, but
// a malicious refire or a regression in the template guard should
// not silently slip past. The console.warn lands in logs without
// surfacing as a toast; the function returns without firing the
// network call.
//
// After a successful action we refetch BOTH the user detail (so the
// modal reflects the new status and any added history row) and the
// list (so the chip filter counts agree with reality).

async function handleKycApprove(): Promise<void> {
  if (!detailUser.value) return
  const applicationId = detailUser.value.latest_application_id
  if (!applicationId) return
  if (!canDoKycApprove.value) {
    console.warn('[StaffUsersView] kyc approve blocked: no kyc_approve permission')
    return
  }

  kycActionLoading.value = true
  try {
    await approveKYC(applicationId)
    showToast(t('staff.userDetail.kyc.approvedToast'), 'success')
    // Refetch detail so the badge and history reflect the new state.
    detailUser.value = await fetchUserDetail(detailUser.value.id)
    // Refetch list so the chip-filtered counts stay accurate.
    await loadUsers()
  } catch {
    showToast(t('common.error'), 'error')
  } finally {
    kycActionLoading.value = false
  }
}

function openKycReject(): void {
  if (!canDoKycApprove.value) {
    console.warn('[StaffUsersView] kyc reject blocked: no kyc_approve permission')
    return
  }
  kycRejectReason.value = ''
  showKycRejectModal.value = true
}

async function handleKycReject(): Promise<void> {
  if (!detailUser.value) return
  const applicationId = detailUser.value.latest_application_id
  if (!applicationId) return
  if (!canDoKycApprove.value) {
    console.warn('[StaffUsersView] kyc reject blocked: no kyc_approve permission')
    return
  }
  // Reason is required for reject per R1 §3 ("Reject требует обязательное
  // поле причины"). The button stays disabled until the input is non-empty,
  // but trim-check here covers whitespace-only entries.
  const reason = kycRejectReason.value.trim()
  if (!reason) return

  kycActionLoading.value = true
  try {
    await rejectKYC(applicationId, { reason })
    showToast(t('staff.userDetail.kyc.rejectedToast'), 'success')
    showKycRejectModal.value = false
    kycRejectReason.value = ''
    detailUser.value = await fetchUserDetail(detailUser.value.id)
    await loadUsers()
  } catch {
    showToast(t('common.error'), 'error')
  } finally {
    kycActionLoading.value = false
  }
}

watch([roleFilter, kycStatusFilter], () => loadUsers())

onMounted(loadUsers)
</script>

<template>
  <div class="staff-users">
    <!-- Filters: role chips top row, kyc_status chips bottom row.
         iter 2.7 A5: KYC chip row added below the existing role row;
         the two filters compose at the backend boundary. -->
    <div class="staff-users__filters">
      <div class="staff-users__filter-row">
        <button
          class="filter-chip" :class="{ active: !roleFilter }"
          @click="setRoleFilter('')"
        >{{ t('common.all') }}</button>
        <button
          v-for="r in ['investor', 'agent', 'company', 'staff']"
          :key="r"
          class="filter-chip" :class="{ active: roleFilter === r }"
          @click="setRoleFilter(r)"
        >{{ r }}</button>
      </div>
      <div class="staff-users__filter-row">
        <button
          class="filter-chip filter-chip--kyc" :class="{ active: !kycStatusFilter }"
          @click="setKycStatusFilter('')"
        >{{ t('staff.userDetail.kyc.filterAll') }}</button>
        <button
          v-for="s in ALL_KYC_STATUSES"
          :key="s"
          class="filter-chip filter-chip--kyc"
          :class="{ active: kycStatusFilter === s }"
          @click="setKycStatusFilter(s)"
        >{{ t(`staff.userDetail.kyc.filter.${s}`) }}</button>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="staff-users__center">
      <CLoader :size="32" />
    </div>

    <!-- Error -->
    <div v-else-if="error" class="staff-users__center">
      <CButton variant="secondary" size="sm" @click="loadUsers">{{ t('common.retry') }}</CButton>
    </div>

    <!-- Empty -->
    <CEmptyState v-else-if="!items.length" :title="t('common.noResults')" />

    <!-- List -->
    <template v-else>
      <div class="user-list">
        <button
          v-for="item in items"
          :key="item.id"
          type="button"
          class="user-item"
          @click="openDetail(item.id)"
        >
          <CAvatar :name="fullName(item)" :size="40" />
          <div class="user-item__info">
            <div class="user-item__name">{{ fullName(item) }}</div>
            <div class="user-item__detail">
              {{ item.role }} &bull; {{ item.email ?? '—' }}
            </div>
          </div>
          <div class="user-item__right">
            <CBadge :variant="kycVariant(item.kyc_status)" :text="item.kyc_status" />
            <div v-if="!item.is_active" class="user-item__blocked">
              <CBadge variant="danger" :text="t('staff.userDetail.blocked')" />
            </div>
          </div>
        </button>
      </div>

      <!-- Pagination -->
      <div v-if="totalPages > 1" class="staff-users__pagination">
        <CButton
          variant="outline" size="sm"
          :disabled="page <= 1"
          @click="page--; loadUsers()"
        >&larr;</CButton>
        <span class="staff-users__page">{{ page }} / {{ totalPages }}</span>
        <CButton
          variant="outline" size="sm"
          :disabled="page >= totalPages"
          @click="page++; loadUsers()"
        >&rarr;</CButton>
      </div>
    </template>

    <!-- Detail modal -->
    <CModal :open="showDetail" @close="showDetail = false">
      <div v-if="detailLoading" class="staff-users__center" style="min-height:200px">
        <CLoader :size="24" />
      </div>
      <template v-else-if="detailUser">
        <h3 class="detail__title">{{ t('staff.userDetail.title') }}</h3>
        <div class="detail__row">
          <span class="detail__label">{{ t('staff.userDetail.role') }}</span>
          <CBadge :variant="roleVariant(detailUser.role)" :text="detailUser.role" />
        </div>
        <div class="detail__row">
          <span class="detail__label">{{ t('staff.userDetail.status') }}</span>
          <CBadge
            :variant="detailUser.is_active ? 'success' : 'danger'"
            :text="detailUser.is_active ? t('staff.userDetail.active') : t('staff.userDetail.blocked')"
          />
        </div>
        <div class="detail__row">
          <span class="detail__label">{{ t('staff.userDetail.kycStatus') }}</span>
          <CBadge :variant="kycVariant(detailUser.kyc_status)" :text="detailUser.kyc_status" />
        </div>
        <div class="detail__row">
          <span class="detail__label">{{ t('staff.userDetail.onboardingStep') }}</span>
          <span class="detail__value">{{ detailUser.onboarding_step }}</span>
        </div>
        <div class="detail__row">
          <span class="detail__label">{{ t('staff.userDetail.registered') }}</span>
          <span class="detail__value">
            <Clock :size="16" style="vertical-align:-1px" />
            {{ formatDate(detailUser.created_at) }}
          </span>
        </div>

        <!-- KYC Application section (iter 2.7 A5).
             FP-25 self-hide: only shown when the user has at least one
             application row (latest_application_id != null). Company /
             staff role users skip KYC entirely, so they'll never have
             a row and the section disappears silently.

             FP-23 double guard on Approve / Reject:
               1. canDoKycApprove computed wraps both buttons (template
                  guard);
               2. handlers re-check + console.warn before firing.
             Buttons further restricted to status=submitted -- terminal
             statuses show only history. -->
        <div
          v-if="detailUser.latest_application_id"
          class="detail__section"
        >
          <h4 class="detail__subtitle">{{ t('staff.userDetail.kyc.sectionTitle') }}</h4>

          <div class="detail__row">
            <span class="detail__label">{{ t('staff.userDetail.kyc.latestStatus') }}</span>
            <CBadge
              :variant="kycVariant(detailUser.latest_application_status ?? 'not_started')"
              :text="detailUser.latest_application_status ?? '—'"
            />
          </div>

          <!-- History timeline. Hidden when there's only the single
               latest row (already shown above). 2+ rows means the user
               has re-submitted at least once -- R1 §3 "история re-submits
               если есть". -->
          <div
            v-if="detailUser.kyc_applications_history.length > 1"
            class="kyc-history"
          >
            <div class="kyc-history__title">
              {{ t('staff.userDetail.kyc.historyTitle') }}
            </div>
            <ul class="kyc-history__list">
              <li
                v-for="app in detailUser.kyc_applications_history"
                :key="app.id"
                class="kyc-history__row"
              >
                <CBadge :variant="kycVariant(app.status)" :text="app.status" />
                <span class="kyc-history__date">{{ formatDate(app.created_at) }}</span>
              </li>
            </ul>
          </div>

          <!-- Approve / Reject CTAs.
               Visible only when the latest application is still pending
               (status=submitted) AND the current staff has kyc_approve.
               Terminal statuses (approved / rejected) leave the section
               in read-only form. -->
          <div
            v-if="
              detailUser.latest_application_status === 'submitted'
              && canDoKycApprove
            "
            class="detail__actions"
          >
            <CButton
              variant="primary"
              size="sm"
              :loading="kycActionLoading"
              @click="handleKycApprove"
            >{{ t('staff.userDetail.kyc.approve') }}</CButton>
            <CButton
              variant="danger"
              size="sm"
              :disabled="kycActionLoading"
              @click="openKycReject"
            >{{ t('staff.userDetail.kyc.reject') }}</CButton>
          </div>
        </div>

        <!-- Staff permissions (if staff) -->
        <div v-if="detailUser.staff_profile" class="detail__section">
          <h4 class="detail__subtitle">{{ t('staff.userDetail.permissions') }}</h4>
          <div
            v-for="key in ALL_PERMISSION_KEYS"
            :key="key"
            class="detail__perm"
          >
            <CCheckbox
              :model-value="!!detailUser.staff_profile.permissions[key]"
              @update:model-value="(v: boolean) => setPermission(key, v)"
            >
              {{ key }}
            </CCheckbox>
          </div>
        </div>

        <!-- Actions -->
        <div class="detail__actions">
          <CButton
            v-if="detailUser.is_active && detailUser.role !== 'staff'"
            variant="danger" size="sm"
            @click="showBlockModal = true"
          >{{ t('staff.userDetail.block') }}</CButton>
          <CButton
            v-if="detailUser.role !== 'staff'"
            variant="secondary" size="sm"
            @click="showPromoteModal = true"
          >{{ t('staff.userDetail.promoteToStaff') }}</CButton>
        </div>
      </template>
    </CModal>

    <!-- Block confirmation -->
    <CModal :open="showBlockModal" @close="showBlockModal = false">
      <h3 class="detail__title">{{ t('staff.userDetail.block') }}</h3>
      <p class="detail__confirm-text">{{ t('staff.userDetail.blockConfirm') }}</p>
      <CInput
        v-model="blockReason"
        :label="t('staff.userDetail.blockReason')"
        :placeholder="t('staff.userDetail.blockReason')"
      />
      <div class="detail__actions" style="margin-top:16px">
        <CButton variant="outline" size="sm" @click="showBlockModal = false">{{ t('common.cancel') }}</CButton>
        <CButton variant="danger" size="sm" :loading="actionLoading" @click="handleBlock">{{ t('common.confirm') }}</CButton>
      </div>
    </CModal>

    <!-- Promote confirmation -->
    <CModal :open="showPromoteModal" @close="showPromoteModal = false">
      <h3 class="detail__title">{{ t('staff.userDetail.promoteToStaff') }}</h3>
      <p class="detail__confirm-text">{{ t('staff.userDetail.promoteConfirm') }}</p>
      <div class="detail__actions" style="margin-top:16px">
        <CButton variant="outline" size="sm" @click="showPromoteModal = false">{{ t('common.cancel') }}</CButton>
        <CButton variant="primary" size="sm" :loading="actionLoading" @click="handlePromote">{{ t('common.confirm') }}</CButton>
      </div>
    </CModal>

    <!-- KYC reject reason (iter 2.7 A5).
         Reason is REQUIRED per R1 §3 -- the confirm button stays
         disabled while the trimmed input is empty. -->
    <CModal :open="showKycRejectModal" @close="showKycRejectModal = false">
      <h3 class="detail__title">{{ t('staff.userDetail.kyc.reject') }}</h3>
      <p class="detail__confirm-text">{{ t('staff.userDetail.kyc.rejectHint') }}</p>
      <CInput
        v-model="kycRejectReason"
        :label="t('staff.userDetail.kyc.rejectReason')"
        :placeholder="t('staff.userDetail.kyc.rejectReason')"
      />
      <div class="detail__actions" style="margin-top:16px">
        <CButton
          variant="outline"
          size="sm"
          @click="showKycRejectModal = false"
        >{{ t('common.cancel') }}</CButton>
        <CButton
          variant="danger"
          size="sm"
          :disabled="!kycRejectReason.trim() || kycActionLoading"
          :loading="kycActionLoading"
          @click="handleKycReject"
        >{{ t('staff.userDetail.kyc.reject') }}</CButton>
      </div>
    </CModal>
  </div>
</template>

<style scoped>
.staff-users { padding: var(--space-4); }

/* iter 2.7 A5: filters are now two stacked rows (role + kyc_status).
   Each row scrolls horizontally on narrow viewports. */
.staff-users__filters {
  display: flex; flex-direction: column; gap: var(--space-2);
  margin-bottom: var(--space-4);
}
.staff-users__filter-row {
  display: flex; gap: var(--space-2); overflow-x: auto; padding-bottom: var(--space-1);
}
.filter-chip {
  /* A5: pointer target floor. */
  min-height: var(--tap-min);
  padding: var(--space-2) var(--space-4); border-radius: var(--radius-sm); border: 1px solid var(--border-default);
  background: var(--bg-page); color: var(--text-secondary); font-size: var(--fs-xs); font-weight: 600;
  cursor: pointer; white-space: nowrap; text-transform: capitalize;
  font-family: inherit;
}
.filter-chip.active { background: var(--primary); color: var(--on-primary); border-color: var(--primary); }

/* Subtle visual distinction for KYC chips so the user can tell which
   row is which at a glance without reading. The kyc chips share the
   same active state with role chips for behaviour parity. */
.filter-chip--kyc {
  text-transform: none;
}

.user-list { display: flex; flex-direction: column; }
.user-item {
  appearance: none; background: none; border: none; margin: 0; padding: 0;
  font: inherit; color: inherit; text-align: start; width: 100%;
  display: flex; align-items: center; gap: var(--space-3); padding: var(--space-4) 0;
  border-bottom: 1px solid var(--border-default); cursor: pointer; transition: background 0.2s;
}
.user-item:hover { background: var(--bg-subtle); }
.user-item__info { flex: 1; min-width: 0; }
.user-item__name { font-size: var(--fs-sm); font-weight: 600; color: var(--text-primary); }
.user-item__detail { font-size: var(--fs-xs); color: var(--text-tertiary); text-transform: capitalize; }
.user-item__right { text-align: right; flex-shrink: 0; }
.user-item__blocked { margin-top: var(--space-1); }

.staff-users__pagination {
  display: flex; align-items: center; justify-content: center; gap: var(--space-3); margin-top: var(--space-4);
}
.staff-users__page { font-size: var(--fs-xs); color: var(--text-secondary); }

.staff-users__center {
  display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: var(--center-md); gap: var(--space-4);
}

/* Detail modal */
.detail__title { font-size: var(--fs-h4); font-weight: 700; color: var(--text-primary); margin: 0 0 var(--space-4); }
.detail__subtitle { font-size: var(--fs-sm); font-weight: 700; color: var(--text-primary); margin: var(--space-4) 0 var(--space-2); }
.detail__row { display: flex; justify-content: space-between; align-items: center; padding: var(--space-2) 0; border-bottom: 1px solid var(--border-default); }
.detail__label { font-size: var(--fs-xs); color: var(--text-secondary); }
.detail__value { font-size: var(--fs-sm); color: var(--text-primary); }
.detail__section { margin-top: var(--space-3); }
.detail__perm { padding: var(--space-1) 0; }
.detail__actions { display: flex; gap: var(--space-2); margin-top: var(--space-4); flex-wrap: wrap; }
.detail__confirm-text { font-size: var(--fs-sm); color: var(--text-secondary); margin: 0 0 var(--space-3); }

/* KYC history timeline (iter 2.7 A5). */
.kyc-history {
  margin: var(--space-3) 0 var(--space-4);
  padding: var(--space-3);
  background: var(--bg-subtle);
  border-radius: var(--radius-sm);
}
.kyc-history__title {
  font-size: var(--fs-xs);
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: var(--space-2);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.kyc-history__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.kyc-history__row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  font-size: var(--fs-xs);
  color: var(--text-primary);
}
.kyc-history__date {
  color: var(--text-tertiary);
  font-size: var(--fs-xs);
}

/* READING MEASURE — descriptive text only. --maxw-prose (680px) is a CEILING,
   so this rule cannot bind until the container is already wider than a
   comfortable line: on a phone it does nothing at all, which is why it needs
   no media query. Measured at 1280 before applying: `event-card__desc` ran to
   932px and `staff-dash__role-count` to 901. Names, figures and table cells
   are deliberately NOT capped — a name is not prose, and capping it would only
   leave dead space in its row. */
.detail__subtitle { max-width: var(--maxw-prose); }
</style>
