// =============================================================================
// AIVIS.ONE Frontend -- MIME Utilities (iter 2.6 R25 STYLE-25-01)
// =============================================================================
//
// Shared mime-type helpers. Extracted from duplicate inline copies in
// PublicAttachmentsSection.vue and PublicAttachmentLandingView.vue
// (STYLE-25-01).
//
// CONSUMERS.
//   - PublicAttachmentsSection (iter 2.6 Batch 4)
//   - PublicAttachmentLandingView (iter 2.6 Batch 4)
//   - AttachmentsSection (auth-flow, still has its own copy at the
//     time of writing -- a separate cleanup folds it onto this
//     implementation)
//
// MAPPING DESIGN.
//   Coarse-grained mapping by mime prefix / known type. Anything
//   unmapped falls through to a generic File icon. Adding a new
//   bucket is a one-line addition; there is no contract beyond
//   "return one of the imported lucide-vue-next icon components".
//
// WHY A SEPARATE FILE.
//   - The imports (lucide-vue-next icon components) are heavy compared
//     to plain string/number utils. Keeping them in their own module
//     means callers that just need `formatBytes` don't drag in the
//     icon set as a transitive dependency.
//   - `format.ts` is for pure scalar formatters (string in -> string
//     out); `mimeIcon` returns a Vue component reference. Different
//     return shape, different module.
// =============================================================================

import {
  File as FileIcon,
  FileArchive,
  FileSpreadsheet,
  FileText,
  Image as ImageIcon,
  Video,
} from 'lucide-vue-next'

/**
 * Map a MIME type to a representative lucide-vue-next icon component.
 *
 * Returned component is suitable for `<component :is="mimeIcon(mime)" />`.
 * Unknown mimes resolve to the generic File icon -- adding a more
 * specific bucket is a one-line addition with no migration cost
 * because the fallback already produced a sensible (if generic) icon.
 *
 * Buckets:
 *   image/*                            -> ImageIcon
 *   video/*                            -> Video
 *   application/pdf                    -> FileText (matches OS convention:
 *                                         "document" icon for PDFs)
 *   spreadsheet / csv / xls            -> FileSpreadsheet
 *   zip / archive (substring match)    -> FileArchive
 *   anything else                      -> FileIcon
 */
export function mimeIcon(mime: string) {
  if (mime.startsWith('image/')) return ImageIcon
  if (mime.startsWith('video/')) return Video
  if (mime === 'application/pdf') return FileText
  if (mime.includes('spreadsheet') || mime === 'text/csv' || mime === 'application/vnd.ms-excel') {
    return FileSpreadsheet
  }
  if (mime.includes('zip') || mime.includes('archive')) return FileArchive
  return FileIcon
}
