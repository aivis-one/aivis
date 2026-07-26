# Dependency Risk Signals

## Typosquatting Detection

### Algorithm
1. For each dependency name, compute Levenshtein distance to top-500 packages
2. Flag if distance ≤ 2 from a popular package AND the dependency is NOT the popular package itself

### Common Substitution Patterns
- Character swap: `0↔o`, `1↔l↔i`, `rn↔m`, `vv↔w`
- Missing character: `reac` (react), `expres` (express)
- Doubled character: `expresss`, `lodaash`
- Hyphen/underscore: `node_fetch` vs `node-fetch`
- Scope stripping: `@babel/core` → `babel-core-new`

### Known Typosquat Targets (top examples)

**npm**: lodash, react, express, axios, chalk, moment, webpack, commander, typescript, eslint, next, vue, angular, jquery, underscore

**PyPI**: requests, numpy, pandas, django, flask, boto3, setuptools, urllib3, pip, colorama, beautifulsoup4, scrapy, pillow, cryptography

### Severity
- Distance 1 from top-100 package: 🔴 CRITICAL
- Distance 2 from top-100 package: 🟡 WARNING
- Distance 1-2 from top-500 package: 🟡 WARNING

---

## Suspicious Install Scripts (npm)

### Red Flags in postinstall/preinstall
- Contains `curl`, `wget`, `http.get`, `https.get` → 🔴 network access
- Contains `child_process`, `exec`, `spawn` → 🔴 shell execution
- Contains `eval(`, `Function(` → 🔴 code execution
- Contains `Buffer.from(` + `toString(` → 🟡 possible obfuscation
- Contains `fs.readFile('/etc/` or `process.env` exfiltration patterns → 🔴

### Legitimate postinstall (do not flag)
- `node-gyp rebuild` for native addons (sharp, sqlite3, canvas, bcrypt)
- `patch-package` for patching deps
- `husky install` for git hooks
- `ngcc` for Angular compatibility

---

## Import/Manifest Mismatch

### Python
Scan for `import X` and `from X import ...` in `.py` files.
Check each X against:
1. Python stdlib modules (don't flag)
2. Entries in requirements.txt / pyproject.toml
3. Local project modules (relative imports, project packages)

Flag 🟡 WARNING if import not found in manifest AND not stdlib AND not local.

### Node.js
Scan for `require('X')` and `import ... from 'X'` in `.js/.ts` files.
Check each X against:
1. Node built-in modules (`fs`, `path`, `http`, etc.)
2. Entries in package.json dependencies/devDependencies
3. Relative imports (`./`, `../`)

Flag 🟡 WARNING if external import not in package.json.

---

## Abandonment Signals (observable from local files)

| Signal | Where to check | Severity |
|--------|---------------|----------|
| `deprecated` field in package.json | package.json | 🟡 WARNING |
| Version in lock file > 2 years old | lock file timestamps | 🟡 WARNING |
| Package not maintained note in README | README of dependency (if vendored) | 🟢 SUGGESTION |
