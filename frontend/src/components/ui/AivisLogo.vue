<script setup lang="ts">
// AIVIS.ONE logo — the real brand mark + the vector wordmark, configurable height.
//
// TWO ASSETS, AND THEY ARE CARRIED DIFFERENTLY ON PURPOSE:
//   the MARK is /aivis-mark.svg, an <img>. It carries 12 gradients whose ids
//     would leak into the host document once inlined and can collide with
//     another inline SVG's ids. As a file, its ids are scoped to itself.
//   the WORDMARK is INLINE. It paints with fill="currentColor" and has no ids
//     at all, so inlining is safe and is the only way it can inherit the text
//     colour and follow the theme. An <img> cannot see currentColor.
//
// It replaced a CSS text span reading "AIVIS.ONE" in whatever font happened to
// be loaded. The wordmark is the drawn lettering, so it is the same shape at
// every size and in every locale.

withDefaults(
  defineProps<{
    height?: number
    showText?: boolean
  }>(),
  {
    height: 28,
    showText: true,
  },
)
</script>

<template>
  <span class="aivis-logo">
    <img
      class="aivis-logo-icon"
      src="/aivis-mark.svg"
      alt="AIVIS"
      :style="{ width: height + 'px', height: height + 'px' }"
    />
    <svg
      v-if="showText"
      class="aivis-logo-wordmark"
      viewBox="237 453 120 25"
      role="img"
      aria-label="aivis.one"
      :style="{ height: Math.round(height * 0.5) + 'px' }"
    >
      <g fill="currentColor">
      <rect x="257.17" y="461.49" width="2.86" height="14.96"/>
      <circle cx="258.6" cy="457.31" r="1.85"/>
      <rect x="280.22" y="461.49" width="2.86" height="14.96"/>
      <circle cx="281.66" cy="457.31" r="1.85"/>
      <path d="M253.6,467.69c0-9.06-10.51-7.22-13.09-4.37l1.12,2.07c2.91-2.1,9-3.08,8.71,2.04h-5.4c-2.56,0-5.09,2.19-5.01,4.91.15,5.03,7.84,6.23,10.67,2.55v1.56h2.99c.06-4.34,0-4.99,0-8.76ZM245.47,474.49c-3.39-.31-3.3-4.54,0-4.54h4.98c0,3.22-2.03,4.8-4.98,4.54Z"/>
      <path d="M355.46,468.39c0-8.27-10.61-9.92-13.64-3.31-4.17,9.09,6.28,15.68,12.72,9.19l-1.48-1.85c-2.8,3.22-8.91,2.06-9.3-2.47h11.71v-1.56ZM343.75,467.73c.63-5.5,8.68-5.63,9.17,0h-9.17Z"/>
      <path d="M313.98,461.27c-10.02.8-9.49,16.24,1.65,15.44,10.08-.73,9.29-16.3-1.65-15.44ZM315.1,474.37c-7.08.34-7.34-10.02-1.13-10.76,7.48-.89,8.07,10.43,1.13,10.76Z"/>
      <path d="M327.76,463.31v-1.82h-2.6v14.96h2.66c0-3.02-.06-4.9-.06-7.57,0-5.56,7.81-6.41,7.81-2.1v9.67h2.73v-9.95c0-5.41-7.31-6.94-10.54-3.19Z"/>
      <path d="M290.6,465.59c-.08-3.07,5.96-2.15,7.54-.98l.72-2.08c-3.11-2.08-10.44-2.42-10.98,2.68-.61,5.76,7.93,4.07,8.86,6.59.31.83,0,1.59-.72,2.07-2.01,1.35-5.75.11-7.63-1.06l-.91,2.19c3.99,2.99,13.25,3.29,12.03-3.64-.75-4.28-8.84-2.79-8.92-5.78Z"/>
      <polygon points="270.16 473.06 265.09 461.49 262.16 461.49 268.58 476.46 271.7 476.46 277.9 461.49 274.99 461.49 270.16 473.06"/>
      <circle cx="303.76" cy="474.87" r="1.85"/>
      </g>
    </svg>
  </span>
</template>

<style scoped>
.aivis-logo {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  text-decoration: none;
}

.aivis-logo-icon {
  flex-shrink: 0;
}

/* currentColor: the wordmark follows the surrounding text colour, so it themes
   with everything else instead of carrying a colour of its own. */
.aivis-logo-wordmark {
  flex-shrink: 0;
  width: auto;
  color: var(--text-primary);
}
</style>
