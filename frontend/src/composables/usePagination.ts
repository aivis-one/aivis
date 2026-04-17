// =============================================================================
// CBSHOME Frontend -- useInfiniteScroll Composable (Phase F4.1)
// =============================================================================
//
// Attach an IntersectionObserver to a sentinel element. When the
// sentinel enters the viewport AND there is more data to load, fire
// loadMore(). Used by the Investor storefront grid.
//
// USAGE:
//   import { useInfiniteScroll } from '@/composables/usePagination'
//
//   const sentinelRef = ref<HTMLElement | null>(null)
//   useInfiniteScroll(sentinelRef, hasMore, loadMore)
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
// =============================================================================

import { onMounted, onUnmounted, watch, type Ref } from 'vue'

export function useInfiniteScroll(
  sentinelRef: Ref<HTMLElement | null>,
  hasMore: Ref<boolean>,
  loadMore: () => void | Promise<void>,
): void {
  let observer: IntersectionObserver | null = null

  function attach(target: HTMLElement): void {
    observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting && hasMore.value) {
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

  onUnmounted(() => detach())
}
