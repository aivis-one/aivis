# Health Audit — Probe Definitions v1.2.0

Detailed specification for each of the 12 runtime health probes.

---

## Probe 1: Disk Bloat

**Purpose:** Detect files that have grown beyond acceptable thresholds in runtime/data directories.

**Scan targets:** All directories listed in `.gitignore` that contain runtime data.
Common: `data/`, `framework/logs/`, `runtime/`, `cache/`, `*.db`, `*.log`, `*.jsonl`.

**Thresholds:**

| File Type | WARNING | CRITICAL |
|-----------|---------|----------|
| Log files (*.log, *.jsonl) | > 10 MB | > 50 MB |
| Database files (*.db, *.sqlite) | > 50 MB | > 200 MB |
| Cache files | > 20 MB | > 100 MB |
| Vendored binaries | > 0 MB (any) | > 50 MB |
| Any single file | > 100 MB | > 500 MB |

**Detection method:**
1. Walk gitignored directories recursively
2. Measure file sizes
3. Compare against thresholds
4. Report top 10 largest files with sizes

**Scoring:**
- 10/10: All files under WARNING thresholds
- 8/10: 1-2 files at WARNING level
- 6/10: 3-5 files at WARNING level
- 4/10: Any file at CRITICAL level
- 2/10: Multiple files at CRITICAL level
- 0/10: Total runtime data > 500 MB

---

## Probe 2: Log Rotation

**Purpose:** Verify every log file handler in the codebase has size-based rotation configured.

**Detection method:**
1. Find all Python logging configurations:
   - `logging.FileHandler` without `RotatingFileHandler` or `TimedRotatingFileHandler`
   - Custom log writers (AsyncLogBuffer, file.write()) without size checks
   - TOML/YAML/JSON logging configs with file handlers
2. Find all log file paths referenced in code
3. For each handler, verify:
   - Max file size is configured (maxBytes or equivalent)
   - Backup count is configured (backupCount > 0)
   - Rotation actually triggers (not just configured but bypassed)

**Severity escalation:**
- File handler with rotation: OK
- File handler without rotation but file < 1 MB: SUGGESTION
- File handler without rotation and file > 1 MB: WARNING
- File handler without rotation and file > 10 MB: CRITICAL

**Scoring:**
- 10/10: All handlers have rotation
- 8/10: 1 handler missing rotation (file small)
- 5/10: 1+ handlers missing rotation (files growing)
- 2/10: Majority of handlers lack rotation
- 0/10: No rotation anywhere, files > 50 MB

---

## Probe 3: Log Duplication

**Purpose:** Detect when a single event is written to multiple log files (write multiplication).

**Detection method:**
1. Trace event write chains:
   - Find all `logger.log()`, `logger.info()`, etc. calls
   - Find custom emit/write methods
   - For each emitter, trace: does it call another logger/writer?
2. Build write graph: Event → [File1, File2, File3]
3. Any event reaching 2+ files = duplication

**Patterns to detect:**
- Logger A calls Logger B which writes to its own file
- Same data written to both structured (JSONL) and unstructured (text) logs
- Mirror/forward patterns between loggers
- Multiple handlers on same logger writing to different files (intentional = OK if documented)

**Severity:**
- Intentional dual-write (documented): SUGGESTION (consider removing)
- Unintentional 2x write: WARNING
- 3x+ write multiplication: CRITICAL

**Scoring:**
- 10/10: No duplication found
- 8/10: Documented intentional dual-write only
- 5/10: 1-2 undocumented duplication chains
- 2/10: Systemic duplication (3x+ on major event paths)
- 0/10: Every event duplicated to 3+ destinations

---

## Probe 4: DB Growth

**Purpose:** Verify that time-series/append-only database tables have working cleanup policies.

**Detection method:**
1. Find all SQLite/PostgreSQL tables with timestamp columns
2. For each table, check:
   - Is there a TTL/archive policy in config?
   - Is there code that executes the cleanup?
   - When does the cleanup actually run? (startup? cron? manual only? hibernation only?)
   - Has cleanup run recently? (check row counts, oldest entries)
3. Estimate growth rate: rows/day, MB/month

**Severity:**
- Table with TTL + working cleanup + recent execution: OK
- Table with TTL but cleanup only on rare events: WARNING
- Table with TTL but cleanup code unreachable: CRITICAL
- Table with no TTL and growing: CRITICAL
- Table with < 1000 rows and no TTL: SUGGESTION

**Scoring:**
- 10/10: All tables have working TTL + regular cleanup
- 8/10: All tables have TTL, 1-2 with infrequent cleanup
- 5/10: Some tables lack TTL but are small
- 3/10: Large tables with no cleanup
- 0/10: Multiple tables growing unbounded > 100K rows

---

## Probe 5: Dead Files

**Purpose:** Find files and directories that exist on disk but are never referenced from code.

**Detection method:**
1. List all files in runtime/data directories
2. For each file/directory:
   - Grep codebase for references (path, filename, stem)
   - Check imports, configs, scripts, Docker files
   - Check .gitignore entries (gitignored but still referenced = alive)
3. A file is "dead" if:
   - Zero references from any source/config file
   - Not a standard framework file (.gitkeep, __init__.py)
   - Older than 30 days (grace period for new files)

**Severity:**
- Dead file < 1 MB: SUGGESTION
- Dead file 1-50 MB: WARNING
- Dead file/directory > 50 MB: CRITICAL
- Dead vendored runtime (interpreters, SDKs): CRITICAL regardless of size

**Scoring:**
- 10/10: No dead files
- 8/10: 1-2 small dead files
- 5/10: Multiple dead files or 1 large one
- 2/10: Dead directory trees (e.g., vendored runtime)
- 0/10: > 100 MB of dead files

---

## Probe 6: Config Drift

**Purpose:** Detect cases where configuration declares a policy but code doesn't honor it.

**Detection method:**
1. Parse all config files (TOML, YAML, JSON, .env.example)
2. For each policy-like setting:
   - Find the code that should implement it
   - Verify the code actually reads and applies the setting
   - Check for hardcoded overrides that bypass config
3. Common drift patterns:
   - Config says `archive_after_days=30` but archive code is unreachable
   - Config says `max_retries=3` but code has `while True`
   - Config has feature flag but no code checks it
   - Config defines threshold but code uses hardcoded value

**Severity:**
- Config read but partially applied: SUGGESTION
- Config defined but never read by code: WARNING
- Config implies safety policy but code bypasses it: CRITICAL

**Scoring:**
- 10/10: All config entries have corresponding code that reads them
- 8/10: 1-2 unused config entries
- 5/10: Policy configs (TTL, limits, thresholds) not honored
- 2/10: Safety-related configs (auth, limits) bypassed
- 0/10: Majority of config is decorative

---

## Probe 7: Orphan Data

**Purpose:** Find legacy-named artifacts from previous project iterations.

**Detection method:**
1. Collect all known project name changes (e.g., bfg → bogame)
2. Search for files/directories/DB tables using old names:
   - File names: `bfg.db`, `bfg-backend.log`, etc.
   - Directory names: `bfg-backend/`, `old_project/`
   - Database table names: tables with deprecated prefixes
   - Config keys: settings referencing old paths
3. Also detect:
   - `.bak`, `.old`, `.deprecated` files in production paths
   - Timestamped snapshots older than 90 days
   - Empty directories (except .gitkeep)

**Severity:**
- Empty directory: SUGGESTION
- Small orphan file (< 1 MB): SUGGESTION
- Orphan database (any size): WARNING
- Orphan with active code references (confusion risk): CRITICAL

**Scoring:**
- 10/10: No orphan artifacts
- 8/10: 1-2 empty directories only
- 6/10: Small orphan files
- 4/10: Orphan databases or large files
- 2/10: Orphans with code still referencing them (name confusion)
- 0/10: Systemic legacy mess across multiple directories

---

## Probe 8: ADR Currency

**Purpose:** Verify that Architecture Decision Records exist, are up-to-date, and cover key decisions.
ADRs capture the "theory of the system" — what evaporates fastest. Without them,
AI generates code that violates past decisions because the context exists nowhere.

**Detection method:**
1. Find ADR files: search for `ADR-*.md`, `adr-*.md`, `**/adr/**`, `**/decisions/**`
   Also check: CLAUDE.md, ARCHITECTURE.md for inline decision records
2. For each ADR found, check:
   - Has a Status field (Proposed/Accepted/Deprecated)?
   - Has Alternatives Considered section (highest-value, most skipped)?
   - References code paths affected?
   - Last modified date vs code changes in affected paths
3. Cross-reference: architectural decisions visible in code that have NO ADR:
   - Why this database? Why this queue? Why this auth pattern?
   - Why this module structure? Why these service boundaries?
   - Search for comments like "we chose X because" — should be an ADR
4. Currency check: ADR last modified > 6 months ago + affected code changed recently = stale

**Thresholds:**

| ADR State | Level | Signal |
|----------|-------|--------|
| ADRs exist, current, cover key decisions | DIAMOND | Theory of system preserved |
| ADRs exist but some missing Alternatives section | OK | Mostly documented |
| ADRs exist but stale (> 6 months, code changed) | WARNING | Decisions drifting from reality |
| Few ADRs, major decisions undocumented | WARNING | Partial coverage |
| No ADRs anywhere | CRITICAL | Theory of system exists only in heads |

**Scoring:**
- 10/10: ADRs cover all major decisions, all current, all have Alternatives
- 8/10: ADRs exist, mostly current, some missing Alternatives
- 5/10: Some ADRs but major gaps (key decisions undocumented)
- 3/10: 1-2 ADRs only, most decisions undocumented
- 0/10: No ADRs, no decision documentation anywhere

---

## Probe 9: Domain Rules Coverage

**Purpose:** Verify that domain knowledge is captured in machine-readable rules files,
not just in developer heads. Rules files (`.claude/rules/`, CLAUDE.md) encode
domain invariants from production experience that guide AI code generation.

**Detection method:**
1. Find rules files:
   - `.claude/rules/*.md` with glob patterns
   - CLAUDE.md (project-level rules)
   - `.cursor/rules/`, `.github/copilot-instructions.md` (other AI tools)
2. Identify bounded contexts / domain areas in the codebase:
   - Major directories in src/, framework/, services/
   - Distinct functional areas (payments, auth, orders, notifications, etc.)
3. For each domain area, check:
   - Is there a corresponding rules file?
   - Does the rules file contain production-specific knowledge?
     (not just "use good practices" but "webhooks arrive twice, idempotency required")
   - Does the rules file have glob patterns matching the domain files?
4. Coverage calculation: `rules_coverage = domains_with_rules / total_domains`

**Quality signals for rules files:**
- GOOD: Specific, actionable ("Payment provider uses both 'paid' and 'payment_confirmed'")
- BAD: Generic, obvious ("Write clean code", "Handle errors properly")
- GOOD: References production incidents or specific vendor behavior
- BAD: Could apply to any project (not domain-specific)

**Thresholds:**

| Coverage | Level | Signal |
|---------|-------|--------|
| > 80% domains have quality rules | DIAMOND | Domain knowledge machine-readable |
| 50-80% domains have rules | OK | Good coverage, some gaps |
| 20-50% domains have rules | WARNING | Significant knowledge in heads only |
| < 20% domains have rules | CRITICAL | AI generates without domain context |

**Scoring:**
- 10/10: > 80% coverage, all rules are specific and actionable
- 8/10: 50-80% coverage, quality rules
- 5/10: 20-50% coverage or rules are too generic
- 3/10: < 20% coverage
- 0/10: No rules files anywhere, no CLAUDE.md domain sections

---

## Probe 10: SQLite Table Sizes

**Purpose:** Detect individual database tables that have grown beyond healthy thresholds.
While Probe 4 (DB Growth) checks for TTL/cleanup policies, this probe measures actual
current table sizes to catch cases where policies exist but cleanup has fallen behind.

**Detection method:**
1. Find all `.db` and `.sqlite` files in the project
2. For each database, run: `SELECT name, COUNT(*) as row_count FROM sqlite_master WHERE type='table'`
3. For each table: `SELECT COUNT(*) FROM {table}` and estimate size via `page_count * page_size`
4. Compare against thresholds

**Thresholds:**

| Row Count | Level | Signal |
|-----------|-------|--------|
| < 10,000 | OK | Healthy table size |
| 10,000-50,000 | SUGGESTION | Growing, monitor |
| 50,000-200,000 | WARNING | Large table, verify cleanup runs |
| > 200,000 | CRITICAL | Table needs immediate cleanup or archival |

**Disk size thresholds:**

| Table Disk Size | Level | Signal |
|----------------|-------|--------|
| < 10 MB | OK | Healthy |
| 10-50 MB | WARNING | Growing, verify vacuum schedule |
| > 50 MB | CRITICAL | Bloated, needs vacuum + cleanup |

**Scoring:**
- 10/10: All tables under 10K rows, total DB size < 10 MB
- 8/10: Largest table < 50K rows
- 5/10: Tables in 50K-200K range
- 3/10: Tables > 200K rows
- 0/10: Multiple tables > 200K rows or total DB > 200 MB

---

## Probe 11: Memory Entry Age

**Purpose:** Detect stale entries in memory/episodic tables that exceed the project's
retention policy. Old entries add noise to retrieval, slow queries, and waste storage.

**Detection method:**
1. Identify memory-related tables: tables with columns like `created_at`, `timestamp`,
   `last_accessed`, `episode_date`, or tables named `*memory*`, `*episodic*`, `*context*`
2. For each memory table:
   - Find the oldest entry: `SELECT MIN(created_at) FROM {table}`
   - Find entries older than retention policy (default: 90 days if no policy found)
   - Count stale entries: `SELECT COUNT(*) FROM {table} WHERE created_at < date('now', '-90 days')`
   - Calculate stale ratio: `stale_entries / total_entries`
3. Check for retention policy in config files (TTL settings, archive policies)

**Thresholds:**

| Stale Ratio | Level | Signal |
|------------|-------|--------|
| < 5% | DIAMOND | Memory is fresh and well-maintained |
| 5-15% | OK | Minor staleness, acceptable |
| 15-40% | WARNING | Significant stale entries, cleanup needed |
| > 40% | CRITICAL | Memory dominated by stale data |

**Scoring:**
- 10/10: < 5% stale entries, all within retention policy
- 8/10: 5-15% stale, retention policy exists and mostly honored
- 5/10: 15-40% stale or no retention policy defined
- 3/10: > 40% stale entries
- 0/10: No cleanup mechanism, oldest entries > 1 year

---

## Probe 12: WAL/Log Freshness

**Purpose:** Detect SQLite WAL (Write-Ahead Log) files that have grown large without
checkpointing, and log files that have not been rotated recently. Both indicate
maintenance processes that are configured but not actually running.

**Detection method:**
1. Find all `*-wal` files alongside `.db` files
2. For each WAL file:
   - Measure file size
   - Check last modification time
   - Compare against the main DB file's last modification
   - A WAL > 5 MB suggests checkpoint is not running
3. Find all `.log` and `.jsonl` files in runtime directories
4. For each log file:
   - Check last rotation (presence of `.log.1`, `.log.2` etc.)
   - Measure time since last rotation
   - A log file > 10 MB with no rotation files = rotation not running

**WAL thresholds:**

| WAL Size | Level | Signal |
|----------|-------|--------|
| < 1 MB | OK | Checkpointing is working |
| 1-5 MB | SUGGESTION | Monitor checkpoint frequency |
| 5-20 MB | WARNING | Checkpoint may not be running regularly |
| > 20 MB | CRITICAL | Checkpoint is not running, performance impact likely |

**Log freshness thresholds:**

| Last Rotation | Level | Signal |
|--------------|-------|--------|
| < 7 days | OK | Rotation is active |
| 7-30 days | SUGGESTION | Check rotation schedule |
| 30-90 days | WARNING | Rotation may be broken |
| > 90 days or never | CRITICAL | No rotation happening |

**Scoring:**
- 10/10: All WAL files < 1 MB, all logs rotated within 7 days
- 8/10: WAL < 5 MB, logs rotated within 30 days
- 5/10: WAL 5-20 MB or logs not rotated in 30-90 days
- 3/10: WAL > 20 MB or logs never rotated
- 0/10: Multiple WAL files > 20 MB and no log rotation anywhere
