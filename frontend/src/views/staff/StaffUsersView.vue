<script setup lang="ts">
// Staff user management — list, search, filter, detail modal.
// GET /api/v1/staff/users (?role=, ?page=, ?per_page=)
// GET /api/v1/staff/users/{id}
// PATCH /api/v1/staff/users/{id}/block
// POST /api/v1/staff/users (promote to staff, admin only)
// PATCH /api/v1/staff/users/{id}/permissions (admin only)
//
// Sprint 4.4 (Block C):
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

import { ref, onMounted, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Clock } from 'lucide-vue-next'
import { CAvatar, CBadge, CLoader, CButton, CModal, CEmptyState, CInput } from '@/components/ui'
import { useToast } from '@/composables/useToast'
import { fetchUsers, fetchUserDetail, blockUser, createStaff, updatePermissions } from '@/api/admin'
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
const ALL_PERMISSION_KEYS = [
  'avatar_mode',
  'kyc_approve',
  'payment_review',
  'user_block',
  'financial_operations',
  'agent_application_review',
  'translation_edit',
  'company_manage',
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

const { t } = useI18n()
const { showToast } = useToast()

// -- List state --
const items = ref<UserListItem[]>([])
const total = ref(0)
const page = ref(1)
const perPage = 20
const roleFilter = ref('')
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

async function loadUsers(): Promise<void> {
  loading.value = true
  error.value = false
  try {
    const resp = await fetchUsers({
      role: roleFilter.value || undefined,
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

async function togglePermission(key: PermissionKey, current: boolean): Promise<void> {
  if (!detailUser.value?.staff_profile) return
  try {
    const updated = await updatePermissions(detailUser.value.staff_profile.id, {
      [key]: !current,
    })
    detailUser.value.staff_profile = updated
    showToast(t('staff.userDetail.permissionsUpdated'), 'success')
  } catch {
    showToast(t('common.error'), 'error')
  }
}

function setRoleFilter(role: string): void {
  roleFilter.value = role
  page.value = 1
}

watch([roleFilter], () => loadUsers())

onMounted(loadUsers)
</script>

<template>
  <div class="staff-users">
    <!-- Role filter chips -->
    <div class="staff-users__filters">
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
        <div
          v-for="item in items"
          :key="item.id"
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
        </div>
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
            <Clock :size="12" style="vertical-align:-1px" />
            {{ new Date(detailUser.created_at).toLocaleDateString() }}
          </span>
        </div>

        <!-- Staff permissions (if staff) -->
        <div v-if="detailUser.staff_profile" class="detail__section">
          <h4 class="detail__subtitle">{{ t('staff.userDetail.permissions') }}</h4>
          <div
            v-for="key in ALL_PERMISSION_KEYS"
            :key="key"
            class="detail__perm"
          >
            <label class="detail__perm-label">
              <input
                type="checkbox"
                :checked="!!detailUser.staff_profile.permissions[key]"
                @change="togglePermission(key, !!detailUser.staff_profile.permissions[key])"
              />
              {{ key }}
            </label>
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
  </div>
</template>

<style scoped>
.staff-users { padding: 16px; }

.staff-users__filters {
  display: flex; gap: 8px; overflow-x: auto; margin-bottom: 16px; padding-bottom: 4px;
}
.filter-chip {
  padding: 6px 14px; border-radius: var(--radius-sm); border: 1px solid var(--border);
  background: var(--bg); color: var(--text-secondary); font-size: 12px; font-weight: 600;
  cursor: pointer; white-space: nowrap; text-transform: capitalize;
}
.filter-chip.active { background: var(--primary); color: white; border-color: var(--primary); }

.user-list { display: flex; flex-direction: column; }
.user-item {
  display: flex; align-items: center; gap: 12px; padding: 14px 0;
  border-bottom: 1px solid var(--border); cursor: pointer; transition: background 0.2s;
}
.user-item:hover { background: var(--bg-subtle); }
.user-item__info { flex: 1; min-width: 0; }
.user-item__name { font-size: 14px; font-weight: 600; color: var(--text); }
.user-item__detail { font-size: 12px; color: var(--text-tertiary); text-transform: capitalize; }
.user-item__right { text-align: right; flex-shrink: 0; }
.user-item__blocked { margin-top: 4px; }

.staff-users__pagination {
  display: flex; align-items: center; justify-content: center; gap: 12px; margin-top: 16px;
}
.staff-users__page { font-size: 13px; color: var(--text-secondary); }

.staff-users__center {
  display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 200px; gap: 16px;
}

/* Detail modal */
.detail__title { font-size: 18px; font-weight: 700; color: var(--text); margin: 0 0 16px; }
.detail__subtitle { font-size: 14px; font-weight: 700; color: var(--text); margin: 16px 0 8px; }
.detail__row { display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px solid var(--border); }
.detail__label { font-size: 13px; color: var(--text-secondary); }
.detail__value { font-size: 13px; color: var(--text); }
.detail__section { margin-top: 12px; }
.detail__perm { padding: 4px 0; }
.detail__perm-label { display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--text); cursor: pointer; }
.detail__actions { display: flex; gap: 8px; margin-top: 16px; }
.detail__confirm-text { font-size: 14px; color: var(--text-secondary); margin: 0 0 12px; }
</style>
