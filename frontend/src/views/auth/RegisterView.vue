<script setup lang="ts">
import AuthShell from '@/components/layout/AuthShell.vue'
import { Info, ShieldAlert } from '@/components/ui/icons'
// =============================================================================
// AIVIS.ONE Frontend -- RegisterView (iter 2.6 batch 2 + R22 STYLE-22-02)
// =============================================================================
//
// Email + password + confirmation registration form. Reads the
// referral code from sessionStorage on submit (FP-13, first-wins per
// tab session), passes it to authStore.registerViaEmail, which clears
// the key after a successful response.
//
// iter 2.6 batch 2 changes:
//
//   1. LOGIN LINKS are router-driven instead of emit-driven.
//      The header back-button and the footer "Sign in" link both used
//      to emit('go-login') to App.vue's authView ref. App.vue's
//      standalone-flow branch is gone (router-driven content now);
//      both buttons call router.push({ name: 'login', query:
//      route.query }) instead. Forwarding `?next=` keeps the visitor's
//      intended destination alive across the register <-> login pivot.
//
//   2. `next` IS KEPT for the length of the tab session (utils/postAuthReturn).
//      A visitor who pressed "Buy" on the open storefront is sent here with
//      the product page in `next`; once the entry steps are done (e-mail
//      code, and the documents step where one is left) the product opens.
//
// THE TWO CONSENT TICKS. The cabinet terms and the privacy policy each have
//   their own tick and a link to the full document (in the visitor's
//   language, in the cabinet's own document window, with the static file as
//   the fallback link). Registration is not sent until both are ticked, and
//   once the account exists both acceptances are recorded against the
//   current documents (POST /documents/{id}/sign through their by-type ids).
//   A recording that fails does not undo the registration: the documents
//   step after the e-mail code asks again for whatever is still unsigned.
//
// R22 STYLE-22-02:
//   goToLogin() catches navigation rejections with the standard
//   NavigationFailure filter -- benign types (duplicated / cancelled
//   / aborted) stay silent, real issues log. Matches the pattern
//   established by useAuthWall (R20 STYLE-20-01) and now applied
//   across all router.push() call-sites that branch on user action.
// =============================================================================

import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { REFERRAL_KEY, useAuthStore } from '@/stores/auth'
import { ApiResponseError, ApiNetworkError, ApiTimeoutError } from '@/api/client'
import { safeNavigate } from '@/composables/safeNavigate'
import AivisLogo from '@/components/ui/AivisLogo.vue'
import { CBackLink, CCheckbox, CInput } from '@/components/ui'
import LegalDocModal from '@/components/legal/LegalDocModal.vue'
import { acceptDocumentByType } from '@/api/documents'
import { rememberReturnPath } from '@/utils/postAuthReturn'

const { t, locale } = useI18n()
const route = useRoute()
const authStore = useAuthStore()
const router = useRouter()

const email = ref('')
const password = ref('')
const confirmPassword = ref('')
const error = ref('')
const acceptedTerms = ref(false)
const acceptedPrivacy = ref(false)

// The two documents the registration ticks stand for. Both are the cabinet's
// own static files (public/legal/<lang>/<type>.html, the same BASE_URL + legal/
// path the document viewers use); the href is the fallback for a click that
// is not ours and the way to save the file.
const docLang = computed(() => (locale.value === 'ru' ? 'ru' : 'en'))
function docUrl(type: string): string {
  return `${import.meta.env.BASE_URL}legal/${docLang.value}/${type}.html`
}
const termsUrl = computed(() => docUrl('cabinet_terms'))
const privacyUrl = computed(() => docUrl('privacy_policy'))

// One document window, told which of the two to open.
const openDoc = ref<'cabinet_terms' | 'privacy_policy' | null>(null)
const docTitle = computed(() =>
  openDoc.value === 'privacy_policy'
    ? t('auth.register.consentPrivacy')
    : t('auth.register.consentTerms'),
)

// A visitor sent here by "Buy" is told that buying comes after the identity
// check. The page they wanted is kept and opened after the entry steps.
const buyIntent = computed(() => route.query.intent === 'purchase')
rememberReturnPath(route.query.next)

const REQUIRED_DOCUMENTS = ['cabinet_terms', 'privacy_policy'] as const

async function recordAcceptances(lang: string): Promise<void> {
  for (const type of REQUIRED_DOCUMENTS) {
    try {
      await acceptDocumentByType(type, lang)
    } catch {
      // The documents step after the e-mail code asks again for what is
      // still unsigned; a failed recording never undoes the registration.
    }
  }
}

function goToLogin(): void {
  // Forward `?next=...` so the eventual sign-in returns the visitor
  // to the same public page they were aiming for.
  void safeNavigate(router.push({ name: 'login', query: route.query }), '[RegisterView] to login')
}

async function handleRegister(): Promise<void> {
  error.value = ''

  if (!email.value || !password.value || !confirmPassword.value) {
    error.value = t('auth.error.fillAllFields')
    return
  }

  if (password.value !== confirmPassword.value) {
    error.value = t('auth.error.passwordMismatch')
    return
  }

  if (password.value.length < 8) {
    error.value = t('auth.register.passwordHint')
    return
  }
  if (!acceptedTerms.value || !acceptedPrivacy.value) {
    error.value = t('auth.register.consentRequired')
    return
  }

  const referralCode = sessionStorage.getItem(REFERRAL_KEY)

  try {
    // The text language is the one on this screen; the account language is
    // sent with the registration.
    const readLang = docLang.value
    await authStore.registerViaEmail(email.value, password.value, referralCode)
    await recordAcceptances(readLang)
    // BUG-07 fix: after registration the user is at onboarding_step=registered.
    // Push straight to /verify (meta.skipOnboarding=true) -- going through /
    // would bounce us via root.beforeEnter + globalGuard for no reason.
    //
    // `?next=` is kept by rememberReturnPath (see the file header), not
    // forwarded through the e-mail step.
    //
    // safeNavigate is no-throw by contract -- critical here so a benign
    // NavigationFailure does NOT bubble into the outer registration-error
    // catch and surface as a generic-error toast after successful registration.
    await safeNavigate(router.push({ name: 'verify' }), '[RegisterView] post-register to verify')
  } catch (err) {
    if (err instanceof ApiResponseError) {
      if (err.status === 409) {
        error.value = t('auth.error.emailTaken')
      } else {
        error.value = err.detail
      }
    } else if (err instanceof ApiNetworkError) {
      error.value = t('auth.error.networkError')
    } else if (err instanceof ApiTimeoutError) {
      error.value = t('auth.error.timeout')
    } else {
      error.value = t('common.error')
    }
  }
}
</script>

<template>
  <AuthShell>
    <template #start>
      <AivisLogo :height="28" />
      <CBackLink :label="t('auth.back')" @click="goToLogin" />
    </template>

    <h1 class="ds-auth__title">
      {{ t('auth.register.title') }}
    </h1>
    <p class="ds-auth__subtitle">
      {{ t('auth.register.subtitle') }}
    </p>
    <div v-if="buyIntent" class="ds-alert ds-alert--info" role="status">
      <span class="ds-alert__icon" aria-hidden="true"><Info size="sm" /></span>
      <div class="ds-alert__content">
        <p class="ds-alert__text">{{ t('auth.register.buyNote') }}</p>
      </div>
    </div>

    <div class="ds-auth__form">
      <CInput
        v-model="email"
        :label="t('auth.register.email')"
        type="email"
        placeholder="name@example.com"
        autocomplete="email"
        @keydown.enter="handleRegister"
      />

      <!-- The hint belongs to the field, directly under it, so the pair is wrapped
             and the field's own bottom margin is dropped; the wrapper carries
             the spacing that used to sit on .form-group. -->
      <div class="ds-field">
        <CInput
          v-model="password"
          class="form-group__field"
          :label="t('auth.register.password')"
          type="password"
          :placeholder="t('auth.register.passPlaceholder')"
          autocomplete="new-password"
          @keydown.enter="handleRegister"
        />
        <div class="ds-field__hint">
          {{ t('auth.register.passwordHint') }}
        </div>
      </div>

      <CInput
        v-model="confirmPassword"
        :label="t('auth.register.confirmPassword')"
        type="password"
        :placeholder="t('auth.register.confirmPlaceholder')"
        autocomplete="new-password"
        @keydown.enter="handleRegister"
      />

      <div v-if="error" class="ds-alert ds-alert--danger" role="alert">
        <span class="ds-alert__icon" aria-hidden="true"><ShieldAlert size="sm" /></span>
        <div class="ds-alert__content">
          <p class="ds-alert__text">{{ error }}</p>
        </div>
      </div>

      <CCheckbox v-model="acceptedTerms">
        {{ t('auth.register.consentPrefix') }}
        <a
          :href="termsUrl"
          target="_blank"
          rel="noopener"
          @click.prevent="openDoc = 'cabinet_terms'"
          >{{ t('auth.register.consentTerms') }}</a
        >.
      </CCheckbox>

      <CCheckbox v-model="acceptedPrivacy">
        {{ t('auth.register.consentPrefix') }}
        <a
          :href="privacyUrl"
          target="_blank"
          rel="noopener"
          @click.prevent="openDoc = 'privacy_policy'"
          >{{ t('auth.register.consentPrivacy') }}</a
        >.
      </CCheckbox>

      <button
        class="ds-button ds-button--primary ds-button--block"
        :aria-busy="authStore.loading || undefined"
        :disabled="authStore.loading"
        @click="handleRegister"
      >
        <span v-if="authStore.loading" class="ds-button__spinner" aria-hidden="true" />
        <span>{{ t('auth.register.btn') }}</span>
      </button>

      <div class="ds-auth__foot">
        <span>{{ t('auth.register.hasAccount') }}</span>
        <button type="button" class="ds-button ds-button--ghost" data-size="sm" @click="goToLogin">
          {{ t('auth.register.loginLink') }}
        </button>
      </div>
    </div>

    <LegalDocModal
      :open="openDoc !== null"
      :title="docTitle"
      :lang="docLang"
      :type="openDoc ?? 'cabinet_terms'"
      @close="openDoc = null"
    />
  </AuthShell>
</template>

<style scoped>
/* The field inside a hint pair gives up its own margin to the wrapper. */
.form-group__field {
  margin-block-end: 0;
}
</style>
