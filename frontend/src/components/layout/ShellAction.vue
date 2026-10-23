<script setup lang="ts">
// The screen's one primary action, as the frame's floating strip (K25): put it as
// the last element of the screen. On a phone it is kept above the tab bar (the bar
// height and the safe-area inset are the system's); from 880 it stands in the flow.
// The content is the caller's (one primary Button, the figure it acts on).
</script>

<template>
  <div class="ds-shell__action"><slot /></div>
</template>
