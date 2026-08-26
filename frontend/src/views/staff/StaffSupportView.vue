<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- StaffSupportView (Ф-3)
// =============================================================================
//
// One route (/staff/support): the queue by default, a conversation
// panel in place of it once a card is tapped. No child route for a
// single thread -- see STAKE A below for why that is deliberate, not
// a shortcut.
//
// Reached from a nav-item in StaffMoreView, same tier as
// StaffAgentAppsView / StaffAvatarView (both outside STAFF_TABS).
// Neither of those has a CBackLink or an inline <h1> -- 14 of 15
// screens in this cabinet skip both; the one exception
// (StaffCompanyDetailView) is a real routed detail entity with tabs.
// This screen follows the dominant convention: no page title, a
// short one-line hint instead (matches StaffAgentAppsView's
// `.staff-apps__hint`).
//
// STAKE A (gate): one route, not a routed thread id.
//   The new GET .../messages endpoint is gated ONLY by "does this
//   thread exist" (_require_known_thread) -- NOT by whether the
//   caller's own queue would ever have shown it. list_operator_threads
//   filters visibility server-side; the read endpoint does not. If a
//   thread id were reachable as a route param, a plain operator could
//   type a colleague's claimed thread's id into the URL bar and read
//   a conversation their own queue never surfaced. Keeping the
//   selection as component-local state driven only by rows already
//   present in `support.queue` (itself already visibility-filtered)
//   closes that door without adding a check the backend doesn't
//   already need for its own reasons. This is a narrower answer than
//   the handoff's "без нового вида в нижней навигации" alone requires
//   -- named here because it wasn't asked for, it was found.
//
// STAKE B (gate): a COPY of Ф-2's bubbles/composer, not a shared
//   component. See the cross-reference comment in
//   views/investor/InvestorSupportView.vue's own header. Cost of
//   extracting was named and rejected: it would have meant editing an
//   already-shipped screen for one that did not exist yet, to save
//   two small blocks that differ in submit logic and in how "which
//   side" is computed anyway.
//
// STAKE C (gate): side is computed from `message.sender ===
//   selectedThread.client`, never from identity. comms' own message
//   body carries only `sender` (a bare uuid, no role) -- verified by
//   re-reading comms' _message_out serializer -- so a message from a
//   PREVIOUS operator on a transferred thread lands on the same
//   (right) side as one from the current viewer, unlabelled by name.
//   Accepted price for a proof-of-concept tool; T-75 (names instead
//   of uuids) is the registered fix for showing WHICH operator wrote
//   it, not for which SIDE it is on -- that question is answered
//   correctly already, by the same rule comms itself uses in
//   notify_new_message.
//
// STATUS ACTIONS ARE NOT GATED ON "MINE" (found while re-reading
//   service.py for this same question). comms lets ANY active
//   operator change ANY section thread's status, claimed by them or
//   not -- service.py documents this as accepted, not a gap. This
//   view narrows it anyway: status controls render on ALREADY-CLAIMED
//   rows (mine or a colleague's, the latter visible to a supervisor
//   only), never on a still-unclaimed pool row. That narrowing is
//   this screen's own choice, not a backend limit -- closing a
//   request nobody has even looked at yet has no described use case
//   here, so it isn't built, but it is not being called impossible
//   either.
//
// "CLAIMED, QUEUE NOT YET REFRESHED" (gate requirement).
//   claimThread() mutates the SAME row object in `support.queue` in
//   place (store's _replaceQueueRow) -- it does not remove/reinsert
//   it and does not trigger a fetchQueue(). The three group lists
//   below (poolRows/mineRows/foreignRows) are plain `computed`
//   filters over that one array, so the instant the claim resolves,
//   the row reclassifies from "unclaimed" to "mine" in the same
//   render -- no network round-trip needed to see it move. The one
//   thing that does NOT update until a real fetchQueue(): `unread`
//   (claim's response never carries it -- store preserves whatever
//   the row had) and the row's position in the server's own
//   recency order. Neither reads as loss: an unclaimed row never
//   carried `unread` to begin with, so the absence continues exactly
//   as it was: absent means "not applicable", never a lied-about
//   zero.
// =============================================================================

import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { RefreshCw } from 'lucide-vue-next'
import { CBackLink, CButton, CEmptyState, CLoader, CTextarea } from '@/components/ui'
import { useSupportStore } from '@/stores/support'
import { useAuthStore } from '@/stores/auth'
import type { SupportActionError } from '@/stores/support'
import type { SupportMessageResponse, SupportOperatorThreadRow } from '@/api/support'

const { t } = useI18n()
const support = useSupportStore()
const auth = useAuthStore()

const myOperatorId = computed<string | null>(() => auth.user?.id ?? null)

// -- Queue --------------------------------------------------------------

const poolRows = computed<SupportOperatorThreadRow[]>(() =>
  support.queue.filter((row) => row.assignee === null),
)
const mineRows = computed<SupportOperatorThreadRow[]>(() =>
  support.queue.filter((row) => row.assignee === myOperatorId.value),
)
// Non-empty only for a supervisor: a plain operator's own queue never
// contains a colleague's claimed thread at all (comms' own visibility
// filter), so this group is naturally empty for everyone else.
const foreignRows = computed<SupportOperatorThreadRow[]>(() =>
  support.queue.filter((row) => row.assignee !== null && row.assignee !== myOperatorId.value),
)

function retryQueue(): void {
  void support.fetchQueue()
}

async function handleClaim(threadId: string): Promise<void> {
  await support.claimThread(threadId)
}

// -- Selection: which conversation panel is open, if any ----------------

const openThreadId = ref<string | null>(null)

// Derived LIVE from the queue array, not a separate fetched copy --
// see stake A header: the moment claimThread() updates a row, this
// picks up the change for free, in the same render.
const selectedThread = computed<SupportOperatorThreadRow | null>(
  () => support.queue.find((row) => row.id === openThreadId.value) ?? null,
)

const isMine = computed<boolean>(
  () => selectedThread.value !== null && selectedThread.value.assignee === myOperatorId.value,
)
const isPool = computed<boolean>(
  () => selectedThread.value !== null && selectedThread.value.assignee === null,
)
const isForeign = computed<boolean>(
  () =>
    selectedThread.value !== null &&
    selectedThread.value.assignee !== null &&
    selectedThread.value.assignee !== myOperatorId.value,
)

function openThread(threadId: string): void {
  openThreadId.value = threadId
  void support.fetchStaffMessages(threadId)
}

function closeThread(): void {
  openThreadId.value = null
}

function retryFeed(): void {
  if (openThreadId.value !== null) {
    void support.fetchStaffMessages(openThreadId.value)
  }
}

// Store hands back comms' own order ("newest first"); read "oldest
// first" here -- same rule as Ф-2, re-applied rather than shared
// (stake B).
const chronologicalMessages = computed<SupportMessageResponse[]>(() =>
  [...support.staffMessages].reverse(),
)

// -- Who is asking (T-75) -----------------------------------------------
//
// TWO IDENTIFIERS ON THIS SCREEN, and they are not interchangeable. The
// THREAD id is what the operator quotes to a colleague or looks up in
// comms, and it keeps its place. The CLIENT id identifies the person and
// was never on screen at all -- it appears now, but only underneath the
// name, and only when there is no name to show.
//
// The join rule is StaffUsersView.fullName's, deliberately: same section
// of the product, same way of rendering a person. It differs in the
// fallback only, because "—" tells an operator nothing they can act on
// whereas an email or a uuid identifies the person they are answering.
function clientName(row: SupportOperatorThreadRow): string {
  const parts = [row.client_profile?.first_name, row.client_profile?.last_name].filter(Boolean)
  if (parts.length > 0) return parts.join(' ')
  return row.client_profile?.email ?? row.client
}

// True when the line above is already the client's identifier, so the
// secondary line would repeat it.
function clientNameIsIdentifier(row: SupportOperatorThreadRow): boolean {
  return clientName(row) === row.client
}

// STAKE C: side by comparison with the thread's fixed client id, never
// by identity -- see header.
function isRight(message: SupportMessageResponse): boolean {
  return selectedThread.value !== null && message.sender !== selectedThread.value.client
}

function errorMessage(err: SupportActionError | null): string {
  if (!err) return ''
  if (err.status === 502 || err.status === 504) {
    return t('staff.support.errorUnavailable')
  }
  return t('staff.support.errorGeneric')
}

// -- Reply ----------------------------------------------------------------

const composerText = ref('')

async function handleSend(): Promise<void> {
  const id = openThreadId.value
  const text = composerText.value.trim()
  if (id === null || text === '' || support.replying[id]) return

  await support.replyToThread(id, text)
  if (support.replyErrors[id]) return

  composerText.value = ''
  void support.fetchStaffMessages(id)
}

// -- Status -----------------------------------------------------------

// Only rendered on an ALREADY-CLAIMED thread (mine or a colleague's) --
// see header on why a still-unclaimed pool row gets none.
const canChangeStatus = computed<boolean>(
  () => selectedThread.value !== null && selectedThread.value.assignee !== null,
)

async function handleResolve(): Promise<void> {
  const id = openThreadId.value
  if (id === null) return
  await support.setThreadStatus(id, 'resolved')
}

async function handleClose(): Promise<void> {
  const id = openThreadId.value
  if (id === null) return
  await support.setThreadStatus(id, 'closed')
}

onMounted(() => {
  void support.fetchQueue()
})
</script>

<template>
  <div class="ssup">
    <!-- ============================== QUEUE ============================== -->
    <template v-if="openThreadId === null">
      <p class="ssup__hint">
        {{ t('staff.support.hint') }}
      </p>

      <div class="ssup__toolbar">
        <CButton
          variant="outline"
          size="sm"
          inline
          :disabled="support.queueLoading"
          :aria-label="t('staff.support.refresh')"
          @click="retryQueue"
        >
          <RefreshCw :size="16" />
        </CButton>
      </div>

      <div v-if="support.queueLoading && !support.queueLoaded" class="ssup__center">
        <CLoader :size="32" />
      </div>

      <div v-else-if="support.queueError" class="ssup__center">
        <CEmptyState :description="errorMessage(support.queueError)" />
        <CButton variant="primary" inline @click="retryQueue">
          {{ t('common.retry') }}
        </CButton>
      </div>

      <div v-else-if="support.queue.length === 0" class="ssup__center">
        <CEmptyState :title="t('staff.support.empty')" />
      </div>

      <div v-else class="ssup__groups">
        <section v-if="poolRows.length > 0" class="ssup__group">
          <h2 class="ssup__group-title">
            {{ t('staff.support.groupPool') }}
          </h2>
          <!-- Pool rows never carry an unread count, and that is a
               property of comms rather than a gap on this screen: the
               count is attached only to threads the operator takes part
               in, and nobody takes part in an unclaimed one. Said on
               screen because its absence is otherwise read as a bug. -->
          <p class="ssup__group-note">{{ t('staff.support.poolNoUnread') }}</p>
          <div
            v-for="row in poolRows"
            :key="row.id"
            class="ssup__row"
            role="button"
            tabindex="0"
            @click="openThread(row.id)"
            @keyup.enter="openThread(row.id)"
            @keyup.space.prevent="openThread(row.id)"
          >
            <div class="ssup__row-body">
              <span class="ssup__row-client">{{ clientName(row) }}</span>
              <span class="ssup__row-id">{{ row.id.slice(0, 8) }}</span>
              <span v-if="row.last_message_at" class="ssup__row-time">
                {{ new Date(row.last_message_at).toLocaleString() }}
              </span>
            </div>
            <div v-if="support.claimErrors[row.id]" class="ssup__row-error">
              {{
                support.claimErrors[row.id]?.status === 409
                  ? t('staff.support.claimConflict')
                  : errorMessage(support.claimErrors[row.id])
              }}
            </div>
            <CButton
              variant="primary"
              size="sm"
              inline
              :loading="support.claiming[row.id]"
              :disabled="support.claiming[row.id]"
              @click.stop="handleClaim(row.id)"
            >
              {{ t('staff.support.claim') }}
            </CButton>
          </div>
        </section>

        <section v-if="mineRows.length > 0" class="ssup__group">
          <h2 class="ssup__group-title">
            {{ t('staff.support.groupMine') }}
          </h2>
          <div
            v-for="row in mineRows"
            :key="row.id"
            class="ssup__row"
            role="button"
            tabindex="0"
            @click="openThread(row.id)"
            @keyup.enter="openThread(row.id)"
            @keyup.space.prevent="openThread(row.id)"
          >
            <div class="ssup__row-body">
              <span class="ssup__row-client">{{ clientName(row) }}</span>
              <span class="ssup__row-id">{{ row.id.slice(0, 8) }}</span>
              <span
                v-if="typeof row.unread === 'number' && row.unread > 0"
                class="ssup__row-unread"
              >
                {{ row.unread }}
              </span>
            </div>
          </div>
        </section>

        <section v-if="foreignRows.length > 0" class="ssup__group">
          <h2 class="ssup__group-title">
            {{ t('staff.support.groupForeign') }}
          </h2>
          <div
            v-for="row in foreignRows"
            :key="row.id"
            class="ssup__row"
            role="button"
            tabindex="0"
            @click="openThread(row.id)"
            @keyup.enter="openThread(row.id)"
            @keyup.space.prevent="openThread(row.id)"
          >
            <div class="ssup__row-body">
              <span class="ssup__row-client">{{ clientName(row) }}</span>
              <span class="ssup__row-id">{{ row.id.slice(0, 8) }}</span>
            </div>
          </div>
        </section>
      </div>
    </template>

    <!-- =========================== CONVERSATION =========================== -->
    <template v-else>
      <div class="ssup__back-row">
        <CBackLink :label="t('staff.support.backToQueue')" @click="closeThread" />
      </div>

      <div v-if="selectedThread === null" class="ssup__center">
        <!-- The row left the queue mid-view (a colleague's claim
             changed visibility, or a refresh dropped it). Reading is
             still allowed by the backend, but this screen has nothing
             left in `support.queue` to gate actions against, so it
             sends the person back rather than guess. -->
        <CEmptyState :title="t('staff.support.empty')" />
      </div>

      <template v-else>
        <div class="ssup__panel-head">
          <span class="ssup__panel-client">{{ clientName(selectedThread) }}</span>
          <span class="ssup__panel-ids">
            <span v-if="!clientNameIsIdentifier(selectedThread)" class="ssup__panel-id">
              {{ selectedThread.client }}
            </span>
            <span class="ssup__panel-id">
              {{ t('staff.support.threadId', { id: selectedThread.id.slice(0, 8) }) }}
            </span>
          </span>
        </div>

        <div v-if="isMine || isForeign" class="ssup__status-row">
          <CButton
            v-if="canChangeStatus"
            variant="outline"
            size="sm"
            inline
            :loading="support.changingStatus[selectedThread.id]"
            :disabled="support.changingStatus[selectedThread.id]"
            @click="handleResolve"
          >
            {{ t('staff.support.statusResolve') }}
          </CButton>
          <CButton
            v-if="canChangeStatus"
            variant="outline"
            size="sm"
            inline
            :loading="support.changingStatus[selectedThread.id]"
            :disabled="support.changingStatus[selectedThread.id]"
            @click="handleClose"
          >
            {{ t('staff.support.statusClose') }}
          </CButton>
          <div v-if="support.statusErrors[selectedThread.id]" class="ssup__row-error">
            {{ errorMessage(support.statusErrors[selectedThread.id]) }}
          </div>
        </div>

        <div v-if="isPool" class="ssup__claim-row">
          <span class="ssup__hint">{{ t('staff.support.readOnlyHint') }}</span>
          <CButton
            variant="primary"
            size="sm"
            inline
            :loading="support.claiming[selectedThread.id]"
            :disabled="support.claiming[selectedThread.id]"
            @click="handleClaim(selectedThread.id)"
          >
            {{ t('staff.support.claim') }}
          </CButton>
          <div v-if="support.claimErrors[selectedThread.id]" class="ssup__row-error">
            {{
              support.claimErrors[selectedThread.id]?.status === 409
                ? t('staff.support.claimConflict')
                : errorMessage(support.claimErrors[selectedThread.id])
            }}
          </div>
        </div>

        <p v-if="isForeign" class="ssup__hint">
          {{ t('staff.support.foreignHint') }}
        </p>

        <div class="ssup__body">
          <div v-if="support.staffMessagesLoading" class="ssup__center">
            <CLoader :size="24" />
          </div>

          <div v-else-if="support.staffMessagesError" class="ssup__center">
            <CEmptyState
              :title="t('staff.support.feedErrorTitle')"
              :description="errorMessage(support.staffMessagesError)"
            />
            <CButton variant="outline" size="sm" inline @click="retryFeed">
              {{ t('common.retry') }}
            </CButton>
          </div>

          <div v-else-if="chronologicalMessages.length === 0" class="ssup__center">
            <CEmptyState :title="t('staff.support.empty')" />
          </div>

          <div v-else class="ssup__feed">
            <div
              v-for="message in chronologicalMessages"
              :key="message.id"
              class="ssup__msg"
              :class="{ 'ssup__msg--right': isRight(message) }"
            >
              <span class="ssup__msg-sender sr-only">
                {{
                  isRight(message)
                    ? t('staff.support.sender.operator')
                    : t('staff.support.sender.client')
                }}
              </span>
              <p class="ssup__msg-body">
                {{ message.body }}
              </p>
            </div>
          </div>
        </div>

        <div v-if="isMine" class="ssup__composer">
          <div v-if="support.replyErrors[selectedThread.id]" class="ssup__composer-error">
            {{
              support.replyErrors[selectedThread.id]?.status === 409
                ? t('staff.support.readOnlyHint')
                : errorMessage(support.replyErrors[selectedThread.id])
            }}
          </div>
          <CTextarea
            v-model="composerText"
            :placeholder="t('staff.support.placeholder')"
            :disabled="support.replying[selectedThread.id]"
            maxlength="4000"
            :rows="2"
            size="compact"
          />
          <CButton
            variant="primary"
            :loading="support.replying[selectedThread.id]"
            :disabled="composerText.trim() === '' || support.replying[selectedThread.id]"
            @click="handleSend"
          >
            {{ t('staff.support.send') }}
          </CButton>
        </div>
      </template>
    </template>
  </div>
</template>

<style scoped>
.ssup {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-4);
  min-height: 0;
  flex: 1;
}

.ssup__hint {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  margin: 0;
}

.ssup__toolbar {
  display: flex;
  justify-content: flex-end;
}

.ssup__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  min-height: var(--center-md);
  padding: var(--space-5) var(--space-2);
  flex: 1;
}

.ssup__groups {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}
.ssup__group {
  display: flex;
  flex-direction: column;
}
.ssup__group-title {
  font-size: var(--fs-xs);
  font-weight: 700;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin: 0 0 var(--space-2);
}

.ssup__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-3) 0;
  border-bottom: 1px solid var(--border-default);
  cursor: pointer;
}
.ssup__row-body {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
}
.ssup__group-note {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
  margin: 0 0 var(--space-2);
}
.ssup__row-client {
  font-size: var(--fs-sm);
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
/* Demoted from primary to tertiary by T-75: the name above is what the
   operator reads, this is what they quote. */
.ssup__row-id {
  font-family: var(--font-mono);
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
}
.ssup__panel-head {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  padding-bottom: var(--space-3);
  border-bottom: 1px solid var(--border-default);
  min-width: 0;
}
.ssup__panel-client {
  font-size: var(--fs-md);
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ssup__panel-ids {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}
.ssup__panel-id {
  font-family: var(--font-mono);
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
}
.ssup__row-time {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
}
.ssup__row-unread {
  font-size: var(--fs-xs);
  font-weight: 700;
  color: var(--on-primary);
  background: var(--primary);
  border-radius: var(--radius-pill);
  padding: 0 var(--space-2);
  min-width: 20px;
  text-align: center;
}
.ssup__row-error {
  font-size: var(--fs-xs);
  color: var(--danger);
}

.ssup__back-row {
  display: flex;
}

.ssup__status-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.ssup__claim-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.ssup__body {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  flex: 1;
  min-height: 0;
}

.ssup__feed {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  overflow-y: auto;
  flex: 1;
  min-height: 0;
}

/* Same alignment technique as InvestorSupportView's copy (stake B):
   align-self on a column flexbox mirrors correctly under [dir="rtl"]
   with no extra override needed. */
.ssup__msg {
  max-width: 85%;
  padding: var(--space-3);
  border-radius: var(--radius-md);
  background: var(--bg-subtle);
  align-self: flex-start;
}
.ssup__msg--right {
  align-self: flex-end;
  background: var(--primary);
}
.ssup__msg--right .ssup__msg-body {
  color: var(--on-primary);
}

.ssup__msg-body {
  margin: 0;
  font-size: var(--fs-sm);
  color: var(--text-primary);
  white-space: pre-wrap;
  overflow-wrap: break-word;
}

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

.ssup__composer {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding-top: var(--space-2);
  border-top: 1px solid var(--border-default);
}

.ssup__composer-error {
  font-size: var(--fs-sm);
  color: var(--danger);
}
</style>
