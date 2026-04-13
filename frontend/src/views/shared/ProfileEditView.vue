<script setup lang="ts">
import { onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { ref } from 'vue'
import CButton from '@/components/ui/CButton.vue'
import CInput from '@/components/ui/CInput.vue'
import CFileUpload from '@/components/ui/CFileUpload.vue'
import { useForm } from '@/composables/useForm'
import { useToast } from '@/composables/useToast'
import { useProfileStore } from '@/stores/profile'
import { useAuthStore } from '@/stores/auth'

const { t } = useI18n()
const router = useRouter()
const profileStore = useProfileStore()
const authStore = useAuthStore()
const { addToast } = useToast()

const { values, errors, submitting, handleSubmit } = useForm({
  initialValues: {
    first_name: '',
    last_name: '',
    phone: '',
    bio: '',
    country: '',
    city: '',
  },
  validate(v) {
    const errs: Record<string, string> = {}
    if (!v.first_name) errs.first_name = t('validation.required')
    return errs
  },
  async onSubmit(v) {
    const success = await profileStore.updateProfile({
      first_name: v.first_name as string,
      last_name: v.last_name as string,
      phone: v.phone as string,
      bio: v.bio as string,
      country: v.country as string,
      city: v.city as string,
    })
    if (success) {
      addToast('success', t('profile.updated'))
      goBack()
    } else {
      addToast('error', profileStore.error ?? t('common.error'))
    }
  },
})

onMounted(async () => {
  await profileStore.fetchProfile()
  populateForm()
})

watch(
  () => profileStore.profile,
  () => populateForm(),
)

function populateForm() {
  if (profileStore.profile) {
    values.first_name = profileStore.profile.first_name
    values.last_name = profileStore.profile.last_name
    values.phone = profileStore.profile.phone
    values.bio = profileStore.profile.bio
    values.country = profileStore.profile.country
    values.city = profileStore.profile.city
  }
}

const avatarFile = ref<File | null>(null)
const avatarUploading = ref(false)

async function handleAvatarChange(file: File | File[] | null) {
  if (!file || Array.isArray(file)) return
  avatarFile.value = file
  avatarUploading.value = true
  const success = await profileStore.uploadAvatar(file)
  avatarUploading.value = false
  if (success) {
    addToast('success', t('profile.changeAvatar'))
  } else {
    addToast('error', profileStore.error ?? t('common.error'))
  }
}

function goBack() {
  const role = authStore.userRole ?? 'investor'
  router.push(`/${role}/profile`)
}
</script>

<template>
  <div class="profile-edit">
    <h1 class="profile-edit__title">{{ t('profile.edit') }}</h1>

    <div class="profile-edit__avatar">
      <div v-if="profileStore.profile?.avatar_url" class="profile-edit__avatar-preview">
        <img :src="profileStore.profile.avatar_url" :alt="t('profile.avatar')" />
      </div>
      <CFileUpload
        :model-value="avatarFile"
        accept="image/jpeg,image/png,image/webp"
        :max-size="5 * 1024 * 1024"
        :label="t('profile.changeAvatar')"
        :disabled="avatarUploading"
        @update:model-value="handleAvatarChange"
      />
    </div>

    <form class="profile-edit__form" @submit.prevent="handleSubmit">
      <CInput
        v-model="values.first_name"
        :label="t('profile.firstName')"
        :error="errors.first_name"
      />
      <CInput v-model="values.last_name" :label="t('profile.lastName')" :error="errors.last_name" />
      <CInput v-model="values.phone" :label="t('profile.phone')" :error="errors.phone" />
      <CInput v-model="values.bio" :label="t('profile.bio')" :error="errors.bio" />
      <CInput v-model="values.country" :label="t('profile.country')" :error="errors.country" />
      <CInput v-model="values.city" :label="t('profile.city')" :error="errors.city" />

      <div class="profile-edit__actions">
        <CButton type="submit" variant="primary" :loading="submitting">
          {{ t('profile.save') }}
        </CButton>
        <CButton variant="ghost" @click="goBack">
          {{ t('profile.cancel') }}
        </CButton>
      </div>
    </form>
  </div>
</template>

<style scoped>
.profile-edit {
  padding: var(--space-md);
  display: flex;
  flex-direction: column;
  gap: var(--space-lg);
}

.profile-edit__title {
  font-size: var(--text-2xl);
  font-weight: 700;
  color: var(--text);
}

.profile-edit__avatar {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.profile-edit__avatar-preview img {
  width: 80px;
  height: 80px;
  border-radius: 50%;
  object-fit: cover;
}

.profile-edit__form {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.profile-edit__actions {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  margin-top: var(--space-sm);
}
</style>
