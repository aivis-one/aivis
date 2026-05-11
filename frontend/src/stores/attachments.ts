// =============================================================================
// CBSHOME Frontend -- Attachments Store (iter 2.5 batch 4, R2 §7.1)
// =============================================================================
//
// Pinia store for the Investor `CompanyOverviewView` documents section
// (batch 6). Backs the auth-flow attachments endpoint that landed in
// iter 2.2 backend; the frontend simply did not call it until this
// iteration.
//
// SHAPE.
//   currentCompanyId  -- the company whose attachments are currently
//                        held in `items`; null when no view is mounted
//   items             -- AttachmentResponse[] for currentCompanyId
//   loading           -- true while the fetch is in flight
//   errored           -- last fetch failed; view shows retry
//
// SCOPE NOTE -- per-company, not paginated.
//   R2 §7.1 lists one company's documents in full; the backend
//   endpoint is a non-paginated GET. The view does L1 grouping +
//   client-side language filtering on top of the raw items list; the
//   store keeps the unfiltered array so multiple filter views (a
//   future language picker) read the same source of truth without
//   re-fetching.
//
//   Compare stores/portfolio.ts's per-company group (currentCompanyId
//   + currentDetail + currentPurchases): that store mixes a top-level
//   positions list AND a per-company detail with pagination, so it
//   carries TWO epoch counters. This store has ONE group (just the
//   per-company list), so ONE counter suffices.
//
// EPOCH GUARD (FP-17).
//   Every network-touching path bumps `fetchEpoch`. Resolves whose
//   epoch no longer matches the current counter are dropped. This
//   covers: rapid navigation between two CompanyOverview's, view
//   unmount mid-fetch, reset() during an in-flight fetch.
//
// IDEMPOTENCY OF setCompanyId.
//   setCompanyId(id) is NOT a no-op when id === currentCompanyId --
//   it re-fetches. Same convention as portfolioStore.setCompanyId.
//   The caller's trigger (typically onMounted) means "I want fresh
//   data", and detecting cache hits at this layer would require an
//   invalidation policy nobody currently needs. The view's Retry
//   button reuses setCompanyId for the same reason.
//
// CLEAR-ON-UNMOUNT.
//   The view calls clearCurrent() in onUnmounted. This bumps the
//   epoch and wipes items/loading/errored so navigating away mid-
//   fetch doesn't leave a stale spinner-and-companyId pair. NOT a
//   session-boundary clear -- that's reset() below.
//
// RESET POLICY (F5.1 B1 carried forward).
//   reset() bumps fetchEpoch FIRST so any in-flight resolve drops
//   silently, then clears every public ref. Wired into
//   stores/sessionReset.ts. User A's documents list cannot bleed
//   into user B's session in the same tab.
// =============================================================================

import { ref } from 'vue'
import { defineStore } from 'pinia'

import { listAttachments } from '@/api/attachments'
import type { AttachmentResponse } from '@/api/types'

export const useAttachmentsStore = defineStore('attachments', () => {
  const currentCompanyId = ref<string | null>(null)
  const items = ref<AttachmentResponse[]>([])
  const loading = ref<boolean>(false)
  const errored = ref<boolean>(false)

  // Shared epoch counter. See stores/transactions.ts header for the
  // why-not-a-ref rationale (closure scope = store lifetime).
  let fetchEpoch = 0

  /**
   * Select a company and load its attachments.
   *
   * Idempotent only in the trivial sense (same id still re-fetches);
   * matches portfolioStore.setCompanyId. The currentCompanyId switch
   * happens BEFORE the fetch so an early render of the consuming
   * view (e.g. a v-if="currentCompanyId === ..." section) sees the
   * right pairing even during the in-flight window.
   *
   * The previous company's items are wiped synchronously so the
   * consuming view never paints company A's documents under company
   * B's hero between navigation and resolve.
   */
  async function setCompanyId(id: string): Promise<void> {
    const epoch = ++fetchEpoch
    currentCompanyId.value = id
    items.value = []
    loading.value = true
    errored.value = false
    try {
      const resp = await listAttachments(id)
      if (epoch !== fetchEpoch) return
      items.value = resp
    } catch {
      if (epoch !== fetchEpoch) return
      errored.value = true
    } finally {
      if (epoch === fetchEpoch) {
        loading.value = false
      }
    }
  }

  /**
   * Clear per-company state when the view unmounts. Bumps fetchEpoch
   * so any in-flight fetch resolves to a no-op. NOT a session-
   * boundary reset -- session boundaries go through reset() below.
   */
  function clearCurrent(): void {
    ++fetchEpoch
    currentCompanyId.value = null
    items.value = []
    loading.value = false
    errored.value = false
  }

  /**
   * Full session reset. Identical body to clearCurrent in this
   * store -- there's only one group of state -- but kept as a
   * distinct method to (a) make the sessionReset.ts wiring read
   * symmetrically with the other stores' reset() and (b) preserve
   * the call-site semantic distinction (clearCurrent = view event,
   * reset = session event).
   */
  function reset(): void {
    ++fetchEpoch
    currentCompanyId.value = null
    items.value = []
    loading.value = false
    errored.value = false
  }

  return {
    currentCompanyId,
    items,
    loading,
    errored,
    setCompanyId,
    clearCurrent,
    reset,
  }
})
