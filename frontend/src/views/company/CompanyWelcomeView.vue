<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- CompanyWelcomeView
// =============================================================================
//
// The full screen a project account meets at its first sign-in, and the only
// screen open to it until the documents its role signs are accepted (the router
// guard sends every other project route here). The project account is created
// by the Company's staff, so there is no registration step where the ticks
// could be placed: each document is read behind a link and accepted by its own
// tick, and the cabinet opens through one button once every tick is set.
//
// The documents are the ones the platform marks as required for the project
// role (the Cabinet Terms and the Privacy Policy today); the screen lists
// whatever the server reports as not accepted yet and nothing else.
// =============================================================================

import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'

import AivisLogo from '@/components/ui/AivisLogo.vue'
import CAppControls from '@/components/ui/CAppControls.vue'
import { CButton, CCheckbox, CLoader } from '@/components/ui'
import AuthLogoutLink from '@/components/shared/AuthLogoutLink.vue'
import LegalDocModal from '@/components/legal/LegalDocModal.vue'
import { ApiResponseError } from '@/api/client'
import { signDocument } from '@/api/documents'
import { safeNavigate } from '@/composables/safeNavigate'
import { useToast } from '@/composables/useToast'
import { useCompanyTermsStore } from '@/stores/companyTerms'
import type { DocumentResponse } from '@/api/types'

const router = useRouter()
const { t, locale } = useI18n()
const { showToast } = useToast()
const termsStore = useCompanyTermsStore()

const docLang = computed(() => (locale.value === 'ru' ? 'ru' : 'en'))
const checking = ref(true)
const accepting = ref(false)
const ticked = reactive<Record<string, boolean>>({})
const reading = ref<DocumentResponse | null>(null)

const pending = computed<DocumentResponse[]>(() => termsStore.pending)
const allTicked = computed<boolean>(
  () => pending.value.length > 0 && pending.value.every((d) => ticked[d.id] === true),
)

// The two documents every account accepts have their wording on the sign-up
// screen; any other document a role is required to sign is named by its title.
function docName(doc: DocumentResponse): string {
  if (doc.type === 'cabinet_terms') return t('auth.register.consentTerms')
  if (doc.type === 'privacy_policy') return t('auth.register.consentPrivacy')
  return doc.title
}

function openCabinet(): void {
  void safeNavigate(
    router.replace({ name: 'company-dashboard' }),
    '[CompanyWelcomeView] to cabinet',
  )
}

async function check(): Promise<void> {
  checking.value = true
  await termsStore.ensure()
  checking.value = false
  if (termsStore.status === 'signed') openCabinet()
}

async function onAccept(): Promise<void> {
  if (!allTicked.value || accepting.value) return
  accepting.value = true
  try {
    for (const doc of pending.value) {
      try {
        await signDocument(doc.id)
      } catch (err) {
        // A second tab or a replayed request: the document is already accepted.
        if (!(err instanceof ApiResponseError && err.status === 409)) throw err
      }
    }
    termsStore.markSigned()
    openCabinet()
  } catch {
    showToast(t('comp.welcome.error'), 'error')
  } finally {
    accepting.value = false
  }
}

onMounted(() => {
  void check()
})
</script>

<template>
  <div class="welcome">
    <div class="welcome__bar">
      <AivisLogo :height="28" :show-text="false" />
      <CAppControls />
    </div>

    <div class="welcome__card">
      <div v-if="checking" class="welcome__center">
        <CLoader :size="28" />
      </div>

      <!-- The state could not be read -->
      <template v-else-if="termsStore.status === 'error'">
        <h1 class="welcome__title">
          {{ t('comp.welcome.errorTitle') }}
        </h1>
        <CButton variant="outline" @click="check">
          {{ t('common.retry') }}
        </CButton>
      </template>

      <template v-else>
        <h1 class="welcome__title">
          {{ t('comp.welcome.title') }}
        </h1>
        <p class="welcome__text">
          {{ t('comp.welcome.intro') }}
        </p>

        <div v-for="doc in pending" :key="doc.id" class="welcome__doc">
          <CCheckbox
            v-model="ticked[doc.id]"
            :label="`${t('auth.register.consentPrefix')} ${docName(doc)}`"
          />
          <a href="#read" class="welcome__read" @click.prevent="reading = doc">
            {{ t('comp.welcome.read') }}
          </a>
        </div>

        <CButton variant="primary" :disabled="!allTicked" :loading="accepting" @click="onAccept">
          {{ t('comp.welcome.accept') }}
        </CButton>
      </template>

      <div class="welcome__logout">
        <AuthLogoutLink />
      </div>
    </div>

    <LegalDocModal
      :open="reading !== null"
      :title="reading ? docName(reading) : ''"
      :lang="docLang"
      :type="reading?.type ?? ''"
      @close="reading = null"
    />
  </div>
</template>

<style scoped>
.welcome {
  min-block-size: 100vh;
  min-block-size: 100dvh;
  display: flex;
  flex-direction: column;
  background: var(--bg-page);
}

.welcome__bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-3) var(--space-4);
  border-block-end: thin solid var(--border-default);
}

.welcome__card {
  inline-size: 100%;
  max-inline-size: var(--maxw-prose, 560px);
  margin: 0 auto;
  padding: var(--space-5) var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.welcome__center {
  display: flex;
  justify-content: center;
  padding: var(--space-6, 32px) 0;
}

.welcome__title {
  margin: 0;
  font-size: var(--fs-h3, 1.375rem);
  font-weight: 700;
  color: var(--text-primary);
}

.welcome__text {
  margin: 0;
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  line-height: 1.5;
}

.welcome__doc {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.welcome__read {
  align-self: flex-start;
  margin-inline-start: var(--space-6, 32px);
  font-size: var(--fs-sm);
  color: var(--primary);
}

.welcome__logout {
  display: flex;
  justify-content: center;
  padding-block-start: var(--space-2);
}

/* On a tablet and a desktop the card gets more room above it. */
@media (min-width: 880px) {
  .welcome__card {
    padding-block-start: var(--space-6, 32px);
  }
}
</style>
