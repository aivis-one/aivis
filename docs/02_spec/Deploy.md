# Deploy
> SPEC v3.0.0 | Deploy-Verify-Swap — production deployment governance
> Triggered by: sprint close (release-ready), hotfix, Self-Dev MB auto-deploy
> ADR: ADR-DEPLOY-VERIFY-SWAP

---

## Purpose

Govern production deployments to servers. Blue-green swap via Docker Compose profiles + Nginx upstream. 5-check verification gate before traffic switch. Instant rollback. Audit trail.

Run Deploy when:
- After 04_Sprint-Closer confirms release-ready code
- Hotfix requires mid-sprint production update
- Self-Dev MB triggers automated deploy (subject to deploy_approval tier)

---

## Before You Begin

Load in chat:

□ 01_Declaration.md
□ docs/01_refer/ENVIRONMENT.md
□ S{N}-SPRINT.md (current sprint)
□ ADR-DEPLOY-VERIFY-SWAP.md (if exists — from project ADR library)

Confirm:
□ Git tag exists for version to deploy
□ All tests pass on tagged commit
□ Target server(s) known (deploy/servers/*.env)

---

## Session Control

**STOP gates** are marked with ⛔ below. At each gate, Claude Chat reviews
before proceeding. Human approval required where noted.

---

## Pre-flight

| # | Check | Fail action |
|---|-------|-------------|
| 1 | Git tag exists and is pushed | Abort |
| 2 | All tests pass on tagged commit | Abort |
| 3 | Target server(s) reachable via SSH | Abort |
| 4 | Secrets exist on target (/opt/{project}/.env) | Abort |
| 5 | Sufficient disk space for second container image | Abort |

⛔ **GATE: Pre-flight.** All checks pass → proceed. Any fail → abort, report.

---

## Phase 0: MIGRATE (conditional — skip if no schema changes)

**Rule: Additive-only migrations per deploy (expand-contract).**

| Operation | Allowed? | When |
|-----------|----------|------|
| ADD COLUMN (nullable/default) | ✅ | Any deploy |
| CREATE TABLE | ✅ | Any deploy |
| CREATE INDEX CONCURRENTLY | ✅ | Any deploy |
| DROP COLUMN | ❌ | Separate deploy after stability confirmed |
| ALTER COLUMN TYPE | ❌ | Expand first (new column + copy), contract later |
| RENAME COLUMN | ❌ | Expand first (add new), contract later |

Steps:
1. Run DB migration against shared {project}-db
2. Verify active container still works after migration:
   - GET /health/ready (includes schema_version check)
   - Quick smoke test (3-5 critical paths)
3. If active breaks → ABORT, rollback migration
4. If active OK → proceed to Phase 1

⛔ **GATE: Migration.** Active container still healthy after migration → proceed.

---

## Phase 1: PREPARE

1. SSH to target server
2. Determine inactive color: read /opt/{project}/active-color → opposite
3. Set {PROJECT}_WORKER_ENABLED=false for inactive container
4. Pull new image for inactive profile
5. Start inactive container
6. Wait for container healthy (max 30s)

---

## Phase 2: VERIFY

5-check gate against inactive container (~90s total):

| # | Check | Pass criteria | Timeout |
|---|-------|---------------|---------|
| 1 | /health/ready | HTTP 200, all deps OK, schema_version compatible | 10s |
| 2 | Smoke tests (@pytest.mark.smoke) | 0 failures | 60s |
| 3 | Motherboard dry-run | Execution completes, status ≠ FAILED | 60s |
| 4 | Hardening diff | read_only, cap_drop ALL, no-new-privileges present | 5s |
| 5 | Rollback round-trip (conditional) | Both directions swap cleanly | 120s |

Check 5 runs: first deploy per server + after docker-compose.yml changes.

### Approval Gate

| deploy_approval (identity.yaml) | Behavior |
|----------------------------------|----------|
| `required` (default) | Telegram notification with diff + results. Human approve/reject. |
| `auto_if_tests_pass` | Auto-proceed if all 5 checks pass. Telegram informational. |
| `auto_full` | No gate, audit trail only. Future (S15+), explicit opt-in. |

⛔ **GATE: VERIFY → SWAP.** ALL checks pass + approval (if required) → proceed. ANY failure → stop inactive container, alert, abort.

---

## Phase 3: SWAP

1. Update nginx/active-upstream.conf → point to inactive container port
2. Validate: `nginx -t` → if FAIL: abort swap, keep current upstream, alert
3. Reload: `nginx -s reload`
4. Post-swap verify: GET /health/ready through proxy (public port)
5. Update /opt/{project}/active-color → new color
6. Update worker flags: new-active WORKERS=true, old-active WORKERS=false
7. Restart old container with workers disabled (picks up WORKERS=false)

⛔ **GATE: SWAP.** Post-swap health check passes → deploy complete. Fail → rollback.

---

## Rollback

If issues detected post-swap:

1. Revert nginx/active-upstream.conf → old container port
2. Validate + reload Nginx
3. Update /opt/{project}/active-color → old color
4. Restore worker flags (old=true, new=false)
5. Restart new container with workers disabled
6. Post-rollback verify: GET /health/ready through proxy
7. Log rollback reason

**Time to rollback:** <10 seconds (Nginx reload only, no image pull needed).

---

## Multi-Server Execution

Sequential: server-1 → full cycle (Phase 0-3) → server-2 → ...
Stop on first failure. Remaining servers stay on previous version.

---

## Audit Trail

Each deploy logs to S{N}-SPRINT.md Protocol Log:

```
| S{N}-Deploy-{server} | Deploy | [date] | [SUCCESS/ROLLBACK/ABORT] — v[tag], checks [N/5], [duration]s |
```

---

## Session Code

| Session Type | Format | Example |
|---|---|---|
| Deploy | S{N}-Deploy-{server} | S13-Deploy-vps1 |
| Multi-server | S{N}-Deploy-all | S13-Deploy-all |

---

## Prerequisites (before first use)

- [ ] R6 fixed: /health/ready returns real dependency checks + schema_version
- [ ] docker-compose.yml updated with blue/green profiles
- [ ] {PROJECT}_WORKER_ENABLED flag implemented in application entrypoint
- [ ] Nginx upstream templates created
- [ ] @pytest.mark.smoke test suite (5-10 tests)
- [ ] Motherboard dry-run capability available
- [ ] deploy.sh and deploy-all.sh written and tested
- [ ] identity.yaml deploy_approval field
- [ ] Telegram deploy notification (diff + results + approve/reject)

---

## Chat Boundary — MANDATORY STOP

After deploy complete (or abort) — this chat is DONE. Close it.
Log result to S{N}-SPRINT.md Protocol Log.

---

[*] Deploy SPEC v3.0.0 * ready
Deploy-Verify-Swap — production deployment governance
Run: after sprint close (release-ready), hotfix, Self-Dev MB auto-deploy
ADR: ADR-DEPLOY-VERIFY-SWAP
