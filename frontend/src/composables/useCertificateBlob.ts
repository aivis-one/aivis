// =============================================================================
// CBSHOME Frontend -- useCertificateBlob Composable (Phase F4.4 B3)
// =============================================================================
//
// Wrap `fetchCertificateBlob` with automatic lifecycle hygiene. The
// API call returns a URL from URL.createObjectURL, which pins the
// underlying blob in memory until URL.revokeObjectURL is called.
// Doing that by hand at every call-site is error-prone: a forgotten
// onUnmounted leaks for the whole SPA session (a certificate is a
// PDF-sized HTML, tens to hundreds of KB), and a second load on the
// same composable instance leaks the previous URL.
//
// This composable solves both:
//   - Each successful `load()` revokes the URL from the previous
//     `load()` before overwriting `blobUrl`.
//   - `onScopeDispose` revokes the final URL when the consuming
//     component unmounts (or the effect scope closes for any other
//     reason, e.g. `effectScope`-based isolation in a future dialog
//     wrapper).
//
// USAGE:
//   const { blobUrl, loading, errored, load, clear } =
//     useCertificateBlob()
//
//   await load(purchaseId)  // populates blobUrl, or flips errored
//   <iframe v-if="blobUrl" :src="blobUrl" sandbox="" />
//
// ERROR MODEL.
//   load() mirrors fetchCertificateBlob: it throws ApiResponseError
//   / ApiNetworkError / ApiTimeoutError on failure. The composable
//   also flips the local `errored` ref to true so templates can do
//   `v-if="errored"` without binding to the throw chain. Callers
//   that need the error object for a toast wrap load() in a try/catch.
//
// SANDBOX REMINDER.
//   The blob URL shares the page's origin once rendered in an iframe,
//   so consumers MUST set `sandbox=""` (or an allow-list stricter
//   than the default same-origin) when embedding it. See TD-F11b.
//   This composable does not enforce the attribute -- Vue's template
//   layer is the right place to lock it in.
// =============================================================================

import { onScopeDispose, ref } from 'vue'

import { fetchCertificateBlob } from '@/api/certificates'

export function useCertificateBlob() {
  const blobUrl = ref<string | null>(null)
  const loading = ref(false)
  const errored = ref(false)

  /**
   * Fetch the certificate HTML for `purchaseId` and publish a fresh
   * blob URL on `blobUrl`. Revokes any previous URL held by this
   * composable instance before doing so -- a common pattern when the
   * sheet reopens on a different purchase without unmounting between.
   *
   * Rethrows the underlying error. `errored` flips to true for
   * template-driven error states; callers that also show a toast
   * should wrap the call in try/catch.
   */
  async function load(purchaseId: string): Promise<void> {
    loading.value = true
    errored.value = false
    // Revoke BEFORE the fetch so a crash during fetch still releases
    // the previous URL -- we're not going to render it again.
    if (blobUrl.value) {
      URL.revokeObjectURL(blobUrl.value)
      blobUrl.value = null
    }
    try {
      blobUrl.value = await fetchCertificateBlob(purchaseId)
    } catch (err) {
      errored.value = true
      throw err
    } finally {
      loading.value = false
    }
  }

  /**
   * Manually revoke the current URL (e.g. when the sheet closes and
   * the blob is no longer needed before unmount). Idempotent.
   */
  function clear(): void {
    if (blobUrl.value) {
      URL.revokeObjectURL(blobUrl.value)
      blobUrl.value = null
    }
    errored.value = false
  }

  onScopeDispose(() => {
    if (blobUrl.value) {
      URL.revokeObjectURL(blobUrl.value)
      blobUrl.value = null
    }
  })

  return {
    blobUrl,
    loading,
    errored,
    load,
    clear,
  }
}
