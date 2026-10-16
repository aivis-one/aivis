# Probe Definitions — probekit-project-hygiene

## Probe 1: PH-DEAD-FILES

**Purpose:** Find source files with zero imports or references anywhere in the codebase.

**Detection method:**
1. List all git-tracked source files (*.ts, *.vue, *.py, *.js, *.css, *.html)
2. For each file, extract its module name (filename without extension)
3. Grep the entire codebase for references to that module name
4. Exclude self-references (the file itself)
5. Exclude known entry points: main.ts, index.html, App.vue, vite.config.ts, vitest.config.ts, *.config.js
6. Exclude config-referenced files: check package.json scripts, vite plugins, etc.
7. Grace period: if file was modified in git within last 30 days, mark as REVIEW not DELETE

**Thresholds:**
| Size | Severity |
|------|----------|
| < 1 KB | 🟢 SUGGESTION |
| 1-50 KB | 🟡 WARNING |
| > 50 KB | 🔴 CRITICAL |

---

## Probe 2: PH-DEAD-CODE

**Purpose:** Find unused exports within source files.

**Detection method:**
1. For each source file, extract all `export` statements (named exports, default exports)
2. For each exported symbol, grep across all other source files for import of that symbol
3. Flag exports with zero external imports
4. Skip: type-only exports (interfaces, type aliases) — they may be used by TypeScript without import
5. Skip: re-exports from index.ts barrel files

**Thresholds:**
| Dead exports per file | Severity |
|----------------------|----------|
| 1-2 unused exports | 🟢 SUGGESTION |
| 3-5 unused exports | 🟡 WARNING |
| > 5 unused exports or entire file is dead | 🔴 CRITICAL |

---

## Probe 3: PH-DUPLICATES

**Purpose:** Find files with identical or near-identical content.

**Detection method:**
1. Group files by size (exact byte count)
2. For files with identical sizes: compute content hash (first 4KB + last 4KB for speed)
3. For exact hash matches: flag as duplicate pair
4. For files with same basename in different directories: compare first 50 lines
5. Report which copy is the "primary" (more recently modified or in more central location)

**Thresholds:**
| Duplicate size | Severity |
|---------------|----------|
| < 5 KB | 🟢 SUGGESTION |
| 5-100 KB | 🟡 WARNING |
| > 100 KB | 🔴 CRITICAL |

---

## Probe 4: PH-STALE-DEPS

**Purpose:** Find declared dependencies never imported in source code.

**Detection method:**
For JavaScript/TypeScript (package.json):
1. Read dependencies + devDependencies
2. For each package: grep `from ['"]PACKAGE` and `require(['"]PACKAGE` across all source files
3. Also check: vite.config.ts plugins, eslint.config.js extends, vitest.config.ts
4. Whitelist CLI-only tools: eslint, prettier, vitest, husky, lint-staged, vue-tsc, typescript
5. Whitelist Vite plugins: check vite.config.ts for plugin() calls
6. Whitelist type packages: @types/* (used by TypeScript compiler, not imported)

For Python (requirements.txt / pyproject.toml):
1. Read all declared packages
2. Grep for `import PACKAGE` and `from PACKAGE import` across all .py files

**Thresholds:**
| Unused deps | Severity |
|-------------|----------|
| 1-2 stale deps | 🟢 SUGGESTION |
| 3-5 stale deps | 🟡 WARNING |
| > 5 stale deps | 🔴 CRITICAL |

---

## Probe 5: PH-UNUSED-CONFIG

**Purpose:** Find configuration entries with no code reference.

**Detection method:**
1. Read .env.example (or .env.sample): extract variable names
2. For each variable: grep for `process.env.VARNAME`, `import.meta.env.VARNAME`, `os.environ[VARNAME]`, `settings.VARNAME` across source
3. Read other config files: docker-compose.yml, Dockerfile — check for unused build args, services
4. Check for commented-out config blocks (# or //) that should be removed

**Thresholds:**
| Unused configs | Severity |
|---------------|----------|
| 1-3 unused vars | 🟢 SUGGESTION |
| 4-8 unused vars | 🟡 WARNING |
| > 8 unused vars | 🔴 CRITICAL |

---

## Probe 6: PH-ORPHAN-TESTS

**Purpose:** Find test files whose target module no longer exists.

**Detection method:**
1. List all test files (*.test.ts, *.test.py, *.spec.ts, *_test.py)
2. For each test file: extract the module it tests from:
   - Import statement (e.g., `import { useAuthStore } from '@/stores/auth'`)
   - File naming convention (e.g., `auth.test.ts` → `stores/auth.ts`)
3. Check if the target module file exists on disk
4. Flag orphan tests where target is deleted/moved

**Thresholds:**
| Orphan test | Severity |
|-------------|----------|
| Any orphan test | 🟡 WARNING (tests should match code) |

---

## Probe 7: PH-ARCHIVE-DUPS

**Purpose:** Find files in archive/ directories identical to active files.

**Detection method:**
1. List all files in archive/ (or similar: backup/, old/, deprecated/)
2. For each archived file: compute content hash
3. Compare against content hashes of all files in active directories (src/, docs/, etc.)
4. Flag exact matches as duplicates

**Thresholds:**
| Archive dup size | Severity |
|-----------------|----------|
| < 10 KB | 🟢 SUGGESTION |
| 10-100 KB | 🟡 WARNING |
| > 100 KB | 🔴 CRITICAL |

---

## Probe 8: PH-EMPTY-DIRS

**Purpose:** Find empty directories or .gitkeep-only directories.

**Detection method:**
1. Walk directory tree of git-tracked content
2. Find directories containing zero files (or only .gitkeep)
3. Check if directory is referenced in documentation as a placeholder
4. Check if directory is in a pattern like `src/components/shared/` that will be populated later

**Thresholds:**
| Empty dir context | Severity |
|------------------|----------|
| Documented placeholder | 🟢 SUGGESTION |
| Undocumented empty dir | 🟡 WARNING |

---

## Probe 9: PH-STALE-DOCS

**Purpose:** Find documentation with broken file path references.

**Detection method:**
1. List all .md files in docs/
2. For each file: extract inline file path references using regex:
   - Backtick paths: `src/api/users.ts`
   - Table cell paths: `| docs/01_refer/FILE.md |`
   - Reference links: `[text](path/to/file.md)`
3. For each extracted path: check if it exists relative to project root
4. Ignore: URLs (https://...), anchors (#section), command examples
5. Flag broken paths

**Thresholds:**
| Broken refs per doc | Severity |
|--------------------|----------|
| 1-2 broken refs | 🟢 SUGGESTION |
| 3-5 broken refs | 🟡 WARNING |
| > 5 broken refs | 🔴 CRITICAL |

---

## Probe 10: PH-GIT-BLOAT

**Purpose:** Find large files tracked by git that should use LFS or be excluded.

**Detection method:**
1. Run `git ls-files` with sizes
2. Flag files > 100 KB that are binary (images, archives, compiled)
3. Flag ANY file > 500 KB regardless of type
4. Identify candidates for Git LFS migration
5. Check .gitignore for patterns that should exist but don't

**Binary detection:** Check file extension against known binary types:
.jpg, .jpeg, .png, .gif, .svg (if > 100KB), .ico, .woff, .woff2, .ttf,
.zip, .tar, .gz, .mp3, .mp4, .pdf, .exe, .dll, .so, .dylib

**Thresholds:**
| File size | Severity |
|-----------|----------|
| 100-500 KB binary | 🟡 WARNING |
| > 500 KB any file | 🔴 CRITICAL |
| package-lock.json (any size) | exempt (required for reproducible builds) |
