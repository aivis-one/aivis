<script setup lang="ts">
// Identity verification screen (H10).
//
// ONE SCREEN CARRYING FOUR STATES, not a modal over the page the 402
// interrupted. Since H21 P-111 the gate refuses only the money routes --
// buying, an installment plan, a withdrawal, the agent application --
// and the rest of the product is open before verification. So the page
// answers two questions: what verification unlocks and costs, and how
// to get back to the product without it (kyc.unlocks and the back
// button at the foot of the card, shown in every state).
//
//   not_started -> what it costs, what the account holds, and either
//                  "start" or a link to the deposit screen
//   submitted   -> paid, waiting for a decision
//   rejected    -> refused, with the reason staff gave; a new session costs
//                  the fee again
//   revoked     -> the approval was withdrawn; support is reachable
//
// The form also asks for the applicant's name, phone and country (saved to
// the profile when the application is sent), links the KYC notice (recorded
// as read at the same moment) and starts from a confirmed e-mail: a person
// without one is sent to the settings. A person short of the fee goes to the
// deposit screen with the minimum already in the amount field.
//
// GET /kyc/status and POST /kyc/submit are open to an unverified
// investor (backend kyc/gate.py), which is what makes this screen
// loadable by the very users it exists for.
//
// H12: THE SESSION NOW CARRIES DOCUMENTS. Until this pass the button
// paid ten dollars and opened an empty application, and staff approved
// without seeing anything. The not_started and rejected/revoked
// branches now hold a form: document type, front, selfie, and -- for
// an ID card or a driving licence -- the reverse.
//
// THE FILE CHECKS HERE ARE A COURTESY, NOT A BOUNDARY. The backend
// refuses the same things again from the filename extension, and it is
// the one that counts; these exist so a person is told about a HEIC
// before uploading eight megabytes of it, not after.

import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { api, ApiResponseError } from '@/api/client'
import {
  KYC_ACCEPT_ATTRIBUTE,
  localFileRejection,
  requiresBackImage,
  submitKycApplication,
  type KycDocumentType,
} from '@/api/kyc'
import { safeNavigate } from '@/composables/safeNavigate'
import { acceptDocumentByType } from '@/api/documents'
import { updateMe } from '@/api/users'
import { COUNTRIES } from '@/utils/countries'
import AivisLogo from '@/components/ui/AivisLogo.vue'
import CAppControls from '@/components/ui/CAppControls.vue'
import { CInput, CSelect } from '@/components/ui'
import AuthLogoutLink from '@/components/shared/AuthLogoutLink.vue'
import LegalDocModal from '@/components/legal/LegalDocModal.vue'

interface KYCStatusResponse {
  kyc_status: string
  application_id?: string | null
  application_status?: string | null
  rejection_reason?: string | null
  fee_cents: number
  available_cents: number
}

// The smallest top-up that pays the fee; the deposit screen opens with it.
const KYC_TOP_UP_MIN_USD = 10

const router = useRouter()
const { t, locale } = useI18n()
const authStore = useAuthStore()

const loading = ref(true)
const submitting = ref(false)
const error = ref('')
const status = ref<KYCStatusResponse | null>(null)

// ---------------------------------------------------------------------------
// The applicant's details. They are asked here and nowhere in the entry
// steps; they are saved to the profile when the application is sent.
// ---------------------------------------------------------------------------

const firstName = ref('')
const lastName = ref('')
const phone = ref('')
const country = ref('')
const countryOptions = COUNTRIES

function seedDetails(): void {
  const profile = authStore.user?.profile
  if (!profile || typeof profile !== 'object') return
  const text = (v: unknown): string => (typeof v === 'string' ? v : '')
  firstName.value = text(profile.first_name)
  lastName.value = text(profile.last_name)
  phone.value = text(profile.phone)
  country.value = text(profile.country)
}

const detailsReady = computed(
  () =>
    firstName.value.trim().length > 0 &&
    lastName.value.trim().length > 0 &&
    country.value.length > 0,
)

// A person who signed in without an e-mail has none to confirm: verification
// starts from a confirmed e-mail, so the screen sends them to the settings.
const emailMissing = ref(false)

// The KYC notice opens in the cabinet's document window, in the language of
// the cabinet; sending the application records it as read.
const noticeOpen = ref(false)
const docLang = computed(() => (locale.value === 'ru' ? 'ru' : 'en'))
const noticeUrl = computed(() => `${import.meta.env.BASE_URL}legal/${docLang.value}/kyc_notice.html`)

const documentType = ref<KycDocumentType>('passport')

// The three file slots, and the name of one of them. Named because
// pickFile and setSlot both take it and a repeated union is a repeated
// place to forget a member.
type SlotTarget = 'front' | 'back' | 'selfie'

const frontImage = ref<File | null>(null)
const backImage = ref<File | null>(null)
const selfieImage = ref<File | null>(null)

const needsBack = computed(() => requiresBackImage(documentType.value))

// Every file the form is currently asking for is present. The back is
// counted only when this document type has one -- otherwise a passport
// could never be submitted.
const documentsReady = computed(
  () =>
    frontImage.value !== null &&
    selfieImage.value !== null &&
    (!needsBack.value || backImage.value !== null),
)

// The dispatch from `target` to the ref it names, in ONE place. It used
// to be written out three times, and that is how the branch below came
// to be missing one of them: a branch that cleared the input LOOKED
// like it had cleared the choice.
function setSlot(target: SlotTarget, file: File | null): void {
  if (target === 'front') frontImage.value = file
  else if (target === 'back') backImage.value = file
  else selfieImage.value = file
}

function pickFile(target: SlotTarget, event: Event): void {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0] ?? null

  if (file === null) {
    // The person opened the picker and cancelled. Clear the slot rather
    // than keeping the previous choice, so what the form shows is what
    // it will send.
    setSlot(target, null)
    return
  }

  const rejection = localFileRejection(file)
  if (rejection !== null) {
    // CLEARING THE INPUT AND CLEARING THE SLOT ARE ONE ACTION. The
    // input is what the person SEES; the ref is what the form SENDS.
    // This branch used to do only the first, so "front.jpg, then
    // front.heic" left the field blank, the submit button live and
    // front.jpg still staged -- the submission carried a document its
    // owner believed they had replaced, and staff decided on that one.
    // A document in storage that is not the one the person chose is a
    // record that lies about the basis of a decision, which is why this
    // is a blocker and not a cosmetic bug.
    error.value = t(rejection)
    input.value = ''
    setSlot(target, null)
    return
  }

  error.value = ''
  setSlot(target, file)
}

// A passport carries nothing on its reverse, so a back image chosen
// before the type was switched must not travel with the submission --
// the backend refuses the whole set if it does.
function onDocumentTypeChange(): void {
  if (!needsBack.value) {
    backImage.value = null
  }
}

const feeUsd = computed(() =>
  status.value ? (status.value.fee_cents / 100).toFixed(2) : '0.00',
)
const availableUsd = computed(() =>
  status.value ? (status.value.available_cents / 100).toFixed(2) : '0.00',
)
const canAfford = computed(
  () =>
    status.value !== null &&
    status.value.available_cents >= status.value.fee_cents,
)

// Declared after canAfford on purpose: it reads it, and a const that
// references a later const in the same scope is a temporal-dead-zone
// trap waiting for the first person who moves an evaluation earlier.
const canSubmit = computed(
  () => canAfford.value && documentsReady.value && detailsReady.value && !emailMissing.value,
)

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  emailMissing.value = !authStore.user ? false : !authStore.user.email
  try {
    status.value = await api.get<KYCStatusResponse>('/api/v1/kyc/status')
    // Already through: nothing to show here. Send them where they were
    // going in the first place.
    if (status.value.kyc_status === 'approved') {
      void safeNavigate(router.push('/'), '[KYCVerificationView] approved')
    }
  } catch (e) {
    error.value =
      e instanceof ApiResponseError ? e.detail : t('kyc.errorLoad')
  } finally {
    loading.value = false
  }
}

async function startVerification(): Promise<void> {
  if (!documentsReady.value || frontImage.value === null || selfieImage.value === null) {
    error.value = t('kyc.upload.errorIncomplete')
    return
  }

  if (!detailsReady.value) {
    error.value = t('kyc.details.errorIncomplete')
    return
  }

  submitting.value = true
  error.value = ''
  try {
    // Nothing is charged before this point. The details go to the profile and
    // the notice is recorded as read first; the fee is taken by the submit.
    await updateMe({
      profile: {
        first_name: firstName.value.trim(),
        last_name: lastName.value.trim(),
        phone: phone.value.trim() || null,
        country: country.value,
      },
    })
    await acceptDocumentByType('kyc_notice', docLang.value)
    await submitKycApplication(
      documentType.value,
      frontImage.value,
      selfieImage.value,
      needsBack.value ? backImage.value : null,
    )
    frontImage.value = null
    backImage.value = null
    selfieImage.value = null
    await authStore.fetchMe()
    await load()
  } catch (e) {
    if (e instanceof ApiResponseError && e.code === 'kyc_email_not_verified') {
      emailMissing.value = true
      error.value = ''
    } else {
      error.value = e instanceof ApiResponseError ? e.detail : t('kyc.errorStart')
    }
  } finally {
    submitting.value = false
  }
}

// The deposit screen opens with the fee in the amount field and the
// minimum named, so a person who is short pays exactly what is needed.
function toDeposit(): void {
  void safeNavigate(
    router.push({
      path: '/investor/balance/deposit',
      query: { amount: String(KYC_TOP_UP_MIN_USD), min: String(KYC_TOP_UP_MIN_USD) },
    }),
    '[KYCVerificationView] to deposit',
  )
}

function toSettings(): void {
  void safeNavigate(
    router.push({ path: '/investor/settings', query: { confirm_email: '1' } }),
    '[KYCVerificationView] to settings',
  )
}

function toSupport(): void {
  void safeNavigate(
    router.push('/investor/support'),
    '[KYCVerificationView] to support',
  )
}

// Back to where the person came from -- usually the purchase,
// installment or withdrawal screen the gate refused. A deep link has no
// prior entry, so it goes to '/', which lands on the role's dashboard.
function goBack(): void {
  if (window.history.state?.back) {
    router.back()
    return
  }
  void safeNavigate(router.push('/'), '[KYCVerificationView] back')
}

onMounted(() => {
  seedDetails()
  void load()
})
</script>

<template>
  <div class="auth-page">
    <div class="auth-content">
      <AivisLogo class="logo" />
      <CAppControls />

      <div v-if="loading" class="kyc-card">{{ t('common.loading') }}</div>

      <div v-else-if="status" class="kyc-card">
        <!-- Paid, waiting -->
        <template v-if="status.kyc_status === 'submitted'">
          <h1 class="kyc-title">{{ t('kyc.pendingTitle') }}</h1>
          <p class="kyc-text">{{ t('kyc.pendingText') }}</p>
        </template>

        <!-- Not started, refused, or an approval withdrawn: the same form -->
        <template v-else>
          <h1 class="kyc-title">
            {{
              status.kyc_status === 'revoked'
                ? t('kyc.revokedTitle')
                : status.kyc_status === 'rejected'
                  ? t('kyc.rejectedTitle')
                  : t('kyc.title')
            }}
          </h1>
          <p class="kyc-text">
            {{
              status.kyc_status === 'revoked'
                ? t('kyc.revokedText')
                : status.kyc_status === 'rejected'
                  ? t('kyc.rejectedText', { fee: feeUsd })
                  : t('kyc.introPaid', { fee: feeUsd })
            }}
          </p>
          <p
            v-if="status.kyc_status === 'rejected' && status.rejection_reason"
            class="kyc-reason"
          >
            {{ t('kyc.rejectedReason', { reason: status.rejection_reason }) }}
          </p>
          <p class="kyc-balance">
            {{ t('kyc.balance', { available: availableUsd }) }}
          </p>

          <!-- Verification starts from a confirmed e-mail -->
          <div v-if="emailMissing" class="kyc-gate">
            <p class="kyc-text">{{ t('kyc.emailFirst') }}</p>
            <button type="button" class="btn btn-primary" @click="toSettings">
              {{ t('kyc.toSettings') }}
            </button>
          </div>

          <template v-else>
            <div class="kyc-form">
              <div class="kyc-row">
                <CInput
                  v-model="firstName"
                  class="kyc-row__col"
                  :label="t('kyc.details.firstName')"
                  autocomplete="given-name"
                />
                <CInput
                  v-model="lastName"
                  class="kyc-row__col"
                  :label="t('kyc.details.lastName')"
                  autocomplete="family-name"
                />
              </div>
              <CInput
                v-model="phone"
                :label="t('kyc.details.phone')"
                type="tel"
                autocomplete="tel"
              />
              <CSelect
                v-model="country"
                :label="t('kyc.details.country')"
                :options="countryOptions"
                placeholder="—"
              />

              <label class="kyc-field">
                <span class="kyc-label">{{ t('kyc.upload.documentType') }}</span>
                <select v-model="documentType" class="kyc-select" @change="onDocumentTypeChange">
                  <option value="passport">
                    {{ t('kyc.upload.typePassport') }}
                  </option>
                  <option value="id_card">
                    {{ t('kyc.upload.typeIdCard') }}
                  </option>
                  <option value="driving_licence">
                    {{ t('kyc.upload.typeDrivingLicence') }}
                  </option>
                </select>
              </label>

              <label class="kyc-field">
                <span class="kyc-label">{{ t('kyc.upload.front') }}</span>
                <input
                  type="file"
                  class="kyc-file"
                  :accept="KYC_ACCEPT_ATTRIBUTE"
                  @change="pickFile('front', $event)"
                />
              </label>

              <label v-if="needsBack" class="kyc-field">
                <span class="kyc-label">{{ t('kyc.upload.back') }}</span>
                <input
                  type="file"
                  class="kyc-file"
                  :accept="KYC_ACCEPT_ATTRIBUTE"
                  @change="pickFile('back', $event)"
                />
              </label>

              <label class="kyc-field">
                <span class="kyc-label">{{ t('kyc.upload.selfie') }}</span>
                <input
                  type="file"
                  class="kyc-file"
                  :accept="KYC_ACCEPT_ATTRIBUTE"
                  @change="pickFile('selfie', $event)"
                />
              </label>

              <p class="kyc-hint">{{ t('kyc.upload.hint') }}</p>
              <p class="kyc-hint">
                {{ t('kyc.notice.lead') }}
                <a :href="noticeUrl" target="_blank" rel="noopener" @click.prevent="noticeOpen = true">{{
                  t('kyc.notice.link')
                }}</a
                >.
              </p>
            </div>

            <button
              v-if="canAfford"
              class="btn btn-primary"
              :disabled="submitting || !canSubmit"
              @click="startVerification"
            >
              {{
                status.kyc_status === 'not_started'
                  ? t('kyc.start', { fee: feeUsd })
                  : t('kyc.startAgain', { fee: feeUsd })
              }}
            </button>
            <template v-else>
              <p class="kyc-text">{{ t('kyc.needsTopUp') }}</p>
              <button class="btn btn-primary" @click="toDeposit">
                {{ t('kyc.toDeposit') }}
              </button>
            </template>
            <button v-if="status.kyc_status !== 'not_started'" class="btn btn-outline" @click="toSupport">
              {{ t('kyc.toSupport') }}
            </button>
          </template>
        </template>

        <p class="kyc-text">{{ t('kyc.unlocks') }}</p>
        <button class="btn btn-outline" @click="goBack">
          {{ t('kyc.back') }}
        </button>
        <div class="kyc-logout">
          <AuthLogoutLink />
        </div>
      </div>
      <p v-if="error" class="kyc-error">{{ error }}</p>
    </div>

    <LegalDocModal
      :open="noticeOpen"
      :title="t('kyc.notice.link')"
      :lang="docLang"
      type="kyc_notice"
      @close="noticeOpen = false"
    />
  </div>
</template>

<style scoped>
.auth-page {
  min-block-size: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-4);
}

.auth-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-4);
  inline-size: 100%;
}

.logo {
  margin-block-end: var(--space-2);
}

/* Fixed-width by intent -- registered in checks/preauth.py, which says
   what the card holds. A wider column would only stretch its content. */
.kyc-card {
  inline-size: 100%;
  max-inline-size: var(--maxw-form);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  text-align: center;
}

.kyc-title {
  font-size: var(--fs-lg);
  font-weight: 600;
}

.kyc-text {
  color: var(--text-secondary);
}

.kyc-balance {
  font-variant-numeric: tabular-nums;
}

.kyc-form {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  text-align: start;
}

.kyc-field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.kyc-label {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
}

.kyc-select,
.kyc-file {
  inline-size: 100%;
}

.kyc-hint {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
}

.kyc-row {
  display: flex;
  gap: var(--space-3);
}

.kyc-row__col {
  flex: 1;
  min-inline-size: 0;
}

.kyc-reason {
  color: var(--danger);
}

.kyc-gate {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.kyc-hint a {
  color: var(--primary);
  text-decoration: underline;
}

.kyc-logout {
  display: flex;
  justify-content: center;
}

.kyc-error {
  color: var(--danger);
  max-inline-size: var(--maxw-form);
  text-align: center;
}
</style>
