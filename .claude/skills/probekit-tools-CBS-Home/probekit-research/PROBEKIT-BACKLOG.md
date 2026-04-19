# ProbeKit Ecosystem — Backlog

Бэклог проблем, недоработок и будущих улучшений экосистемы ProbeKit.
Приоритет реализации — после переезда на Linux сервер.

---

## Выполнено

### DONE: Tier 0 — Runtime Health Blind Spot (2026-03-29)

Создана пара health-audit скилов, закрывающих системную слепую зону —
ProbeKit никогда не проверял runtime-артефакты (логи, БД, мёртвые файлы, config drift).

Обнаружено при ручном анализе: 482 MB мусора (3x лог-дупликация 176 MB, episodic memory
357K мусорных строк 121 MB, мёртвый vendored Python 142 MB) — ни один из 12 скилов
не нашёл эти проблемы за 10 спринтов аудитов.

**Создано:**
- `probekit-health-audit` v1.0.0 — универсальный (7 проб: disk-bloat, log-rotation, log-duplication, db-growth, dead-files, config-drift, orphan-data)
- `probekit-health-audit-bogame` v1.0.0 — проектный (7 проб: episodic-efficiency, db-vacuum, gdscript-api-sync, migration-relevance, service-registry-health, motherboard-completeness, project-isolation)
- `probekit-test-suite` v2.4.0 → v2.5.0 — добавлены stages 3.8 и 3.9 (health), новый mode `--health`

**Pipeline (12 stages):**
```
arch → arch-bogame → code → code-bogame → security → dependency → health → health-bogame → unit → integration → e2e → perf
```

### DONE: Tier 1 — Усиление существующих скилов (2026-03-29)

Добавлены недостающие проверки в 4 существующих скила:

- `probekit-code-audit` v2.2.0 → v2.3.0 — новая Section 13: **Orphan Files** (файлы без import/require)
- `probekit-code-audit-bogame` v1.0.0 → v1.1.0 — новая Dimension 13: **Config↔Reality Drift** (TOML declares → code honors)
- `probekit-arch-review` v1.1.0 → v1.2.0 — 13-й dimension: **Operational Health** (data growth, log rotation, cleanup)
- `probekit-dependency-audit` v1.0.0 → v1.1.0 — новый Step 3.5: **Phantom Dependencies** (в manifest, не в коде)
- `probekit-test-suite` v2.5.0 — quality-gate-contract обновлён для health stages

---

## Известные проблемы

### P1: Windows-специфичные bash-команды в perf-test profiling
- **Где:** `probekit-perf-test/references/profiling-guide.md`
- **Суть:** Команды py-spy, clinic.js, pprof написаны для bash (Linux/macOS). На Windows работают только через WSL или Git Bash.
- **Примеры:** `pgrep`, `$!`, `kill -SIGINT`, pipe-конструкции
- **Решение после переезда:** На Linux всё заработает нативно. Дополнительно: добавить auto-detect OS и адаптировать команды (PowerShell fallback для тех кто останется на Windows).
- **Приоритет:** Решится сам при переезде на Linux

### P2: False positives в secret detection
- **Где:** `probekit-security-audit/references/secret-patterns.md`
- **Суть:** Regex-паттерны могут срабатывать на test fixtures, example configs, documentation с placeholder-ключами
- **Текущая митигация:** Exclusion list (placeholder, test, example, changeme, TODO)
- **Улучшение:** Добавить контекстный анализ — если файл в `tests/`, `fixtures/`, `examples/` → снизить severity до 🟢 SUGGESTION вместо 🔴 CRITICAL
- **Приоритет:** Medium

### P3: .probekit.yml — спецификация vs реальность
- **Где:** `probekit-test-suite/SKILL.md` Step 1, `probekit-research/research-front-5-infrastructure.md` Блок 2
- **Суть:** Описана полная спецификация .probekit.yml (paths, thresholds, excludes, features, scoring, custom_checks, output), но скилы пока поддерживают только базовые секции (paths, thresholds, scoring.weights)
- **Нереализованные секции:**
  - `severity_overrides` — повышение/понижение severity для конкретных правил
  - `custom_checks` — пользовательские правила из YAML-файлов
  - `output.formats` — SARIF output (см. F1)
  - `features.delta_mode` — инкрементальный анализ (см. F2)
  - `features.auto_baseline` — автогенерация baseline (см. F3)
- **Приоритет:** Low — defaults работают, расширение по мере потребности

---

## Нереализованные фичи (из research)

### F1: SARIF Output Format
- **Источник:** `research-front-5-infrastructure.md` Блок 3
- **Суть:** Стандартный JSON-формат для статического анализа (SARIF 2.1.0). Поддерживается GitHub Code Scanning, Azure DevOps, VS Code SARIF Viewer
- **Что даёт:**
  - GitHub автоматически показывает findings в PR review
  - VS Code подсвечивает findings inline
  - Интеграция с CI/CD pipelines
- **Объём:** ~200 строк mapping code (severity → SARIF level, findings → SARIF results)
- **Приоритет:** Medium — полезно при настройке CI/CD на Linux сервере

### F2: Delta/Incremental Mode
- **Источник:** `research-front-5-infrastructure.md` Блок 7
- **Суть:** Анализировать только изменённые файлы (git diff), показывать NEW vs RESOLVED findings
- **Что даёт:**
  - Быстрый feedback в PR review (не пересканировать весь проект)
  - Tracking: "этот коммит добавил 2 🔴 и убрал 1 🟡"
  - Не блокировать на legacy findings
- **Алгоритм:** git diff → changed files → scan only those → compare with baseline
- **Зависимости:** Требует F3 (Baseline system)
- **Приоритет:** High — значительно ускорит daily workflow

### F3: Baseline System
- **Источник:** `research-front-5-infrastructure.md` Блок 4 (SonarQube New Code Period concept)
- **Суть:** `.probekit-baseline.json` — snapshot всех findings на определённый момент. Новые findings = "появились после baseline". Старые = "известные, не блокируют"
- **Что даёт:**
  - Legacy codebase с 200 warnings не блокирует CI
  - Фокус на новых проблемах
  - Tracking прогресса: baseline shrinks over time
- **Формат:** JSON с finding hashes (file + line + rule → hash)
- **Приоритет:** High — критично для больших кодовых баз

### F4: Custom Check Rules
- **Источник:** `research-front-5-infrastructure.md` Блок 2 (.probekit.yml `custom_checks`)
- **Суть:** Пользовательские правила в YAML-файлах, подключаемые через `.probekit.yml`
- **Пример:**
  ```yaml
  # .probekit/rules/company-standards.yml
  rules:
    - id: CS-LOG-01
      pattern: "print("
      message: "Use logger instead of print()"
      severity: WARNING
      languages: [python]
  ```
- **Что даёт:** Команда определяет свои стандарты без форка скилов
- **Приоритет:** Low — для зрелых команд с устоявшимися стандартами

### F5: Cross-Skill Finding Deduplication
- **Суть:** code-audit Section 4 и security-audit могут найти одну и ту же SQL injection. Сейчас — дублирование в SUITE-REPORT
- **Решение:** Finding ID содержит file:line:rule. При агрегации в test-suite — deduplicate по file:line, показывать higher severity
- **Приоритет:** Medium — cosmetic, но влияет на scoring accuracy

### F6: Godot Integration для security-audit и dependency-audit
- **Суть:** Новые скилы (security-audit, dependency-audit) пока не имеют Godot/GDScript-специфичных patterns
- **Что нужно:**
  - security-audit: паттерны для GDScript (HTTP запросы, file access, eval-подобные конструкции)
  - dependency-audit: поддержка `addons/` и `project.godot` как manifest-файлов
- **Приоритет:** Low — Godot projects обычно не web-facing

---

## Улучшения после переезда на Linux

### L1: Нативный profiling
- py-spy, pprof, clinic.js работают нативно
- Убрать WSL workaround из profiling-guide.md
- Добавить `perf` (Linux perf_events) как дополнительный profiler

### L2: CI/CD интеграция
- SARIF output → GitHub Actions / GitLab CI
- Pre-commit hooks для security-audit (secret scan)
- Scheduled full suite run (nightly)

### L3: Shell-safe commands cleanup
- Убрать PowerShell fallback из tool-detection.md
- Унифицировать все commands на bash
- Обновить ENVIRONMENT.md detection

---

## Архитектурные скилы — backlog из ARCH-REVIEW-COMBINED-RESEARCH (2026-03-19)

Источник: `docs/01_reference/KNOWLEDGE/CODE-AUDIT/PROBKIT-REVIEW/!ARCH-REVIEW-COMBINED-RESEARCH.md`

### A1: arch-review — 3 новых analysis sections (Security, API Design, Configuration)
- **Скилл:** probekit-arch-review
- **Файлы:** `analysis-sections.md`, `SKILL.md`, `output-template.md`
- **Суть:** Добавить Section 14 (Security Architecture), Section 15 (API Design Quality), Section 16 (Configuration Architecture). Потребует scorecard 12→15 dimensions, обновление weighted formula (total weight 13.9→17.5)
- **Что даёт:**
  - Security: auth model, secrets management strategy, trust boundaries — архитектурный уровень (не дублирует security-audit который сканирует code-level)
  - API Design: consistency, versioning, pagination, error responses — проектная зрелость API
  - Configuration: config module structure, validation, secrets separation, environment parity
- **Зависимости:** Обновить output-template.md scorecard, SKILL.md Step 5 dimensions
- **Приоритет:** Medium — расширяет покрытие, но 12 sections уже работают хорошо

### A2: arch-review — Calibration scale (anchor points per dimension)
- **Скилл:** probekit-arch-review
- **Файлы:** `analysis-sections.md` или новый `calibration-anchors.md`
- **Суть:** 4 anchor points per dimension (Broken 1-3, Weak 4-5, Solid 6-7, Excellent 8-10) с конкретными criteria для каждого уровня. Уменьшает субъективность scoring.
- **Пример:** Modularity: Broken = god module >2000 LOC, zero tests; Solid = modules <500 LOC, clear API surface; Excellent = plugin architecture with auto-discovery
- **Приоритет:** Medium — полезно для consistency across reviews

### A3: arch-review-bogame — Agent Observability dimension
- **Скилл:** probekit-arch-review-bogame
- **Файлы:** `SKILL.md`, `project-rules.md`, `output-template.md`
- **Суть:** 13-й dimension: Agent Decision Tracing (decision audit trail), Cost Attribution (per-agent/per-task cost tracking), Quality Signals (output quality metrics per agent)
- **Что даёт:** Видимость в работу агентов — не только "сервис работает", но "агент принимает правильные решения за разумную цену"
- **Приоритет:** Medium — важно для зрелости агентной системы

### A4: arch-review-bogame — Escalation rules update
- **Скилл:** probekit-arch-review-bogame
- **Файлы:** `references/severity-format.md` (или создать для bogame)
- **Суть:** Обновить escalation rules с BOGame-специфичными правилами severity. Из research:
  - Agent без kill switch → CRITICAL
  - Protocol execution без persistence → CRITICAL
  - Shared mutable state между агентами → CRITICAL
  - Missing observability на agent decisions → WARNING
  - Motherboard без checkpoint после high-risk node → WARNING
- **Приоритет:** Low — текущие rules работают, это refinement

### A5: arch-review-bogame — Agent orchestration deep checks (~65 checks)
- **Скилл:** probekit-arch-review-bogame
- **Файлы:** `project-rules.md` sections 8-12 (расширение)
- **Суть:** Из research — дополнительные проверки:
  - Context Window Budget Tracking (agent не превышает token budget)
  - Agent Tool Allowlisting (agent имеет access только к разрешённым tools)
  - Two-Phase Action Pattern (Plan → Validate → Execute)
  - Agent Timeout Budgets
  - Protocol Versioning & Migration
  - Protocol Execution Observability (metrics per step)
  - Protocol Idempotency (safe retry)
  - SQLite busy_timeout configuration check
  - Single-Writer Enforcement
  - WAL File Growth Control
  - Blast Radius Containment (multi-project)
  - Noisy Neighbor Detection
  - Data Type Safety Between Nodes
  - Paused Flow Persistence (currently in-memory only)
  - Prompt Injection Protection
  - MCP Tool Safety
- **Приоритет:** Low-Medium — incremental, добавлять по мере потребности

### A6: coding-standards.md — Advanced async + SQLite patterns
- **Скилл:** probekit-arch-review-bogame
- **Файлы:** `references/coding-standards.md`
- **Суть:** Из research — дополнительные coding standards:
  - Advanced async: no `asyncio.run()` inside running loop, `run_in_executor` for CPU work, connection pool with pre_ping
  - SQLite: parameterized queries only, WAL mode everywhere, busy_timeout ≥ 3000ms, single writer per DB file
- **Приоритет:** Low — текущие standards покрывают основные кейсы

---

## Порядок реализации (рекомендуемый)

### Tier 1 — Разблокирующие (сразу после переезда)
1. **L1-L3** — cleanup Windows-specific
2. **F3** — Baseline system (разблокирует F2)
3. **F2** — Delta mode (daily workflow improvement)

### Tier 2 — Качество скоринга и покрытия
4. **A1** — arch-review: 3 новых sections (Security, API Design, Config) → scorecard 12→15
5. **A2** — arch-review: Calibration scale (anchor points per dimension)
6. **A3** — arch-review-bogame: Agent Observability dimension → scorecard 12→13
7. **F5** — Finding deduplication (scoring accuracy)

### Tier 3 — CI/CD и интеграции
8. **F1** — SARIF output (CI/CD integration)
9. **P2** — Context-aware secret detection

### Tier 4 — Incremental improvements
10. **A4** — arch-review-bogame: Escalation rules update
11. **A5** — arch-review-bogame: Agent orchestration deep checks (~65 checks)
12. **A6** — coding-standards: Advanced async + SQLite patterns
13. **F4** — Custom check rules
14. **F6** — Godot integration (если понадобится)
