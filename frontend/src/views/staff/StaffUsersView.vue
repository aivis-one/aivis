<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- StaffUsersView (iter 2.7 A3 + A5)
// =============================================================================
//
// Staff user management -- list, search, role / kyc_status filter, detail modal.
//   GET    /api/v1/staff/users (?search=, ?role=, ?kyc_status=, ?page=, ?per_page=)
//   GET    /api/v1/staff/users/{id}
//   PATCH  /api/v1/staff/users/{id}/block
//   PATCH  /api/v1/staff/users/{id}/unblock
//   PATCH  /api/v1/staff/users/{id}/email (admin only, H28 P-105)
//   POST   /api/v1/staff/users (promote to staff, admin only)
//   PATCH  /api/v1/staff/users/{id}/permissions (admin only)
//   POST   /api/v1/staff/users/{staff_profile_id}/deactivate (admin only)
//   POST   /api/v1/staff/kyc/{application_id}/approve  (iter 2.7 A5)
//   POST   /api/v1/staff/kyc/{application_id}/reject   (iter 2.7 A5)
//
// The permission keys the card shows are checked both ways at compile time
// in utils/staffRights.ts (PERMISSION_KEYS): a key the backend schema lacks or
// a new one this screen forgot fails the type check.
//
// What a member sees follows their rights: the Block and Unblock buttons need
// user_block; promoting, the rights card and taking a member off duty are the
// administrator's (every permission on); the KYC section needs kyc_approve.
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

import { ref, onMounted, onBeforeUnmount, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Check, FileText, Ghost } from '@/components/ui/icons'
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
import CAlert from '@/components/ui/CAlert.vue'
import CListSkeleton from '@/components/ui/CListSkeleton.vue'
import CPager from '@/components/ui/CPager.vue'
import { useUrlPage } from '@/components/ui/useUrlPage'
import { tOrRaw } from '@/utils/i18n'
import {
  PERMISSION_CARD_KEYS,
  PERMISSION_PRESETS,
  adminChangeOfTick,
  adminPatch,
  holdsEveryPermission,
  matchingPreset,
  presetPatch,
} from '@/utils/staffRights'
import type { PermissionPreset } from '@/utils/staffRights'
import { ApiResponseError } from '@/api/client'
import { useToast } from '@/composables/useToast'
import { useStaffPermissions } from '@/composables/useStaffPermissions'
import { useAvatar } from '@/composables/useAvatar'
import { useAuthStore } from '@/stores/auth'
import {
  fetchUsers,
  fetchUserDetail,
  blockUser,
  changeUserEmail,
  unblockUser,
  createStaff,
  deactivateStaff,
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
// regardless of optional-on-the-wire shape. The list of keys the card shows
// (and its compile-time exhaustiveness check) lives in utils/staffRights.ts,
// next to the presets and the section table that read the same keys.
type PermissionKey = keyof Required<UpdatePermissionsRequest>

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
const { canDo, isAdmin } = useStaffPermissions()
const authStore = useAuthStore()

// iter 2.7 A5: FP-23 template guard for the Approve / Reject buttons
// in the detail modal's KYC section. Reads the effective permission
// merged with defaults on the current staff member.
const canDoKycApprove = canDo('kyc_approve')
// Blocking and unblocking need user_block; the buttons are not drawn without it.
const canBlock = canDo('user_block')

// -- From the card to the person's money and into their cabinet --
//
// Payments and withdrawals are read with payment_review, purchases with
// financial_operations; the lists open already narrowed to the person (the
// address names them, see composables/useUrlUserFilter.ts). "Act as this user"
// starts the avatar mode and needs avatar_mode; the server refuses a staff or
// platform target, so the card does not offer it for one.
const canSeePayments = canDo('payment_review')
const canSeePurchases = canDo('financial_operations')
const canAct = canDo('avatar_mode')
const router = useRouter()
const { loading: avatarLoading, startAvatarSession } = useAvatar()
const showActAsModal = ref(false)

/** A person who has money in the product: not a staff member, not the platform. */
const hasMoneyView = computed(
  () => detailUser.value != null && !['staff', 'platform'].includes(detailUser.value.role),
)
const showMoneyLinks = computed(
  () => hasMoneyView.value && (canSeePayments.value || canSeePurchases.value),
)
const canActAs = computed(
  () => hasMoneyView.value && canAct.value && detailUser.value?.id !== authStore.user?.id,
)

function openList(path: string, param: 'user_id' | 'buyer_id'): void {
  if (!detailUser.value) return
  const query = { [param]: detailUser.value.id }
  showDetail.value = false
  void router.push({ path, query })
}

async function handleActAs(): Promise<void> {
  if (!detailUser.value) return
  const id = detailUser.value.id
  showActAsModal.value = false
  showDetail.value = false
  await startAvatarSession(id)
}

// Names the screen shows for what the server sends as tokens: a role is
// spoken as a person would (buyer, integrator, project, staff), a status as
// the filter chips say it.
function roleLabel(role: string): string {
  return tOrRaw(t, `staff.roles.${role}`, role)
}
function kycLabel(status: string): string {
  return tOrRaw(t, `staff.userDetail.kyc.filter.${status}`, status)
}
function stepLabel(step: string): string {
  return tOrRaw(t, `staff.userDetail.onboardingSteps.${step}`, step)
}
function permissionLabel(key: string): string {
  return tOrRaw(t, `staff.rights.keys.${key}`, key)
}

// -- List state --
const items = ref<UserListItem[]>([])
const total = ref(0)
const page = useUrlPage()

function goToPage(n: number): void {
  page.value = n
  void loadUsers()
}
const perPage = 20
const roleFilter = ref('')
// The search box: what is typed (`searchInput`) and what the list is read
// with (`search`). The list follows the typing after a short pause, and at
// once on Enter; a search of less than two letters reads the whole list.
const searchInput = ref('')
const search = ref('')
const SEARCH_PAUSE_MS = 350
let searchTimer: ReturnType<typeof setTimeout> | null = null
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

// -- Change email modal (H28 P-105) --
// Support is the only way an address changes, and only an admin may do
// it (the backend re-checks). Not offered on the admin's own card: a
// change of one's own address is the self-service path the product
// removed, and the backend refuses it. The reason is required (it is the
// audit row's only record of why); the button stays disabled until both
// fields carry something other than blanks.
const showEmailModal = ref(false)
const newEmail = ref('')
const emailReason = ref('')
const canChangeEmail = computed(
  () =>
    isAdmin.value &&
    detailUser.value != null &&
    detailUser.value.id !== authStore.user?.id &&
    detailUser.value.role !== 'platform',
)
const emailFormFilled = computed(
  () => newEmail.value.trim() !== '' && emailReason.value.trim() !== '',
)

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

// Each read carries a number; an answer that comes back after a newer read
// was started is dropped, so the list always shows the LAST filter chosen even
// when the chips are pressed faster than the server answers.
let loadEpoch = 0

async function loadUsers(): Promise<void> {
  const mine = ++loadEpoch
  loading.value = true
  error.value = false
  try {
    const resp = await fetchUsers({
      role: roleFilter.value || undefined,
      kyc_status: kycStatusFilter.value || undefined,
      search: search.value || undefined,
      page: page.value,
      per_page: perPage,
    })
    if (mine !== loadEpoch) return
    items.value = resp.items
    total.value = resp.total
  } catch (err) {
    if (mine !== loadEpoch) return
    error.value = true
    showToast(serverReason(err, 'common.error'), 'error')
  } finally {
    if (mine === loadEpoch) loading.value = false
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

function applySearch(): void {
  if (searchTimer) {
    clearTimeout(searchTimer)
    searchTimer = null
  }
  const typed = searchInput.value.trim()
  // The server matches a substring; one letter matches nearly everyone.
  const next = typed.length >= 2 ? typed : ''
  if (next === search.value) return
  search.value = next
  page.value = 1
}

watch(searchInput, () => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(applySearch, SEARCH_PAUSE_MS)
})

onBeforeUnmount(() => {
  if (searchTimer) clearTimeout(searchTimer)
})

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

async function handleChangeEmail(): Promise<void> {
  if (!detailUser.value || !emailFormFilled.value) return
  actionLoading.value = true
  try {
    await changeUserEmail(detailUser.value.id, {
      email: newEmail.value.trim(),
      reason: emailReason.value.trim(),
    })
    showToast(t('staff.userDetail.emailChanged'), 'success')
    showEmailModal.value = false
    newEmail.value = ''
    emailReason.value = ''
    await loadUsers()
  } catch (err) {
    // 409 (address taken), 400 (no email / same address) and 422 (not
    // an address) all carry the server's own reason.
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
//
// A tick that marks the last shown right makes the member an administrator (the
// card sends translation_edit on with it), and a tick that clears a right of an
// administrator takes the mark away. Both are asked first, with a warning.
type AdminChange = 'grant' | 'remove' | 'make'
const adminAsk = ref<{ change: AdminChange; key?: PermissionKey; value?: boolean } | null>(null)
const ownCard = computed(
  () => detailUser.value != null && detailUser.value.id === authStore.user?.id,
)

async function setPermission(key: PermissionKey, value: boolean): Promise<void> {
  if (!detailUser.value?.staff_profile) return
  const change = adminChangeOfTick(detailUser.value.staff_profile.permissions, key, value)
  if (change) {
    adminAsk.value = { change, key, value }
    return
  }
  await sendPermission(key, value)
}

async function sendPermission(key: PermissionKey, value: boolean): Promise<void> {
  if (!detailUser.value?.staff_profile) return
  const next = { ...detailUser.value.staff_profile.permissions, [key]: value }
  const everyShown = PERMISSION_CARD_KEYS.every((k) => next[k] === true)
  try {
    const updated = await updatePermissions(detailUser.value.staff_profile.id, {
      [key]: value,
      translation_edit: everyShown,
    })
    detailUser.value.staff_profile = updated
    showToast(t('staff.userDetail.permissionsUpdated'), 'success')
  } catch (err) {
    showToast(serverReason(err, 'common.error'), 'error')
  }
}

// "Make administrator": every one of the ten keys on in one request.
async function makeAdministrator(): Promise<void> {
  if (!detailUser.value?.staff_profile || !isAdmin.value) return
  try {
    detailUser.value.staff_profile = await updatePermissions(
      detailUser.value.staff_profile.id,
      adminPatch(),
    )
    showToast(t('staff.userDetail.permissionsUpdated'), 'success')
  } catch (err) {
    showToast(serverReason(err, 'common.error'), 'error')
  }
}

async function confirmAdminAsk(): Promise<void> {
  const ask = adminAsk.value
  adminAsk.value = null
  if (!ask) return
  if (ask.change === 'make') await makeAdministrator()
  else if (ask.key !== undefined && ask.value !== undefined)
    await sendPermission(ask.key, ask.value)
}

// One press of a preset marks its set: the member holds exactly those rights
// afterwards (utils/staffRights.ts says why it replaces rather than adds).
async function applyPreset(preset: PermissionPreset): Promise<void> {
  if (!detailUser.value?.staff_profile || !isAdmin.value) return
  try {
    const updated = await updatePermissions(detailUser.value.staff_profile.id, presetPatch(preset))
    detailUser.value.staff_profile = updated
    showToast(t('staff.userDetail.permissionsUpdated'), 'success')
  } catch (err) {
    showToast(serverReason(err, 'common.error'), 'error')
  }
}

const activePreset = computed(() => matchingPreset(detailUser.value?.staff_profile?.permissions))
const isEveryRight = computed(() =>
  holdsEveryPermission(detailUser.value?.staff_profile?.permissions),
)

// Taking a member off duty (administrator only). Not offered on one's own
// card, and only while the member is on duty.
const showDeactivateModal = ref(false)
const canDeactivate = computed(
  () =>
    isAdmin.value &&
    detailUser.value?.staff_profile?.is_active === true &&
    detailUser.value.id !== authStore.user?.id,
)

async function handleDeactivate(): Promise<void> {
  const profile = detailUser.value?.staff_profile
  if (!detailUser.value || !profile) return
  actionLoading.value = true
  try {
    detailUser.value.staff_profile = await deactivateStaff(profile.id)
    showToast(t('staff.userDetail.deactivated'), 'success')
    showDeactivateModal.value = false
    await loadUsers()
  } catch (err) {
    showToast(serverReason(err, 'common.error'), 'error')
  } finally {
    actionLoading.value = false
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

watch([roleFilter, kycStatusFilter, search], () => loadUsers())

// A press on the Home's identity-check counter while this list is already open
// changes only the address; the chip follows it, and the list is read again by
// the watch above.
watch(
  () => route.query.kyc_status,
  (value) => {
    const next = String(value ?? '')
    const status = (ALL_KYC_STATUSES as readonly string[]).includes(next) ? (next as KYCStatus) : ''
    if (status !== kycStatusFilter.value) {
      kycStatusFilter.value = status
      page.value = 1
    }
  },
)

onMounted(loadUsers)
</script>

<template>
  <div class="staff-users">
    <!-- Filters: role chips top row, kyc_status chips bottom row.
         iter 2.7 A5: KYC chip row added below the existing role row;
         the two filters compose at the backend boundary. -->
    <div class="staff-users__filters">
      <CInput
        v-model="searchInput"
        type="search"
        autocomplete="off"
        :placeholder="t('staff.searchPlaceholder')"
        :aria-label="t('staff.searchPlaceholder')"
        maxlength="255"
        @keydown.enter.prevent="applySearch"
      />
      <div class="ds-chip-row" role="group" :aria-label="t('staff.userDetail.role')">
        <button
          class="ds-chip"
          :aria-pressed="!roleFilter"
          @click="setRoleFilter('')"
          type="button"
        >
          <Check class="ds-chip__check" size="sm" />
          <span>{{ t('common.all') }}</span>
        </button>
        <button
          v-for="r in ['investor', 'agent', 'company', 'staff']"
          :key="r"
          class="ds-chip"
          :aria-pressed="roleFilter === r"
          @click="setRoleFilter(r)"
          type="button"
        >
          <Check class="ds-chip__check" size="sm" />
          <span>{{ roleLabel(r) }}</span>
        </button>
      </div>
      <div class="ds-chip-row" role="group" :aria-label="t('staff.userDetail.kycStatus')">
        <button
          class="ds-chip"
          :aria-pressed="!kycStatusFilter"
          @click="setKycStatusFilter('')"
          type="button"
        >
          <Check class="ds-chip__check" size="sm" />
          <span>{{ t('staff.userDetail.kyc.filterAll') }}</span>
        </button>
        <button
          v-for="s in ALL_KYC_STATUSES"
          :key="s"
          class="ds-chip"
          :aria-pressed="kycStatusFilter === s"
          @click="setKycStatusFilter(s)"
          type="button"
        >
          <Check class="ds-chip__check" size="sm" />
          <span>{{ t(`staff.userDetail.kyc.filter.${s}`) }}</span>
        </button>
      </div>
    </div>

    <!-- Loading -->
    <CListSkeleton v-if="loading" />

    <!-- Error -->
    <CEmptyState v-else-if="error" tone="danger" :title="t('common.error')">
      <template #actions>
        <CButton variant="secondary" size="sm" inline @click="loadUsers">
          {{ t('common.retry') }}
        </CButton>
      </template>
    </CEmptyState>

    <!-- Empty -->
    <CEmptyState v-else-if="!items.length" :title="t('common.noResults')" />

    <!-- List (K23 rows; a row opens the person's card in place) -->
    <template v-else>
      <ul class="ds-rows user-list">
        <li v-for="item in items" :key="item.id" class="ds-row">
          <CAvatar :name="fullName(item)" :size="32" />
          <span class="ds-row__body">
            <button type="button" class="ds-row__link user-item" @click="openDetail(item.id)">
              <span class="ds-row__title">{{ fullName(item) }}</span>
            </button>
            <span class="ds-row__meta">
              {{ roleLabel(item.role) }} &bull; {{ item.email ?? '—' }}
            </span>
          </span>
          <span class="ds-row__trail">
            <CBadge :variant="kycVariant(item.kyc_status)" :text="kycLabel(item.kyc_status)" />
            <CBadge v-if="!item.is_active" variant="danger" :text="t('staff.userDetail.blocked')" />
          </span>
        </li>
      </ul>

      <!-- Pagination (K17) -->
      <CPager :page="page" :total-pages="totalPages" @update:page="goToPage" />
    </template>

    <!-- Detail modal -->
    <CModal
      :open="showDetail"
      :title="detailUser && !detailLoading ? t('staff.userDetail.title') : undefined"
      @close="showDetail = false"
    >
      <CLoader v-if="detailLoading" centered />
      <template v-else-if="detailUser">
        <dl class="ds-kv">
          <div class="ds-kv__row">
            <dt>{{ t('staff.userDetail.role') }}</dt>
            <dd>
              <CBadge :variant="roleVariant(detailUser.role)" :text="roleLabel(detailUser.role)" />
            </dd>
          </div>
          <div class="ds-kv__row">
            <dt>{{ t('staff.userDetail.status') }}</dt>
            <dd>
              <CBadge
                :variant="detailUser.is_active ? 'success' : 'danger'"
                :text="
                  detailUser.is_active
                    ? t('staff.userDetail.active')
                    : t('staff.userDetail.blocked')
                "
              />
            </dd>
          </div>
          <div class="ds-kv__row">
            <dt>{{ t('staff.userDetail.kycStatus') }}</dt>
            <dd>
              <CBadge
                :variant="kycVariant(detailUser.kyc_status)"
                :text="kycLabel(detailUser.kyc_status)"
              />
            </dd>
          </div>
          <div class="ds-kv__row">
            <dt>{{ t('staff.userDetail.onboardingStep') }}</dt>
            <dd>{{ stepLabel(detailUser.onboarding_step) }}</dd>
          </div>
          <div class="ds-kv__row">
            <dt>{{ t('staff.userDetail.registered') }}</dt>
            <dd>{{ formatDate(detailUser.created_at) }}</dd>
          </div>
        </dl>

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
        <section v-if="showKycSection" class="detail__section">
          <h3 class="detail__subtitle">
            {{ t('staff.userDetail.kyc.sectionTitle') }}
          </h3>

          <dl class="ds-kv">
            <div class="ds-kv__row">
              <dt>{{ t('staff.userDetail.kyc.latestStatus') }}</dt>
              <dd>
                <CBadge
                  :variant="kycVariant(detailUser.latest_application_status ?? 'not_started')"
                  :text="
                    detailUser.latest_application_status
                      ? kycLabel(detailUser.latest_application_status)
                      : '—'
                  "
                />
              </dd>
            </div>
          </dl>

          <!-- History timeline. Hidden when there's only the single
               latest row (already shown above). 2+ rows means the user
               has re-submitted at least once -- R1 §3 "история re-submits
               если есть". -->
          <div v-if="detailUser.kyc_applications_history.length > 1" class="detail__block">
            <h4 class="ds-label">
              {{ t('staff.userDetail.kyc.historyTitle') }}
            </h4>
            <dl class="ds-kv kyc-history__list">
              <div
                v-for="app in detailUser.kyc_applications_history"
                :key="app.id"
                class="ds-kv__row"
              >
                <dt>{{ formatDate(app.created_at) }}</dt>
                <dd><CBadge :variant="kycVariant(app.status)" :text="kycLabel(app.status)" /></dd>
              </div>
            </dl>
          </div>

          <!-- Documents (H12). Only for staff who may decide: the
               owner tied looking and deciding to one permission on
               purpose -- approving without looking is what these
               exist to prevent. -->
          <div v-if="canDoKycApprove && detailUser.latest_application_id" class="detail__block">
            <h4 class="ds-label">
              {{ t('staff.userDetail.kyc.documents.title') }}
            </h4>
            <p v-if="kycDocumentsLoading" class="ds-note detail__note">
              {{ t('common.loading') }}
            </p>
            <p v-else-if="kycDocuments.length === 0" class="ds-note detail__note">
              {{ t('staff.userDetail.kyc.documents.empty') }}
            </p>
            <template v-else>
              <ul class="ds-rows">
                <li v-for="doc in kycDocuments" :key="doc.id" class="ds-row">
                  <span class="ds-row__lead"><FileText size="sm" /></span>
                  <span class="ds-row__body">
                    <span class="ds-row__title">
                      {{ t(DOCUMENT_KIND_LABELS[doc.kind] ?? doc.kind) }}
                    </span>
                  </span>
                  <span class="ds-row__trail">
                    <button
                      type="button"
                      class="ds-button ds-button--secondary"
                      data-size="sm"
                      :disabled="kycDocumentPending === doc.id"
                      @click="openKycDocument(doc.id)"
                    >
                      <span>{{ t('staff.userDetail.kyc.documents.view') }}</span>
                    </button>
                  </span>
                </li>
              </ul>
              <p class="ds-note detail__note">
                {{ t('staff.userDetail.kyc.documents.ttlNotice', { seconds: kycDocumentTtl }) }}
              </p>
            </template>
          </div>

          <!-- Application-level pair. Visible only while the latest
               application is still pending (status=submitted) AND the
               current staff has kyc_approve. -->
          <div
            v-if="detailUser.latest_application_status === 'submitted' && canDoKycApprove"
            class="ds-dialog__actions"
          >
            <CButton
              variant="primary"
              size="sm"
              inline
              :disabled="kycActionLoading"
              @click="openKycDecision('approve')"
            >
              {{ t('staff.userDetail.kyc.approve') }}
            </CButton>
            <CButton
              variant="danger"
              size="sm"
              inline
              :disabled="kycActionLoading"
              @click="openKycDecision('reject')"
            >
              {{ t('staff.userDetail.kyc.reject') }}
            </CButton>
          </div>

          <!-- Person-level control (P-65). Mutually exclusive with the
               pair above by construction: kycPersonAction is null while
               an application is open. -->
          <div v-else-if="kycPersonAction" class="ds-dialog__actions">
            <CButton
              :variant="KYC_DECISION_SPECS[kycPersonAction].variant"
              size="sm"
              inline
              :disabled="kycActionLoading"
              @click="openKycDecision(kycPersonAction)"
            >
              {{ t(KYC_DECISION_SPECS[kycPersonAction].labelKey) }}
            </CButton>
          </div>
        </section>

        <!-- From the card to the person's money and purchases: the lists open
             already narrowed to them. -->
        <section v-if="showMoneyLinks" class="detail__section">
          <h3 class="detail__subtitle">
            {{ t('staff.userDetail.linksTitle') }}
          </h3>
          <div class="ds-chip-row">
            <CButton
              v-if="canSeePayments"
              variant="secondary"
              size="sm"
              inline
              @click="openList('/staff/finance/payments', 'user_id')"
            >
              {{ t('staff.hub.finance.payments') }}
            </CButton>
            <CButton
              v-if="canSeePayments"
              variant="secondary"
              size="sm"
              inline
              @click="openList('/staff/finance/withdrawals', 'user_id')"
            >
              {{ t('staff.hub.finance.withdrawals') }}
            </CButton>
            <CButton
              v-if="canSeePurchases"
              variant="secondary"
              size="sm"
              inline
              @click="openList('/staff/finance/purchases', 'buyer_id')"
            >
              {{ t('staff.hub.finance.purchases') }}
            </CButton>
          </div>
        </section>

        <!-- Staff rights (if staff). The administrator marks them: four
             preset buttons mark a whole set with one press, the ticks below
             mark single rights. A member who is not the administrator has no
             right to read or change another's rights, so the block is not
             drawn for them. -->
        <section v-if="detailUser.staff_profile && isAdmin" class="detail__section">
          <h3 class="detail__subtitle">
            {{ t('staff.userDetail.permissions') }}
            <CBadge v-if="isEveryRight" variant="primary" :text="t('staff.settings.roleAdmin')" />
            <CBadge
              v-if="!detailUser.staff_profile.is_active"
              variant="danger"
              :text="t('staff.userDetail.offDuty')"
            />
          </h3>
          <p class="ds-note detail__note">
            {{ t('staff.rights.presetHint') }}
          </p>
          <div
            class="ds-chip-row perm-presets"
            role="group"
            :aria-label="t('staff.userDetail.permissions')"
          >
            <button
              v-for="preset in PERMISSION_PRESETS"
              :key="preset.id"
              type="button"
              class="ds-chip"
              :aria-pressed="activePreset?.id === preset.id"
              @click="applyPreset(preset)"
            >
              <Check class="ds-chip__check" size="sm" />
              <span>{{ t(preset.labelKey) }}</span>
            </button>
          </div>
          <div v-if="!isEveryRight" class="perm-admin">
            <CButton variant="secondary" size="sm" inline @click="adminAsk = { change: 'make' }">
              {{ t('staff.userDetail.makeAdmin') }}
            </CButton>
          </div>
          <CCheckbox
            v-for="key in PERMISSION_CARD_KEYS"
            :key="key"
            :model-value="!!detailUser.staff_profile.permissions[key]"
            @update:model-value="(v: boolean) => setPermission(key, v)"
          >
            {{ permissionLabel(key) }}
          </CCheckbox>
        </section>

        <!-- Actions -->
        <div class="ds-dialog__actions">
          <CButton
            v-if="canActAs"
            variant="secondary"
            size="sm"
            inline
            :loading="avatarLoading"
            @click="showActAsModal = true"
          >
            <Ghost size="sm" /> {{ t('staff.userDetail.actAs') }}
          </CButton>
          <CButton
            v-if="canBlock && detailUser.is_active && detailUser.role !== 'staff'"
            variant="danger"
            size="sm"
            inline
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
            v-if="canBlock && !detailUser.is_active"
            variant="primary"
            size="sm"
            inline
            @click="showUnblockModal = true"
          >
            {{ t('staff.userDetail.unblock') }}
          </CButton>
          <CButton
            v-if="canChangeEmail"
            variant="secondary"
            size="sm"
            inline
            @click="showEmailModal = true"
          >
            {{ t('staff.userDetail.changeEmail') }}
          </CButton>
          <CButton
            v-if="isAdmin && detailUser.role !== 'staff'"
            variant="secondary"
            size="sm"
            inline
            @click="showPromoteModal = true"
          >
            {{ t('staff.userDetail.promoteToStaff') }}
          </CButton>
          <CButton
            v-if="canDeactivate"
            variant="danger"
            size="sm"
            inline
            @click="showDeactivateModal = true"
          >
            {{ t('staff.userDetail.deactivate') }}
          </CButton>
        </div>
      </template>
    </CModal>

    <!-- The administrator mark: asked before a tick or the button grants or removes it -->
    <CModal
      :open="adminAsk !== null"
      :title="
        adminAsk?.change === 'remove'
          ? t('staff.userDetail.removeAdminTitle')
          : t('staff.userDetail.makeAdmin')
      "
      @close="adminAsk = null"
    >
      <p class="ds-dialog__text">
        {{
          adminAsk?.change === 'remove'
            ? t('staff.userDetail.removeAdminWarning')
            : adminAsk?.change === 'grant'
              ? t('staff.userDetail.grantAdminWarning')
              : t('staff.userDetail.makeAdminWarning')
        }}
      </p>
      <CAlert v-if="ownCard && adminAsk?.change === 'remove'" tone="warning">
        {{ t('staff.userDetail.ownCardWarning') }}
      </CAlert>
      <div class="ds-dialog__actions">
        <CButton variant="outline" size="sm" inline @click="adminAsk = null">
          {{ t('common.cancel') }}
        </CButton>
        <CButton
          :variant="adminAsk?.change === 'remove' ? 'danger' : 'primary'"
          size="sm"
          inline
          @click="confirmAdminAsk"
        >
          {{ t('common.confirm') }}
        </CButton>
      </div>
    </CModal>

    <!-- Act as this user: the avatar mode -->
    <CModal
      :open="showActAsModal"
      :title="t('staff.userDetail.actAs')"
      @close="showActAsModal = false"
    >
      <p class="ds-dialog__text">
        {{ t('staff.userDetail.actAsConfirm') }}
      </p>
      <div class="ds-dialog__actions">
        <CButton variant="outline" size="sm" inline @click="showActAsModal = false">
          {{ t('common.cancel') }}
        </CButton>
        <CButton variant="primary" size="sm" inline :loading="avatarLoading" @click="handleActAs">
          {{ t('staff.avatar.start') }}
        </CButton>
      </div>
    </CModal>

    <!-- Block confirmation -->
    <CModal
      :open="showBlockModal"
      :title="t('staff.userDetail.block')"
      @close="showBlockModal = false"
    >
      <p class="ds-dialog__text">
        {{ t('staff.userDetail.blockConfirm') }}
      </p>
      <CInput
        v-model="blockReason"
        :label="t('staff.userDetail.blockReason')"
        :placeholder="t('staff.userDetail.blockReason')"
      />
      <div class="ds-dialog__actions">
        <CButton variant="outline" size="sm" inline @click="showBlockModal = false">
          {{ t('common.cancel') }}
        </CButton>
        <CButton variant="danger" size="sm" inline :loading="actionLoading" @click="handleBlock">
          {{ t('common.confirm') }}
        </CButton>
      </div>
    </CModal>

    <!-- Change email (admin only, H28 P-105) -->
    <CModal
      :open="showEmailModal"
      :title="t('staff.userDetail.changeEmail')"
      @close="showEmailModal = false"
    >
      <p class="ds-dialog__text">
        {{ t('staff.userDetail.changeEmailConfirm') }}
      </p>
      <CInput
        v-model="newEmail"
        type="email"
        :label="t('staff.userDetail.newEmail')"
        :placeholder="t('staff.userDetail.newEmail')"
      />
      <CInput
        v-model="emailReason"
        :label="t('staff.userDetail.changeEmailReason')"
        :placeholder="t('staff.userDetail.changeEmailReason')"
      />
      <div class="ds-dialog__actions">
        <CButton variant="outline" size="sm" inline @click="showEmailModal = false">
          {{ t('common.cancel') }}
        </CButton>
        <CButton
          variant="primary"
          size="sm"
          inline
          :loading="actionLoading"
          :disabled="!emailFormFilled"
          @click="handleChangeEmail"
        >
          {{ t('common.confirm') }}
        </CButton>
      </div>
    </CModal>

    <!-- Unblock confirmation. No reason input -- see the handleUnblock
         comment and the backend's unblock_user docstring. -->
    <CModal
      :open="showUnblockModal"
      :title="t('staff.userDetail.unblock')"
      @close="showUnblockModal = false"
    >
      <p class="ds-dialog__text">
        {{ t('staff.userDetail.unblockConfirm') }}
      </p>
      <div class="ds-dialog__actions">
        <CButton variant="outline" size="sm" inline @click="showUnblockModal = false">
          {{ t('common.cancel') }}
        </CButton>
        <CButton variant="primary" size="sm" inline :loading="actionLoading" @click="handleUnblock">
          {{ t('common.confirm') }}
        </CButton>
      </div>
    </CModal>

    <!-- Take a staff member off duty (administrator only) -->
    <CModal
      :open="showDeactivateModal"
      :title="t('staff.userDetail.deactivate')"
      @close="showDeactivateModal = false"
    >
      <p class="ds-dialog__text">
        {{ t('staff.userDetail.deactivateConfirm') }}
      </p>
      <div class="ds-dialog__actions">
        <CButton variant="outline" size="sm" inline @click="showDeactivateModal = false">
          {{ t('common.cancel') }}
        </CButton>
        <CButton
          variant="danger"
          size="sm"
          inline
          :loading="actionLoading"
          @click="handleDeactivate"
        >
          {{ t('common.confirm') }}
        </CButton>
      </div>
    </CModal>

    <!-- Promote confirmation -->
    <CModal
      :open="showPromoteModal"
      :title="t('staff.userDetail.promoteToStaff')"
      @close="showPromoteModal = false"
    >
      <p class="ds-dialog__text">
        {{ t('staff.userDetail.promoteConfirm') }}
      </p>
      <div class="ds-dialog__actions">
        <CButton variant="outline" size="sm" inline @click="showPromoteModal = false">
          {{ t('common.cancel') }}
        </CButton>
        <CButton variant="primary" size="sm" inline :loading="actionLoading" @click="handlePromote">
          {{ t('common.confirm') }}
        </CButton>
      </div>
    </CModal>

    <!-- KYC decision reason (iter 2.7 A5, four modes since P-65).
         Reason is REQUIRED per R1 §3 -- the confirm button stays
         disabled while the trimmed input is empty. Everything that
         varies by mode comes from kycDecisionSpec; see the table. -->
    <CModal
      :open="showKycDecisionModal"
      :title="t(kycDecisionSpec.labelKey)"
      @close="showKycDecisionModal = false"
    >
      <p class="ds-dialog__text">
        {{ t(kycDecisionSpec.hintKey) }}
      </p>
      <CInput
        v-model="kycDecisionReason"
        :label="t('staff.userDetail.kyc.reason')"
        :placeholder="t('staff.userDetail.kyc.reason')"
      />
      <div class="ds-dialog__actions">
        <CButton variant="outline" size="sm" inline @click="showKycDecisionModal = false">
          {{ t('common.cancel') }}
        </CButton>
        <CButton
          :variant="kycDecisionSpec.variant"
          size="sm"
          inline
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
  display: grid;
  gap: var(--space-4);
  align-content: start;
}

/* iter 2.7 A5: filters are two stacked chip rows (role + kyc_status), under the search. */
.staff-users__filters {
  display: grid;
  gap: var(--space-2);
}

/* Detail modal */
.detail__section,
.detail__block {
  display: grid;
  gap: var(--space-2);
}
.detail__subtitle {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
  margin: 0;
  font-family: var(--font-display);
  font-size: var(--fs-body);
  font-weight: 700;
  color: var(--text-primary);
}
.detail__note {
  max-inline-size: var(--maxw-prose);
}
</style>
