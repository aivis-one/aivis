<script setup lang="ts">
import { onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import CButton from '@/components/ui/CButton.vue'
import CSkeleton from '@/components/ui/CSkeleton.vue'
import { useProfileStore } from '@/stores/profile'
import { useAuthStore } from '@/stores/auth'

const { t } = useI18n()
const router = useRouter()
const profileStore = useProfileStore()
const authStore = useAuthStore()

onMounted(() => {
  profileStore.fetchProfile()
})

function goToEdit() {
  const role = authStore.userRole ?? 'investor'
  router.push(`/${role}/profile/edit`)
}
</script>

<template>
  <div class="profile-view">
    <h1 class="profile-view__title">{{ t('profile.title') }}</h1>

    <CSkeleton v-if="profileStore.loading && !profileStore.profile" variant="card" />

    <template v-else-if="profileStore.profile">
      <div class="profile-view__header">
        <div class="profile-view__avatar">
          <img
            v-if="profileStore.hasAvatar"
            :src="profileStore.profile.avatar_url!"
            :alt="t('profile.avatar')"
            class="profile-view__avatar-img"
          />
          <div v-else class="profile-view__avatar-placeholder">
            {{ profileStore.profile.first_name?.charAt(0) ?? '?' }}
          </div>
        </div>
        <div class="profile-view__info">
          <h2 class="profile-view__name">{{ profileStore.fullName }}</h2>
          <p class="profile-view__email">{{ authStore.user?.id }}</p>
        </div>
      </div>

      <div class="profile-view__details">
        <div class="profile-view__field">
          <span class="profile-view__label">{{ t('profile.phone') }}</span>
          <span class="profile-view__value">{{ profileStore.profile.phone || '—' }}</span>
        </div>
        <div class="profile-view__field">
          <span class="profile-view__label">{{ t('profile.bio') }}</span>
          <span class="profile-view__value">{{ profileStore.profile.bio || '—' }}</span>
        </div>
        <div class="profile-view__field">
          <span class="profile-view__label">{{ t('profile.country') }}</span>
          <span class="profile-view__value">{{ profileStore.profile.country || '—' }}</span>
        </div>
        <div class="profile-view__field">
          <span class="profile-view__label">{{ t('profile.city') }}</span>
          <span class="profile-view__value">{{ profileStore.profile.city || '—' }}</span>
        </div>
        <div class="profile-view__field">
          <span class="profile-view__label">{{ t('profile.language') }}</span>
          <span class="profile-view__value">{{ profileStore.profile.language || '—' }}</span>
        </div>
        <div class="profile-view__field">
          <span class="profile-view__label">{{ t('profile.timezone') }}</span>
          <span class="profile-view__value">{{ profileStore.profile.timezone || '—' }}</span>
        </div>
      </div>

      <CButton variant="primary" @click="goToEdit">
        {{ t('profile.edit') }}
      </CButton>
    </template>
  </div>
</template>

<style scoped>
.profile-view {
  padding: var(--space-md);
  display: flex;
  flex-direction: column;
  gap: var(--space-lg);
}

.profile-view__title {
  font-size: var(--text-2xl);
  font-weight: 700;
  color: var(--text);
}

.profile-view__header {
  display: flex;
  align-items: center;
  gap: var(--space-md);
}

.profile-view__avatar-img {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  object-fit: cover;
}

.profile-view__avatar-placeholder {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  background: var(--primary);
  color: var(--text-on-accent);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-2xl);
  font-weight: 700;
}

.profile-view__name {
  font-size: var(--text-xl);
  font-weight: 700;
  color: var(--text);
}

.profile-view__email {
  font-size: var(--text-caption);
  color: var(--text-secondary);
}

.profile-view__details {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.profile-view__field {
  display: flex;
  justify-content: space-between;
  padding: var(--space-sm) 0;
  border-bottom: 1px solid var(--border);
}

.profile-view__label {
  font-size: var(--text-caption);
  font-weight: 600;
  color: var(--text-secondary);
}

.profile-view__value {
  font-size: var(--text-base);
  color: var(--text);
}
</style>
