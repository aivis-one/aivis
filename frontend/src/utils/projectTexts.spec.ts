// =============================================================================
// utils/projectTexts -- the edit screens' side of the translations (H38)
// =============================================================================
//
// A PATCH that carries `translations` replaces the stored map WHOLE, so what
// a screen sends must keep every language and field it does not edit. And
// the languages a screen offers come from SUPPORTED_LOCALES, base first.
//
// Axes:
//   REPEAT    -- a field in two languages; a language the screen does not
//                offer (de) and a field it does not edit (name) ride along
//   EMPTINESS -- no stored map, a blank draft field (removes the
//                translation), a language left empty (dropped)
//   SHORTAGE  -- a malformed map from the server (non-string text, a
//                non-object language) is read without throwing
// =============================================================================

import { describe, expect, it } from 'vitest'
import { SUPPORTED_LOCALES } from '@/i18n/locales.config'
import {
  BASE_LANGUAGE,
  EDIT_LANGUAGES,
  asTranslations,
  baseText,
  emptyDraft,
  imageIn,
  makeDraft,
  sameTranslations,
  translationsFromDraft,
  variantLanguage,
} from './projectTexts'

describe('the editing languages', () => {
  it('are SUPPORTED_LOCALES, the base first', () => {
    expect(EDIT_LANGUAGES[0]!.code).toBe(BASE_LANGUAGE)
    expect(EDIT_LANGUAGES.map((l) => l.code).sort()).toEqual(
      SUPPORTED_LOCALES.map((l) => l.code).sort(),
    )
  })
})

describe('a draft', () => {
  it('starts from the English base and the stored translations', () => {
    const draft = makeDraft(
      ['name', 'description'],
      { name: 'Farm', description: null },
      { ru: { name: 'Ферма' }, de: { name: 'Hof' } },
    )
    expect(baseText(draft, 'name')).toBe('Farm')
    expect(baseText(draft, 'description')).toBe('')
    expect(draft.ru).toEqual({ name: 'Ферма', description: '' })
    // German is not offered: it is not in the draft, but it is kept (below).
    expect(draft.de).toBeUndefined()
  })

  it('is empty in every language when new', () => {
    const draft = emptyDraft(['title'])
    expect(Object.keys(draft).sort()).toEqual(EDIT_LANGUAGES.map((l) => l.code).sort())
    expect(Object.values(draft).every((fields) => fields.title === '')).toBe(true)
  })
})

describe('the translations sent back', () => {
  const stored = { ru: { name: 'Ферма', description: 'Яблоки' }, de: { name: 'Hof' } }

  it('keep the languages and fields the screen does not edit', () => {
    const draft = makeDraft(['description'], { description: 'Apples' }, stored)
    draft.ru!.description = 'Груши'
    expect(translationsFromDraft(draft, ['description'], stored)).toEqual({
      ru: { name: 'Ферма', description: 'Груши' },
      de: { name: 'Hof' },
    })
  })

  it('drop a blank field and a language left empty', () => {
    const draft = makeDraft(['name'], { name: 'Farm' }, { ru: { name: 'Ферма' } })
    draft.ru!.name = '   '
    expect(translationsFromDraft(draft, ['name'], { ru: { name: 'Ферма' } })).toEqual({})
  })

  it('never carry the base language', () => {
    const draft = makeDraft(['name'], { name: 'Farm' }, null)
    expect(translationsFromDraft(draft, ['name'], null)).toEqual({})
  })

  it('compare as maps, not as key orders', () => {
    expect(sameTranslations({ ru: { a: '1', b: '2' } }, { ru: { b: '2', a: '1' } })).toBe(true)
    expect(sameTranslations({ ru: { a: '1' } }, { ru: { a: '2' } })).toBe(false)
    expect(sameTranslations({}, null)).toBe(true)
  })

  it('read a malformed map without throwing', () => {
    expect(asTranslations({ ru: { name: 5, description: 'ok' }, de: 'x' })).toEqual({
      ru: { description: 'ok' },
    })
    expect(asTranslations('nope')).toEqual({})
  })
})

describe('the pictures per language', () => {
  const variants = {
    en: { cover_url: 'https://x/common.png' },
    ru: { cover_url: 'https://x/ru.png', logo_url: null },
  }

  it('reads a link per language, null when there is none', () => {
    expect(imageIn(variants, 'en', 'cover_url')).toBe('https://x/common.png')
    expect(imageIn(variants, 'ru', 'cover_url')).toBe('https://x/ru.png')
    expect(imageIn(variants, 'ru', 'logo_url')).toBeNull()
    expect(imageIn(variants, 'de', 'cover_url')).toBeNull()
    expect(imageIn(null, 'en', 'cover_url')).toBeNull()
  })

  it('sends no language for the common file', () => {
    expect(variantLanguage(BASE_LANGUAGE)).toBeNull()
    expect(variantLanguage('ru')).toBe('ru')
  })
})
