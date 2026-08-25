// =============================================================================
// AIVIS.ONE Frontend -- Staff Posts API (iter 2.7 Block B)
// =============================================================================
//
// Typed wrappers for /api/v1/staff/posts/* (backend
// posts/staff_router.py). All endpoints require the content_manage
// permission server-side; the frontend gates the CTAs through
// useStaffPermissions().canDo('content_manage') before calling.
//
// Unlike the public /api/v1/posts surface (published-only), the staff
// list returns drafts too (is_published omitted or false). Soft-
// deleted rows stay hidden either way.
//
// Endpoints:
//   GET    /api/v1/staff/posts          -- list (drafts included)
//   POST   /api/v1/staff/posts          -- create
//   PATCH  /api/v1/staff/posts/{id}     -- partial update
//   DELETE /api/v1/staff/posts/{id}     -- soft-delete
// =============================================================================

import { api } from '@/api/client'
import { buildQueryString } from '@/utils/querystring'
import type {
  PostListResponse,
  PostResponse,
  CreatePostRequest,
  UpdatePostRequest,
} from '@/api/types'

/**
 * GET /api/v1/staff/posts -- paginated post list with optional filters.
 *
 * Filters (all optional, combinable):
 *   - owner_type:   'platform' | 'company' (backend OwnerType StrEnum,
 *                   422 on any other value)
 *   - owner_id:     company_profiles.id; only meaningful with
 *                   owner_type='company'
 *   - is_published: true / false exact match; omit for both
 *   - search:       case-insensitive substring on title (backend
 *                   escapes %, _, \ so literals match)
 *
 * Pagination: page (1-indexed), per_page (1..100). Sort is fixed
 * server-side.
 */
export function fetchStaffPosts(params?: {
  owner_type?: 'platform' | 'company'
  owner_id?: string
  is_published?: boolean
  search?: string
  page?: number
  per_page?: number
}): Promise<PostListResponse> {
  const qs = buildQueryString({
    owner_type: params?.owner_type,
    owner_id: params?.owner_id,
    is_published: params?.is_published,
    search: params?.search,
    page: params?.page,
    per_page: params?.per_page,
  })
  return api.get<PostListResponse>(`/api/v1/staff/posts${qs}`)
}

/** POST /api/v1/staff/posts -- create a platform or company post. */
export function createStaffPost(body: CreatePostRequest): Promise<PostResponse> {
  return api.post<PostResponse>('/api/v1/staff/posts', body)
}

/** PATCH /api/v1/staff/posts/{id} -- partial update of a post. */
export function updateStaffPost(postId: string, body: UpdatePostRequest): Promise<PostResponse> {
  return api.patch<PostResponse>(`/api/v1/staff/posts/${postId}`, body)
}

/** DELETE /api/v1/staff/posts/{id} -- soft-delete a post. */
export function deleteStaffPost(postId: string): Promise<void> {
  return api.delete(`/api/v1/staff/posts/${postId}`)
}
