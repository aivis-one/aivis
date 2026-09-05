<script setup lang="ts">
// Identity verification screen (H10).
//
// ONE SCREEN CARRYING FOUR STATES, not a modal over whatever page the
// 402 interrupted. The gate refuses from any endpoint, so a modal would
// leave the person looking at a product they cannot use behind it, with
// half its widgets showing errors of their own. Here the answer to
// "what do you want from me and where do I go" is the whole page.
//
//   not_started -> what it costs, what the account holds, and either
//                  "start" or a link to the deposit screen
//   submitted   -> paid, waiting for a decision
//   rejected    -> refused; a new session costs the fee again
//   revoked     -> the approval was withdrawn; support is reachable
//
// GET /kyc/status and POST /kyc/submit are both in front of the gate
// (backend kyc/gate.py), which is what makes this screen loadable by
// the very users it exists for.
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
import AivisLogo from '@/components/ui/AivisLogo.vue'
import CAppControls from '@/components/ui/CAppControls.vue'

interface KYCStatusResponse {
  kyc_status: string
  application_id?: string | null
  application_status?: string | null
  fee_cents: number
  available_cents: number
}

const router = useRouter()
const { t } = useI18n()
const authStore = useAuthStore()

const loading = ref(true)
const submitting = ref(false)
const error = ref('')
const status = ref<KYCStatusResponse | null>(null)

const documentType = ref<KycDocumentType>('passport')
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

function pickFile(target: 'front' | 'back' | 'selfie', event: Event): void {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0] ?? null

  if (file === null) {
    // The person opened the picker and cancelled. Clear the slot rather
    // than keeping the previous choice, so what the form shows is what
    // it will send.
    if (target === 'front') frontImage.value = null
    else if (target === 'back') backImage.value = null
    else selfieImage.value = null
    return
  }

  const rejection = localFileRejection(file)
  if (rejection !== null) {
    error.value = t(rejection)
    input.value = ''
    return
  }

  error.value = ''
  if (target === 'front') frontImage.value = file
  else if (target === 'back') backImage.value = file
  else selfieImage.value = file
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
const canSubmit = computed(() => canAfford.value && documentsReady.value)

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
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

  submitting.value = true
  error.value = ''
  try {
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
    error.value =
      e instanceof ApiResponseError ? e.detail : t('kyc.errorStart')
  } finally {
    submitting.value = false
  }
}

function toDeposit(): void {
  void safeNavigate(
    router.push('/investor/balance/deposit'),
    '[KYCVerificationView] to deposit',
  )
}

function toSupport(): void {
  void safeNavigate(
    router.push('/investor/support'),
    '[KYCVerificationView] to support',
  )
}

onMounted(load)
</script>

<template>
  <div class="auth-page">
    <div class="auth-content">
      <AivisLogo class="logo" />
      <CAppControls />

      <div v-if="loading" class="kyc-card">{{ t('common.loading') }}</div>

      <div v-else-if="status" class="kyc-card">
        <!-- Not started: the money question -->
        <template v-if="status.kyc_status === 'not_started'">
          <h1 class="kyc-title">{{ t('kyc.title') }}</h1>
          <p class="kyc-text">{{ t('kyc.introPaid', { fee: feeUsd }) }}</p>
          <p class="kyc-balance">
            {{ t('kyc.balance', { available: availableUsd }) }}
          </p>
          <div class="kyc-form">
            <label class="kyc-field">
              <span class="kyc-label">{{ t('kyc.upload.documentType') }}</span>
              <select
                v-model="documentType"
                class="kyc-select"
                @change="onDocumentTypeChange"
              >
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
          </div>
          <button
            v-if="canAfford"
            class="btn btn-primary"
            :disabled="submitting || !canSubmit"
            @click="startVerification"
          >
            {{ t('kyc.start', { fee: feeUsd }) }}
          </button>
          <template v-else>
            <p class="kyc-text">{{ t('kyc.needsTopUp') }}</p>
            <button class="btn btn-primary" @click="toDeposit">
              {{ t('kyc.toDeposit') }}
            </button>
          </template>
        </template>

        <!-- Paid, waiting -->
        <template v-else-if="status.kyc_status === 'submitted'">
          <h1 class="kyc-title">{{ t('kyc.pendingTitle') }}</h1>
          <p class="kyc-text">{{ t('kyc.pendingText') }}</p>
        </template>

        <!-- Refused, or an approval withdrawn -->
        <template v-else>
          <h1 class="kyc-title">
            {{
              status.kyc_status === 'revoked'
                ? t('kyc.revokedTitle')
                : t('kyc.rejectedTitle')
            }}
          </h1>
          <p class="kyc-text">
            {{
              status.kyc_status === 'revoked'
                ? t('kyc.revokedText')
                : t('kyc.rejectedText', { fee: feeUsd })
            }}
          </p>
          <p class="kyc-balance">
            {{ t('kyc.balance', { available: availableUsd }) }}
          </p>
          <div class="kyc-form">
            <label class="kyc-field">
              <span class="kyc-label">{{ t('kyc.upload.documentType') }}</span>
              <select
                v-model="documentType"
                class="kyc-select"
                @change="onDocumentTypeChange"
              >
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
          </div>
          <button
            v-if="canAfford"
            class="btn btn-primary"
            :disabled="submitting || !canSubmit"
            @click="startVerification"
          >
            {{ t('kyc.startAgain', { fee: feeUsd }) }}
          </button>
          <button v-else class="btn btn-primary" @click="toDeposit">
            {{ t('kyc.toDeposit') }}
          </button>
          <button class="btn btn-outline" @click="toSupport">
            {{ t('kyc.toSupport') }}
          </button>
        </template>
      </div>

      <p v-if="error" class="kyc-error">{{ error }}</p>
    </div>
  </div>
</template>

<style scoped>
.auth-page {
  min-height: 100vh;
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
  width: 100%;
}

.logo {
  margin-bottom: var(--space-2);
}

/* Fixed-width by intent -- registered in checks/preauth.py. The card
   holds one heading, two lines of prose and at most two buttons; a
   wider column would only stretch the prose. */
.kyc-card {
  width: 100%;
  max-width: var(--maxw-form);
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
  text-align: left;
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
  width: 100%;
}

.kyc-hint {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
}

.kyc-error {
  color: var(--danger);
  max-width: var(--maxw-form);
  text-align: center;
}
</style>
