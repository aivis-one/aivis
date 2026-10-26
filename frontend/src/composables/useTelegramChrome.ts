// =============================================================================
// AIVIS.ONE Frontend -- Telegram's own chrome: the Back button and the theme
// =============================================================================
//
// Inside Telegram the Mini App has the host's Back button in its header and the
// host's colour scheme. Both are wired here and only through the platform layer
// (platform/): in a plain browser this composable does nothing at all, so the web
// is unchanged.
//
//   - BACK: shown on every route that is not the root of a tab. The roots are the
//     tab paths of the cabinet (router/tabs.ts) and, for the staff cabinet, the
//     sections of a hub (one segment under a hub tab: /staff/finance/payments). A
//     press goes back one step in the app's own history; when the Mini App was
//     opened straight on a deep page there is no step back, so the press goes to
//     the root of the tab the page belongs to.
//   - THEME: while the person has not chosen a light or dark of their own, the
//     colour scheme of Telegram is followed, and followed again when Telegram
//     changes it. A choice made in Settings stays.
// =============================================================================

import { onBeforeUnmount, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { platform } from '@/platform'
import { useTheme } from '@/composables/useTheme'
import { extraTabsFor, tabsFor } from '@/router/tabs'
import type { Shell } from '@/router/helpers'

export interface BackPlan {
  /** True when the page is the root of a tab: no Back button. */
  root: boolean
  /** Where a press goes when the app's own history has no step back. */
  home: string
}

function segments(path: string): number {
  return path.split('/').filter(Boolean).length
}

/**
 * Whether a path is the root of a tab of its shell, and the root a press falls
 * back to. A path outside every tab of a cabinet (the notifications page, a
 * detail page of another section) is not a root.
 */
export function backPlan(path: string, shell: Shell | undefined): BackPlan {
  const tabs = tabsFor(shell)
  if (!tabs) return { root: true, home: '/' }
  const all = [...tabs, ...extraTabsFor(shell)]
  let best: { path: string } | null = null
  for (const tab of all) {
    const under = path === tab.path || path.startsWith(`${tab.path}/`)
    if (under && (!best || tab.path.length > best.path.length)) best = tab
  }
  const home = (best ?? tabs[0]!).path
  if (!best) return { root: false, home }
  const depth = segments(path) - segments(best.path)
  // A hub section of the staff cabinet sits one segment under its tab and is a root.
  const sectionDepth = shell === 'staff' ? 1 : 0
  return { root: depth <= sectionDepth, home }
}

export function useTelegramChrome(): void {
  if (platform.name !== 'telegram') return

  const router = useRouter()
  const route = useRoute()

  function press(plan: BackPlan): void {
    const state = window.history.state as { back?: string | null } | null
    if (state?.back) router.back()
    else void router.replace(plan.home)
  }

  watch(
    () => [route.path, route.meta.shell] as const,
    ([path, shell]) => {
      try {
        const plan = backPlan(path, shell as Shell | undefined)
        if (plan.root) platform.hideBackButton()
        else platform.showBackButton(() => press(plan))
      } catch {
        // An old Telegram client without the Back button: nothing to show.
      }
    },
    { immediate: true },
  )

  const { followHost } = useTheme()
  followHost(platform.getTheme())
  const stop = platform.onThemeChanged((theme) => followHost(theme))

  onBeforeUnmount(() => {
    stop()
    followHost(null)
    try {
      platform.hideBackButton()
    } catch {
      // Nothing to hide.
    }
  })
}
