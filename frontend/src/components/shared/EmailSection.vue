<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- EmailSection
// =============================================================================
//
// The e-mail of the account, in the settings. A person who signed in through
// Telegram has none; identity verification starts from a CONFIRMED e-mail, so
// this is where one is added and confirmed:
//
//   1. no e-mail -> a field and "Send the code" (POST /users/me/email)
//   2. the code  -> six digits from the letter (POST /auth/verify-email),
//                   with "Send again" (POST /auth/verify-email/resend)
//   3. confirmed -> the address is shown
//
// An account that has an address already shows it, with "Confirm" only when the
// settings were opened to confirm it (`confirm` prop: the verification screen
// sends a person here with the address still unconfirmed).
// =============================================================================

import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { CButton, CInput } from '@/components/ui'
import { ApiResponseError } from '@/api/client'
import { attachEmail, confirmEmailCode, resendEmailCode } from '@/api/users'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/composables/useToast'

const props = defineProps<{ confirm?: boolean }>()

const { t } = useI18n()
const authStore = useAuthStore()
const { showToast } = useToast()

const address = computed(() => authStore.user?.email ?? '')

const emailInput = ref('')
const codeInput = ref('')
const awaitingCode = ref(props.confirm === true)
const busy = ref(false)
const error = ref('')

watch(
  () => props.confirm,
  (v) => {
    if (v) awaitingCode.value = true
  },
)

function messageFor(err: unknown): string {
  if (err instanceof ApiResponseError) {
    if (err.code === 'email_taken') return t('inv.settings.email.taken')
    if (err.code === 'email_already_set') return t('inv.settings.email.alreadySet')
    if (err.status === 400) return t('inv.settings.email.wrongCode')
  }
  return t('inv.settings.email.failed')
}

async function sendCode(): Promise<void> {
  const value = emailInput.value.trim()
  if (!value || busy.value) return
  busy.value = true
  error.value = ''
  try {
    await attachEmail(value)
    await authStore.fetchMe()
    awaitingCode.value = true
    showToast(t('inv.settings.email.sent'), 'success')
  } catch (err) {
    error.value = messageFor(err)
  } finally {
    busy.value = false
  }
}

async function confirmCode(): Promise<void> {
  const value = codeInput.value.trim()
  if (value.length !== 6 || busy.value) return
  busy.value = true
  error.value = ''
  try {
    await confirmEmailCode(value)
    await authStore.fetchMe()
    awaitingCode.value = false
    codeInput.value = ''
    showToast(t('inv.settings.email.confirmed'), 'success')
  } catch (err) {
    error.value = messageFor(err)
  } finally {
    busy.value = false
  }
}

async function sendAgain(): Promise<void> {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try {
    await resendEmailCode()
    showToast(t('inv.settings.email.sent'), 'success')
  } catch (err) {
    error.value = messageFor(err)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div v-if="awaitingCode || !address" class="em">
    <div class="em__title">
      {{ t('inv.settings.email.title') }}
    </div>

    <!-- The code step -->
    <template v-if="awaitingCode">
      <p class="em__hint">
        {{ t('inv.settings.email.codeHint', { email: address }) }}
      </p>
      <CInput
        v-model="codeInput"
        :label="t('inv.settings.email.codeLabel')"
        inputmode="numeric"
        maxlength="6"
        autocomplete="one-time-code"
        :error="error"
        @keydown.enter="confirmCode"
      />
      <div class="em__actions">
        <CButton variant="outline" size="sm" :disabled="busy" @click="sendAgain">
          {{ t('inv.settings.email.sendAgain') }}
        </CButton>
        <CButton
          variant="primary"
          size="sm"
          :loading="busy"
          :disabled="busy || codeInput.trim().length !== 6"
          @click="confirmCode"
        >
          {{ t('inv.settings.email.confirm') }}
        </CButton>
      </div>
    </template>

    <!-- No e-mail yet -->
    <template v-else-if="!address">
      <p class="em__hint">
        {{ t('inv.settings.email.needed') }}
      </p>
      <CInput
        v-model="emailInput"
        :label="t('inv.settings.email.label')"
        type="email"
        autocomplete="email"
        placeholder="name@example.com"
        :error="error"
        @keydown.enter="sendCode"
      />
      <div class="em__actions">
        <CButton
          variant="primary"
          size="sm"
          :loading="busy"
          :disabled="busy || !emailInput.trim()"
          @click="sendCode"
        >
          {{ t('inv.settings.email.sendCode') }}
        </CButton>
      </div>
    </template>
  </div>
</template>

<style scoped>
.em {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-4);
}

.em__title {
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--text-primary);
}

.em__hint {
  margin: 0;
  font-size: var(--fs-xs);
  line-height: 1.5;
  color: var(--text-secondary);
}

.em__actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-2);
}
</style>
