// =============================================================================
// AIVIS.ONE Frontend -- Installment Plans API (Phase F4.2)
// =============================================================================
//
// Typed wrappers for installment-plan endpoints.
// Source of truth: backend/app/modules/installments/router.py (Sprint 6.2).
//
// Plan creation is nested under the product resource; queries live
// under the top-level /installments namespace. That split mirrors
// the backend's two routers and keeps the URL shape predictable.
//
// listMyPlans / getPlanDetail were unused by F4.2 itself when this
// file was written -- they landed ahead of their own consumers so a
// later screen could use them without a second round-trip to the API
// layer. TASK-39 item 1 is that consumer: InstallmentPlansView.vue /
// InstallmentPlanDetailView.vue.
//
// F4.3 B1.1: inline URLSearchParams replaced with buildQueryString
// (TD-F08e closure). No behavioural change.
// =============================================================================

import { api } from '@/api/client'
import { buildQueryString } from '@/utils/querystring'
import type {
  CreateInstallmentPlanRequest,
  InstallmentPlanDetailResponse,
  InstallmentPlanListResponse,
  InstallmentPlanResponse,
} from '@/api/types'

/**
 * POST /api/v1/products/{product_id}/installment
 *
 * Creates a new installment plan by snapshotting the selected
 * ProductInstallment template. The first tranche IS paid inline in
 * the same request (UX-01, see backend service.py::create_plan) --
 * the balance is debited and the Purchase row exists before this
 * call resolves. Tranches 2..N are paid by the installments worker
 * as they come due.
 *
 * 4xx conditions the caller must be ready to handle:
 *   - 400 "KYC verification required ..."            -- investor not KYC-approved
 *   - 400 "Installment template does not belong ..." -- template/product mismatch
 *   - 400 "Insufficient balance ..."                 -- can't afford first tranche
 *   - 400 Product/Company not active
 *   - 403                                             -- wrong role
 *   - 404                                             -- product or template missing
 */
export function createInstallmentPlan(
  productId: string,
  body: CreateInstallmentPlanRequest,
): Promise<InstallmentPlanResponse> {
  return api.post<InstallmentPlanResponse>(`/api/v1/products/${productId}/installment`, body)
}

/**
 * GET /api/v1/installments/me -- paginated list of the authenticated
 * buyer's installment plans, newest first. Used by F4.4 Portfolio.
 */
export function listMyPlans(params?: {
  page?: number
  per_page?: number
}): Promise<InstallmentPlanListResponse> {
  const qs = buildQueryString({
    page: params?.page,
    per_page: params?.per_page,
  })
  return api.get<InstallmentPlanListResponse>(`/api/v1/installments/me${qs}`)
}

/**
 * GET /api/v1/installments/{plan_id} -- plan detail with expanded
 * tranche list. Ownership-enforced on the backend; non-owners get 404.
 */
export function getPlanDetail(planId: string): Promise<InstallmentPlanDetailResponse> {
  return api.get<InstallmentPlanDetailResponse>(`/api/v1/installments/${planId}`)
}
