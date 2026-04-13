import { createRouter, createWebHistory } from 'vue-router'
import { setupGuards } from './guards'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    // Root redirect
    { path: '/', redirect: '/auth/login' },

    // Auth (public)
    {
      path: '/auth',
      children: [
        {
          path: 'login',
          name: 'login',
          component: () => import('@/views/auth/LoginView.vue'),
          meta: { isPublic: true },
        },
        {
          path: 'register',
          name: 'register',
          component: () => import('@/views/auth/RegisterView.vue'),
          meta: { isPublic: true },
        },
        {
          path: 'verify',
          name: 'verify',
          component: () => import('@/views/auth/VerifyView.vue'),
          meta: { isPublic: true },
        },
      ],
    },

    // Onboarding wizard (authenticated, any role)
    {
      path: '/onboarding',
      name: 'onboarding',
      component: () => import('@/views/shared/OnboardingView.vue'),
      meta: { requiresAuth: true },
    },

    // Investor (investor + agent can access)
    {
      path: '/investor',
      component: () => import('@/components/layout/InvestorShell.vue'),
      meta: { requiresAuth: true, roles: ['investor', 'agent'] },
      children: [
        { path: '', redirect: '/investor/dashboard' },
        {
          path: 'dashboard',
          name: 'investor-dashboard',
          component: () => import('@/views/investor/DashboardView.vue'),
        },
        {
          path: 'portfolio',
          name: 'investor-portfolio',
          component: () => import('@/views/investor/DashboardView.vue'),
        },
        {
          path: 'balance',
          name: 'investor-balance',
          component: () => import('@/views/investor/DashboardView.vue'),
        },
        {
          path: 'documents',
          name: 'investor-documents',
          component: () => import('@/views/shared/DocumentsView.vue'),
        },
        {
          path: 'documents/:id',
          name: 'investor-document-detail',
          component: () => import('@/views/shared/DocumentDetailView.vue'),
        },
        {
          path: 'documents/:id/sign',
          name: 'investor-document-sign',
          component: () => import('@/views/shared/DocumentSignView.vue'),
        },
        {
          path: 'profile',
          name: 'investor-profile',
          component: () => import('@/views/shared/ProfileView.vue'),
        },
        {
          path: 'profile/edit',
          name: 'investor-profile-edit',
          component: () => import('@/views/shared/ProfileEditView.vue'),
        },
        {
          path: 'kyc',
          name: 'investor-kyc',
          component: () => import('@/views/shared/KYCStatusView.vue'),
        },
        {
          path: 'kyc/form',
          name: 'investor-kyc-form',
          component: () => import('@/views/shared/KYCFormView.vue'),
        },
        {
          path: 'kyc/upload',
          name: 'investor-kyc-upload',
          component: () => import('@/views/shared/KYCUploadView.vue'),
        },
        {
          path: 'settings',
          name: 'investor-settings',
          component: () => import('@/views/shared/SettingsView.vue'),
        },
      ],
    },

    // Agent
    {
      path: '/agent',
      component: () => import('@/components/layout/AgentShell.vue'),
      meta: { requiresAuth: true, roles: ['agent'] },
      children: [
        { path: '', redirect: '/agent/dashboard' },
        {
          path: 'dashboard',
          name: 'agent-dashboard',
          component: () => import('@/views/agent/DashboardView.vue'),
        },
        {
          path: 'hub',
          name: 'agent-hub',
          component: () => import('@/views/agent/DashboardView.vue'),
        },
        {
          path: 'commissions',
          name: 'agent-commissions',
          component: () => import('@/views/agent/DashboardView.vue'),
        },
        {
          path: 'passive',
          name: 'agent-passive',
          component: () => import('@/views/agent/DashboardView.vue'),
        },
        {
          path: 'profile',
          name: 'agent-profile',
          component: () => import('@/views/shared/ProfileView.vue'),
        },
        {
          path: 'profile/edit',
          name: 'agent-profile-edit',
          component: () => import('@/views/shared/ProfileEditView.vue'),
        },
        {
          path: 'kyc',
          name: 'agent-kyc',
          component: () => import('@/views/shared/KYCStatusView.vue'),
        },
        {
          path: 'kyc/form',
          name: 'agent-kyc-form',
          component: () => import('@/views/shared/KYCFormView.vue'),
        },
        {
          path: 'kyc/upload',
          name: 'agent-kyc-upload',
          component: () => import('@/views/shared/KYCUploadView.vue'),
        },
        {
          path: 'settings',
          name: 'agent-settings',
          component: () => import('@/views/shared/SettingsView.vue'),
        },
      ],
    },

    // Company
    {
      path: '/company',
      component: () => import('@/components/layout/CompanyShell.vue'),
      meta: { requiresAuth: true, roles: ['company'] },
      children: [
        { path: '', redirect: '/company/dashboard' },
        {
          path: 'dashboard',
          name: 'company-dashboard',
          component: () => import('@/views/company/DashboardView.vue'),
        },
        {
          path: 'products',
          name: 'company-products',
          component: () => import('@/views/company/DashboardView.vue'),
        },
        {
          path: 'analytics',
          name: 'company-analytics',
          component: () => import('@/views/company/DashboardView.vue'),
        },
        {
          path: 'profile',
          name: 'company-profile',
          component: () => import('@/views/shared/ProfileView.vue'),
        },
        {
          path: 'profile/edit',
          name: 'company-profile-edit',
          component: () => import('@/views/shared/ProfileEditView.vue'),
        },
        {
          path: 'kyc',
          name: 'company-kyc',
          component: () => import('@/views/shared/KYCStatusView.vue'),
        },
        {
          path: 'kyc/form',
          name: 'company-kyc-form',
          component: () => import('@/views/shared/KYCFormView.vue'),
        },
        {
          path: 'kyc/upload',
          name: 'company-kyc-upload',
          component: () => import('@/views/shared/KYCUploadView.vue'),
        },
        {
          path: 'settings',
          name: 'company-settings',
          component: () => import('@/views/shared/SettingsView.vue'),
        },
      ],
    },

    // Staff
    {
      path: '/staff',
      component: () => import('@/components/layout/StaffShell.vue'),
      meta: { requiresAuth: true, roles: ['staff'] },
      children: [
        { path: '', redirect: '/staff/dashboard' },
        {
          path: 'dashboard',
          name: 'staff-dashboard',
          component: () => import('@/views/staff/DashboardView.vue'),
        },
        {
          path: 'users',
          name: 'staff-users',
          component: () => import('@/views/staff/DashboardView.vue'),
        },
        {
          path: 'kyc',
          name: 'staff-kyc',
          component: () => import('@/views/staff/DashboardView.vue'),
        },
        {
          path: 'payments',
          name: 'staff-payments',
          component: () => import('@/views/staff/DashboardView.vue'),
        },
        {
          path: 'more',
          name: 'staff-more',
          component: () => import('@/views/staff/DashboardView.vue'),
        },
        {
          path: 'profile',
          name: 'staff-profile',
          component: () => import('@/views/shared/ProfileView.vue'),
        },
        {
          path: 'profile/edit',
          name: 'staff-profile-edit',
          component: () => import('@/views/shared/ProfileEditView.vue'),
        },
        {
          path: 'settings',
          name: 'staff-settings',
          component: () => import('@/views/shared/SettingsView.vue'),
        },
      ],
    },

    // Catch-all
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

setupGuards(router)
