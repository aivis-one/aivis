// =============================================================================
// Every API call says the reader's language (H38 P-132)
// =============================================================================
//
// The backend answers project data in the language of Accept-Language. The
// JSON client always sent it; the raw fetch() calls of src/api/ (multipart
// uploads, blob downloads) did not -- and an upload answers the edited
// object, which must come back in the reader's language too. One helper,
// languageHeaders(), now feeds all of them.
//
// Pinned here:
//   1. each of the seven raw fetch() calls sends the CURRENT locale (REPEAT:
//      two locales one after another, the second wins);
//   2. the class, not the sample: every module of src/api/ that calls
//      fetch() in code also calls languageHeaders() -- an eighth fetch()
//      added without it fails here;
//   3. languageQuery(): a variant's `?language=`, nothing for the common file
//      (EMPTINESS: null, undefined and '').
// =============================================================================

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { i18n } from '@/i18n'
import { languageHeaders, languageQuery } from './client'
import { fetchAgreementBlob } from './agreements'
import { sendAttachmentMultipart } from './company-attachments'
import { uploadOwnRoadmapCover } from './company-roadmap'
import { submitKycApplication } from './kyc'
import { uploadStaffCompanyMedia } from './media'
import { uploadRoadmapCover } from './staff-companies'
import { downloadTransactionsExport } from './transactions'

let fetchSpy: ReturnType<typeof vi.fn>
const originalLocale = i18n.global.locale.value

beforeEach(() => {
  fetchSpy = vi.fn(
    async () =>
      new Response('{}', {
        status: 200,
        headers: {
          'content-type': 'application/json',
          'content-disposition': 'attachment; filename="x.csv"',
        },
      }),
  )
  vi.stubGlobal('fetch', fetchSpy)
  vi.stubGlobal(
    'URL',
    Object.assign(URL, { createObjectURL: () => 'blob:x', revokeObjectURL: () => {} }),
  )
})

afterEach(() => {
  vi.unstubAllGlobals()
  i18n.global.locale.value = originalLocale
})

const png = () => new File(['png'], 'p.png', { type: 'image/png' })

const RAW_CALLS: Array<[string, () => Promise<unknown>]> = [
  ['agreements', () => fetchAgreementBlob('p1')],
  ['company-attachments', () => sendAttachmentMultipart('/x', 'POST', new FormData())],
  ['company-roadmap', () => uploadOwnRoadmapCover('i1', png())],
  ['kyc', () => submitKycApplication('passport', png(), png())],
  ['media', () => uploadStaffCompanyMedia('c1', 'logo', png())],
  ['staff-companies', () => uploadRoadmapCover('c1', 'i1', png())],
  ['transactions', () => downloadTransactionsExport()],
]

function sentLanguage(): string | undefined {
  const init = fetchSpy.mock.calls.at(-1)?.[1] as RequestInit | undefined
  return (init?.headers as Record<string, string> | undefined)?.['Accept-Language']
}

describe('the raw fetch() calls send Accept-Language', () => {
  it.each(RAW_CALLS)('%s sends the current locale', async (_name, call) => {
    i18n.global.locale.value = 'ru'
    await call().catch(() => undefined)
    expect(fetchSpy).toHaveBeenCalled()
    expect(sentLanguage()).toBe('ru')

    i18n.global.locale.value = 'en'
    await call().catch(() => undefined)
    expect(sentLanguage()).toBe('en')
  })

  it('languageHeaders() is the current locale', () => {
    i18n.global.locale.value = 'ru'
    expect(languageHeaders()).toEqual({ 'Accept-Language': 'ru' })
  })
})

describe('the class: no fetch() in src/api/ without languageHeaders()', () => {
  // The modules' source, comments stripped: a fetch() named in a comment is
  // not a call.
  const sources = import.meta.glob(['./*.ts', '!./*.spec.ts', '!./generated.ts'], {
    query: '?raw',
    import: 'default',
    eager: true,
  }) as Record<string, string>

  function code(source: string): string {
    return source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1')
  }

  it('reads the modules (a glob that matched nothing would prove nothing)', () => {
    expect(Object.keys(sources).length).toBeGreaterThan(10)
    expect(Object.keys(sources)).toContain('./client.ts')
  })

  it('every module that calls fetch() also calls languageHeaders()', () => {
    const calling = Object.entries(sources).filter(([, s]) => /\bfetch\(/.test(code(s)))
    expect(calling.map(([path]) => path).sort()).toEqual(
      [
        './agreements.ts',
        './client.ts',
        './company-attachments.ts',
        './company-roadmap.ts',
        './kyc.ts',
        './media.ts',
        './staff-companies.ts',
        './transactions.ts',
      ].sort(),
    )
    for (const [path, source] of calling) {
      const body = code(source)
      const fetches = body.match(/\bfetch\(/g)?.length ?? 0
      const helpers = body.match(/languageHeaders\(\)/g)?.length ?? 0
      expect(helpers, path).toBeGreaterThanOrEqual(fetches)
    }
  })
})

describe('languageQuery', () => {
  it('names a variant and nothing for the common file', () => {
    expect(languageQuery('ru')).toBe('?language=ru')
    expect(languageQuery(null)).toBe('')
    expect(languageQuery(undefined)).toBe('')
    expect(languageQuery('')).toBe('')
  })
})
