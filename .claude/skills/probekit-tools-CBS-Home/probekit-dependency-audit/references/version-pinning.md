# Version Pinning Audit Guide

## Pinning Levels by Ecosystem

### Python (pip/poetry)

| Format | Level | Severity |
|--------|-------|----------|
| `requests` | Unpinned | 🔴 CRITICAL |
| `requests>=2.0` | Lower bound only | 🔴 CRITICAL |
| `requests>=2.28,<3` | Range | 🟡 WARNING (ok with lock) |
| `requests~=2.31` | Compatible release | 🟡 WARNING (ok with lock) |
| `requests==2.31.0` | Exact pin | 🟢 OK |
| Exact pin + `requirements.lock` / `poetry.lock` | Exact + lock | ✅ BEST |

### npm

| Format | Level | Severity |
|--------|-------|----------|
| `"*"` or `"latest"` | Wildcard | 🔴 CRITICAL |
| `">=4.0.0"` | Lower bound | 🔴 CRITICAL |
| `"^4.17.0"` | Caret (minor float) | 🟡 WARNING (ok with lock) |
| `"~4.17.21"` | Tilde (patch float) | 🟢 OK with lock |
| `"4.17.21"` | Exact | 🟢 OK |
| Exact + `package-lock.json` committed | Exact + lock | ✅ BEST |

### Go

| Format | Level | Severity |
|--------|-------|----------|
| No `go.sum` | No integrity check | 🔴 CRITICAL |
| `go.mod` + `go.sum` present | Pinned with checksum | ✅ BEST |

### Rust

| Format | Level | Severity |
|--------|-------|----------|
| `"*"` in Cargo.toml | Wildcard | 🔴 CRITICAL |
| SemVer range without Cargo.lock | Range only | 🟡 WARNING |
| SemVer + `Cargo.lock` committed | Pinned | ✅ BEST |

---

## Lock File Checks

| Check | Result |
|-------|--------|
| Lock file exists and committed to git | ✅ Good |
| Lock file exists but in `.gitignore` | 🔴 CRITICAL — defeats purpose |
| Lock file missing, manifest has ranges | 🟡 WARNING — builds not reproducible |
| Lock file missing, all exact pins | 🟢 OK — acceptable |

---

## Scoring

```
pinning_score = (exact_count + lock_bonus) / total_deps × 10

exact_count = deps with exact pin or lock coverage
lock_bonus = +1 if lock file committed
total_deps = total dependency count

Thresholds:
  ≥ 8/10: PASS
  5–7/10: WARN
  < 5/10: FAIL
```
