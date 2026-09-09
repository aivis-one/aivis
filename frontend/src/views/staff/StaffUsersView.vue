<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- StaffUsersView (iter 2.7 A3 + A5)
// =============================================================================
//
// Staff user management -- list, role / kyc_status filter, detail modal.
//   GET    /api/v1/staff/users (?role=, ?kyc_status=, ?page=, ?per_page=)
//   GET    /api/v1/staff/users/{id}
//   PATCH  /api/v1/staff/users/{id}/block
//   PATCH  /api/v1/staff/users/{id}/unblock
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
import {
  CAvatar,
  CBadge,
  CLoader,
  CButton,
  CModal,
  CEmptyState,
  CInput,
  CCheckbox,
} from '@/components/ui'
import { ApiResponseError } from '@/api/client'
import { useToast } from '@/composables/useToast'
import { useStaffPermissions } from '@/composables/useStaffPermissions'
import {
  fetchUsers,
  fetchUserDetail,
  blockUser,
  unblockUser,
  createStaff,
  updatePermissions,
  approveKYC,
  approveKYCUser,
  rejectKYC,
  revokeKYCUser,
} from '@/api/admin'
import {
  KYC_DOCUMENT_URL_TTL_SECONDS,
  fetchKycDocuments,
  requestKycDocumentUrl,
  type KycDocument,
} from '@/api/kyc'
import type {
  KYCDecisionRequest,
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
// (schema-side mini-iter that closed the 9-vs-8 drift). project_manage
// was added under TASK-30 §7, narrowing the company/pool/product/
// attachments write surface off company_manage to admin-only. The
// exhaustiveness assertion below now expects ten keys.
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
  'project_manage',
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
//
// `revoked` has been a member since H12 and was missing here until
// P-65. It could be left out while nothing in the product produced it;
// P-65 gives this very screen the button that does, and a panel that
// can revoke but cannot then list who was revoked is half a feature.
// The constant feeds three places at once -- the chip row, the
// query-parameter parse on arrival, and the KYCStatus type below --
// so one member covers all three.
const ALL_KYC_STATUSES = ['not_started', 'submitted', 'approved', 'rejected', 'revoked'] as const
type KYCStatus = (typeof ALL_KYC_STATUSES)[number]

const { t } = useI18n()

// WHY EVERY CATCH IN THIS FILE GOES THROUGH ONE FUNCTION.
//
// All nine handlers here used to be `catch {}` -- the binding dropped,
// the response body with it, and `common.error` shown whatever had
// happened. The backend does say what went wrong: the AivisError
// handler puts a machine `error` code AND a human `message` into every
// failure body, and the client turns that message into
// ApiResponseError.detail. The panel was throwing it away, which is
// how a 422 once hid behind "something went wrong" and cost a round of
// review.
//
// The server's sentence first, the screen's own text as the fallback --
// the same shape TransactionsView and InvestorSettingsView already use.
// The fallback is not decoration: ApiNetworkError and ApiTimeoutError
// carry no server sentence because no server answered, and a dropped
// connection must not be reported as a KYC verdict.
function serverReason(err: unknown, fallbackKey: string): string {
  return err instanceof ApiResponseError && err.detail ? err.detail : t(fallbackKey)
}
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

// Pagination steps are a NAMED CALL, not a two-statement inline expression.
// `@click="page--; loadUsers()"` is two statements in a template
// expression; prettier reflows it across lines and drops the semicolon, and
// Vue's expression parser cannot read the result -- the build fails outright.
// Measured on 2026-08-25, not predicted.
function goToPrevPage(): void {
  page.value--
  void loadUsers()
}

function goToNextPage(): void {
  page.value++
  void loadUsers()
}
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

// -- Unblock modal --
// No reason input -- unblock only reverses a prior block and does not
// need a fresh justification (mirrors the backend's unblock_user,
// which drops block_user's `reason` field for the same rationale).
const showUnblockModal = ref(false)

// -- Promote modal --
const showPromoteModal = ref(false)

// -- KYC decision modal (iter 2.7 A5, four modes since P-65) --
// H10: one modal for every decision. Approve used to fire straight from
// the button with no body; the backend now refuses a decision without a
// reason, and an approval is the decision that opens the whole product
// to an account -- it is the one that most needed a recorded why.
//
// TWO LEVELS, FOUR MODES. The pair this modal started with decides an
// APPLICATION: somebody paid, submitted documents, and waits in the
// queue. P-65 adds the pair that decides a PERSON, which the queue
// cannot reach -- approving someone who never applied (free, and the
// only way to let in an old user arriving under a new address) and
// withdrawing an approval already given.
//
// ONE TABLE INSTEAD OF FOUR TERNARIES. Title, hint, toast, button
// variant and the client to call all vary by mode. Expressed as
// conditionals in the template they were readable at two members and
// would be four nested ternaries each at four -- five independent
// places to edit when a fifth mode arrives, and nothing to make the
// person who edits one remember the other four. One record per mode
// keeps the whole of "what this mode is" in a single place.
type KycDecisionMode = 'approve' | 'reject' | 'approveUser' | 'revokeUser'

interface KycDecisionSpec {
  // Which id the request is addressed to. 'application' takes
  // latest_application_id, 'user' takes the user's own id.
  level: 'application' | 'user'
  labelKey: string
  hintKey: string
  toastKey: string
  variant: 'primary' | 'danger'
  send: (id: string, body: KYCDecisionRequest) => Promise<void>
}

const KYC_DECISION_SPECS: Record<KycDecisionMode, KycDecisionSpec> = {
  approve: {
    level: 'application',
    labelKey: 'staff.userDetail.kyc.approve',
    hintKey: 'staff.userDetail.kyc.approveHint',
    toastKey: 'staff.userDetail.kyc.approvedToast',
    variant: 'primary',
    send: approveKYC,
  },
  reject: {
    level: 'application',
    labelKey: 'staff.userDetail.kyc.reject',
    hintKey: 'staff.userDetail.kyc.rejectHint',
    toastKey: 'staff.userDetail.kyc.rejectedToast',
    variant: 'danger',
    send: rejectKYC,
  },
  approveUser: {
    level: 'user',
    labelKey: 'staff.userDetail.kyc.approveUser',
    hintKey: 'staff.userDetail.kyc.approveUserHint',
    toastKey: 'staff.userDetail.kyc.approvedUserToast',
    variant: 'primary',
    send: approveKYCUser,
  },
  revokeUser: {
    level: 'user',
    labelKey: 'staff.userDetail.kyc.revokeUser',
    hintKey: 'staff.userDetail.kyc.revokeUserHint',
    toastKey: 'staff.userDetail.kyc.revokedUserToast',
    variant: 'danger',
    send: revokeKYCUser,
  },
}

const showKycDecisionModal = ref(false)
const kycDecisionMode = ref<KycDecisionMode>('reject')
const kycDecisionReason = ref('')
const kycActionLoading = ref(false)

const kycDecisionSpec = computed(() => KYC_DECISION_SPECS[kycDecisionMode.value])

// WHOSE CARD OFFERS A PERSON-LEVEL KYC CONTROL AT ALL.
//
// NOT "the roles that go through the KYC gate" -- check that against
// kyc/gate.py and the list is wrong. GATE_EXEMPT_ROLES there is
// {staff, platform, agent, company}: an agent is exempt from the
// ROUTE gate and would drop out of this list on that reading.
//
// The reason is the MONEY path, which reads kyc_status with no regard
// for role at all: purchases/service.py and installments/service.py
// both refuse outright unless kyc_status is approved. So an agent, gate
// or no gate, cannot buy or take out an installment plan until somebody
// approves them -- and approving them by hand is the only free way to
// do it. That is what puts agent in this list, and it is why anybody
// "fixing" the list against GATE_EXEMPT_ROLES would break the flow.
//
// company is absent because it was not established whether a company
// user can buy at all; companies/service.py does create them carrying
// kyc_status=not_started. If the answer turns out to be yes, this list
// grows by one word.
const KYC_MONEY_ROLES = ['investor', 'agent'] as const

// FP-25 SELF-HIDE, WIDENED (P-65). The section used to appear only for
// somebody who already had an application row, on the ground that
// company and staff users never get one and an empty block is noise.
// That reasoning survives; what did not is the consequence, because
// the person with no application row is exactly who manual approval
// exists for -- the old user arriving under a new address. So the
// section also appears for a KYC_MONEY_ROLES person whose reviewer can
// act on them. Everyone else sees what they saw before: nothing.
const showKycSection = computed(() => {
  const user = detailUser.value
  if (!user) return false
  if (user.latest_application_id) return true
  return canDoKycApprove.value && (KYC_MONEY_ROLES as readonly string[]).includes(user.role)
})

// WHICH PERSON-LEVEL CONTROL, IF ANY. Exactly one is offered at a time
// and never beside the application-level pair, because two controls
// deciding one thing is two places for the rule to live.
//
// Order matters. An open application is answered through the queue's
// own pair, so it wins first -- which also means the state "approved
// person with a submitted application" needs no branch of its own: it
// lands here and is decided as the application it is.
//
// The final fallthrough sends every OTHER kyc_status, including one
// this file has never heard of, to manual approval rather than to
// revocation. Deliberate: approval is reversible here (revocation is
// the control right above it) and revocation of an unknown state is
// not. The backend refuses either way if the state does not permit it
// -- kyc_already_approved / kyc_not_approved -- and serverReason puts
// that sentence on the screen.
const kycPersonAction = computed<'approveUser' | 'revokeUser' | null>(() => {
  const user = detailUser.value
  if (!user || !canDoKycApprove.value) return null
  if (user.latest_application_status === 'submitted') return null
  return user.kyc_status === 'approved' ? 'revokeUser' : 'approveUser'
})

const totalPages = computed(() => Math.ceil(total.value / perPage))

const kycVariant = (status: string) => {
  if (status === 'approved') return 'success'
  if (status === 'submitted') return 'warning'
  // Revoked reads as danger alongside rejected, not as neutral: both
  // say the person cannot buy. Neutral is for not_started, where
  // nothing has gone wrong and nobody has done anything yet.
  if (status === 'rejected' || status === 'revoked') return 'danger'
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
  } catch (err) {
    error.value = true
    showToast(serverReason(err, 'common.error'), 'error')
  } finally {
    loading.value = false
  }
}

async function openDetail(userId: string): Promise<void> {
  showDetail.value = true
  detailLoading.value = true
  detailUser.value = null
  kycDocuments.value = []
  // A TTL belongs to the link it was issued for. Carrying the previous
  // card's number into this one would state a duration for documents
  // nobody has asked for yet.
  kycDocumentTtl.value = KYC_DOCUMENT_URL_TTL_SECONDS
  try {
    detailUser.value = await fetchUserDetail(userId)
    await loadKycDocuments()
  } catch (err) {
    showToast(serverReason(err, 'common.error'), 'error')
    showDetail.value = false
  } finally {
    detailLoading.value = false
  }
}

// -- KYC documents (H12) --
//
// LISTED ON OPEN, NOT ON DEMAND, because the reason the documents exist
// is that a decision must not be made without looking at them: a panel
// that hides them behind a second click invites deciding from the
// status badge alone.
//
// THE IMAGES THEMSELVES ARE NOT FETCHED HERE. Each one costs a POST
// that records who looked, so a link is issued when a staff member
// actually opens a document -- listing a person's application is not
// the same act as reading their passport, and the audit log must be
// able to tell them apart.

const kycDocuments = ref<KycDocument[]>([])
const kycDocumentsLoading = ref(false)
const kycDocumentPending = ref<string | null>(null)

// How long the last link this panel issued is good for. The number is
// the server's, not ours: the endpoint returns ttl_seconds so the
// screen can say when the link stops working without a client-side
// copy of the backend's setting drifting from it. The constant is the
// starting value only, for the notice shown before any link exists.
const kycDocumentTtl = ref<number>(KYC_DOCUMENT_URL_TTL_SECONDS)

const DOCUMENT_KIND_LABELS: Record<string, string> = {
  front: 'staff.userDetail.kyc.documents.kindFront',
  back: 'staff.userDetail.kyc.documents.kindBack',
  selfie: 'staff.userDetail.kyc.documents.kindSelfie',
}

async function loadKycDocuments(): Promise<void> {
  const applicationId = detailUser.value?.latest_application_id
  // No application, or no permission to look: nothing to ask for. The
  // backend would refuse the second case anyway; not asking keeps a
  // guaranteed 403 out of the console on every modal open.
  if (!applicationId || !canDoKycApprove.value) {
    kycDocuments.value = []
    return
  }

  kycDocumentsLoading.value = true
  try {
    kycDocuments.value = await fetchKycDocuments(applicationId)
  } catch (err) {
    kycDocuments.value = []
    showToast(serverReason(err, 'staff.userDetail.kyc.documents.errorLoad'), 'error')
  } finally {
    kycDocumentsLoading.value = false
  }
}

async function openKycDocument(documentId: string): Promise<void> {
  if (!canDoKycApprove.value) {
    console.warn('[StaffUsersView] document open blocked: no kyc_approve permission')
    return
  }

  kycDocumentPending.value = documentId
  try {
    const { url, ttl_seconds } = await requestKycDocumentUrl(documentId)
    // A failed request leaves this alone on purpose: the notice
    // describes the links that were issued, and a request that failed
    // issued none.
    kycDocumentTtl.value = ttl_seconds
    // noopener: the signed URL travels in the new tab's address bar,
    // and a document viewer has no business holding a handle on the
    // staff panel that opened it.
    window.open(url, '_blank', 'noopener')
  } catch (err) {
    showToast(serverReason(err, 'staff.userDetail.kyc.documents.errorLink'), 'error')
  } finally {
    kycDocumentPending.value = null
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
  } catch (err) {
    showToast(serverReason(err, 'common.error'), 'error')
  } finally {
    actionLoading.value = false
  }
}

async function handleUnblock(): Promise<void> {
  if (!detailUser.value) return
  actionLoading.value = true
  try {
    await unblockUser(detailUser.value.id)
    showToast(t('staff.userDetail.unblockedNote'), 'success')
    showUnblockModal.value = false
    showDetail.value = false
    await loadUsers()
  } catch (err) {
    showToast(serverReason(err, 'common.error'), 'error')
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
  } catch (err) {
    showToast(serverReason(err, 'common.error'), 'error')
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
  } catch (err) {
    showToast(serverReason(err, 'common.error'), 'error')
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

function openKycDecision(mode: KycDecisionMode): void {
  if (!canDoKycApprove.value) {
    console.warn(`[StaffUsersView] kyc ${mode} blocked: no kyc_approve permission`)
    return
  }
  kycDecisionMode.value = mode
  kycDecisionReason.value = ''
  showKycDecisionModal.value = true
}

async function handleKycDecision(): Promise<void> {
  if (!detailUser.value) return
  if (!canDoKycApprove.value) {
    console.warn('[StaffUsersView] kyc decision blocked: no kyc_approve permission')
    return
  }
  const spec = KYC_DECISION_SPECS[kycDecisionMode.value]
  // WHICH ID THIS DECISION IS ADDRESSED TO. Until P-65 the handler read
  // latest_application_id unconditionally and returned when it was
  // null -- which silently disabled the modal for exactly the person
  // the person-level path exists to serve, the one who never applied.
  const targetId =
    spec.level === 'application' ? detailUser.value.latest_application_id : detailUser.value.id
  // The application-level modes are only reachable from a card whose
  // latest application is `submitted`, so the id is there. The check is
  // the type-level floor, not a route somebody takes.
  if (!targetId) return
  // The confirm button stays disabled while the trimmed input is empty;
  // this check covers whitespace-only entries, which the backend also
  // refuses -- better to stop here than to spend a request on a 422.
  const reason = kycDecisionReason.value.trim()
  if (!reason) return

  kycActionLoading.value = true
  try {
    await spec.send(targetId, { reason })
    showToast(t(spec.toastKey), 'success')
    showKycDecisionModal.value = false
    kycDecisionReason.value = ''
    // Refetch detail so the badge and history reflect the new state,
    // then the list so the chip-filtered counts stay accurate. This is
    // also what moves the card between the person-level controls: a
    // manual approval creates an application row server-side, so the
    // refetched card offers Revoke where it offered Approve.
    detailUser.value = await fetchUserDetail(detailUser.value.id)
    await loadUsers()
  } catch (err) {
    showToast(serverReason(err, 'common.error'), 'error')
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
        <button class="filter-chip" :class="{ active: !roleFilter }" @click="setRoleFilter('')">
          {{ t('common.all') }}
        </button>
        <button
          v-for="r in ['investor', 'agent', 'company', 'staff']"
          :key="r"
          class="filter-chip"
          :class="{ active: roleFilter === r }"
          @click="setRoleFilter(r)"
        >
          {{ r }}
        </button>
      </div>
      <div class="staff-users__filter-row">
        <button
          class="filter-chip filter-chip--kyc"
          :class="{ active: !kycStatusFilter }"
          @click="setKycStatusFilter('')"
        >
          {{ t('staff.userDetail.kyc.filterAll') }}
        </button>
        <button
          v-for="s in ALL_KYC_STATUSES"
          :key="s"
          class="filter-chip filter-chip--kyc"
          :class="{ active: kycStatusFilter === s }"
          @click="setKycStatusFilter(s)"
        >
          {{ t(`staff.userDetail.kyc.filter.${s}`) }}
        </button>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="staff-users__center">
      <CLoader :size="32" />
    </div>

    <!-- Error -->
    <div v-else-if="error" class="staff-users__center">
      <CButton variant="secondary" size="sm" @click="loadUsers">
        {{ t('common.retry') }}
      </CButton>
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
            <div class="user-item__name">
              {{ fullName(item) }}
            </div>
            <div class="user-item__detail">{{ item.role }} &bull; {{ item.email ?? '—' }}</div>
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
        <CButton variant="outline" size="sm" :disabled="page <= 1" @click="goToPrevPage()">
          &larr;
        </CButton>
        <span class="staff-users__page">{{ page }} / {{ totalPages }}</span>
        <CButton variant="outline" size="sm" :disabled="page >= totalPages" @click="goToNextPage()">
          &rarr;
        </CButton>
      </div>
    </template>

    <!-- Detail modal -->
    <CModal :open="showDetail" @close="showDetail = false">
      <div v-if="detailLoading" class="staff-users__center" style="min-height: 200px">
        <CLoader :size="24" />
      </div>
      <template v-else-if="detailUser">
        <h3 class="detail__title">
          {{ t('staff.userDetail.title') }}
        </h3>
        <div class="detail__row">
          <span class="detail__label">{{ t('staff.userDetail.role') }}</span>
          <CBadge :variant="roleVariant(detailUser.role)" :text="detailUser.role" />
        </div>
        <div class="detail__row">
          <span class="detail__label">{{ t('staff.userDetail.status') }}</span>
          <CBadge
            :variant="detailUser.is_active ? 'success' : 'danger'"
            :text="
              detailUser.is_active ? t('staff.userDetail.active') : t('staff.userDetail.blocked')
            "
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
            <Clock :size="16" style="vertical-align: -1px" />
            {{ formatDate(detailUser.created_at) }}
          </span>
        </div>

        <!-- KYC section (iter 2.7 A5, widened by P-65).
             Visibility is showKycSection: an application row as before,
             or a person a reviewer may still act on. See the computed
             for why the role list is what it is.

             FP-23 double guard on every control:
               1. canDoKycApprove wraps them (template guard);
               2. handlers re-check + console.warn before firing.
             The application-level pair stays restricted to
             status=submitted; the person-level control appears only
             when that pair does not, and picks itself in
             kycPersonAction. -->
        <div v-if="showKycSection" class="detail__section">
          <h4 class="detail__subtitle">
            {{ t('staff.userDetail.kyc.sectionTitle') }}
          </h4>

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
          <div v-if="detailUser.kyc_applications_history.length > 1" class="kyc-history">
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

          <!-- Documents (H12). Only for staff who may decide: the
               owner tied looking and deciding to one permission on
               purpose -- approving without looking is what these
               exist to prevent. -->
          <div v-if="canDoKycApprove && detailUser.latest_application_id" class="kyc-documents">
            <div class="kyc-documents__title">
              {{ t('staff.userDetail.kyc.documents.title') }}
            </div>
            <div v-if="kycDocumentsLoading" class="kyc-documents__empty">
              {{ t('common.loading') }}
            </div>
            <div v-else-if="kycDocuments.length === 0" class="kyc-documents__empty">
              {{ t('staff.userDetail.kyc.documents.empty') }}
            </div>
            <template v-else>
              <ul class="kyc-documents__list">
                <li
                  v-for="doc in kycDocuments"
                  :key="doc.id"
                  class="kyc-documents__row"
                >
                  <span class="kyc-documents__kind">
                    {{ t(DOCUMENT_KIND_LABELS[doc.kind] ?? doc.kind) }}
                  </span>
                  <CButton
                    variant="outline"
                    size="sm"
                    :disabled="kycDocumentPending === doc.id"
                    @click="openKycDocument(doc.id)"
                  >
                    {{ t('staff.userDetail.kyc.documents.view') }}
                  </CButton>
                </li>
              </ul>
              <p class="kyc-documents__notice">
                {{ t('staff.userDetail.kyc.documents.ttlNotice', { seconds: kycDocumentTtl }) }}
              </p>
            </template>
          </div>

          <!-- Application-level pair. Visible only while the latest
               application is still pending (status=submitted) AND the
               current staff has kyc_approve. -->
          <div
            v-if="detailUser.latest_application_status === 'submitted' && canDoKycApprove"
            class="detail__actions"
          >
            <CButton
              variant="primary"
              size="sm"
              :disabled="kycActionLoading"
              @click="openKycDecision('approve')"
            >
              {{ t('staff.userDetail.kyc.approve') }}
            </CButton>
            <CButton
              variant="danger"
              size="sm"
              :disabled="kycActionLoading"
              @click="openKycDecision('reject')"
            >
              {{ t('staff.userDetail.kyc.reject') }}
            </CButton>
          </div>

          <!-- Person-level control (P-65). Mutually exclusive with the
               pair above by construction: kycPersonAction is null while
               an application is open. -->
          <div v-else-if="kycPersonAction" class="detail__actions">
            <CButton
              :variant="KYC_DECISION_SPECS[kycPersonAction].variant"
              size="sm"
              :disabled="kycActionLoading"
              @click="openKycDecision(kycPersonAction)"
            >
              {{ t(KYC_DECISION_SPECS[kycPersonAction].labelKey) }}
            </CButton>
          </div>
        </div>

        <!-- Staff permissions (if staff) -->
        <div v-if="detailUser.staff_profile" class="detail__section">
          <h4 class="detail__subtitle">
            {{ t('staff.userDetail.permissions') }}
          </h4>
          <div v-for="key in ALL_PERMISSION_KEYS" :key="key" class="detail__perm">
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
            variant="danger"
            size="sm"
            @click="showBlockModal = true"
          >
            {{ t('staff.userDetail.block') }}
          </CButton>
          <!-- Unblock: inverse of the block button's is_active gate.
               Deliberately NOT restricted to role !== 'staff' -- a
               user can be promoted to staff while still blocked
               (create_staff does not check is_active on the backend),
               and unblock must still be reachable for that account. -->
          <CButton
            v-if="!detailUser.is_active"
            variant="primary"
            size="sm"
            @click="showUnblockModal = true"
          >
            {{ t('staff.userDetail.unblock') }}
          </CButton>
          <CButton
            v-if="detailUser.role !== 'staff'"
            variant="secondary"
            size="sm"
            @click="showPromoteModal = true"
          >
            {{ t('staff.userDetail.promoteToStaff') }}
          </CButton>
        </div>
      </template>
    </CModal>

    <!-- Block confirmation -->
    <CModal :open="showBlockModal" @close="showBlockModal = false">
      <h3 class="detail__title">
        {{ t('staff.userDetail.block') }}
      </h3>
      <p class="detail__confirm-text">
        {{ t('staff.userDetail.blockConfirm') }}
      </p>
      <CInput
        v-model="blockReason"
        :label="t('staff.userDetail.blockReason')"
        :placeholder="t('staff.userDetail.blockReason')"
      />
      <div class="detail__actions" style="margin-top: 16px">
        <CButton variant="outline" size="sm" @click="showBlockModal = false">
          {{ t('common.cancel') }}
        </CButton>
        <CButton variant="danger" size="sm" :loading="actionLoading" @click="handleBlock">
          {{ t('common.confirm') }}
        </CButton>
      </div>
    </CModal>

    <!-- Unblock confirmation. No reason input -- see the handleUnblock
         comment and the backend's unblock_user docstring. -->
    <CModal :open="showUnblockModal" @close="showUnblockModal = false">
      <h3 class="detail__title">
        {{ t('staff.userDetail.unblock') }}
      </h3>
      <p class="detail__confirm-text">
        {{ t('staff.userDetail.unblockConfirm') }}
      </p>
      <div class="detail__actions" style="margin-top: 16px">
        <CButton variant="outline" size="sm" @click="showUnblockModal = false">
          {{ t('common.cancel') }}
        </CButton>
        <CButton variant="primary" size="sm" :loading="actionLoading" @click="handleUnblock">
          {{ t('common.confirm') }}
        </CButton>
      </div>
    </CModal>

    <!-- Promote confirmation -->
    <CModal :open="showPromoteModal" @close="showPromoteModal = false">
      <h3 class="detail__title">
        {{ t('staff.userDetail.promoteToStaff') }}
      </h3>
      <p class="detail__confirm-text">
        {{ t('staff.userDetail.promoteConfirm') }}
      </p>
      <div class="detail__actions" style="margin-top: 16px">
        <CButton variant="outline" size="sm" @click="showPromoteModal = false">
          {{ t('common.cancel') }}
        </CButton>
        <CButton variant="primary" size="sm" :loading="actionLoading" @click="handlePromote">
          {{ t('common.confirm') }}
        </CButton>
      </div>
    </CModal>

    <!-- KYC decision reason (iter 2.7 A5, four modes since P-65).
         Reason is REQUIRED per R1 §3 -- the confirm button stays
         disabled while the trimmed input is empty. Everything that
         varies by mode comes from kycDecisionSpec; see the table. -->
    <CModal :open="showKycDecisionModal" @close="showKycDecisionModal = false">
      <h3 class="detail__title">
        {{ t(kycDecisionSpec.labelKey) }}
      </h3>
      <p class="detail__confirm-text">
        {{ t(kycDecisionSpec.hintKey) }}
      </p>
      <CInput
        v-model="kycDecisionReason"
        :label="t('staff.userDetail.kyc.reason')"
        :placeholder="t('staff.userDetail.kyc.reason')"
      />
      <div class="detail__actions" style="margin-top: 16px">
        <CButton variant="outline" size="sm" @click="showKycDecisionModal = false">
          {{ t('common.cancel') }}
        </CButton>
        <CButton
          :variant="kycDecisionSpec.variant"
          size="sm"
          :disabled="!kycDecisionReason.trim() || kycActionLoading"
          :loading="kycActionLoading"
          @click="handleKycDecision"
        >
          {{ t(kycDecisionSpec.labelKey) }}
        </CButton>
      </div>
    </CModal>
  </div>
</template>

<style scoped>
.staff-users {
  padding: var(--space-4);
}

/* iter 2.7 A5: filters are now two stacked rows (role + kyc_status).
   Each row scrolls horizontally on narrow viewports. */
.staff-users__filters {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin-bottom: var(--space-4);
}
.staff-users__filter-row {
  display: flex;
  gap: var(--space-2);
  overflow-x: auto;
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
  font-family: inherit;
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

/* Subtle visual distinction for KYC chips so the user can tell which
   row is which at a glance without reading. The kyc chips share the
   same active state with role chips for behaviour parity. */
.filter-chip--kyc {
  text-transform: none;
}

.user-list {
  display: flex;
  flex-direction: column;
}
.user-item {
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
  transition: background 0.2s;
}
.user-item:hover {
  background: var(--bg-subtle);
}
.user-item__info {
  flex: 1;
  min-width: 0;
}
.user-item__name {
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--text-primary);
}
.user-item__detail {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
  text-transform: capitalize;
}
.user-item__right {
  text-align: right;
  flex-shrink: 0;
}
.user-item__blocked {
  margin-top: var(--space-1);
}

.staff-users__pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  margin-top: var(--space-4);
}
.staff-users__page {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
}

.staff-users__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: var(--center-md);
  gap: var(--space-4);
}

/* Detail modal */
.detail__title {
  font-size: var(--fs-h4);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 var(--space-4);
}
.detail__subtitle {
  font-size: var(--fs-sm);
  font-weight: 700;
  color: var(--text-primary);
  margin: var(--space-4) 0 var(--space-2);
}
.detail__row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-2) 0;
  border-bottom: 1px solid var(--border-default);
}
.detail__label {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
}
.detail__value {
  font-size: var(--fs-sm);
  color: var(--text-primary);
}
.detail__section {
  margin-top: var(--space-3);
}
.detail__perm {
  padding: var(--space-1) 0;
}
.detail__actions {
  display: flex;
  gap: var(--space-2);
  margin-top: var(--space-4);
  flex-wrap: wrap;
}
.detail__confirm-text {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  margin: 0 0 var(--space-3);
}

/* KYC history timeline (iter 2.7 A5). */
.kyc-documents {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.kyc-documents__title {
  font-weight: 600;
}

.kyc-documents__empty,
.kyc-documents__notice {
  color: var(--text-secondary);
  font-size: var(--fs-sm);
}

.kyc-documents__list {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  list-style: none;
  padding: 0;
}

.kyc-documents__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}

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
.detail__subtitle {
  max-width: var(--maxw-prose);
}
</style>
