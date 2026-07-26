# ProbeKit Environment Detection — Core Reference

Standard procedure for detecting project environment. All ProbeKit skills use this.

## Step 1 — Read ENVIRONMENT.md

Check for `ENVIRONMENT.md` in the project (common locations: root, `docs/`, `docs/01_refer/`).
If found — read it for shell type, tool pitfalls, project paths, known issues.
Never hardcode shell syntax — adapt to the detected environment.

## Step 2 — Detect Shell

| Signal | Shell |
|--------|-------|
| `$env:`, `Get-`, `.ps1` in history | PowerShell |
| `/bin/bash`, `#!/bin/bash`, `.bashrc` | Bash |
| `/bin/zsh`, `.zshrc` | Zsh |
| `COMSPEC` contains `cmd.exe` | CMD (rare) |

Shell-specific rules:
- **PowerShell**: use single quotes for `-k` patterns in pytest; use `&` to call executables with spaces; use `/dev/null` equivalent `$null`; semicolons to chain commands
- **Bash/Zsh**: standard Unix invocation; use `&&` to chain; redirect to `/dev/null`
- Always quote paths with spaces using double quotes

## Step 3 — Detect Language and Framework

Scan project root for markers in this priority order:

### Python
| Marker | Framework |
|--------|-----------|
| `pyproject.toml` with `[tool.pytest]` | pytest |
| `pytest.ini`, `setup.cfg [tool:pytest]` | pytest |
| `requirements.txt`, `Pipfile`, `poetry.lock` | Python project |
| `from fastapi` in source | FastAPI |
| `from flask` in source | Flask |
| `from django` in source | Django |
| `import sqlalchemy` in source | SQLAlchemy |

### JavaScript / TypeScript
| Marker | Framework |
|--------|-----------|
| `package.json` with `"jest"` | Jest |
| `package.json` with `"vitest"` | Vitest |
| `package.json` with `"mocha"` | Mocha |
| `next.config.*` | Next.js |
| `express` in dependencies | Express |
| `.ts` files + `tsconfig.json` | TypeScript |

### Go
| Marker | Framework |
|--------|-----------|
| `go.mod` | Go project |
| `*_test.go` files | Go testing (stdlib) |
| `testify` in `go.mod` | Testify |

### GDScript / Godot
| Marker | Framework |
|--------|-----------|
| `project.godot` | Godot project |
| `addons/gut/` directory | GUT test framework |
| `.gutconfig.json` | GUT configured |
| `.gd` file extensions | GDScript |

### Java
| Marker | Framework |
|--------|-----------|
| `pom.xml` | Maven |
| `build.gradle` | Gradle |
| JUnit imports in test files | JUnit |

### Rust
| Marker | Framework |
|--------|-----------|
| `Cargo.toml` | Cargo |
| `#[test]` in source | Rust test |

## Step 4 — Detect Test Structure

Look for existing test directories and conventions:
- `tests/`, `test/`, `__tests__/`, `spec/`, `specs/`
- `*_test.go`, `test_*.py`, `*.test.ts`, `*.spec.ts`
- `conftest.py`, `jest.config.*`, `vitest.config.*`
- `res://test/` (Godot)

If existing tests found → match their conventions (naming, location, fixtures).
If no tests found → use language-standard defaults.

## Step 5 — Detect Package Manager

| Marker | Manager |
|--------|---------|
| `package-lock.json` | npm |
| `yarn.lock` | Yarn |
| `pnpm-lock.yaml` | pnpm |
| `poetry.lock` | Poetry |
| `Pipfile.lock` | Pipenv |
| `requirements.txt` (alone) | pip |
| `go.sum` | Go modules |
| `Cargo.lock` | Cargo |

## Step 6 — Prerequisite Check (REQUIRED)

After detecting environment, verify that required tools are available.
**Fail fast with clear message** if prerequisites are missing.

### Check Matrix

| Detected Stack | Check | Command | Fail Message |
|----------------|-------|---------|-------------|
| Node/npm | node_modules exists | `ls {project}/node_modules/.package-lock.json` | "Dependencies not installed. Run `npm install` first." |
| Node/npm | node available | `node -v` | "Node.js not found. Install Node.js." |
| TypeScript | tsconfig exists | `ls {project}/tsconfig.json` | "tsconfig.json not found. Cannot run type checks." |
| Python | python available | `python --version` or `python3 --version` | "Python not found." |
| Python | venv or deps | `ls {project}/.venv` or `pip list` | "Python environment not set up. Run `pip install -r requirements.txt` or create venv." |
| Python/pytest | pytest available | `python -m pytest --version` | "pytest not found. Run `pip install pytest`." |
| Go | go available | `go version` | "Go not found." |
| Godot/GUT | gut addon | `ls addons/gut/` | "GUT not installed." |
| ESLint | eslint available | `npx eslint --version` | "ESLint not configured." |
| Vitest | vitest available | `npx vitest --version` | "Vitest not found. Run `npm install`." |

### Behavior

1. Run checks relevant to detected stack only (don't check Python for a JS project)
2. If ANY required check fails:
   - Log: `PREREQ-FAIL: {tool} — {message}`
   - Offer to fix if possible (e.g., run `npm install`)
   - If cannot fix → **STOP skill execution**, report clearly to user
3. If all checks pass:
   - Log: `PREREQ-OK: {language}/{framework}/{test_framework}`
   - Continue to skill execution

### Optional vs Required

| Check | Required? | Notes |
|-------|-----------|-------|
| Runtime (node/python/go) | ✅ Required | Cannot proceed without |
| Dependencies (node_modules/.venv) | ✅ Required | Commands will fail |
| Config files (tsconfig/pyproject) | ✅ Required | Analysis needs config |
| Test framework (vitest/pytest) | ⚠️ Required for test skills | Skip for audit-only skills |
| Linter (eslint/ruff) | ⚠️ Optional | Warn but continue if missing |
| Build tools (vite/webpack) | ⚠️ Optional | Only needed for build checks |

## Usage in Skills

Each skill should run environment detection in Step 1 and record:
- `language`: primary language
- `framework`: web/test framework
- `shell`: shell type for command execution
- `test_framework`: test runner
- `package_manager`: dependency manager
- `existing_tests`: boolean + location
- `prereqs_ok`: boolean (from Step 6)

Pass these to all subsequent steps. Never assume — always detect.
