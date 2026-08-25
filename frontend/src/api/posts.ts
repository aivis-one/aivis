// =============================================================================
// AIVIS.ONE Frontend -- Posts API (Phase F9.1, narrow probe for F4.4 B2)
// =============================================================================
//
// Typed wrapper for the public posts feed.
// Source of truth: backend/app/modules/posts/router.py (Sprint 9.1).
//
// ENDPOINTS WRAPPED:
//   GET  /api/v1/posts     -- paginated list, optional filters
//
// SCOPE NOTE.
//   F4.4 B2 only needs the list probe -- the Investor Dashboard
//   shows the most recent N posts as a widget. Detail view, banner
//   dismiss (POST /api/v1/posts/{id}/dismiss), and filter
//   affordances land in F9.2 when the dedicated Posts/Events UI is
//   built. Adding those wrappers prematurely would duplicate work
//   once F9.2 clarifies the final surface (e.g. whether dismiss is
//   called from a bottom-sheet or inline).
//
// AUTH.
//   Backend uses get_optional_user -- anonymous callers get the
//   same list, with is_dismissed=false on every item. The typed
//   wrapper does not branch on auth state; the API client already
//   attaches the Bearer token when present and the backend decides
//   what to compute.
// =============================================================================

import { api } from '@/api/client'
import { buildQueryString } from '@/utils/querystring'
import type { PostListResponse } from '@/api/types'

export interface ListPostsParams {
  page?: number
  per_page?: number
  // owner_type + company_id are the backend's published filter
  // surface; kept here for forward-compat with F9.2 even though
  // the B2 dashboard call does not use them.
  owner_type?: string
  company_id?: string
  tag?: string
}

/**
 * GET /api/v1/posts
 *
 * Paginated list of published, non-deleted posts. Ordered newest
 * first on the backend (created_at DESC). The dashboard widget
 * calls this with `{ per_page: 5 }` and renders the `items` slice.
 */
export function listPosts(params?: ListPostsParams): Promise<PostListResponse> {
  const qs = buildQueryString({
    page: params?.page,
    per_page: params?.per_page,
    owner_type: params?.owner_type,
    company_id: params?.company_id,
    tag: params?.tag,
  })
  return api.get<PostListResponse>(`/api/v1/posts${qs}`)
}
