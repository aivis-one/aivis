<script setup lang="ts">
import { ref, onMounted } from 'vue'
import LoadingView from '@/views/auth/LoadingView.vue'
import CToast from '@/components/ui/CToast.vue'
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()
const initializing = ref(true)

onMounted(async () => {
  await authStore.restoreSession()
  initializing.value = false
  // Navigation guards in router/guards.ts handle all redirects
})
</script>

<template>
  <LoadingView v-if="initializing" />
  <RouterView v-else />
  <CToast />
</template>
