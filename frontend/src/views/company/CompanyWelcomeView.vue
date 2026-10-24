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

import { CButton, CCheckbox, CLoader } from '@/components/ui'
import AuthShell from '@/components/layout/AuthShell.vue'
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
  <AuthShell>
    <div v-if="checking" class="ds-empty" aria-busy="true">
      <CLoader :size="28" />
    </div>

    <!-- The state could not be read -->
    <template v-else-if="termsStore.status === 'error'">
      <h1 class="ds-auth__title">
        {{ t('comp.welcome.errorTitle') }}
      </h1>
      <CButton variant="outline" @click="check">
        {{ t('common.retry') }}
      </CButton>
    </template>

    <template v-else>
      <h1 class="ds-auth__title">
        {{ t('comp.welcome.title') }}
      </h1>
      <p class="ds-auth__subtitle">
        {{ t('comp.welcome.intro') }}
      </p>

      <form class="ds-auth__form" @submit.prevent="onAccept">
        <div v-for="doc in pending" :key="doc.id" class="welcome__doc">
          <CCheckbox
            v-model="ticked[doc.id]"
            :label="`${t('auth.register.consentPrefix')} ${docName(doc)}`"
          />
          <CButton variant="link" type="button" @click="reading = doc">
            {{ t('comp.welcome.read') }}
          </CButton>
        </div>

        <CButton variant="primary" type="submit" :disabled="!allTicked" :loading="accepting">
          {{ t('comp.welcome.accept') }}
        </CButton>
      </form>
    </template>

    <div class="ds-auth__foot">
      <AuthLogoutLink />
    </div>

    <LegalDocModal
      :open="reading !== null"
      :title="reading ? docName(reading) : ''"
      :lang="docLang"
      :type="reading?.type ?? ''"
      @close="reading = null"
    />
  </AuthShell>
</template>

<style scoped>
/* One document: its tick, and the link that reads it. */
.welcome__doc {
  display: grid;
  justify-items: start;
  gap: var(--space-1);
}
</style>
