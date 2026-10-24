<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- CompanySettingsView (the project account's Settings tab)
// =============================================================================
//
// Settings tab inside CompanyShell, in the order a project looks for things:
//   1. Hero -- logo, name, status.
//   2. Personal block -- the name, the e-mail and the language of the person
//      who works in the account.
//   3. Profile -- description, status (or the "withdraw" button while the
//      project is on sale), and a pencil that opens the profile and media form.
//   4. Parts -- the price of a part and the parts for sale, READ ONLY. The price
//      of a part is the fair value of the project divided by 1,000,000,000,
//      one for every project; it changes only by a revaluation of the project,
//      never by a hand entry here, and the parts for sale are 25 percent of the
//      parts and never grow. Nothing on this screen writes either figure.
//   5. Distribution -- the fixed division of the parts, a table, read only.
//   6. Documents (the project's legal documents to read), Support, FAQ,
//      Activity (the change log).
//   7. Media links, then the account: two-factor authentication, sessions,
//      notification preferences, deactivation, sign-out.
//
// Posts, the roadmap and documents of the project live on the Publications
// tab; the balance in the top bar opens the balance screen.
//
// A project may withdraw itself from the store (status -> hidden) through
// PATCH /api/v1/companies/me while it is active. It may not republish itself or
// archive itself: both are the administrator's, and this view shows a hidden or
// archived project's status as plain text with a short explanation, never a
// button that would only be refused.
//
// DATA SOURCE. companyProfile.loadIfMissing() -- cache-first. Everything else
// appears only after the profile is non-null; a failed load shows a retry.
// =============================================================================

import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  ChevronRight,
  ExternalLink,
  FileText,
  HelpCircle,
  History,
  Image as ImageIcon,
  LogOut,
  MessageCircle,
  Pencil,
  Video,
} from '@/components/ui/icons'

import {
  CAvatar,
  CBadge,
  CButton,
  CEmptyState,
  CIconBox,
  CInput,
  CLoader,
  CModal,
  CSelect,
  CTextarea,
} from '@/components/ui'
import { useScreenHeader } from '@/components/layout/screenHeader'
import TwoFactorSection from '@/components/shared/TwoFactorSection.vue'
import ActiveSessionsSection from '@/components/shared/ActiveSessionsSection.vue'
import NotificationPreferencesSection from '@/components/shared/NotificationPreferencesSection.vue'
import DeactivateAccountSection from '@/components/shared/DeactivateAccountSection.vue'
import { useAuthStore } from '@/stores/auth'
import { useCompanyProfileStore } from '@/stores/companyProfile'
import { useCompanyDashboardStore } from '@/stores/companyDashboard'
import { safeNavigate } from '@/composables/safeNavigate'
import { useToast } from '@/composables/useToast'
import { formatNumber, formatPrice } from '@/utils/format'
import { tOrRaw } from '@/utils/i18n'
import { updateOwnCompany } from '@/api/companies'
import { updateMe } from '@/api/users'
import { setLocale } from '@/i18n'
import { SUPPORTED_LOCALES } from '@/i18n/locales.config'
import { ApiResponseError } from '@/api/client'
import type { UpdateOwnCompanyRequest, UserUpdate } from '@/api/types'

const { t, locale } = useI18n()
const router = useRouter()
const authStore = useAuthStore()
const profileStore = useCompanyProfileStore()
const dashboardStore = useCompanyDashboardStore()
const { showToast } = useToast()

// The frame's header carries the title and the line under it.
useScreenHeader({
  title: () => t('comp.settings.title'),
  lead: () => t('comp.settings.subtitle'),
})

// ---------------------------------------------------------------------------
// Derived view state
// ---------------------------------------------------------------------------

const profile = computed(() => profileStore.profile)

const initialLoading = computed<boolean>(() => {
  if (profileStore.error) return false
  return profile.value === null
})

const hasError = computed<boolean>(() => profileStore.error !== null)

// ---------------------------------------------------------------------------
// Hero readouts
// ---------------------------------------------------------------------------

const companyName = computed<string>(() => profile.value?.name ?? '')
const logoUrl = computed<string | null>(() => profile.value?.logo_url ?? null)

const status = computed<string>(() => profile.value?.status ?? '')
const statusLabel = computed<string>(() =>
  // FP-15: server-driven enum -> tOrRaw with raw fallback so a future
  // backend status (e.g. "suspended") shows up readable instead of
  // the dotted i18n path.
  tOrRaw(t, `comp.settings.status.${status.value}`, status.value),
)
const statusVariant = computed<'success' | 'warning' | 'neutral'>(() => {
  if (status.value === 'active') return 'success'
  if (status.value === 'hidden') return 'warning'
  return 'neutral'
})

// ---------------------------------------------------------------------------
// Status: self-service withdraw (TASK-30 ruling 12)
// ---------------------------------------------------------------------------
//
// The ONLY status transition a project may make on its own is
// ACTIVE -> HIDDEN ("withdraw"). Publishing (HIDDEN -> ACTIVE) and
// archiving are staff-only actions (done from
// StaffCompanyProfileSection); this view never offers them. The
// server (update_own_company) rejects everything else with a 400
// regardless -- canWithdraw only decides whether the CTA is SHOWN, it
// is not the safety mechanism.
//
// HIDDEN / ARCHIVED render as plain read-only text with a short
// explanation instead of a button that would just 400 if clicked.

const canWithdraw = computed<boolean>(() => status.value === 'active')

const showWithdrawConfirm = ref(false)
const withdrawing = ref(false)

function openWithdrawConfirm(): void {
  if (!canWithdraw.value) {
    console.warn('[CompanySettingsView] openWithdrawConfirm blocked: status is not active')
    return
  }
  showWithdrawConfirm.value = true
}

async function handleWithdraw(): Promise<void> {
  if (!canWithdraw.value) {
    console.warn('[CompanySettingsView] handleWithdraw blocked: status is not active')
    return
  }
  withdrawing.value = true
  try {
    const updated = await updateOwnCompany({ status: 'hidden' })
    profileStore.applyProfile(updated)
    showWithdrawConfirm.value = false
    showToast(t('comp.settings.profile.withdrawSuccess'), 'success')
  } catch (err) {
    // Server-side is the real gate (a stale client could still race
    // an admin's concurrent publish/archive and hit the 400) -- show
    // its message rather than swallowing it as an unhandled rejection.
    const message =
      err instanceof ApiResponseError ? err.detail : t('comp.settings.profile.withdrawError')
    showToast(message, 'error')
  } finally {
    withdrawing.value = false
  }
}

// ---------------------------------------------------------------------------
// Profile: self-service edit (TASK-30 W1)
// ---------------------------------------------------------------------------
//
// One modal covers description + the four media URLs. Submit sends only
// the fields that actually changed, diffed against the loaded profile --
// same exclude_unset contract the roadmap/attachments editors already
// rely on (omit = keep, null = clear). Pricing/supply/distribution and
// status are NOT part of this form -- pricing stays staff-only, status
// has its own dedicated withdraw flow above.

const showEditProfile = ref(false)
const savingProfile = ref(false)

const draftDescription = ref('')
const draftLogoUrl = ref('')
const draftCoverUrl = ref('')
const draftPromoVideoUrl = ref('')
const draftPresentationUrl = ref('')

function openEditProfile(): void {
  const p = profile.value
  if (!p) return
  draftDescription.value = p.description ?? ''
  draftLogoUrl.value = p.logo_url ?? ''
  draftCoverUrl.value = p.cover_url ?? ''
  draftPromoVideoUrl.value = p.promo_video_url ?? ''
  draftPresentationUrl.value = p.presentation_url ?? ''
  showEditProfile.value = true
}

function closeEditProfile(): void {
  showEditProfile.value = false
}

const trimmedDescription = computed<string>(() => draftDescription.value.trim())
const trimmedLogoUrl = computed<string>(() => draftLogoUrl.value.trim())
const trimmedCoverUrl = computed<string>(() => draftCoverUrl.value.trim())
const trimmedPromoVideoUrl = computed<string>(() => draftPromoVideoUrl.value.trim())
const trimmedPresentationUrl = computed<string>(() => draftPresentationUrl.value.trim())

// Every media URL is optional, but if present must be http(s) -- mirror
// the backend validator (and the roadmap section's externalUrlValid
// pattern) so we don't round-trip a guaranteed 422.
function isValidOptionalUrl(v: string): boolean {
  if (!v) return true
  return v.startsWith('http://') || v.startsWith('https://')
}

const logoUrlValid = computed<boolean>(() => isValidOptionalUrl(trimmedLogoUrl.value))
const coverUrlValid = computed<boolean>(() => isValidOptionalUrl(trimmedCoverUrl.value))
const promoVideoUrlValid = computed<boolean>(() => isValidOptionalUrl(trimmedPromoVideoUrl.value))
const presentationUrlValid = computed<boolean>(() =>
  isValidOptionalUrl(trimmedPresentationUrl.value),
)

const canSubmitProfile = computed<boolean>(
  () =>
    logoUrlValid.value &&
    coverUrlValid.value &&
    promoVideoUrlValid.value &&
    presentationUrlValid.value,
)

// Diff against the loaded profile -- send only fields that changed.
// Clearing a field sends explicit null; an untouched field is omitted
// entirely so the backend's exclude_unset PATCH leaves it alone.
function buildProfileUpdateBody(): UpdateOwnCompanyRequest {
  const body: UpdateOwnCompanyRequest = {}
  const p = profile.value
  if (!p) return body

  const origDescription = p.description ?? ''
  if (trimmedDescription.value !== origDescription) {
    body.description = trimmedDescription.value ? trimmedDescription.value : null
  }

  const origLogoUrl = p.logo_url ?? ''
  if (trimmedLogoUrl.value !== origLogoUrl) {
    body.logo_url = trimmedLogoUrl.value ? trimmedLogoUrl.value : null
  }

  const origCoverUrl = p.cover_url ?? ''
  if (trimmedCoverUrl.value !== origCoverUrl) {
    body.cover_url = trimmedCoverUrl.value ? trimmedCoverUrl.value : null
  }

  const origPromoVideoUrl = p.promo_video_url ?? ''
  if (trimmedPromoVideoUrl.value !== origPromoVideoUrl) {
    body.promo_video_url = trimmedPromoVideoUrl.value ? trimmedPromoVideoUrl.value : null
  }

  const origPresentationUrl = p.presentation_url ?? ''
  if (trimmedPresentationUrl.value !== origPresentationUrl) {
    body.presentation_url = trimmedPresentationUrl.value ? trimmedPresentationUrl.value : null
  }

  return body
}

async function handleSaveProfile(): Promise<void> {
  if (!canSubmitProfile.value) return

  const body = buildProfileUpdateBody()
  // Nothing changed -- close without a redundant PATCH.
  if (Object.keys(body).length === 0) {
    showEditProfile.value = false
    return
  }

  savingProfile.value = true
  try {
    const updated = await updateOwnCompany(body)
    profileStore.applyProfile(updated)
    showEditProfile.value = false
    showToast(t('comp.settings.profile.editSuccess'), 'success')
  } catch (err) {
    const message =
      err instanceof ApiResponseError && err.detail
        ? err.detail
        : t('comp.settings.profile.editError')
    showToast(message, 'error')
  } finally {
    savingProfile.value = false
  }
}

// ---------------------------------------------------------------------------
// Parts -- price and parts for sale, read only
// ---------------------------------------------------------------------------

// The fixed division of the parts, in percent. Shown as a table; the project
// does not edit it.
const DISTRIBUTION_ROWS: readonly { key: string; percent: number }[] = [
  { key: 'sale', percent: 25 },
  { key: 'index', percent: 10 },
  { key: 'bonus', percent: 14 },
  { key: 'reserve', percent: 51 },
]

// ---------------------------------------------------------------------------
// Personal block -- name, e-mail, language
// ---------------------------------------------------------------------------

function userProfile(): Record<string, unknown> {
  const p = authStore.user?.profile
  return p && typeof p === 'object' ? (p as Record<string, unknown>) : {}
}

const firstName = computed<string>(() => {
  const v = userProfile().first_name
  return typeof v === 'string' ? v : ''
})
const lastName = computed<string>(() => {
  const v = userProfile().last_name
  return typeof v === 'string' ? v : ''
})
const personName = computed<string>(() =>
  [firstName.value, lastName.value].filter(Boolean).join(' ').trim(),
)
const personEmail = computed<string>(() => authStore.user?.email ?? '')
const currentLanguage = computed<string>(() => authStore.user?.language ?? '')
const languageLabel = computed<string>(
  () =>
    SUPPORTED_LOCALES.find((l) => l.code === currentLanguage.value)?.label ?? currentLanguage.value,
)
const languageOptions = SUPPORTED_LOCALES.map((l) => ({ value: l.code, label: l.label }))

const showEditPerson = ref(false)
const savingPerson = ref(false)
const draftFirstName = ref('')
const draftLastName = ref('')
const draftLanguage = ref('')

function openEditPerson(): void {
  draftFirstName.value = firstName.value
  draftLastName.value = lastName.value
  draftLanguage.value = currentLanguage.value
  showEditPerson.value = true
}

const canSubmitPerson = computed<boolean>(
  () => draftFirstName.value.trim().length > 0 === draftLastName.value.trim().length > 0,
)

async function handleSavePerson(): Promise<void> {
  if (!canSubmitPerson.value) return
  const body: UserUpdate = {}
  const changes: Record<string, unknown> = {}
  if (draftFirstName.value.trim() !== firstName.value)
    changes.first_name = draftFirstName.value.trim()
  if (draftLastName.value.trim() !== lastName.value) changes.last_name = draftLastName.value.trim()
  if (Object.keys(changes).length > 0) body.profile = changes
  const newLanguage =
    draftLanguage.value && draftLanguage.value !== currentLanguage.value ? draftLanguage.value : ''
  if (newLanguage) body.language = newLanguage
  if (Object.keys(body).length === 0) {
    showEditPerson.value = false
    return
  }
  savingPerson.value = true
  try {
    await updateMe(body)
    await authStore.fetchMe()
    if (newLanguage) await setLocale(newLanguage)
    showEditPerson.value = false
    showToast(t('comp.settings.person.editSuccess'), 'success')
  } catch {
    showToast(t('comp.settings.person.editError'), 'error')
  } finally {
    savingPerson.value = false
  }
}

// ---------------------------------------------------------------------------
// Media links -- show the section only if at least one is set
// ---------------------------------------------------------------------------

interface MediaLink {
  key: string
  url: string
  label: string
  icon: typeof ImageIcon
}

const mediaLinks = computed<MediaLink[]>(() => {
  const p = profile.value
  if (!p) return []
  const out: MediaLink[] = []
  if (p.logo_url) {
    out.push({
      key: 'logo',
      url: p.logo_url,
      label: t('comp.settings.links.logo'),
      icon: ImageIcon,
    })
  }
  if (p.cover_url) {
    out.push({
      key: 'cover',
      url: p.cover_url,
      label: t('comp.settings.links.cover'),
      icon: ImageIcon,
    })
  }
  if (p.promo_video_url) {
    out.push({
      key: 'promoVideo',
      url: p.promo_video_url,
      label: t('comp.settings.links.promoVideo'),
      icon: Video,
    })
  }
  if (p.presentation_url) {
    out.push({
      key: 'presentation',
      url: p.presentation_url,
      label: t('comp.settings.links.presentation'),
      icon: ExternalLink,
    })
  }
  return out
})

// ---------------------------------------------------------------------------
// Lifecycle + actions
// ---------------------------------------------------------------------------

const loggingOut = ref<boolean>(false)

async function handleLogout(): Promise<void> {
  if (loggingOut.value) return
  loggingOut.value = true
  try {
    await authStore.logout()
  } finally {
    // Auth state already cleared. If push gets rejected by a benign
    // NavigationFailure type, the next route guard will bounce the
    // tokenless user to /login anyway -- no toast needed.
    void safeNavigate(router.push('/login'), '[CompanySettingsView] to login')
  }
}

async function loadProfile(): Promise<void> {
  await profileStore.loadIfMissing()
  if (dashboardStore.summary === null) void dashboardStore.refresh()
}

onMounted(() => {
  void loadProfile()
})
</script>

<template>
  <!-- Initial loading -->
  <div v-if="initialLoading" class="ds-empty" aria-busy="true">
    <CLoader />
  </div>

  <!-- Error -->
  <CEmptyState
    v-else-if="hasError"
    tone="danger"
    :title="t('comp.settings.errorTitle')"
    :description="profileStore.error ?? ''"
  >
    <template #actions>
      <CButton variant="outline" size="sm" inline @click="loadProfile">
        {{ t('comp.settings.errorRetry') }}
      </CButton>
    </template>
  </CEmptyState>

  <!-- Loaded -->
  <template v-else-if="profile">
    <!-- The project: its mark, its name and its status -->
    <ul class="ds-rows">
      <li class="ds-row">
        <CAvatar :name="companyName" :url="logoUrl ?? undefined" :size="56" />
        <span class="ds-row__body">
          <span class="ds-row__title">{{ companyName }}</span>
        </span>
        <span class="ds-row__trail">
          <CBadge :variant="statusVariant" :text="statusLabel" />
        </span>
      </li>
    </ul>

    <!-- Personal block -->
    <section class="ds-card" aria-labelledby="cset-person">
      <header class="ds-card__head">
        <h2 id="cset-person" class="ds-card__title">{{ t('comp.settings.person.title') }}</h2>
        <button
          type="button"
          class="ds-button ds-button--ghost ds-button--icon"
          data-size="sm"
          :aria-label="`${t('common.edit')}: ${t('comp.settings.person.title')}`"
          @click="openEditPerson"
        >
          <Pencil size="sm" />
        </button>
      </header>
      <dl class="ds-kv">
        <div class="ds-kv__row">
          <dt>{{ t('comp.settings.person.name') }}</dt>
          <dd>{{ personName || t('comp.settings.person.notSet') }}</dd>
        </div>
        <div class="ds-kv__row">
          <dt>{{ t('comp.settings.person.email') }}</dt>
          <dd>{{ personEmail }}</dd>
        </div>
        <div class="ds-kv__row">
          <dt>{{ t('comp.settings.person.language') }}</dt>
          <dd>{{ languageLabel }}</dd>
        </div>
      </dl>
    </section>

    <!-- Profile -->
    <section v-if="profile.description || status" class="ds-card" aria-labelledby="cset-profile">
      <header class="ds-card__head">
        <h2 id="cset-profile" class="ds-card__title">{{ t('comp.settings.profile.title') }}</h2>
        <button
          type="button"
          class="ds-button ds-button--ghost ds-button--icon"
          data-size="sm"
          :aria-label="`${t('common.edit')}: ${t('comp.settings.profile.title')}`"
          @click="openEditProfile"
        >
          <Pencil size="sm" />
        </button>
      </header>
      <div v-if="profile.description">
        <p class="ds-card__label">{{ t('comp.settings.profile.description') }}</p>
        <p class="ds-card__body cset__multiline">{{ profile.description }}</p>
      </div>
      <dl v-if="status" class="ds-kv">
        <div class="ds-kv__row">
          <dt>{{ t('comp.settings.profile.status') }}</dt>
          <dd>{{ statusLabel }}</dd>
        </div>
      </dl>
      <!-- Hidden/archived: explain who can undo it, right under the status
           rather than only inside a modal the user may never open. -->
      <p v-if="status === 'hidden'" class="ds-card__body">
        {{ t('comp.settings.profile.hiddenHint') }}
      </p>
      <p v-else-if="status === 'archived'" class="ds-card__body">
        {{ t('comp.settings.profile.archivedHint') }}
      </p>
      <footer v-if="canWithdraw" class="ds-card__foot">
        <CButton variant="outline" size="sm" inline @click="openWithdrawConfirm">
          {{ t('comp.settings.profile.withdrawCta') }}
        </CButton>
      </footer>
    </section>

    <!-- Parts: the price of a part and the parts for sale, read only -->
    <section class="ds-card" aria-labelledby="cset-parts">
      <header class="ds-card__head">
        <h2 id="cset-parts" class="ds-card__title">{{ t('comp.settings.parts.title') }}</h2>
      </header>
      <dl class="ds-kv">
        <div class="ds-kv__row">
          <dt>{{ t('comp.settings.parts.price') }}</dt>
          <dd>{{ formatPrice(profile.price_per_unit_cents) }}</dd>
        </div>
      </dl>
      <p class="ds-card__body">
        {{ t('comp.settings.parts.priceHint') }}
      </p>
      <dl class="ds-kv">
        <div class="ds-kv__row">
          <dt>{{ t('comp.settings.parts.supply') }}</dt>
          <dd>
            {{
              dashboardStore.summary?.pool
                ? formatNumber(dashboardStore.summary.pool.total_options, locale)
                : '—'
            }}
          </dd>
        </div>
      </dl>
      <p class="ds-card__body">
        {{ t('comp.settings.parts.supplyHint') }}
      </p>
    </section>

    <!-- Distribution: the fixed division of the parts, read only -->
    <section class="ds-card" aria-labelledby="cset-distribution">
      <header class="ds-card__head">
        <h2 id="cset-distribution" class="ds-card__title">
          {{ t('comp.settings.distribution.title') }}
        </h2>
      </header>
      <dl class="ds-kv">
        <div v-for="row in DISTRIBUTION_ROWS" :key="row.key" class="ds-kv__row">
          <dt>{{ t(`comp.settings.distribution.rows.${row.key}`) }}</dt>
          <dd>{{ row.percent }}%</dd>
        </div>
      </dl>
      <p class="ds-card__body">
        {{ t('comp.settings.distribution.hint') }}
      </p>
    </section>

    <!-- The ways to the project's other screens: documents, support, FAQ and activity.
         CompanyShell has no More tab (five fixed tabs), so each entry is a tile here. -->
    <nav class="ds-navtiles" :aria-label="t('comp.settings.title')">
      <RouterLink to="/company/docs" class="ds-navtile">
        <CIconBox><FileText /></CIconBox>
        <span class="ds-navtile__text">
          <span class="ds-navtile__title">{{ t('comp.settings.docs.title') }}</span>
          <span class="ds-navtile__desc">{{ t('comp.settings.docs.cta') }}</span>
        </span>
        <ChevronRight class="ds-navtile__go" size="sm" />
      </RouterLink>
      <RouterLink to="/company/support" class="ds-navtile">
        <CIconBox><MessageCircle /></CIconBox>
        <span class="ds-navtile__text">
          <span class="ds-navtile__title">{{ t('comp.settings.support.title') }}</span>
          <span class="ds-navtile__desc">{{ t('comp.settings.support.cta') }}</span>
        </span>
        <ChevronRight class="ds-navtile__go" size="sm" />
      </RouterLink>
      <!-- This is the company's OWN, SEPARATE FAQ (owner ruling) -- see CompanyFaqView.vue -->
      <RouterLink to="/company/faq" class="ds-navtile">
        <CIconBox><HelpCircle /></CIconBox>
        <span class="ds-navtile__text">
          <span class="ds-navtile__title">{{ t('comp.settings.faq.title') }}</span>
          <span class="ds-navtile__desc">{{ t('comp.settings.faq.cta') }}</span>
        </span>
        <ChevronRight class="ds-navtile__go" size="sm" />
      </RouterLink>
      <RouterLink to="/company/audit" class="ds-navtile">
        <CIconBox><History /></CIconBox>
        <span class="ds-navtile__text">
          <span class="ds-navtile__title">{{ t('comp.settings.audit.title') }}</span>
          <span class="ds-navtile__desc">{{ t('comp.settings.audit.cta') }}</span>
        </span>
        <ChevronRight class="ds-navtile__go" size="sm" />
      </RouterLink>
    </nav>

    <!-- Media links -->
    <section v-if="mediaLinks.length > 0" class="cset__section" aria-labelledby="cset-links">
      <h2 id="cset-links" class="cset__section-title">
        {{ t('comp.settings.links.title') }}
      </h2>
      <ul class="ds-rows">
        <li v-for="link in mediaLinks" :key="link.key" class="ds-row">
          <span class="ds-row__lead"><component :is="link.icon" size="sm" /></span>
          <span class="ds-row__body">
            <a class="ds-row__link" :href="link.url" target="_blank" rel="noopener noreferrer">
              <span class="ds-row__title">{{ link.label }}</span>
            </a>
          </span>
          <span class="ds-row__trail">
            {{ t('comp.settings.links.open') }}
            <ExternalLink size="sm" />
          </span>
        </li>
      </ul>
    </section>

    <!-- Actions -->
    <section class="cset__section" aria-labelledby="cset-actions">
      <h2 id="cset-actions" class="cset__section-title">
        {{ t('comp.settings.actions.title') }}
      </h2>
      <TwoFactorSection tPrefix="comp.settings.actions" />
      <ActiveSessionsSection tPrefix="comp.settings.actions" />
      <NotificationPreferencesSection tPrefix="comp.settings.actions" />
      <DeactivateAccountSection tPrefix="comp.settings.actions" />
      <ul class="ds-rows">
        <li class="ds-row" :aria-disabled="loggingOut || undefined">
          <span class="ds-row__lead" data-tone="danger"><LogOut size="sm" /></span>
          <span class="ds-row__body">
            <button type="button" class="ds-row__link" :disabled="loggingOut" @click="handleLogout">
              <span class="ds-row__title">{{ t('comp.settings.actions.logout') }}</span>
            </button>
          </span>
          <span class="ds-row__trail"><ChevronRight size="sm" /></span>
        </li>
      </ul>
    </section>

    <!-- Withdraw confirm modal (ACTIVE -> HIDDEN only) -->
    <CModal
      :open="showWithdrawConfirm"
      :title="t('comp.settings.profile.withdrawConfirmTitle')"
      @close="showWithdrawConfirm = false"
    >
      <p class="ds-dialog__text">
        {{ t('comp.settings.profile.withdrawConfirmBody') }}
      </p>
      <div class="ds-dialog__actions">
        <CButton variant="outline" size="sm" inline @click="showWithdrawConfirm = false">
          {{ t('common.cancel') }}
        </CButton>
        <CButton variant="primary" size="sm" inline :loading="withdrawing" @click="handleWithdraw">
          {{ t('comp.settings.profile.withdrawConfirmSubmit') }}
        </CButton>
      </div>
    </CModal>

    <!-- Profile edit modal (TASK-30 W1): description + the four media
         URLs. Pricing/supply/distribution/status are NOT here. -->
    <CModal
      :open="showEditProfile"
      :title="t('comp.settings.profile.editTitle')"
      @close="closeEditProfile"
    >
      <CTextarea
        v-model="draftDescription"
        :label="t('comp.settings.profile.description')"
        :rows="5"
        maxlength="5000"
      />

      <CInput
        v-model="draftLogoUrl"
        :label="t('comp.settings.links.logo')"
        placeholder="https://..."
        maxlength="2000"
        :error="!logoUrlValid ? t('comp.settings.profile.urlFormatError') : ''"
      />

      <CInput
        v-model="draftCoverUrl"
        :label="t('comp.settings.links.cover')"
        placeholder="https://..."
        maxlength="2000"
        :error="!coverUrlValid ? t('comp.settings.profile.urlFormatError') : ''"
      />

      <CInput
        v-model="draftPromoVideoUrl"
        :label="t('comp.settings.links.promoVideo')"
        placeholder="https://..."
        maxlength="2000"
        :error="!promoVideoUrlValid ? t('comp.settings.profile.urlFormatError') : ''"
      />

      <CInput
        v-model="draftPresentationUrl"
        :label="t('comp.settings.links.presentation')"
        placeholder="https://..."
        maxlength="2000"
        :error="!presentationUrlValid ? t('comp.settings.profile.urlFormatError') : ''"
      />

      <div class="ds-dialog__actions">
        <CButton variant="outline" size="sm" inline @click="closeEditProfile">
          {{ t('common.cancel') }}
        </CButton>
        <CButton
          variant="primary"
          size="sm"
          inline
          :loading="savingProfile"
          :disabled="!canSubmitProfile"
          @click="handleSaveProfile"
        >
          {{ t('common.save') }}
        </CButton>
      </div>
    </CModal>

    <!-- Personal block edit modal: name and language -->
    <CModal
      :open="showEditPerson"
      :title="t('comp.settings.person.editTitle')"
      @close="showEditPerson = false"
    >
      <CInput
        v-model="draftFirstName"
        :label="t('comp.settings.person.firstName')"
        maxlength="100"
      />
      <CInput v-model="draftLastName" :label="t('comp.settings.person.lastName')" maxlength="100" />
      <CSelect
        v-model="draftLanguage"
        :label="t('comp.settings.person.language')"
        :options="languageOptions"
      />
      <div class="ds-dialog__actions">
        <CButton variant="outline" size="sm" inline @click="showEditPerson = false">
          {{ t('common.cancel') }}
        </CButton>
        <CButton
          variant="primary"
          size="sm"
          inline
          :loading="savingPerson"
          :disabled="!canSubmitPerson"
          @click="handleSavePerson"
        >
          {{ t('common.save') }}
        </CButton>
      </div>
    </CModal>
  </template>
</template>

<style scoped>
/* A section: its heading over its rows, on the frame's rhythm. */
.cset__section {
  display: grid;
  gap: var(--space-2);
}
.cset__section-title {
  margin: 0 0 var(--space-1);
  font-family: var(--font-display);
  font-size: var(--fs-h4);
  font-weight: 700;
  line-height: var(--lh-snug);
  color: var(--text-primary);
}

/* The description keeps its line breaks. */
.cset__multiline {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
</style>
