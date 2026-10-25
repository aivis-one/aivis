// =============================================================================
// useReloadOnLocale -- re-run a view's own load on a locale switch (H38)
// =============================================================================
//
// A view that fetches project data itself (not through a store) shows it in
// the language of the moment it loaded. Pass its load function here: it is
// called again after every locale switch while the view is mounted, so the
// backend answers in the new Accept-Language. Stores are covered by
// stores/localeReload.ts. An open edit form is not affected: the forms keep
// their drafts, only the lists and details behind them are re-read.
// =============================================================================

import { onMounted, onUnmounted } from 'vue'
import { onLocaleChange } from '@/i18n'

export function useReloadOnLocale(load: () => unknown): void {
  let stop: (() => void) | null = null
  onMounted(() => {
    stop = onLocaleChange(() => {
      void load()
    })
  })
  onUnmounted(() => {
    stop?.()
    stop = null
  })
}
