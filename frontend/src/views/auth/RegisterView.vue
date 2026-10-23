<script setup lang="ts">
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
import CAppControls from '@/components/ui/CAppControls.vue'
import { CInput } from '@/components/ui'
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
  <div class="auth-screen">
    <header class="auth-header">
      <AivisLogo :height="28" />
      <button type="button" class="btn-link btn-back" @click="goToLogin">
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <polyline points="15 18 9 12 15 6" />
        </svg>
        {{ t('auth.back') }}
      </button>
      <CAppControls />
    </header>

    <div class="auth-content">
      <h1 class="auth-title">
        {{ t('auth.register.title') }}
      </h1>
      <p class="auth-subtitle">
        {{ t('auth.register.subtitle') }}
      </p>
      <p v-if="buyIntent" class="auth-note">
        {{ t('auth.register.buyNote') }}
      </p>

      <div class="auth-form">
        <CInput
          v-model="email"
          :label="t('auth.register.email')"
          type="email"
          placeholder="name@example.com"
          autocomplete="email"
          @keydown.enter="handleRegister"
        />

        <!-- The hint belongs to the field, 4px under it, so the pair is wrapped
             and the field's own bottom margin is dropped; the wrapper carries
             the spacing that used to sit on .form-group. -->
        <div class="form-group">
          <CInput
            v-model="password"
            class="form-group__field"
            :label="t('auth.register.password')"
            type="password"
            :placeholder="t('auth.register.passPlaceholder')"
            autocomplete="new-password"
            @keydown.enter="handleRegister"
          />
          <div class="form-hint">
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

        <div v-if="error" class="auth-error">
          {{ error }}
        </div>

        <label class="auth-consent">
          <input v-model="acceptedTerms" type="checkbox" />
          <span class="auth-consent-text"
            >{{ t('auth.register.consentPrefix') }}
            <a
              :href="termsUrl"
              target="_blank"
              rel="noopener"
              @click.prevent="openDoc = 'cabinet_terms'"
              >{{ t('auth.register.consentTerms') }}</a
            >.</span
          >
        </label>

        <label class="auth-consent auth-consent--second">
          <input v-model="acceptedPrivacy" type="checkbox" />
          <span class="auth-consent-text"
            >{{ t('auth.register.consentPrefix') }}
            <a
              :href="privacyUrl"
              target="_blank"
              rel="noopener"
              @click.prevent="openDoc = 'privacy_policy'"
              >{{ t('auth.register.consentPrivacy') }}</a
            >.</span
          >
        </label>

        <button class="btn btn-primary" :disabled="authStore.loading" @click="handleRegister">
          <span v-if="authStore.loading" class="btn-spinner" />
          <span v-else>{{ t('auth.register.btn') }}</span>
        </button>

        <div class="auth-footer">
          <span class="auth-footer-text">{{ t('auth.register.hasAccount') }}</span>
          <button type="button" class="btn-link" @click="goToLogin">
            {{ t('auth.register.loginLink') }}
          </button>
        </div>
      </div>
    </div>

    <LegalDocModal
      :open="openDoc !== null"
      :title="docTitle"
      :lang="docLang"
      :type="openDoc ?? 'cabinet_terms'"
      @close="openDoc = null"
    />
  </div>
</template>

<style scoped>
.auth-screen {
  min-height: 100vh;
  min-height: 100dvh;
  background: var(--bg-page);
  display: flex;
  flex-direction: column;
}

.auth-header {
  position: sticky;
  top: 0;
  z-index: 100;
  background: var(--bg-page);
  padding: var(--space-4) var(--space-4-lg);
  border-bottom: 1px solid var(--border-default);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.btn-back {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  font-size: var(--fs-sm);
}

.btn-back svg {
  width: 16px;
  height: 16px;
}

.auth-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: var(--space-6) var(--space-5);
  overflow-y: auto;
}

.auth-title {
  font-size: var(--fs-h3);
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: var(--space-2);
  text-align: center;
}

.auth-subtitle {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  margin-bottom: var(--space-6);
  text-align: center;
  line-height: 1.5;
}

.auth-form {
  width: 100%;
  max-width: var(--maxw-form);
}

.form-group {
  margin-bottom: var(--space-4);
}

/* The field inside a hint pair gives up its own margin to the wrapper. */
.form-group__field {
  margin-bottom: 0;
}

.form-hint {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
  margin-top: var(--space-1);
}

.auth-error {
  padding: var(--space-3) var(--space-4);
  background: var(--danger-subtle);
  border: 1px solid var(--danger);
  border-radius: var(--radius-md);
  color: var(--danger);
  font-size: var(--fs-xs);
  margin-bottom: var(--space-4);
  line-height: 1.5;
}

.btn {
  width: 100%;
  padding: var(--space-4);
  border-radius: var(--radius-md);
  font-size: var(--fs-sm);
  font-weight: 600;
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  transition: opacity 0.2s;
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-primary {
  background: var(--primary);
  color: var(--on-primary);
}

.btn-primary:hover:not(:disabled) {
  opacity: 0.9;
}

.btn-spinner {
  width: var(--size-2xs);
  height: var(--size-2xs);
  /* currentColor, not white: the spinner sits inside a primary button whose
     colour is --on-primary, which is #FFFFFF in light and #04243E in dark.
     A white ring on the dark theme's light-azure button is near-invisible. */
  border: 2px solid currentColor;
  opacity: 0.35;
  border-top-color: currentColor;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.btn-link {
  position: relative;
  background: none;
  border: none;
  color: var(--primary);
  font-weight: 600;
  font-size: var(--fs-sm);
  cursor: pointer;
  padding: 0;
}

/* A5: the PAINTED box stays this size on purpose; the HIT AREA is expanded past
   it with a centred overlay. Growing the box itself would move the text this
   control sits inside or beside. max() so an already-large box never shrinks. */
.btn-link::after {
  content: '';
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  width: max(100%, var(--tap-min));
  height: max(100%, var(--tap-min));
}

.btn-link:hover {
  text-decoration: underline;
}

.auth-consent {
  display: flex;
  align-items: flex-start;
  gap: var(--space-2);
  width: 100%;
  margin-top: var(--space-3);
  margin-bottom: var(--space-3);
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
  text-align: left;
  line-height: 1.5;
}

.auth-consent--second {
  margin-bottom: var(--space-5);
}

.auth-note {
  width: 100%;
  max-width: var(--maxw-form);
  padding: var(--space-3) var(--space-4);
  margin-bottom: var(--space-4);
  background: var(--bg-subtle);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  font-size: var(--fs-xs);
  line-height: 1.5;
}

.auth-consent input[type='checkbox'] {
  flex: none;
  /* centre the box on the first text line: (line-height 1.5 * fs-xs - box) / 2 */
  margin: calc((1.5 * var(--fs-xs) - 1rem) / 2) 0 0;
  width: 1rem;
  height: 1rem;
}

.auth-consent a {
  color: var(--primary);
  text-decoration: underline;
}

.auth-footer {
  text-align: center;
  margin-top: var(--space-5);
}

.auth-footer-text {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  margin-right: var(--space-1);
}
</style>
