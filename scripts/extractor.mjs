// =============================================================================
// ui-extractor (alpha) -- deterministic snapshot of a Vue 3 design system.
//
// WHAT IT DOES (alpha scope -- stages 1-3 + emit):
//   1. Discover & classify every src/**/*.vue (ui | domain | layout | view).
//   2. Contract  -- props / emits / slots via vue-component-meta (TS-accurate).
//   3. Composition -- child components used in <template>, resolved through
//      <script setup> imports + the tsconfig `@` alias. Blind spots
//      (dynamic <component :is>, unresolved tags) are surfaced in `gaps`,
//      never dropped silently.
//   Emit -- one flat observed.yaml. No signatures/clustering yet (that is the
//   "enrich" pass), no tokens, no CI, no write-back.
//
// USAGE:
//   node extractor.mjs <frontendRoot> [outFile] [--repo X] [--ref Y] [--tsconfig FILE]
//   node extractor.mjs /src/frontend /out/observed.yaml --repo aivis-one/cbshome --ref main
//   (outFile omitted or "-" => stdout; --tsconfig defaults to tsconfig.json)
//
// Requires (installed in the target frontend): vue, typescript,
// vue-component-meta, @vue/compiler-sfc, @vue/compiler-dom, js-yaml.
// =============================================================================

import fs from 'node:fs'
import path from 'node:path'
import { createChecker } from 'vue-component-meta'
import { parse as parseSfc } from '@vue/compiler-sfc'
import yaml from 'js-yaml'
import ts from 'typescript'

// ---- template parser: prefer compiler-dom, fall back to compiler-core --------
let parseTemplate
try {
  ({ parse: parseTemplate } = await import('@vue/compiler-dom'))
  if (typeof parseTemplate !== 'function') throw new Error('no parse')
} catch {
  const core = await import('@vue/compiler-core')
  parseTemplate = core.baseParse
}

// ---- args -------------------------------------------------------------------
const argv = process.argv.slice(2)
const positional = argv.filter((a) => !a.startsWith('--'))
const flag = (name) => {
  const i = argv.indexOf(`--${name}`)
  return i !== -1 && argv[i + 1] ? argv[i + 1] : null
}
const FRONTEND_ROOT = path.resolve(positional[0] || '.')
const OUT_FILE = positional[1] || '-'
const REPO = flag('repo')
const REF = flag('ref')
// Some Vite setups keep paths/baseUrl in tsconfig.app.json while tsconfig.json
// only holds project references. --tsconfig lets you point at the right one.
const TSCONFIG = flag('tsconfig') || 'tsconfig.json'
// Bump on any behavior change so a run self-identifies which build produced it
// (appears in stderr and in the output's meta.extractor).
const BUILD = 'alpha-b2 barrel-aware'

// ---- tsconfig alias resolution (via the TypeScript config parser) -----------
// Hand-rolling JSONC stripping is unsafe: tsconfig paths contain "/*" and "*/"
// (e.g. "@/*", "src/**/*.ts"), which a naive block-comment regex would eat.
// TypeScript's own parser handles comments, trailing commas and `extends`.
function loadAliases(tsconfigPath) {
  let options = {}
  try {
    const read = ts.readConfigFile(tsconfigPath, ts.sys.readFile)
    options = ts.parseJsonConfigFileContent(
      read.config || {}, ts.sys, path.dirname(tsconfigPath)
    ).options || {}
  } catch {
    /* no/invalid tsconfig -> only relative imports resolve */
  }
  const baseAbs = options.baseUrl || options.pathsBasePath || path.dirname(tsconfigPath) // absolute
  const rules = []
  for (const [pattern, targets] of Object.entries(options.paths || {})) {
    if (!targets || !targets.length) continue
    rules.push({ from: pattern.replace(/\*$/, ''), to: String(targets[0]).replace(/\*$/, '') })
  }
  return { baseAbs, rules }
}

// Resolve a bare import spec to an absolute path (or null if external module).
function resolveImport(spec, importerAbs, aliases) {
  if (spec.startsWith('./') || spec.startsWith('../')) {
    return path.resolve(path.dirname(importerAbs), spec)
  }
  for (const { from, to } of aliases.rules) {
    if (from && spec.startsWith(from)) {
      return path.resolve(aliases.baseAbs, to + spec.slice(from.length))
    }
  }
  return null // node_module / external (e.g. lucide-vue-next, vue-router)
}

// ---- barrel/index re-export resolution --------------------------------------
// Components are often re-exported from a folder index, e.g.
//   export { default as CButton } from './CButton.vue'
// and imported as `import { CButton } from '@/components/ui'`. Such an import
// resolves to a directory, not a .vue, so we read the index and map the
// exported name -> the real .vue file. Parsed indexes are cached.
const barrelCache = new Map() // indexFile -> Map(exportName -> vueAbs)

function parseBarrel(indexFile) {
  if (barrelCache.has(indexFile)) return barrelCache.get(indexFile)
  const out = new Map()
  try {
    const src = fs.readFileSync(indexFile, 'utf8')
    const dir = path.dirname(indexFile)
    const re = /export\s*\{([^}]*)\}\s*from\s*['"]([^'"]+)['"]/g
    let m
    while ((m = re.exec(src))) {
      const targetAbs = path.resolve(dir, m[2])
      if (!targetAbs.endsWith('.vue')) continue // one re-export level (alpha)
      for (const part of m[1].split(',')) {
        const t = part.trim()
        if (!t) continue
        const as = t.match(/\bas\s+([A-Za-z0-9_$]+)$/) // "default as Name" | "Orig as Name"
        out.set(as ? as[1] : t, targetAbs)
      }
    }
  } catch { /* unreadable index -> empty map */ }
  barrelCache.set(indexFile, out)
  return out
}

// Map a matched component import to its .vue file.
// Returns { vue } | { external: true } | { unresolved: true }.
function resolveComponentVue(entry, importerAbs, aliases) {
  const resolved = resolveImport(entry.spec, importerAbs, aliases)
  if (resolved === null) return { external: true }        // node_module
  if (resolved.endsWith('.vue')) return { vue: resolved }  // direct .vue import

  // Otherwise the import points at a folder/index (a barrel). Find its index.
  let dir = resolved
  let indexFile = null
  try {
    if (fs.existsSync(resolved) && fs.statSync(resolved).isDirectory()) {
      for (const f of ['index.ts', 'index.js', 'index.mts', 'index.cts']) {
        const p = path.join(resolved, f)
        if (fs.existsSync(p)) { indexFile = p; break }
      }
    } else {
      for (const ext of ['.ts', '.js', '.mts', '.cts']) { // ".../ui" -> ui.ts
        if (fs.existsSync(resolved + ext)) { indexFile = resolved + ext; break }
      }
      dir = path.dirname(resolved)
    }
  } catch { /* ignore */ }

  if (indexFile) {
    const hit = parseBarrel(indexFile).get(entry.exportName)
    if (hit) return { vue: hit }
  }
  // Fallback: file name == component name (the convention in this project).
  const guess = path.join(dir, `${entry.exportName}.vue`)
  if (fs.existsSync(guess)) return { vue: guess }

  return { unresolved: true } // local import we could not pin to a .vue
}

// ---- file discovery ---------------------------------------------------------
function walk(dir, hit) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === 'node_modules' || entry.name.startsWith('.')) continue
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) walk(full, hit)
    else hit(full)
  }
}

function classify(relPath) {
  const p = relPath.replace(/\\/g, '/')
  if (p.startsWith('src/views/')) return 'view'
  if (p.startsWith('src/components/layout/')) return 'layout'
  if (p.startsWith('src/components/ui/')) return 'ui'
  if (p.startsWith('src/components/')) return 'domain'
  return 'other'
}

// ---- script-setup helpers ---------------------------------------------------
function extractRole(scriptContent) {
  if (!scriptContent) return null
  const lines = scriptContent.split('\n')
  const out = []
  for (const line of lines) {
    const t = line.trim()
    if (t === '') {
      if (out.length) break // blank line ends the leading comment block
      continue
    }
    if (t.startsWith('//')) {
      out.push(t.replace(/^\/\/\s?/, ''))
    } else if (t.startsWith('/*')) {
      out.push(t.replace(/^\/\*+\s?/, '').replace(/\*+\/\s*$/, ''))
      if (t.includes('*/')) break
    } else {
      break // first real code line
    }
  }
  const text = out.join(' ').trim()
  return text || null
}

// Capture default + named imports.
//   localName -> { spec, exportName }
// exportName is the name the module exports under (before any `as`); it is what
// a barrel/index re-exports by. For default imports exportName is 'default'.
function extractImports(scriptContent) {
  const map = {}
  if (!scriptContent) return map
  const re = /import\s+(?:type\s+)?(?:([A-Za-z0-9_$]+)\s*,?\s*)?(?:\{([^}]*)\})?\s*from\s*['"]([^'"]+)['"]/g
  let m
  while ((m = re.exec(scriptContent))) {
    const [, def, named, spec] = m
    if (def) map[def] = { spec, exportName: 'default' }
    if (named) {
      for (const part of named.split(',')) {
        const t = part.trim()
        if (!t) continue
        const as = t.match(/^([A-Za-z0-9_$]+)\s+as\s+([A-Za-z0-9_$]+)$/)
        if (as) map[as[2]] = { spec, exportName: as[1] } // { Orig as Local }
        else map[t] = { spec, exportName: t }            // { Name }
      }
    }
  }
  return map
}

// Vue / vue-router builtins that are never design-system components.
// Stored "flattened" (lowercased, hyphens removed) so <RouterLink> and
// <router-link> both match. component/router-view are handled separately.
const BUILTINS = new Set([
  'transition', 'transitiongroup', 'keepalive', 'teleport',
  'suspense', 'slot', 'template', 'routerlink',
])
const flatten = (tag) => tag.toLowerCase().replace(/-/g, '')
const kebabToPascal = (s) => s.replace(/(^|-)([a-z])/g, (_, __, c) => c.toUpperCase())
const isComponentTag = (tag) => /[A-Z]/.test(tag) || tag.includes('-')

// Walk the template AST, collecting component tags + blind-spot signals.
function scanTemplate(templateContent) {
  const tags = new Set()
  let hasDynamic = false
  let usesRouterView = false
  let root
  try {
    root = parseTemplate(templateContent)
  } catch {
    return { tags, hasDynamic, usesRouterView, parseError: true }
  }
  const visit = (node) => {
    if (!node) return
    if (node.type === 1) { // ELEMENT
      const tag = node.tag
      const flat = flatten(tag)
      if (flat === 'routerview') usesRouterView = true
      else if (flat === 'component') {
        // dynamic <component :is="..."> -> bind directive with arg "is"
        const dyn = (node.props || []).some(
          (p) => p.name === 'bind' && p.arg && p.arg.content === 'is'
        )
        hasDynamic = hasDynamic || dyn
      } else if (!BUILTINS.has(flat) && isComponentTag(tag)) {
        tags.add(tag)
      }
    }
    if (Array.isArray(node.children)) node.children.forEach(visit)
    if (Array.isArray(node.branches)) node.branches.forEach(visit) // v-if
  }
  visit(root)
  return { tags, hasDynamic, usesRouterView, parseError: false }
}

// ---- router parse (which views are route-mounted screens) -------------------
function collectRoutedViews(root, aliases) {
  const routed = new Set()
  const routerDir = path.join(root, 'src', 'router')
  if (!fs.existsSync(routerDir)) return routed
  const re = /import\(\s*['"]([^'"]+\.vue)['"]\s*\)/g
  walk(routerDir, (file) => {
    if (!file.endsWith('.ts')) return
    const src = fs.readFileSync(file, 'utf8')
    let m
    while ((m = re.exec(src))) {
      const abs = resolveImport(m[1], file, aliases)
      if (abs) routed.add(path.relative(root, abs).replace(/\\/g, '/'))
    }
  })
  return routed
}

// ---- main -------------------------------------------------------------------
function main() {
  process.stderr.write(`>> ui-extractor ${BUILD}\n`)
  const tsconfigPath = path.isAbsolute(TSCONFIG) ? TSCONFIG : path.join(FRONTEND_ROOT, TSCONFIG)
  const aliases = loadAliases(tsconfigPath)
  const checker = createChecker(tsconfigPath, {
    forceUseTs: true,
    printer: { newLine: 1 },
  })

  const srcDir = path.join(FRONTEND_ROOT, 'src')
  const vueFiles = []
  if (fs.existsSync(srcDir)) walk(srcDir, (f) => { if (f.endsWith('.vue')) vueFiles.push(f) })
  vueFiles.sort()

  const routed = collectRoutedViews(FRONTEND_ROOT, aliases)
  const nameByPath = {} // rel path -> component name
  const records = []
  const gapsDynamic = []
  const gapsUnresolved = []
  const gapsErrors = [] // per-file failures, so one bad SFC can't kill the scan

  for (const abs of vueFiles) {
    const rel = path.relative(FRONTEND_ROOT, abs).replace(/\\/g, '/')
    const name = path.basename(abs, '.vue')
    nameByPath[rel] = name
    try {
      const source = fs.readFileSync(abs, 'utf8')
      const { descriptor } = parseSfc(source, { filename: abs })
      const scriptContent =
        (descriptor.scriptSetup && descriptor.scriptSetup.content) ||
        (descriptor.script && descriptor.script.content) || ''
      const templateContent = (descriptor.template && descriptor.template.content) || ''

      // --- contract via vue-component-meta ---
      const meta = checker.getComponentMeta(abs)
      const props = (meta.props || [])
        .filter((p) => !p.global)
        .map((p) => {
          let type = p.type
          if (p.required === false && typeof type === 'string') {
            type = type.replace(/\s*\|\s*undefined$/, '') // optional implies undefined
          }
          const rec = { name: p.name, type, required: !!p.required }
          if (p.default !== undefined) rec.default = p.default
          return rec
        })
      const emits = (meta.events || []).map((e) => ({ name: e.name, payload: e.type }))
      const slots = (meta.slots || []).map((s) => ({ name: s.name }))

      // --- composition via template + imports ---
      const imports = extractImports(scriptContent)
      const { tags, hasDynamic, usesRouterView, parseError } = scanTemplate(templateContent)
      const composes = new Set()
      for (const tag of tags) {
        const local = imports[tag] !== undefined ? tag
          : imports[kebabToPascal(tag)] !== undefined ? kebabToPascal(tag) : null
        if (!local) { gapsUnresolved.push({ in: rel, tag }); continue }
        const r = resolveComponentVue(imports[local], abs, aliases)
        if (r.vue) composes.add(path.basename(r.vue, '.vue'))
        else if (r.unresolved) gapsUnresolved.push({ in: rel, tag })
        // r.external (lucide etc.) -> neither a local edge nor a gap
      }
      if (hasDynamic) gapsDynamic.push({ in: rel, note: '<component :is> — resolve target manually' })
      if (parseError) gapsUnresolved.push({ in: rel, tag: '(template parse failed)' })

      records.push({
        name,
        kind: classify(rel),
        path: rel,
        role: extractRole(scriptContent),
        routed: routed.has(rel),
        routerViewSeam: usesRouterView,
        props,
        emits,
        slots,
        composes: [...composes].sort(),
      })
    } catch (err) {
      // Keep the component visible (with an error marker) instead of aborting.
      const msg = String((err && err.message) || err).slice(0, 300)
      records.push({
        name, kind: classify(rel), path: rel, role: null, error: msg,
        routed: routed.has(rel), routerViewSeam: false,
        props: [], emits: [], slots: [], composes: [],
      })
      gapsErrors.push({ in: rel, error: msg })
    }
  }

  // --- reverse edges: usedBy ---
  const usedBy = {}
  for (const r of records) for (const child of r.composes) {
    (usedBy[child] ||= new Set()).add(r.name)
  }
  for (const r of records) r.usedBy = [...(usedBy[r.name] || [])].sort()

  // --- order: kind then name ---
  const kindOrder = { ui: 0, domain: 1, layout: 2, view: 3, other: 4 }
  records.sort((a, b) =>
    (kindOrder[a.kind] - kindOrder[b.kind]) || a.name.localeCompare(b.name))

  const out = {
    meta: {
      repo: REPO || undefined,
      ref: REF || undefined,
      generatedAt: new Date().toISOString(),
      frontendRoot: path.relative(process.cwd(), FRONTEND_ROOT) || '.',
      componentCount: records.length,
      extractor: `ui-extractor ${BUILD}`,
    },
    components: records,
    gaps: { dynamicComponents: gapsDynamic, unresolvedTags: gapsUnresolved, extractionErrors: gapsErrors },
  }

  const text =
    '# observed.yaml — disposable design-system snapshot extracted from source.\n' +
    '# GENERATED by ui-extractor (alpha). Do not edit; re-run the scan instead.\n' +
    yaml.dump(out, { lineWidth: -1, noRefs: true, sortKeys: false, skipInvalid: true })

  if (OUT_FILE === '-') process.stdout.write(text)
  else { fs.writeFileSync(OUT_FILE, text); process.stderr.write(`wrote ${OUT_FILE} (${records.length} components)\n`) }
}

main()
