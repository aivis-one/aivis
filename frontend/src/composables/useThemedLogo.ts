// =============================================================================
// AIVIS.ONE Frontend -- useThemedLogo (H36 P-131)
// =============================================================================
//
// A project has a logo and, optionally, a logo for the dark theme
// (logo_url / logo_dark_url; company_logo_url / company_logo_dark_url on a
// product). Where a logo is shown, the dark one is taken in the dark theme
// when it exists; otherwise the ordinary logo is shown in both themes. The
// dark logo is never shown in the light theme: it is drawn for a dark
// background and may vanish on a light one.
//
// "Dark theme" is the theme actually rendered (useTheme().effective), so a
// viewer on 'auto' follows the system setting live.
// =============================================================================

import { computed } from 'vue'
import type { ComputedRef } from 'vue'
import type { EffectiveTheme } from '@/composables/useTheme'
import { useTheme } from '@/composables/useTheme'

/** The logo to show in `theme`, or null when there is none for it. */
export function pickThemedLogo(
  light: string | null | undefined,
  dark: string | null | undefined,
  theme: EffectiveTheme,
): string | null {
  if (theme === 'dark' && dark) return dark
  return light ?? null
}

/** The logo to show in the rendered theme, following theme changes. */
export function useThemedLogo(
  light: () => string | null | undefined,
  dark: () => string | null | undefined,
): ComputedRef<string | null> {
  const { effective } = useTheme()
  return computed(() => pickThemedLogo(light(), dark(), effective.value))
}

/** A product as the cover chain reads it (PublicProductResponse and kin). */
export interface ProductCoverSource {
  cover_url?: string | null
  company_logo_url?: string | null
  company_logo_dark_url?: string | null
}

/**
 * A product's picture: its own cover, else the company's logo for the
 * rendered theme, else null (the screen draws its placeholder).
 */
export function useProductCover(
  product: () => ProductCoverSource | null | undefined,
): ComputedRef<string | null> {
  const { effective } = useTheme()
  return computed(() => {
    const p = product()
    if (!p) return null
    return (
      p.cover_url ?? pickThemedLogo(p.company_logo_url, p.company_logo_dark_url, effective.value)
    )
  })
}
