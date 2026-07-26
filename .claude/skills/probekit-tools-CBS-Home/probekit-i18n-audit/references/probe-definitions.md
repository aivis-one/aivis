# i18n Audit — Probe Definitions

CBS HOME internationalization compliance probes. 4-locale support: en, ru, de, ar.
Read severity from `probekit-core/references/severity-format.md`.

## P1: Hardcoded Strings in Templates (CRITICAL)

Scan `.vue` template sections for raw text content.

**Allowed:**
- `{{ t('...') }}` or `{{ $t('...') }}` — i18n calls
- `{{ variable }}` — dynamic data
- HTML entities (`&nbsp;`, `&rarr;`), numeric literals (`0`, `100%`)
- Technical strings (CSS class names, URLs), text inside comments

**Forbidden:**
- Any human-readable text directly in templates
- Placeholder text in English/Russian/German/Arabic
- Button labels, headings, descriptions without `t()`

**Detection:**
```bash
grep -rn --include='*.vue' '>[A-Z][a-z]' src/components/ src/views/ | grep -v '{{' | grep -v 'class=' | grep -v '//'
```

## P2: Hardcoded Strings in Script (HIGH)

Scan `<script>` sections for user-visible string literals.

**Allowed:** Route paths, CSS values, event names, console messages, type literals.
**Forbidden:** Toast messages, alert/confirm text, validation error messages in strings.

## P3: Key Parity Across Locales (CRITICAL)

Compare all locale files — every key in `en.json` must exist in `ru.json`, `de.json`, `ar.json`.

**Detection:**
```bash
node -e "
const en = require('./src/i18n/locales/en.json');
const ru = require('./src/i18n/locales/ru.json');
const de = require('./src/i18n/locales/de.json');
const ar = require('./src/i18n/locales/ar.json');
function keys(obj, prefix='') {
  return Object.entries(obj).flatMap(([k,v]) =>
    typeof v === 'object' ? keys(v, prefix+k+'.') : [prefix+k]);
}
const enKeys = keys(en);
const missing = {
  ru: enKeys.filter(k => !keys(ru).includes(k)),
  de: enKeys.filter(k => !keys(de).includes(k)),
  ar: enKeys.filter(k => !keys(ar).includes(k)),
};
console.log(JSON.stringify(missing, null, 2));
"
```

## P4: Unused i18n Keys (LOW)

Find keys defined in locale files but never used in code.

**Detection:** For each key in en.json, grep for it in `src/`. Keys with 0 hits = unused.

## P5: Missing i18n Keys in Code (CRITICAL)

Find `t('key')` calls where key doesn't exist in en.json.

**Detection:**
```bash
grep -rn "t('" src/ --include='*.vue' --include='*.ts' | grep -oP "t\('([^']+)'\)" | sort -u
```
Cross-reference against en.json keys.

## P6: RTL Locale Setup (HIGH)

Verify Arabic locale triggers RTL.

**Checks:**
- `i18n/index.ts` has RTL detection for 'ar'
- `applyDir()` sets `dir="rtl"` on `<html>`
- `index.html` flash prevention script handles RTL
- `global.css` has `[dir="rtl"]` selectors

## P7: Locale File Structure (MEDIUM)

Verify consistent JSON structure across all locale files.

**Checks:** All files valid JSON, same nesting depth, same key hierarchy, no empty string values (`""`).

## P8: Placeholder/Attribute i18n (MEDIUM)

Verify form placeholders and ARIA attributes use i18n.

**Detection:**
```bash
grep -rn 'placeholder="[A-Z]' src/ --include='*.vue'
grep -rn 'aria-label="[A-Z]' src/ --include='*.vue'
grep -rn 'title="[A-Z]' src/ --include='*.vue'
```
