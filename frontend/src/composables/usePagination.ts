// =============================================================================
// CBSHOME Frontend -- useInfiniteScroll Composable (Phase F4.1 + F4.4 B1-post)
// =============================================================================
//
// Attach an IntersectionObserver to a sentinel element. When the
// sentinel enters the viewport AND there is more data to load, fire
// loadMore(). Used by the Investor storefront grid and paginated
// lists (transactions, portfolio purchases).
//
// USAGE:
//   import { useInfiniteScroll } from '@/composables/usePagination'
//
//   const sentinelRef = ref<HTMLElement | null>(null)
//   useInfiniteScroll(sentinelRef, hasMore, loadMore)                 // 3-arg
//   useInfiniteScroll(sentinelRef, hasMore, loadMore, loadMoreErrored) // 4-arg
//   ...
//   <div ref="sentinelRef" />  <!-- placed at the end of the grid -->
//
// WHY INTERSECTIONOBSERVER, NOT scroll EVENTS:
//   - native, throttled by the browser
//   - no layout thrash from getBoundingClientRect
//   - works regardless of which ancestor is the scroll container
//
// ROOT MARGIN:
//   '200px 0px' -- fire 200px BEFORE the sentinel crosses the viewport
//   bottom, so the next page is loading by the time the user actually
//   reaches it.
//
// PAUSE PARAMETER (F4.4 B1-post):
//   The optional fourth argument is a Ref<boolean> that, when true,
//   suppresses the loadMore() call even if hasMore is true and the
//   sentinel is in view. The intended use is a retry-storm brake:
//   when loadMore() fails on a transient network/backend error, the
//   consuming store sets an `loadMoreErrored` ref to true, and this
//   composable stops firing until the user explicitly resets it via
//   a Retry UI affordance. Without this brake, an IntersectionObserver
//   whose sentinel stays in view will re-fire on every scroll oscillation
//   and stampede the backend (or trigger 429 rate limits) with no user
//   feedback.
//
//   Back-compat: legacy 3-arg call-sites (MarketView, BalanceView)
//   keep the old "just fire on intersect + hasMore" behaviour -- they
//   don't pay attention to errors, and their consumers have no pause
//   state to feed in.
// =============================================================================

import { onMounted, onUnmounted, watch, type Ref } from 'vue'

export function useInfiniteScroll(
  sentinelRef: Ref<HTMLElement | null>,
  hasMore: Ref<boolean>,
  loadMore: () => void | Promise<void>,
  paused?: Ref<boolean>,
): void {
  let observer: IntersectionObserver | null = null

  function attach(target: HTMLElement): void {
    observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          // Three-way gate: needs-more, not-paused, actually-visible.
          // `paused` is optional -- when omitted it's treated as never
          // paused, matching the legacy 3-arg contract.
          if (
            entry.isIntersecting &&
            hasMore.value &&
            !(paused?.value ?? false)
          ) {
            void loadMore()
          }
        }
      },
      { rootMargin: '200px 0px' },
    )
    observer.observe(target)
  }

  function detach(): void {
    if (observer) {
      observer.disconnect()
      observer = null
    }
  }

  onMounted(() => {
    if (sentinelRef.value) attach(sentinelRef.value)
  })

  // Re-wire observer if the sentinel element is mounted after the
  // composable runs (e.g. a v-if chain shows the grid after a loading
  // spinner).
  watch(sentinelRef, (el) => {
    detach()
    if (el) attach(el)
  })

  // When the consumer clears the pause (user tapped Retry), the
  // sentinel may already be on-screen without a fresh intersect
  // event to trigger loadMore. Observe `paused` going from true
  // to false and re-check the sentinel's current visibility; if it
  // is intersecting right now, fire once.
  if (paused) {
    watch(paused, (next, prev) => {
      if (!next && prev) {
        const target = sentinelRef.value
        if (!target || !hasMore.value) return
        // getBoundingClientRect here is a one-shot read on user
        // action, not per-scroll -- layout thrash is negligible.
        const rect = target.getBoundingClientRect()
        const viewportH = window.innerHeight || document.documentElement.clientHeight
        const inView = rect.top < viewportH + 200 && rect.bottom > 0
        if (inView) {
          void loadMore()
        }
      }
    })
  }

  onUnmounted(() => detach())
}
