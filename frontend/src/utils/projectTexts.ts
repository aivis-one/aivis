// =============================================================================
// AIVIS.ONE Frontend -- project data in several languages (H38 P-132)
// =============================================================================
//
// The backend keeps a project's texts (company and product name and
// description, roadmap title and description, post title and body) in
// English in their own fields -- the base and the fallback -- and every
// other language in `translations`, {"ru": {"name": "..."}}. A reader gets
// the texts in their language (Accept-Language), else English, in the
// usual fields. An editing screen also gets:
//
//   base           the English texts
//   translations   every stored translation, exactly as stored (no "en")
//   image_variants the pictures per language: "en" is the COMMON file,
//                  every other key that language's variant
//
// A PATCH that carries `translations` REPLACES the stored map whole, so a
// screen builds the map from what it got and what it edits
// (translationsFromDraft): a language or a field the screen does not edit
// travels back unchanged.
//
// The languages offered for editing are SUPPORTED_LOCALES -- the same list
// the language switch shows -- never a literal.
// =============================================================================

import { DEFAULT_LOCALE, SUPPORTED_LOCALES } from '@/i18n/locales.config'

/** The base language: the plain fields, and the common picture. */
export const BASE_LANGUAGE: string = DEFAULT_LOCALE

/** The languages an editing screen offers, base first. */
export const EDIT_LANGUAGES: readonly { code: string; label: string }[] = [
  ...SUPPORTED_LOCALES.filter((l) => l.code === BASE_LANGUAGE),
  ...SUPPORTED_LOCALES.filter((l) => l.code !== BASE_LANGUAGE),
].map((l) => ({ code: l.code, label: l.label }))

/** Stored translations: language -> field -> text. */
export type Translations = Record<string, Record<string, string>>

/** What an editing screen holds: language -> field -> text ("" = none). */
export type TextDraft = Record<string, Record<string, string>>

/** The `translations` of a response, read defensively (the generated type is loose). */
export function asTranslations(value: unknown): Translations {
  const result: Translations = {}
  if (!value || typeof value !== 'object') return result
  for (const [language, fields] of Object.entries(value as Record<string, unknown>)) {
    if (!fields || typeof fields !== 'object') continue
    const kept: Record<string, string> = {}
    for (const [field, text] of Object.entries(fields as Record<string, unknown>)) {
      if (typeof text === 'string') kept[field] = text
    }
    result[language] = kept
  }
  return result
}

/** An empty draft of `fields` in every editing language. */
export function emptyDraft(fields: readonly string[]): TextDraft {
  const draft: TextDraft = {}
  for (const { code } of EDIT_LANGUAGES) {
    draft[code] = Object.fromEntries(fields.map((f) => [f, '']))
  }
  return draft
}

/** The draft of an edited object: English from `base`, the rest from `translations`. */
export function makeDraft(
  fields: readonly string[],
  base: object | null | undefined,
  translations: unknown,
): TextDraft {
  const stored = asTranslations(translations)
  const english = (base ?? {}) as Record<string, unknown>
  const draft = emptyDraft(fields)
  for (const { code } of EDIT_LANGUAGES) {
    for (const field of fields) {
      const text = code === BASE_LANGUAGE ? english[field] : stored[code]?.[field]
      draft[code]![field] = typeof text === 'string' ? text : ''
    }
  }
  return draft
}

/** The English text of one field of a draft. */
export function baseText(draft: TextDraft, field: string): string {
  return draft[BASE_LANGUAGE]?.[field] ?? ''
}

/**
 * The `translations` to send: the stored map with the edited languages'
 * edited fields put in (a blank field removes its translation). Languages
 * and fields this screen does not edit are kept as stored -- the PATCH
 * replaces the map whole.
 */
export function translationsFromDraft(
  draft: TextDraft,
  fields: readonly string[],
  stored: unknown,
): Translations {
  const result = asTranslations(stored)
  for (const { code } of EDIT_LANGUAGES) {
    if (code === BASE_LANGUAGE) continue
    const language: Record<string, string> = { ...(result[code] ?? {}) }
    for (const field of fields) {
      const text = (draft[code]?.[field] ?? '').trim()
      if (text) language[field] = text
      else delete language[field]
    }
    if (Object.keys(language).length > 0) result[code] = language
    else delete result[code]
  }
  return result
}

function canonical(value: Translations): string {
  return JSON.stringify(
    Object.keys(value)
      .sort()
      .map((language) => [
        language,
        Object.keys(value[language]!)
          .sort()
          .map((field) => [field, value[language]![field]]),
      ]),
  )
}

/** Whether two translation maps say the same thing. */
export function sameTranslations(a: unknown, b: unknown): boolean {
  return canonical(asTranslations(a)) === canonical(asTranslations(b))
}

/**
 * The link of one picture in one language from `image_variants`:
 * "en" is the common file. null when there is none.
 */
export function imageIn(variants: unknown, language: string, field: string): string | null {
  if (!variants || typeof variants !== 'object') return null
  const links = (variants as Record<string, unknown>)[language]
  if (!links || typeof links !== 'object') return null
  const url = (links as Record<string, unknown>)[field]
  return typeof url === 'string' ? url : null
}

/** The `language` of a picture endpoint: null for the common file. */
export function variantLanguage(code: string): string | null {
  return code === BASE_LANGUAGE ? null : code
}
