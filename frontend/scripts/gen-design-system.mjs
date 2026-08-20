// =============================================================================
// AIVIS.ONE Frontend -- design-system reference generator
// =============================================================================
//
// Writes AIVIS-Design-System.md at the repository root FROM THE SOURCE, so the
// document cannot drift from the code it describes. Run it after any change to
// components/ui/ or styles/variables.css:
//
//     npm --prefix frontend run docs:ds
//
// WHY GENERATED AND NOT WRITTEN. The hand-maintained artifact table in
// AIVIS-Design-Document.md registered 3 of the 10 design documents that
// actually existed, and nobody noticed for months. A register that has to be
// remembered is a register that goes stale; this one is re-derived on demand
// and its own output records when it was.
//
// THE READER IS AN AGENT, not a designer. That decides the shape:
//   * exact values, never "spacing scale" -- an agent cannot see the screen;
//   * usage counts per component, so dead kit is visible the way CCard and
//     CDivider only became visible when someone counted;
//   * an explicit "what does NOT exist" section, because the expensive
//     discovery is not "which component do I use" but "there is no component
//     for this at all", and that costs a full read of components/ui/ to learn.
//
// PARSING NOTE. This reads the codebase's actual conventions -- `defineProps`
// with a TypeScript type literal, optionally wrapped in `withDefaults`, and
// BEM-ish modifier classes in the scoped <style>. It does not attempt to be a
// general Vue parser. If a component stops matching, it is listed with its
// props marked UNPARSED rather than silently omitted: a generator that drops
// what it cannot read reproduces the exact failure it exists to prevent.
// =============================================================================

import { readFileSync, writeFileSync, readdirSync } from 'node:fs'
import { join, dirname, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const FRONTEND = join(HERE, '..')
const SRC = join(FRONTEND, 'src')
const REPO = join(FRONTEND, '..')
const UI = join(SRC, 'components', 'ui')
const OUT = join(REPO, 'AIVIS-Design-System.md')

// --------------------------------------------------------------------------
// helpers

function walk(dir, out = []) {
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, e.name)
    if (e.isDirectory()) walk(p, out)
    else out.push(p)
  }
  return out
}

const allFiles = walk(SRC).filter((f) => f.endsWith('.vue') || f.endsWith('.ts') || f.endsWith('.css'))
const fileText = new Map(allFiles.map((f) => [f, readFileSync(f, 'utf8')]))

function styleBlock(text) {
  const m = text.match(/<style[^>]*>([\s\S]*?)<\/style>/)
  return m ? m[1] : ''
}
function scriptBlock(text) {
  const m = text.match(/<script[^>]*>([\s\S]*?)<\/script>/)
  return m ? m[1] : ''
}
// The <template> with HTML comments removed. Everything that asks "is this
// component rendered here?" must go through this, never the raw file.
function templateOf(text) {
  const i = text.indexOf('<template>')
  if (i < 0) return ''
  const rest = text.slice(i)
  const j = rest.indexOf('<style')
  return (j > 0 ? rest.slice(0, j) : rest).replace(/<!--[\s\S]*?-->/g, '')
}

// Balanced-brace slice starting at the first `{` at or after `from`.
function braceSlice(s, from) {
  const start = s.indexOf('{', from)
  if (start < 0) return null
  let depth = 0
  for (let i = start; i < s.length; i++) {
    if (s[i] === '{') depth++
    else if (s[i] === '}') {
      depth--
      if (depth === 0) return { body: s.slice(start + 1, i), end: i }
    }
  }
  return null
}

// --------------------------------------------------------------------------
// props / emits

function parseProps(script) {
  const i = script.indexOf('defineProps<')
  if (i < 0) return { props: [], parsed: true, none: true }
  const sl = braceSlice(script, i)
  if (!sl) return { props: [], parsed: false }

  // defaults from withDefaults(..., { ... })
  let defaults = {}
  const wd = script.indexOf('withDefaults(')
  if (wd >= 0 && wd < i) {
    const after = script.indexOf(')', sl.end)
    const dsl = braceSlice(script, after)
    if (dsl) {
      for (const m of dsl.body.matchAll(/([A-Za-z0-9_]+)\s*:\s*([^,\n]+)/g)) {
        defaults[m[1]] = m[2].trim().replace(/,$/, '')
      }
    }
  }

  const props = []
  // strip comment lines so a commented-out prop is not reported as real
  const body = sl.body.replace(/\/\/[^\n]*/g, '').replace(/\/\*[\s\S]*?\*\//g, '')
  for (const line of body.split('\n')) {
    const m = line.match(/^\s*([A-Za-z0-9_]+)(\?)?\s*:\s*(.+?)\s*$/)
    if (!m) continue
    const [, name, optional, type] = m
    props.push({
      name,
      required: !optional,
      type: type.replace(/,$/, '').trim(),
      default: defaults[name] ?? '',
    })
  }
  return { props, parsed: true }
}

function parseEmits(script) {
  const i = script.indexOf('defineEmits<')
  if (i < 0) return []
  const sl = braceSlice(script, i)
  if (!sl) return []
  const out = []
  for (const m of sl.body.matchAll(/'([^']+)'\s*:\s*\[([^\]]*)\]/g)) out.push(`${m[1]}: [${m[2].trim()}]`)
  return out
}

function parseSlots(template) {
  const named = [...template.matchAll(/<slot\s+name="([^"]+)"/g)].map((m) => m[1])
  const hasDefault = /<slot(\s*\/?>|\s+(?!name=))/.test(template)
  return { named, hasDefault }
}

// Modifier classes declared in the component's own <style>: .c-btn--primary etc.
// Scans for EVERY `.base--mod`, not only those hanging off the template's first
// class: CInput's template root is `.c-input-group` while its modifiers hang off
// `.c-input`, so keying on the root reported "no variants" for it.
function parseModifiers(style) {
  const set = new Set()
  for (const m of style.matchAll(/\.([a-z][a-z0-9-]*)--([a-z0-9-]+)/g)) set.add(`${m[1]}--${m[2]}`)
  return [...set].sort()
}

// --------------------------------------------------------------------------
// component inventory

const uiFiles = readdirSync(UI).filter((f) => f.endsWith('.vue')).sort()
const components = uiFiles.map((f) => {
  const path = join(UI, f)
  const text = readFileSync(path, 'utf8')
  const name = f.replace(/\.vue$/, '')
  const script = scriptBlock(text)
  const style = styleBlock(text)
  const template = (text.match(/<template>([\s\S]*?)<\/template>/) || ['', ''])[1]

  const { props, parsed } = parseProps(script)
  const purpose = (script.match(/^\s*\/\/\s*(.+)$/m) || [])[1] || ''

  // Usage: how many OTHER files actually RENDER this component.
  //
  // Counted in .vue TEMPLATES only, with comments stripped. Scanning whole files
  // counted `//     <CButton` in a .ts comment as a real caller and reported 49
  // where the truth is 48. That is the same failure that inflated this repo's
  // raw-control census from 21 to 22 the same day, from a comment in
  // EventEditor.vue -- a mention of markup is not markup.
  let uses = 0
  const users = []
  for (const [fp, t] of fileText) {
    if (fp === path || !fp.endsWith('.vue')) continue
    const tpl = templateOf(t)
    if (new RegExp('<\\s*' + name + '(?=[\\s/>])').test(tpl)) {
      uses++
      users.push(relative(SRC, fp).replace(/\\/g, '/'))
    }
  }

  return {
    name, file: relative(REPO, path).replace(/\\/g, '/'),
    purpose: purpose.trim(),
    props, parsed,
    emits: parseEmits(script),
    slots: parseSlots(template),
    modifiers: parseModifiers(style),
    uses, users: users.sort(),
  }
})

// --------------------------------------------------------------------------
// tokens

const varsPath = join(SRC, 'styles', 'variables.css')
const varsText = readFileSync(varsPath, 'utf8')

// group by the comment header that precedes each block
const tokenGroups = []
{
  let current = { title: '(ungrouped)', tokens: [] }
  for (const raw of varsText.split('\n')) {
    const header = raw.match(/^\s*\/\*\s*=*\s*(.+?)\s*=*\s*\*\/\s*$/)
    if (header && !/^\s*$/.test(header[1])) {
      if (current.tokens.length) tokenGroups.push(current)
      current = { title: header[1].trim(), tokens: [] }
      continue
    }
    const d = raw.match(/^\s*(--[a-z0-9-]+)\s*:\s*([^;]+);/i)
    if (d) current.tokens.push({ name: d[1], value: d[2].trim() })
  }
  if (current.tokens.length) tokenGroups.push(current)
}

// a token declared more than once is theme-dependent (light block + dark block)
const declCount = new Map()
for (const g of tokenGroups) for (const t of g.tokens) declCount.set(t.name, (declCount.get(t.name) || 0) + 1)

// which tokens does nothing reference?
const allText = [...fileText.values()].join('\n')
const unusedTokens = []
for (const name of new Set([...declCount.keys()])) {
  const re = new RegExp('var\\(\\s*' + name + '\\b')
  if (!re.test(allText)) unusedTokens.push(name)
}

// --------------------------------------------------------------------------
// what does NOT exist -- derived, not asserted

const rawControlSites = []
for (const [fp, t] of fileText) {
  if (!fp.endsWith('.vue')) continue
  if (fp.includes(join('components', 'ui'))) continue
  const tpl = (t.match(/<template>([\s\S]*)/) || ['', ''])[1].split('<style')[0].replace(/<!--[\s\S]*?-->/g, '')
  for (const m of tpl.matchAll(/<\s*(input|select|textarea)(?=[\s/>])([^>]*)/g)) {
    const typeM = m[2].match(/type="([^"]+)"/)
    rawControlSites.push({
      file: relative(SRC, fp).replace(/\\/g, '/'),
      tag: m[1],
      type: typeM ? typeM[1] : '(text)',
    })
  }
}

// --------------------------------------------------------------------------
// render

// A `|` inside a cell ends it, and TypeScript unions are full of them.
const cell = (s) => String(s).replace(/\|/g, '\\|')

const now = new Date().toISOString().slice(0, 10)
const L = []
const p = (s = '') => L.push(s)

p('# AIVIS.ONE — Design System Reference')
p()
p('> **GENERATED FILE — do not edit by hand.** Produced by')
p('> `frontend/scripts/gen-design-system.mjs` from `frontend/src/components/ui/` and')
p('> `frontend/src/styles/variables.css`. Regenerate with:')
p('>')
p('> ```')
p('> npm --prefix frontend run docs:ds')
p('> ```')
p('>')
p('> Any edit made here is lost on the next run. Change the SOURCE instead.')
p()
p(`**Generated:** ${now} · **Components:** ${components.length} · ` +
  `**Tokens:** ${declCount.size} distinct (${[...declCount.values()].reduce((a, b) => a + b, 0)} declarations, ` +
  `the extra ones being theme overrides)`)
p()
p('**Audience: an agent working in this repository.** It answers three questions that otherwise cost a')
p('full read of `components/ui/`: what exists, what each thing accepts, and **what does not exist at all**.')
p()
p('---')
p()
p('## 1. Components')
p()
p('| Component | Used by | Props | Variants |')
p('|---|---:|---|---|')
for (const c of components) {
  const vs = c.modifiers.length ? c.modifiers.map((m) => '`' + m + '`').join(' ') : '—'
  p(`| \`${c.name}\` | ${c.uses} | ${c.props.length || '—'} | ${cell(vs)} |`)
}
p()
const unused = components.filter((c) => c.uses === 0)
if (unused.length) {
  p(`**⚠ USED BY NOTHING: ${unused.map((c) => '`' + c.name + '`').join(', ')}.** A component with no`)
  p('callers accumulates defects unnoticed — `CCard` and `CDivider` both had, and both were deleted for it.')
} else {
  p('**Every component has at least one caller.**')
}
p()

for (const c of components) {
  p(`### \`${c.name}\``)
  p()
  p(`\`${c.file}\``)
  if (c.purpose) p(`> ${c.purpose}`)
  p()
  if (!c.parsed) {
    p('**⚠ PROPS UNPARSED** — this component no longer matches the conventions this generator reads.')
    p('Listed anyway rather than omitted, so the gap is visible. Read the file directly.')
  } else if (!c.props.length) {
    p('**Props:** none.')
  } else {
    p('| Prop | Type | Required | Default |')
    p('|---|---|---|---|')
    for (const pr of c.props) {
      p(`| \`${pr.name}\` | \`${cell(pr.type)}\` | ${pr.required ? '**yes**' : 'no'} | ${pr.default ? '`' + cell(pr.default) + '`' : '—'} |`)
    }
  }
  p()
  if (c.emits.length) p(`**Emits:** ${c.emits.map((e) => '`' + e + '`').join(' · ')}`)
  const slotBits = []
  if (c.slots.hasDefault) slotBits.push('default')
  for (const n of c.slots.named) slotBits.push(`\`${n}\``)
  if (slotBits.length) p(`**Slots:** ${slotBits.join(', ')}`)
  if (c.modifiers.length) p(`**Variant classes:** ${c.modifiers.map((m) => '`.' + m + '`').join(' · ')}`)
  p(`**Used by ${c.uses} file(s)**${c.uses && c.uses <= 8 ? ': ' + c.users.map((u) => '`' + u + '`').join(', ') : ''}`)
  p()
}

p('---')
p()
p('## 2. Tokens')
p()
p('Values are as declared in the **light/base** block. A token marked **±theme** is declared more than')
p('once, meaning a dark-theme or media-query block overrides it — resolve it at runtime, do not assume')
p('the value below applies in every theme.')
p()
for (const g of tokenGroups) {
  if (!g.tokens.length) continue
  p(`### ${g.title}`)
  p()
  p('| Token | Value | |')
  p('|---|---|---|')
  const seen = new Set()
  for (const t of g.tokens) {
    if (seen.has(t.name)) continue
    seen.add(t.name)
    p(`| \`${t.name}\` | \`${cell(t.value)}\` | ${declCount.get(t.name) > 1 ? '±theme' : ''} |`)
  }
  p()
}

if (unusedTokens.length) {
  p(`**⚠ DECLARED BUT REFERENCED BY NOTHING (${unusedTokens.length}):** ` +
    unusedTokens.sort().map((t) => '`' + t + '`').join(', '))
  p()
  p('A token nothing uses is either a gap waiting to be filled or dead weight. `--font-mono` sat in this')
  p('state while twelve raw monospace stacks lived in the views, so the answer is not automatically')
  p('"delete it" — check whether something should have been using it.')
  p()
}

p('---')
p()
p('## 3. What does NOT exist')
p()
p('**The expensive discovery is not which component to use — it is that there is none.** Every raw form')
p('control still living outside the kit is listed below, derived from the templates.')
p()
if (!rawControlSites.length) {
  p('No raw form controls remain outside the kit.')
} else {
  p('| Site | Element |')
  p('|---|---|')
  for (const r of rawControlSites) {
    p(`| \`${r.file}\` | \`<${r.tag} type="${r.type}">\` |`)
  }
  p()
  p('**WHY each one is still raw is NOT derivable from source and is therefore not asserted here.**')
  p('It is recorded in `BATCH-PLAN.md`. As of the last audit: a 6-box OTP control and a `display:none`')
  p('file picker, neither of which the kit has a component for.')
}
p()
p('**No component exists for:** a chip / segmented nav row · a navigation tile (icon + title +')
p('description + chevron) · a file input · a multi-box OTP / code entry · a date or datetime picker')
p('(`CInput` carries the native `type` through instead) · a table.')
p('**Confirm against section 1 before concluding one is missing — this list is written, not derived,**')
p('and is the one part of this document that can go stale.')
p()
p('---')
p()
p('## 4. Conventions that are not visible in the props')
p()
p('- **Attribute pass-through.** `CInput` and `CTextarea` set `inheritAttrs: false` and bind everything')
p('  except `class`/`style` onto the CONTROL. `disabled`, `step`, `min`, `inputmode`, `readonly`,')
p('  `spellcheck` and listeners reach the input; `class` and `style` stay on the group wrapper, so a')
p('  consumer can still position the field. `CSelect` does NOT do this yet.')
p('- **Label association.** `CInput`, `CSelect` and `CTextarea` pair label and control with `useId()`.')
p('  Pass the `label` prop rather than rendering your own `<label>` — a visible caption is not an')
p('  accessible name unless it is associated.')
p('- **Field spacing.** Each field group carries `margin-bottom: var(--space-4)`. Inside a container that')
p('  supplies its own rhythm (a flex column with a `gap`), zero it with a class on the component.')
p('- **Scoped styles reach a child root.** A class passed to a component lands on its root element and')
p('  the parent\'s scoped CSS applies to it.')
p()

writeFileSync(OUT, L.join('\n'), 'utf8')
console.log(`wrote ${relative(REPO, OUT)}`)
console.log(`  components: ${components.length}`)
console.log(`  tokens: ${declCount.size} distinct`)
console.log(`  unparsed components: ${components.filter((c) => !c.parsed).length}`)
console.log(`  components with no callers: ${unused.length}`)
console.log(`  raw form controls outside the kit: ${rawControlSites.length}`)
