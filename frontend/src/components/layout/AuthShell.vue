<script setup lang="ts">
// The design system's Auth shell (K33): one header (the logo at the start, the
// language and theme controls at the end) and one main holding the screen's one
// panel, over the page ground. The panel's content is the screen's: an optional
// icon, one title, a subtitle, the form (`ds-auth__form`) and a foot
// (`ds-auth__foot`). On a phone the panel starts from the top, at desktop widths
// it is centred. The `start` slot replaces the logo where a screen puts
// something beside it (a back button). While staff act as another user the banner
// row of the frame (K25) is the first child of the shell, above the header, the
// system's banner slot of this shell (K33).

import AvatarBanner from '@/components/layout/AvatarBanner.vue'
import AivisLogo from '@/components/ui/AivisLogo.vue'
import CAppControls from '@/components/ui/CAppControls.vue'
</script>

<template>
  <div class="ds-auth">
    <AvatarBanner />
    <header class="ds-auth__header">
      <div class="auth-shell__start">
        <slot name="start">
          <AivisLogo :height="28" />
        </slot>
      </div>
      <div class="ds-auth__controls">
        <CAppControls />
      </div>
    </header>
    <main class="ds-auth__main">
      <div class="ds-auth__panel">
        <slot />
      </div>
    </main>
  </div>
</template>

<style scoped>
.auth-shell__start {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}
</style>
