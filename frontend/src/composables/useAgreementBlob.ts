// =============================================================================
// AIVIS.ONE Frontend -- useAgreementBlob Composable
//                       (iter 2.5 R2 §5.5; replaces useCertificateBlob)
// =============================================================================
//
// Wrap an HTML-blob fetcher (fetchAgreementBlob or
// fetchOwnershipCertificateBlob) with automatic lifecycle hygiene. The
// fetcher returns the document as a Blob; this composable makes a URL of it with URL.createObjectURL, which pins the
// underlying blob in memory until URL.revokeObjectURL is called. Doing
// that by hand at every call-site is error-prone:
//   - a forgotten onUnmounted leaks for the whole SPA session (a
//     rendered agreement HTML is tens to hundreds of KB);
//   - a second load on the same composable instance leaks the previous
//     URL.
//
// This composable solves both:
//   - Each successful `load()` revokes the URL from the previous
//     `load()` before overwriting `blobUrl`.
//   - `onScopeDispose` revokes the final URL when the consuming
//     component unmounts (or the effect scope closes for any other
//     reason, e.g. `effectScope`-based isolation in a future dialog
//     wrapper).
//
// PARAMETERISED FETCHER (delta vs former useCertificateBlob).
//   The old composable hardcoded `fetchCertificateBlob` and accepted a
//   purchaseId. R2 §5.3 now exposes two document surfaces -- per-
//   Purchase agreement (id = purchaseId) and per-investor-company
//   ownership certificate (id = companyId) -- that share identical
//   blob-URL lifecycle semantics. To avoid two near-identical
//   composables, the fetcher is passed in:
//
//     const sheet = useAgreementBlob(
//       props.mode === 'ownership'
//         ? fetchOwnershipCertificateBlob
//         : fetchAgreementBlob,
//     )
//
//   The `load(id)` signature stays the same -- the composable does not
//   know or care whether `id` is a purchaseId or a companyId; that is
//   the caller's contract with its fetcher.
//
// USAGE:
//   const { blobUrl, html, loading, errored, load, clear } =
//     useAgreementBlob(fetchAgreementBlob)
//
//   await load(purchaseId)  // populates blobUrl and html, or flips errored
//   <iframe v-if="html" :srcdoc="html" sandbox="" />
//
//   `blobUrl` is the document as it came (the download link hands it over); `html` is
//   its text, which the sheet gives the theme's colours before it shows it, so the
//   document read in the frame follows the theme while the saved file stays as issued.
//
// ERROR MODEL.
//   load() mirrors the fetcher's throw shape: ApiResponseError /
//   ApiNetworkError / ApiTimeoutError on failure. The composable also
//   flips the local `errored` ref so templates can do `v-if="errored"`
//   without binding to the throw chain. Callers that need the error
//   object for a toast wrap load() in a try/catch.
//
//   429 / 500 mapping is the CALLER's job (R2 §5.3, §5.6 ERR-11-01) --
//   this composable surfaces the raw ApiResponseError.status so the
//   sheet can branch on it.
//
// EPOCH GUARD (carried from F4.4 B5-post).
//   `load()` is re-entrant: a sheet that watches `[open, id]` can call
//   it again while the previous fetch is still in flight (rapid row
//   taps, prop churn during transition, etc.). Without a guard:
//     - The losing URL would be written to blobUrl and then
//       immediately overwritten by the winner without revoke, leaking
//       the losing blob for the rest of the component's lifetime.
//     - `loading` would flip to false while the winning fetch is
//       still in flight (the loser's `finally` clears it early).
//     - `errored` would reflect the loser's outcome after the winner
//       already succeeded.
//   The fix is a monotonically-increasing epoch per composable
//   instance. Each `load()` captures its own epoch; only the latest
//   epoch is allowed to publish to blobUrl / errored / loading. A
//   superseded fetch that still resolves with a blob revokes that
//   blob on its own -- the caller never sees the URL.
//
// SANDBOX REMINDER.
//   The blob URL shares the page's origin once rendered in an iframe,
//   so consumers MUST set `sandbox=""` (or an allow-list stricter
//   than the default same-origin) when embedding it, and the same holds for the text
//   put in `srcdoc`. See TD-F11b in
//   AIVIS-Frontend.md. This composable does not enforce the
//   attribute -- Vue's template layer is the right place to lock it in.
// =============================================================================

import { onScopeDispose, ref } from 'vue'

/**
 * Fetcher signature accepted by useAgreementBlob. Both
 * fetchAgreementBlob (purchaseId) and fetchOwnershipCertificateBlob
 * (companyId) match it byte-for-byte; future document surfaces with
 * the same blob-URL contract can be plugged in here without changes
 * to this composable.
 */
export type BlobFetcher = (id: string) => Promise<Blob>

export function useAgreementBlob(fetcher: BlobFetcher) {
  const blobUrl = ref<string | null>(null)
  const html = ref<string>('')
  const loading = ref(false)
  const errored = ref(false)

  // Monotonic per-instance counter. Only the latest load is allowed
  // to publish state; superseded loads revoke their own fetched URL
  // (if it ever resolved) and silently drop the result.
  let epoch = 0

  /**
   * Fetch the document HTML for `id` and publish a fresh blob URL on
   * `blobUrl`. Revokes any previous URL held by this composable
   * instance before doing so -- a common pattern when the sheet
   * reopens on a different id without unmounting between.
   *
   * Rethrows the underlying error. `errored` flips to true for
   * template-driven error states; callers that also show a toast
   * should wrap the call in try/catch. A superseded call still
   * rethrows so the caller's try/catch chain is not silently broken,
   * but it will not flip `errored` -- that belongs to the winner.
   */
  async function load(id: string): Promise<void> {
    const mine = ++epoch
    loading.value = true
    errored.value = false
    // Revoke BEFORE the fetch so a crash during fetch still releases
    // the previous URL -- we're not going to render it again.
    if (blobUrl.value) {
      URL.revokeObjectURL(blobUrl.value)
      blobUrl.value = null
    }
    html.value = ''
    let fresh: Blob | null = null
    let text = ''
    try {
      fresh = await fetcher(id)
      text = await fresh.text()
    } catch (err) {
      if (mine === epoch) {
        errored.value = true
      }
      throw err
    } finally {
      if (mine === epoch) {
        loading.value = false
      }
    }
    if (mine !== epoch) {
      // Superseded -- another load() started after us. Nothing was made of
      // what we fetched (no URL exists yet); drop out without touching shared
      // state.
      return
    }
    if (!fresh) return
    blobUrl.value = URL.createObjectURL(fresh)
    html.value = text
  }

  /**
   * Manually revoke the current URL (e.g. when the sheet closes and
   * the blob is no longer needed before unmount). Idempotent.
   *
   * Also bumps the epoch so any in-flight `load()` that resolves
   * after `clear()` revokes its own blob and does not repopulate
   * blobUrl behind the caller's back.
   */
  function clear(): void {
    epoch += 1
    if (blobUrl.value) {
      URL.revokeObjectURL(blobUrl.value)
      blobUrl.value = null
    }
    html.value = ''
    errored.value = false
    loading.value = false
  }

  onScopeDispose(() => {
    if (blobUrl.value) {
      URL.revokeObjectURL(blobUrl.value)
      blobUrl.value = null
    }
  })

  return {
    blobUrl,
    html,
    loading,
    errored,
    load,
    clear,
  }
}
