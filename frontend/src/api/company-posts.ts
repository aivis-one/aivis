// =============================================================================
// AIVIS.ONE Frontend -- Company Posts Self-Service API (TASK-30)
// =============================================================================
//
// Typed wrappers for /api/v1/company/posts/* (backend
// posts/company_router.py). Distinct from api/staff-posts.ts's post
// functions, which speak the STAFF surface (/api/v1/staff/posts) and
// take an explicit owner_type/owner_id. Every function here operates on
// the CALLER'S OWN company -- there is no owner_type/owner_id/company_id
// parameter anywhere in this module because none of these URLs or
// request bodies accept one; the backend resolves the company server-side
// from the auth token via get_current_company_profile.
//
// Reuses the SAME generated response types as api/staff-posts.ts
// (PostResponse, PostListResponse) but its OWN request types
// (CreateCompanyPostRequest, UpdateCompanyPostRequest) -- those omit
// owner_type/owner_id/is_banner entirely (posts/schemas.py). is_banner
// is a staff-only editorial privilege (the site-wide homepage banner)
// and is never settable through this surface; every company-authored
// post is created with is_banner=False server-side.
//
// Endpoints covered here:
//   GET    /api/v1/company/posts       -- list own posts (drafts included)
//   POST   /api/v1/company/posts       -- create post
//   PATCH  /api/v1/company/posts/{id}  -- update post
//   DELETE /api/v1/company/posts/{id}  -- soft-delete post
// =============================================================================
import { api } from '@/api/client'
import { buildQueryString } from '@/utils/querystring'
import type {
  CreateCompanyPostRequest,
  PostListResponse,
  PostResponse,
  UpdateCompanyPostRequest,
} from '@/api/types'

/**
 * GET /api/v1/company/posts -- paginated list of the caller's own posts,
 * drafts included (mirrors the staff list's drafts-included behaviour --
 * see posts/company_router.py's docstring). Requires role=company
 * server-side (403 for any other role).
 *
 * Filters (all optional, combinable):
 *   - is_published: true / false exact match; omit for both
 *   - search:       case-insensitive substring on title (backend
 *                   escapes %, _, \ so literals match)
 *
 * Pagination: page (1-indexed), per_page (1..100).
 */
export function fetchOwnPosts(params?: {
  is_published?: boolean
  search?: string
  page?: number
  per_page?: number
}): Promise<PostListResponse> {
  const qs = buildQueryString({
    is_published: params?.is_published,
    search: params?.search,
    page: params?.page,
    per_page: params?.per_page,
  })
  return api.get<PostListResponse>(`/api/v1/company/posts${qs}`)
}

/**
 * POST /api/v1/company/posts -- create a post about the caller's own
 * company. Publishes immediately when is_published=true is passed --
 * no moderation/approval step (TASK-30 ruled this out explicitly).
 * Returns the created post (201).
 */
export function createOwnPost(body: CreateCompanyPostRequest): Promise<PostResponse> {
  return api.post<PostResponse>('/api/v1/company/posts', body)
}

/**
 * PATCH /api/v1/company/posts/{postId} -- partial update of an own post.
 * Send ONLY the fields that actually changed -- exclude_unset semantics,
 * same as the staff surface: an omitted field is kept, an explicit null
 * clears it. 404 (never 403) when postId belongs to a different company
 * or to the platform.
 */
export function updateOwnPost(
  postId: string,
  body: UpdateCompanyPostRequest,
): Promise<PostResponse> {
  return api.patch<PostResponse>(`/api/v1/company/posts/${postId}`, body)
}

/**
 * DELETE /api/v1/company/posts/{postId} -- soft-delete an own post.
 * Returns 204. 404 (never 403) on a cross-company or platform postId.
 */
export function deleteOwnPost(postId: string): Promise<void> {
  return api.delete(`/api/v1/company/posts/${postId}`)
}
