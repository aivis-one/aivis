<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- InvestorSupportView (Ф-2)
// =============================================================================
//
// One conversation: feed + composer. Reached from the Support tile in
// InvestorMoreView -> /investor/support. No CHeader (InvestorShell
// renders it, same paradigm as every neighbour); a CBackLink above an
// inline <h1> since this is a detail screen reached from "More", not
// a tab-bar top level (contrast InvestorDocsView, which dropped its
// back-link when it was promoted to a tab).
//
// STATE IS THE STORE'S, EXCEPT ONE LOCAL ID.
//   `knownThreadId` is the only piece of state this component owns:
//   the store has no single "my thread id" field on its own (`thread`
//   is only populated by openThread(); `threads` is the list used
//   only to detect existence). This screen is the one place that
//   decides "which thread am I looking at" and holds it locally, per
//   the api/support.ts docs on threads.support.ts (Ф-1 -- api-slice
//   and store review).
//
// THE FOURTEEN-STATE MACHINE FROM THE GATE, COLLAPSED INTO FOUR
// COMPUTEDS (initLoading / initError / hasThread / showInvite) plus
// the store's own feedLoading/feedError/sending/threadError/sendError.
// Nothing here re-derives what the store already tracks; this file
// only composes it into what the template needs to branch on.
//
// STAKE A (gate): opening + first send is ONE button for the person,
// two store calls underneath. If openThread() succeeds and
// sendMessage() then fails, the screen does NOT fall back to the
// invite state -- `knownThreadId` is set the moment openThread()
// resolves, before sendMessage() is even attempted, so a retry after
// that failure calls sendMessage() alone. This is exactly the
// "thread exists, box has text, error shown" state named on the gate
// (state 10 in the plan) and it is reachable, not theoretical: it is
// what happens whenever comms answers the create call but the send
// call after it times out.
//
// STAKE C (gate): the reverse lives HERE, in `chronologicalMessages`,
// not in the store. The store hands back exactly what comms sent --
// see stores/support.ts's own header on why it never mutates that
// order -- and reversing a fresh array copy on read is the one place
// that decision was always meant to be undone.
//
// STAKE D (gate): a failed markRead is not surfaced at all. It is
// fired after every successful feed load and its result/error is
// left in the store (`support.markError`) for devtools, never read
// here. Read-receipt bookkeeping is not something the person can
// retry or is even aware they did -- showing it as a conversation
// error would teach them to distrust a message that DID go through.
//
// 404-ON-KNOWN-THREAD IS NOT TREATED AS UNREACHABLE (gate note).
//   comms logs support_thread_repointed for a real, if rare, case: a
//   rebuilt comms handing out a fresh thread id for the same user.
//   This screen does not special-case that 404 or silently re-open --
//   re-pointing the local pointer is the BACKEND's job (service.py
//   _remember_thread), and inventing a client-side recovery here
//   would be new, unordered logic on top of stake A's contract. A
//   404 here falls into the same generic error text as any other
//   failure of that action.
// =============================================================================

import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { RefreshCw } from 'lucide-vue-next'
import { CBackLink, CButton, CEmptyState, CLoader, CTextarea } from '@/components/ui'
import { safeNavigate } from '@/composables/safeNavigate'
import { useSupportStore } from '@/stores/support'
import { useAuthStore } from '@/stores/auth'
import type { SupportActionError } from '@/stores/support'
import type { SupportMessageResponse } from '@/api/support'

const { t } = useI18n()
const router = useRouter()
const support = useSupportStore()
const auth = useAuthStore()

// The one thread this screen is showing. null = no request yet.
const knownThreadId = ref<string | null>(null)
const composerText = ref('')

const myUserId = computed<string | null>(() => auth.user?.id ?? null)

const hasThread = computed<boolean>(() => knownThreadId.value !== null)

// Empty state covers BOTH "never opened a request" and "opened one,
// nothing landed in it yet" (state 5 on the gate plan -- reachable
// whenever openThread succeeded and the send after it did not). The
// short-circuit on !hasThread is what keeps this true before a
// thread exists without waiting on feed flags that were never set.
const showInvite = computed<boolean>(
  () =>
    !hasThread.value
    || (!support.messagesLoading
      && !support.messagesError
      && support.messages.length === 0),
)

// Store hands back comms' own order ("newest first"); this screen
// reads "oldest first". A fresh copy every time -- see stake C.
const chronologicalMessages = computed<SupportMessageResponse[]>(() =>
  [...support.messages].reverse(),
)

// Whichever of the two compound-action errors is live right now.
// Mutually exclusive in practice: threadError is only ever set while
// knownThreadId is still null (the open half of stake A), sendError
// only once it is no longer null.
const composerError = computed<SupportActionError | null>(
  () => support.threadError ?? support.sendError,
)

function isMine(message: SupportMessageResponse): boolean {
  return myUserId.value !== null && message.sender === myUserId.value
}

/**
 * 502/504 (comms unreachable) reads as "try later"; everything else
 * -- a 409 conflict, an unmapped 4xx, a network error -- reads as a
 * plain retry prompt. Applied uniformly to every error surface on
 * this screen (init / feed / send), not only the send action the
 * handoff named, so "comms is down" says the same thing everywhere
 * it shows up.
 */
function errorMessage(err: SupportActionError | null): string {
  if (!err) return ''
  if (err.status === 502 || err.status === 504) {
    return t('inv.support.errorUnavailable')
  }
  return t('inv.support.errorGeneric')
}

async function loadFeed(): Promise<void> {
  const id = knownThreadId.value
  if (id === null) return
  await support.fetchMessages(id)
  // Fire-and-forget: a failed mark-read stays in support.markError for
  // devtools only -- see stake D above.
  if (!support.messagesError) {
    void support.markRead(id)
  }
}

async function boot(): Promise<void> {
  await support.fetchThreads()
  if (support.threadsError) return
  const existing = support.threads[0]
  if (existing !== undefined) {
    knownThreadId.value = existing.id
    await loadFeed()
  }
}

async function handleSend(): Promise<void> {
  const text = composerText.value.trim()
  if (text === '' || support.sending) return

  if (knownThreadId.value === null) {
    await support.openThread()
    if (support.threadError) return // stays uncommitted -- box keeps its text
    knownThreadId.value = support.thread?.id ?? null
    if (knownThreadId.value === null) return // defensive; threadError would be set otherwise
  }

  await support.sendMessage(text)
  if (support.sendError) return // box keeps its text -- see stake A

  composerText.value = ''
  await loadFeed()
}

function retryInit(): void {
  void boot()
}

function retryFeed(): void {
  void loadFeed()
}

function goBack(): void {
  // Same history-aware pattern as CBackLink's other consumers
  // (InstallmentView etc.): prefer router.back() so More restores its
  // scroll for free, fall back to a push only for a deep-linked entry.
  if (window.history.state?.back) {
    router.back()
    return
  }
  void safeNavigate(
    router.push({ name: 'investor-more' }),
    '[InvestorSupportView] back',
  )
}

onMounted(() => {
  void boot()
})
</script>

<template>
  <div class="isup">
    <div class="isup__back-row">
      <CBackLink :label="t('inv.support.backLink')" @click="goBack" />
    </div>

    <header class="isup__header">
      <h1 class="isup__title">{{ t('inv.support.title') }}</h1>
    </header>

    <!-- INIT: determining whether a request already exists -->
    <div v-if="support.threadsLoading" class="isup__center">
      <CLoader :size="32" />
    </div>

    <!-- INIT error: never falls back to the invite -- a network -->
    <!-- failure must not look like "you have no history yet". -->
    <div v-else-if="support.threadsError" class="isup__center">
      <CEmptyState
        :title="t('inv.support.initErrorTitle')"
        :description="errorMessage(support.threadsError)"
      />
      <CButton variant="primary" inline @click="retryInit">
        {{ t('inv.support.initErrorRetry') }}
      </CButton>
    </div>

    <template v-else>
      <div class="isup__body">
        <div v-if="hasThread" class="isup__toolbar">
          <CButton
            variant="outline"
            size="sm"
            inline
            :disabled="support.messagesLoading"
            :aria-label="t('inv.support.refresh')"
            @click="retryFeed"
          >
            <RefreshCw :size="16" />
          </CButton>
        </div>

        <div v-if="support.messagesLoading" class="isup__center">
          <CLoader :size="24" />
        </div>

        <div v-else-if="support.messagesError" class="isup__center">
          <CEmptyState
            :title="t('inv.support.feedErrorTitle')"
            :description="errorMessage(support.messagesError)"
          />
          <CButton variant="outline" size="sm" inline @click="retryFeed">
            {{ t('inv.support.feedErrorRetry') }}
          </CButton>
        </div>

        <div v-else-if="showInvite" class="isup__center">
          <CEmptyState :title="t('inv.support.invite')" />
        </div>

        <div v-else class="isup__feed">
          <div
            v-for="message in chronologicalMessages"
            :key="message.id"
            class="isup__msg"
            :class="{ 'isup__msg--mine': isMine(message) }"
          >
            <span class="isup__msg-sender sr-only">
              {{ isMine(message) ? t('inv.support.sender.me') : t('inv.support.sender.operator') }}
            </span>
            <p class="isup__msg-body">{{ message.body }}</p>
          </div>
        </div>
      </div>

      <div class="isup__composer">
        <div v-if="composerError" class="isup__composer-error">
          {{ errorMessage(composerError) }}
        </div>
        <CTextarea
          v-model="composerText"
          :placeholder="t('inv.support.placeholder')"
          :disabled="support.sending"
          maxlength="4000"
          :rows="2"
          size="compact"
        />
        <CButton
          variant="primary"
          :loading="support.sending"
          :disabled="composerText.trim() === '' || support.sending"
          @click="handleSend"
        >
          {{ t('inv.support.send') }}
        </CButton>
      </div>
    </template>
  </div>
</template>

<style scoped>
.isup {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-4);
  /* Composer must stay reachable without the page itself scrolling
     under the shell chrome -- match InstallmentView's full-height
     detail-screen convention rather than InvestorEventsView's plain
     list flow. */
  min-height: 0;
  flex: 1;
}

.isup__back-row {
  display: flex;
}

.isup__header { display: flex; flex-direction: column; gap: var(--space-1); }
.isup__title {
  font-size: var(--fs-lg);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}

.isup__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  min-height: var(--center-md);
  padding: var(--space-5) var(--space-2);
  flex: 1;
}

.isup__body {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  flex: 1;
  min-height: 0;
}

.isup__toolbar {
  display: flex;
  justify-content: flex-end;
}

.isup__feed {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  overflow-y: auto;
  flex: 1;
  min-height: 0;
}

/* Bubble alignment via align-self, not left/right: a column flexbox's
   cross-axis start/end already follows the container's direction, so
   this mirrors correctly under [dir="rtl"] (ar.json) with no extra
   override -- same principle CTabBar's own RTL rule exists to
   preserve, applied here without needing a rule of its own. */
/* No design-system maxw token fits a chat bubble: --maxw-prose (680px)
   is a reading-column ceiling that would do nothing on a phone-width
   screen (same as CEmptyState's own use of it), and --maxw-form
   (360px) is semantically a form width, not a message width. A
   relative cap is the standard messenger convention and scales with
   whatever container this ends up in, mobile or desktop. */
.isup__msg {
  max-width: 85%;
  padding: var(--space-3);
  border-radius: var(--radius-md);
  background: var(--bg-subtle);
  align-self: flex-start;
}
.isup__msg--mine {
  align-self: flex-end;
  background: var(--primary);
}
.isup__msg--mine .isup__msg-body { color: var(--on-primary); }

.isup__msg-body {
  margin: 0;
  font-size: var(--fs-sm);
  color: var(--text-primary);
  white-space: pre-wrap;
  overflow-wrap: break-word;
}

/* Visually hidden but still in the accessibility tree -- same
   technique as CButton.vue's .c-btn__label--sr, kept local here
   since that class is private to CButton's own scoped style. */
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
  border: 0;
}

.isup__composer {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding-top: var(--space-2);
  border-top: 1px solid var(--border-default);
}

.isup__composer-error {
  font-size: var(--fs-sm);
  color: var(--danger);
}
</style>
