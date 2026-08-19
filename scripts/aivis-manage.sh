#!/bin/bash
# ==============================================================================
# aivis -- AIVIS.ONE Platform Management Script
# ==============================================================================
#
# Tracked in the repo, not generated. Reached through a stable entry point:
# /usr/local/bin/aivis (a symlink installed once by scripts/install_aivis.sh,
# never rewritten again) -> $INSTALL_BASE/scripts/manage.sh (a thin `exec`
# wrapper, also installed once) -> this file. `aivis update` pulls this file
# like any other tracked file, so a fix landed here reaches the box on the
# next update instead of waiting for a reinstall.
#
# INSTALL_BASE is a fixed constant, not a per-server fact -- every install
# uses /opt/aivis and nothing in this product lets that vary. What DOES vary
# per server (domains, ports) is read below from $INSTALL_BASE/aivis.conf,
# written once at install time.
# ==============================================================================

INSTALL_BASE="/opt/aivis"
COMPOSE_DIR="$INSTALL_BASE/repo"

CONF_FILE="$INSTALL_BASE/aivis.conf"
if [ ! -f "$CONF_FILE" ]; then
    echo "FATAL: $CONF_FILE not found." >&2
    echo "This looks like an incomplete install -- re-run scripts/install_aivis.sh," >&2
    echo "or create the file by hand with:" >&2
    echo "  API_DOMAIN=api.example.com" >&2
    echo "  FRONTEND_DOMAIN=app.example.com" >&2
    echo "  STORAGE_DOMAIN=storage-mc-admin.example.com" >&2
    echo "  APP_PORT=8000" >&2
    echo "  FRONTEND_PORT=3000" >&2
    exit 1
fi
# shellcheck source=/dev/null
source "$CONF_FILE"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# -- Shared temp-file cleanup -------------------------------------------------
# One registry, one trap, for the whole script. `trap ... EXIT` does not
# stack in bash -- a second, independent `trap ... EXIT` anywhere else in
# this file would silently REPLACE this one, and whichever path only that
# other trap knew about would leak on abort, with no error printed anywhere.
# There is exactly one consumer of this today (the self-update snapshot in
# case_update, below); the registry exists now, before a second consumer
# ever gets a chance to collide with a lone trap, so the next one added is
# safe by construction rather than by whoever adds it having read this
# comment first.
AIVIS_CLEANUP_PATHS=""
aivis_cleanup_register() {
    # Word-splits on the trap command below by design: paths come from our
    # own mktemp calls, never from user input, so none contains whitespace.
    AIVIS_CLEANUP_PATHS="$AIVIS_CLEANUP_PATHS $1"
}
# shellcheck disable=SC2086  # deliberate word-split -- see aivis_cleanup_register
trap 'rm -f $AIVIS_CLEANUP_PATHS' EXIT

cd_compose() {
    cd "$COMPOSE_DIR" || { echo -e "${RED}ERROR: $COMPOSE_DIR not found${NC}"; exit 1; }
}

# ==============================================================================
# STATUS
# ==============================================================================

case_status() {
    cd_compose
    SERVER_IP=$(curl -s --max-time 3 ifconfig.me 2>/dev/null || echo "unknown")

    echo -e "${CYAN}=== AIVIS.ONE Status ===${NC}"
    echo ""
    echo "Server: $SERVER_IP"
    echo "Uptime: $(uptime -p 2>/dev/null || uptime)"
    echo "Memory: $(free -h | awk '/Mem:/ {print $3 "/" $2}')"
    echo "Disk:   $(df -h / | tail -1 | awk '{print $3 "/" $2 " (" $5 " used)"}')"
    echo ""

    echo -e "${CYAN}=== Docker Containers ===${NC}"
    docker compose ps
    echo ""

    echo -e "${CYAN}=== Health Check ===${NC}"
    HEALTH=$(curl -s --max-time 5 "http://127.0.0.1:8000/health" 2>/dev/null)
    if [ -n "$HEALTH" ]; then
        echo "$HEALTH" | python3 -m json.tool 2>/dev/null || echo "$HEALTH"
    else
        echo -e "${RED}✗ App not responding on localhost${NC}"
    fi
    echo ""

    echo -e "${CYAN}=== MinIO ===${NC}"
    if docker compose ps --status running --services 2>/dev/null | grep -q "^minio$"; then
        if curl -sf --max-time 5 "http://127.0.0.1:9000/minio/health/live" > /dev/null 2>&1; then
            echo -e "${GREEN}✓ MinIO healthy (S3 API on 127.0.0.1:9000)${NC}"
        else
            echo -e "${RED}✗ MinIO container running but /minio/health/live not responding${NC}"
        fi
    else
        echo -e "${RED}✗ MinIO container not running${NC}"
    fi
    echo ""

    echo -e "${CYAN}=== External Access ===${NC}"
    if curl -sf --max-time 5 "https://${API_DOMAIN}/health" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ https://${API_DOMAIN}/health OK${NC}"
    else
        echo -e "${RED}✗ https://${API_DOMAIN}/health unreachable${NC}"
    fi
    if curl -sf --max-time 5 "https://${FRONTEND_DOMAIN}" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ https://${FRONTEND_DOMAIN} OK${NC}"
    else
        echo -e "${YELLOW}⚠ https://${FRONTEND_DOMAIN} not available (frontend not deployed yet)${NC}"
    fi
    # storage-mc-admin -- expect 401 (basic-auth gate); 401 means nginx is
    # serving the site correctly, anything else is broken.
    STORAGE_CODE=$(curl -sk --max-time 5 -o /dev/null -w "%{http_code}" "https://${STORAGE_DOMAIN}/" 2>/dev/null || echo "000")
    if [ "$STORAGE_CODE" = "401" ]; then
        echo -e "${GREEN}✓ https://${STORAGE_DOMAIN} OK (401 -- basic-auth gate active)${NC}"
    else
        echo -e "${RED}✗ https://${STORAGE_DOMAIN} unexpected status: $STORAGE_CODE${NC}"
    fi
}

# ==============================================================================
# LOGS
# ==============================================================================

case_logs() {
    cd_compose
    case "${1:-app}" in
        app)         docker compose logs -f --tail=100 app ;;
        db|postgres) docker compose logs -f --tail=100 postgres ;;
        redis)       docker compose logs -f --tail=100 redis ;;
        minio)       docker compose logs -f --tail=100 minio ;;
        frontend)    docker compose logs -f --tail=100 frontend 2>/dev/null || echo "Frontend not running" ;;
        all|"")      docker compose logs -f --tail=100 ;;
        *)           echo "Usage: aivis logs [app|db|redis|minio|frontend|all]" ;;
    esac
}

# ==============================================================================
# TEST DATABASE PROVISIONING (TD-068)
# ==============================================================================

# Provision an isolated test database so the suite never touches the live
# dev DB. Derives the test URL from the app's own DATABASE_URL (same
# creds/host, DB name -> aivis_test), drops + recreates it, migrates via
# alembic, and seeds the minimum the suite needs (platform user + platform
# templates; tests build the rest through register_user). Exports
# TEST_DB_URL (global) for the caller to pass to pytest via -e.
prepare_test_db() {
    echo ""
    echo "Provisioning isolated test database (aivis_test)..."

    local app_db_url
    app_db_url=$(docker compose exec -T app printenv DATABASE_URL | tr -d '\r\n')
    if [ -z "$app_db_url" ]; then
        echo -e "${RED}✗ Could not read DATABASE_URL from app container${NC}"
        return 1
    fi
    # Strip the trailing "/aivis" DB name, append "/aivis_test".
    # % removes the shortest matching suffix, so credentials/host are
    # untouched even if the password contained the substring "aivis".
    TEST_DB_URL="${app_db_url%/aivis}/aivis_test"

    # Drop + recreate via the maintenance DB. FORCE terminates any
    # lingering connections left by a previous run (PG13+).
    docker compose exec -T postgres psql -U aivis -d postgres \
        -c "DROP DATABASE IF EXISTS aivis_test WITH (FORCE);" \
        -c "CREATE DATABASE aivis_test OWNER aivis;" >/dev/null || {
        echo -e "${RED}✗ Could not (re)create aivis_test${NC}"
        return 1
    }

    # Schema via alembic -- faithful to migrations (NOT metadata.create_all,
    # which would miss functional indexes added in migration files).
    docker compose exec -T -e DATABASE_URL="$TEST_DB_URL" app \
        python -m alembic upgrade head || {
        echo -e "${RED}✗ Test DB migration failed${NC}"
        return 1
    }

    # Minimal seed. The seed scripts themselves import referrals.models so
    # the users.referred_by_link_id -> referral_links FK resolves on a
    # fresh DB, so they run plainly here.
    docker compose exec -T -e DATABASE_URL="$TEST_DB_URL" app \
        python scripts/seed_platform.py || {
        echo -e "${RED}✗ Test DB seed (platform user) failed${NC}"
        return 1
    }
    docker compose exec -T -e DATABASE_URL="$TEST_DB_URL" app \
        python -m scripts.seed_platform_templates || {
        echo -e "${RED}✗ Test DB seed (platform templates) failed${NC}"
        return 1
    }

    # Smoke check: 16 active platform-default templates (mirrors the dev-DB
    # check below -- template seeding is the historically fragile part).
    local tmpl_count
    tmpl_count=$(
        docker compose exec -T postgres psql -U aivis -d aivis_test \
            -tAc "SELECT COUNT(*) FROM company_document_templates WHERE company_id IS NULL AND status='active';" \
            2>/dev/null | tr -d '[:space:]'
    )
    if [ "$tmpl_count" != "16" ]; then
        echo -e "${RED}✗ Test DB platform-templates smoke check failed (found: '$tmpl_count', expected 16)${NC}"
        return 1
    fi

    echo -e "${GREEN}✓ aivis_test ready (migrated + seeded, 16 templates)${NC}"
}

# ==============================================================================
# TEST
# ==============================================================================

case_test() {
    cd_compose
    FAILED=0
    case "${1:-all}" in
        backend|"")
            echo "=== Backend Tests ==="
            if ! prepare_test_db; then
                echo -e "${RED}✗ Test DB provisioning failed${NC}"
                exit 1
            fi
            if ! docker compose exec -T -e DATABASE_URL="$TEST_DB_URL" app python -m pytest tests/ -v --tb=short; then
                FAILED=1
            fi
            ;;
        frontend)
            echo "=== Frontend Lint ==="
            if ! docker compose exec -T frontend sh -c "cd /app 2>/dev/null && npx eslint . || true"; then
                echo -e "${YELLOW}⚠ Frontend lint not available (container may lack source)${NC}"
            fi
            ;;
        all)
            echo "=== Backend Tests ==="
            if ! prepare_test_db; then
                echo -e "${RED}✗ Test DB provisioning failed${NC}"
                exit 1
            fi
            if ! docker compose exec -T -e DATABASE_URL="$TEST_DB_URL" app python -m pytest tests/ -v --tb=short; then
                FAILED=1
            fi
            ;;
        *)
            echo "Usage: aivis test [backend|frontend|all]"
            exit 1
            ;;
    esac
    echo ""
    if [ $FAILED -ne 0 ]; then
        echo -e "${RED}✗ Tests failed${NC}"
        exit 1
    else
        echo -e "${GREEN}✓ All tests passed${NC}"
    fi
}

# ==============================================================================
# LINT
# ==============================================================================

case_lint() {
    cd_compose
    echo "=== Ruff ==="
    docker compose exec -T app python -m ruff check app/ tests/
    echo ""
    echo "=== Mypy ==="
    docker compose exec -T app python -m mypy app/
    echo ""
    echo "=== Frontend ESLint ==="
    docker compose exec -T frontend sh -c "cd /app 2>/dev/null && npx eslint . || true" 2>/dev/null \
        || echo -e "${YELLOW}⚠ Frontend lint not available${NC}"
}

# ==============================================================================
# UPDATE
# ==============================================================================

case_update() {
    # Self-update guard -- this file is executed straight from the repo
    # checkout (via the shim at $INSTALL_BASE/scripts/manage.sh), and this
    # very call is about to `git pull` that same checkout below. Bash reads
    # a script incrementally by byte offset, so a mid-run rewrite of this
    # file can drop the interpreter into the middle of a different line.
    # Run the rest of this function from a snapshot instead: the copy is
    # immune to the pull that follows, and the next invocation of `aivis`
    # already picks up the new file on its own.
    if [ "${AIVIS_UPDATE_SNAPSHOT:-0}" != "1" ]; then
        local snapshot
        snapshot=$(mktemp /tmp/aivis-manage-snapshot.XXXXXX) || {
            echo -e "${RED}✗ Could not create the update snapshot${NC}"; exit 1; }
        cp "${BASH_SOURCE[0]}" "$snapshot" || {
            echo -e "${RED}✗ Could not snapshot ${BASH_SOURCE[0]}${NC}"; exit 1; }
        export AIVIS_UPDATE_SNAPSHOT=1 AIVIS_SNAPSHOT_PATH="$snapshot"
        # The main dispatcher below already shifted "update"/"deploy" off
        # $@ before calling this function, so a bare "$@" here would
        # re-launch the snapshot with only the flags -- it needs the
        # command name put back explicitly to land in this branch again.
        exec bash "$snapshot" update "$@"
    fi
    # Running from the snapshot now: register its cleanup with the shared
    # trap at the top of this file instead of setting a trap of our own.
    aivis_cleanup_register "$AIVIS_SNAPSHOT_PATH"

    cd_compose

    # Parse optional flags (order-independent).
    #   --skip-tests      Skip the backend test suite (keep everything else,
    #                     incl. seeds and smoke check).
    #   --frontend-only   Skip the entire backend cycle: backend build,
    #                     full compose restart, migrations, seeds, smoke
    #                     check and backend tests. Only the OpenAPI types
    #                     regeneration + frontend rebuild run. Refuses to
    #                     proceed if backend/ or migrations/ changed in
    #                     the pulled commits (fool-proof guard).
    SKIP_TESTS=0
    FRONTEND_ONLY=0
    while [ $# -gt 0 ]; do
        case "$1" in
            --skip-tests)    SKIP_TESTS=1 ;;
            --frontend-only) FRONTEND_ONLY=1 ;;
            *)
                echo -e "${RED}Unknown option: $1${NC}"
                echo "Usage: aivis update [--skip-tests] [--frontend-only]"
                return 1
                ;;
        esac
        shift
    done

    # --frontend-only implies --skip-tests (no backend cycle = no tests).
    if [ $FRONTEND_ONLY -eq 1 ]; then
        SKIP_TESTS=1
    fi

    echo "=== Updating AIVIS.ONE ==="
    if [ $FRONTEND_ONLY -eq 1 ]; then
        echo -e "${CYAN}Mode: frontend-only (backend cycle skipped)${NC}"
    elif [ $SKIP_TESTS -eq 1 ]; then
        echo -e "${CYAN}Mode: skip-tests (backend tests skipped)${NC}"
    fi
    echo ""

    # Fix git safe directory (git 2.35+ security requirement).
    git config --global --add safe.directory "$COMPOSE_DIR" 2>/dev/null || true

    # Save current state.
    CURRENT_COMMIT=$(git rev-parse --short HEAD)
    BRANCH=$(git branch --show-current)
    echo "Current: $CURRENT_COMMIT ($BRANCH)"

    # Check for uncommitted local changes.
    # Use git status --porcelain (same output git status reads) rather than
    # git diff-index, which fires false positives when file stat metadata
    # drifts (e.g. after chmod, touch, or filesystem restore) even when
    # the working tree is actually clean.
    if [ -n "$(git status --porcelain)" ]; then
        echo -e "${YELLOW}⚠ Uncommitted changes detected:${NC}"
        git status --short
        echo ""
        read -rp "Discard local changes and update? (y/n): " -n 1 < /dev/tty
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "Update cancelled"
            return 0
        fi
        git checkout -- .
    fi

    # Fetch and check if there are any remote changes.
    GIT_SSH_COMMAND="ssh -i /root/.ssh/id_ed25519_aivis_deploy" git fetch origin
    if git diff --quiet HEAD "origin/$BRANCH" 2>/dev/null; then
        echo -e "${GREEN}✓ Already up to date${NC}"
        return 0
    fi

    # Pull changes.
    echo "Pulling updates..."
    if ! GIT_SSH_COMMAND="ssh -i /root/.ssh/id_ed25519_aivis_deploy" git pull origin "$BRANCH"; then
        echo -e "${RED}✗ git pull failed. Local changes may conflict.${NC}"
        echo "  Inspect: git -C $COMPOSE_DIR status"
        echo "  To force: git -C $COMPOSE_DIR stash && aivis update"
        return 1
    fi
    NEW_COMMIT=$(git rev-parse --short HEAD)
    echo "Updated: $CURRENT_COMMIT -> $NEW_COMMIT"
    echo ""

    # Fool-proof guard for --frontend-only: if anything backend-side
    # changed between CURRENT_COMMIT and NEW_COMMIT, refuse hard.
    # Watched paths:
    #   backend/           -- app code + migrations + seed scripts
    #   docker-compose.yml -- service config, env wiring, mounts
    # docker-compose.yml lives at the repo root in aivis (unlike app
    # code which is under backend/), so we list it explicitly.
    if [ $FRONTEND_ONLY -eq 1 ]; then
        if ! git diff --quiet "$CURRENT_COMMIT" "$NEW_COMMIT" -- backend/ docker-compose.yml; then
            echo -e "${RED}✗ Detected backend-side changes between $CURRENT_COMMIT and $NEW_COMMIT${NC}"
            echo -e "${RED}  Refusing to run with --frontend-only.${NC}"
            echo ""
            echo "Changed files:"
            git diff --name-only "$CURRENT_COMMIT" "$NEW_COMMIT" -- backend/ docker-compose.yml | sed 's/^/  /'
            echo ""
            echo "Run: aivis update              (full cycle)"
            echo "  or aivis update --skip-tests (full cycle without tests)"
            return 1
        fi
        echo -e "${GREEN}✓ No backend/docker-compose changes -- proceeding frontend-only${NC}"
        echo ""
    fi

    # Rebuild backend image only -- frontend is rebuilt later, after the
    # OpenAPI schema is regenerated, so the resulting bundle includes the
    # current generated.ts.
    if [ $FRONTEND_ONLY -eq 0 ]; then
    echo "Rebuilding backend image..."
    docker compose build app

    # Restart stack: drop everything, bring up backend + infra first.
    # Frontend stays down until after gen-types so its build picks up the
    # freshly generated types.
    echo "Restarting backend + infra (frontend deferred)..."
    docker compose down
    docker compose up -d app postgres redis minio

    # Wait for app to be healthy.
    echo ""
    echo "Waiting for app..."
    for i in $(seq 1 18); do
        if curl -sf "http://127.0.0.1:8000/ready" > /dev/null 2>&1; then
            echo -e "${GREEN}✓ App is healthy${NC}"
            break
        fi
        if [ "$i" = "18" ]; then
            echo -e "${RED}✗ App did not respond within 90s${NC}"
            docker compose logs --tail=30 app
            return 1
        fi
        echo -n "."
        sleep 5
    done
    echo ""

    # Run migrations.
    echo ""
    echo "Running database migrations..."
    docker compose exec -T app python -m alembic upgrade head || {
        echo -e "${RED}✗ Migration failed!${NC}"
        echo "Check logs: aivis logs app"
        return 1
    }
    echo -e "${GREEN}✓ Migrations applied${NC}"

    # ----------------------------------------------------------------------
    # Seed prod DB in deterministic order.
    #
    # Iter 2.5 mini-fix #3 removed the historical reason for splitting
    # seeds around pytest: tests used to wipe shared rows in the prod DB
    # via cleanup_test_users, forcing a re-seed afterwards. Tests now
    # run against the shared dev DB without transactional isolation
    # (see backend/tests/conftest.py) and use UUID-suffixed identifiers
    # for cross-run isolation, so prod seeds can run in one block with
    # no interference.
    #
    # Each seed is idempotent:
    #   seed_platform            -- Platform user (singleton).
    #   seed_platform_templates  -- 16 active platform-default rows.
    #                               Self-healing: if a previous run left
    #                               only archived rows for a pair, the
    #                               new active version is max(v)+1 and
    #                               an audit row records the recovery.
    #   seed_documents           -- privacy_policy / terms / etc.
    #   seed_storefront          -- demo companies + products.
    #   seed_test_accounts       -- four ready-to-login test accounts.
    # ----------------------------------------------------------------------
    echo ""
    echo "Seeding prod DB..."
    docker compose exec -T app python scripts/seed_platform.py
    docker compose exec -T app python -m scripts.seed_platform_templates
    docker compose exec -T app python scripts/seed_documents.py
    docker compose exec -T app python -m scripts.seed_storefront
    # R-2.3: refuses on APP_ENV=production unless AIVIS_SEED_TEST_ACCOUNTS=1.
    docker compose exec -T app python -m scripts.seed_test_accounts ${AIVIS_SEED_TEST_ACCOUNTS:+--allow-production}
    echo -e "${GREEN}✓ Prod DB seeded${NC}"

    # ----------------------------------------------------------------------
    # Smoke check: platform templates seeded correctly in the prod DB.
    #
    # Replaces the deleted test_seed_platform_templates.py / test_template_
    # snapshot.py. Cheaper, simpler, lives at the install layer where the
    # original bug (purchase_agreement/en disappearing on update) actually
    # manifests. If this passes, the rest of the application has the seed
    # state it expects; if it fails, we abort BEFORE pytest so the failure
    # message is obvious and not buried in test cascades.
    # ----------------------------------------------------------------------
    echo ""
    echo "Smoke check: platform templates seeded..."
    template_count=$(
        docker compose exec -T postgres psql -U aivis -d aivis \
            -tAc "SELECT COUNT(*) FROM company_document_templates WHERE company_id IS NULL AND status='active';" \
            2>/dev/null | tr -d '[:space:]'
    )
    if [ "$template_count" != "16" ]; then
        echo -e "${RED}✗ Platform templates smoke check failed${NC}"
        echo "Expected 16 active platform-default templates, found: '$template_count'"
        echo "The seed_platform_templates script did not produce the expected state."
        echo "Check: docker compose exec -T app python -m scripts.seed_platform_templates --dry-run"
        return 1
    fi
    echo -e "${GREEN}✓ 16 platform templates active${NC}"



    # ----------------------------------------------------------------------
    # Run tests against an ISOLATED aivis_test DB (TD-068), provisioned
    # fresh here -- so a run never accumulates cross-run residue and never
    # touches the live dev DB. Sequential -- xdist was an artefact of the
    # abandoned per-worker design and conftest refuses it. The dev-DB seed
    # above is for the running app; tests use aivis_test via -e DATABASE_URL.
    # ----------------------------------------------------------------------
    pytest_status=0
    if [ $SKIP_TESTS -eq 0 ]; then
        if ! prepare_test_db; then
            echo -e "${RED}✗ Test DB provisioning failed${NC}"
            return 1
        fi
        echo ""
        echo "Running backend tests (against aivis_test)..."
        docker compose exec -T -e DATABASE_URL="$TEST_DB_URL" app python -m pytest tests/ -v --tb=short \
            || pytest_status=$?

        if [ $pytest_status -eq 0 ]; then
            echo -e "${GREEN}✓ All tests passed${NC}"
        else
            echo -e "${RED}✗ Tests failed -- app is running, prod DB seeded${NC}"
            echo "Fix the code and run: aivis update"
        fi
    else
        echo ""
        echo -e "${YELLOW}⊘ Backend tests skipped (--skip-tests)${NC}"
    fi

    else
        # --frontend-only: backend build / restart / migrate / seeds /
        # smoke check / tests all skipped. The frontend still gets
        # rebuilt below with the (unchanged) generated.ts.
        echo -e "${YELLOW}⊘ Backend build / restart / migrate / seeds / tests skipped (--frontend-only)${NC}"
        pytest_status=0
    fi

    # ----------------------------------------------------------------------
    # Regenerate frontend TypeScript types from live OpenAPI schema.
    #
    # If regeneration changes the file (or creates it for the first time),
    # aivis-bot commits and pushes it, so the next `aivis update` on
    # any environment pulls the up-to-date types via plain git.
    #
    # Frontend developers MUST NOT edit generated.ts manually -- the file
    # is overwritten on every deploy. Frontend-only types live in
    # frontend/src/api/types.ts.
    # ----------------------------------------------------------------------
    echo ""
    echo "Regenerating frontend types from backend OpenAPI..."
    if ! curl -sf "http://127.0.0.1:8000/openapi.json" -o /tmp/openapi.json; then
        echo -e "${RED}✗ Cannot fetch /openapi.json from backend${NC}"
        return 1
    fi
    python3 "$COMPOSE_DIR/backend/scripts/generate_ts_types.py" \
        /tmp/openapi.json \
        "$COMPOSE_DIR/frontend/src/api/generated.ts" || {
        echo -e "${RED}✗ generate_ts_types.py failed${NC}"
        rm -f /tmp/openapi.json
        return 1
    }
    rm -f /tmp/openapi.json

    # Did regeneration change anything? --porcelain reports both modified
    # tracked files and untracked new ones (first-ever run).
    if [ -n "$(git status --porcelain frontend/src/api/generated.ts)" ]; then
        echo "Schema drift detected -- committing regenerated generated.ts"

        BOT_NAME="aivis-bot"
        BOT_EMAIL="bot@aivis.local"

        git add frontend/src/api/generated.ts
        git -c user.name="$BOT_NAME" -c user.email="$BOT_EMAIL" commit -m \
"chore(types): regenerate generated.ts

Triggered by aivis update on commit $NEW_COMMIT" || {
            echo -e "${RED}✗ Bot commit failed${NC}"
            return 1
        }

        # Push with one retry: if a parallel push hits the same branch,
        # rebase on it once and try again. Anything beyond that is rare
        # and warrants manual investigation.
        PUSH_OK=0
        for attempt in 1 2; do
            if GIT_SSH_COMMAND="ssh -i /root/.ssh/id_ed25519_aivis_deploy" \
                git push origin "$BRANCH"; then
                PUSH_OK=1
                break
            fi
            if [ "$attempt" = "1" ]; then
                echo "Push failed (likely a parallel push). Rebasing and retrying..."
                GIT_SSH_COMMAND="ssh -i /root/.ssh/id_ed25519_aivis_deploy" \
                    git pull --rebase origin "$BRANCH" || break
            fi
        done

        if [ "$PUSH_OK" = "0" ]; then
            echo -e "${RED}✗ Failed to push regenerated types to GitHub${NC}"
            echo "  Bot commit exists locally on $COMPOSE_DIR but is not on origin."
            echo "  Resolve manually:"
            echo "    cd $COMPOSE_DIR && GIT_SSH_COMMAND=\"ssh -i /root/.ssh/id_ed25519_aivis_deploy\" git push"
            return 1
        fi
        echo -e "${GREEN}✓ Bot pushed regenerated types${NC}"
    else
        echo -e "${GREEN}✓ Types are in sync, no commit needed${NC}"
    fi

    # ----------------------------------------------------------------------
    # Now build the frontend with the fresh generated.ts in place.
    # ----------------------------------------------------------------------
    echo ""
    echo "Building frontend with fresh types..."
    docker compose build frontend
    docker compose up -d frontend

    # Final health check.
    echo ""
    sleep 3
    HEALTH=$(curl -s http://127.0.0.1:8000/health 2>/dev/null)
    if echo "$HEALTH" | grep -q '"status"'; then
        echo -e "${GREEN}✓ Update complete: $CURRENT_COMMIT -> $NEW_COMMIT${NC}"
    else
        echo -e "${RED}✗ Health check failed after update${NC}"
        return 1
    fi

    # Propagate pytest exit code. The whole post-seed pipeline (frontend
    # types regeneration, frontend rebuild, health check) still runs on
    # a test failure so the dev site stays usable, but `aivis update`
    # itself exits non-zero so CI / shell loops detect the breakage.
    if [ $pytest_status -ne 0 ]; then
        return 1
    fi
}

# ==============================================================================
# GEN-TYPES
# ==============================================================================
#
# Manual / on-demand regeneration of frontend/src/api/generated.ts from
# the live backend OpenAPI schema. Useful when a developer wants to
# refresh types without running a full `aivis update` (e.g. while
# iterating on a new Pydantic schema on the test VPS).
#
# This command does NOT commit or push -- it only writes the file.
# `aivis update` is what handles the bot commit/push cycle.
# ==============================================================================

case_gen_types() {
    cd_compose

    if ! curl -sf "http://127.0.0.1:8000/openapi.json" -o /tmp/openapi.json; then
        echo -e "${RED}✗ Cannot fetch /openapi.json from backend${NC}"
        echo "  Is the app container running? Check with: aivis status"
        return 1
    fi

    python3 "$COMPOSE_DIR/backend/scripts/generate_ts_types.py" \
        /tmp/openapi.json \
        "$COMPOSE_DIR/frontend/src/api/generated.ts" || {
        echo -e "${RED}✗ generate_ts_types.py failed${NC}"
        rm -f /tmp/openapi.json
        return 1
    }
    rm -f /tmp/openapi.json

    if [ -n "$(git status --porcelain frontend/src/api/generated.ts)" ]; then
        echo -e "${YELLOW}⚠ generated.ts changed -- not committed${NC}"
        echo "  Run 'aivis update' to commit and push, or commit by hand."
    else
        echo -e "${GREEN}✓ generated.ts is already up to date${NC}"
    fi
}

# ==============================================================================
# RESTART
# ==============================================================================

case_restart() {
    cd_compose
    SERVICE="${1:-}"
    if [ -n "$SERVICE" ]; then
        echo "Restarting $SERVICE..."
        docker compose restart "$SERVICE"
    else
        echo "Restarting all services..."
        docker compose restart
    fi
    echo -e "${GREEN}✓ Done${NC}"
}

# ==============================================================================
# BACKUP
# ==============================================================================
#
# Tarball includes:
#   - PostgreSQL dump (pg_dump)
#   - backend/.env
#   - MinIO bucket snapshot (mc mirror local/aivis-attachments)
#
# Rotation: 7 days. The MinIO mirror step is best-effort -- if mc fails
# (network blip, MinIO down), we proceed with DB-only backup and warn.
# ==============================================================================

case_backup() {
    cd_compose
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    BACKUP_DIR="$INSTALL_BASE/backups"
    BACKUP_FILE="$BACKUP_DIR/aivis_backup_${TIMESTAMP}.tar.gz"
    DB_DUMP_FILE="/tmp/aivis_db_${TIMESTAMP}.sql"
    MINIO_DUMP_DIR="/tmp/aivis_minio_${TIMESTAMP}"
    mkdir -p "$BACKUP_DIR"

    echo "Creating backup..."

    # 1. Dump database.
    echo "  Dumping PostgreSQL..."
    docker compose exec -T postgres pg_dump \
        -U aivis aivis > "$DB_DUMP_FILE"

    # 2. Mirror MinIO bucket (best-effort).
    echo "  Mirroring MinIO bucket..."
    mkdir -p "$MINIO_DUMP_DIR"
    if mc mirror --quiet local/aivis-attachments "$MINIO_DUMP_DIR/" 2>/dev/null; then
        MINIO_OBJECTS=$(find "$MINIO_DUMP_DIR" -type f 2>/dev/null | wc -l)
        echo "  MinIO: $MINIO_OBJECTS objects mirrored"
    else
        echo -e "${YELLOW}  ⚠ MinIO mirror failed -- proceeding with DB-only backup${NC}"
        # Keep the empty dir so tar doesn't choke on a missing path.
    fi

    # 3. Archive: DB dump + .env + MinIO snapshot.
    echo "  Creating archive..."
    tar -czf "$BACKUP_FILE" \
        -C /tmp "aivis_db_${TIMESTAMP}.sql" \
        -C "$COMPOSE_DIR/backend" ".env" \
        -C /tmp "aivis_minio_${TIMESTAMP}"

    # 4. Cleanup tmp.
    rm -f "$DB_DUMP_FILE"
    rm -rf "$MINIO_DUMP_DIR"

    # 5. Rotate: keep last 7 days.
    find "$BACKUP_DIR" -name "aivis_backup_*.tar.gz" -mtime +7 -delete

    echo -e "${GREEN}✓ Backup: $BACKUP_FILE${NC}"
    ls -lh "$BACKUP_FILE"
}

# ==============================================================================
# DATABASE
# ==============================================================================

case_db() {
    cd_compose
    case "${1:-connect}" in
        connect)
            docker compose exec postgres psql -U aivis -d aivis
            ;;
        dump)
            TIMESTAMP=$(date +%Y%m%d_%H%M%S)
            DUMP_FILE="$INSTALL_BASE/backups/aivis_db_${TIMESTAMP}.sql"
            mkdir -p "$INSTALL_BASE/backups"
            docker compose exec -T postgres pg_dump -U aivis aivis > "$DUMP_FILE"
            echo -e "${GREEN}✓ Dump: $DUMP_FILE${NC}"
            ;;
        restore)
            if [ -z "${2:-}" ]; then
                echo "Usage: aivis db restore <file>"
                exit 1
            fi
            if [ ! -f "$2" ]; then
                echo -e "${RED}File not found: $2${NC}"
                exit 1
            fi
            echo -e "${YELLOW}⚠ This will overwrite the current database!${NC}"
            read -rp "Are you sure? (y/n): " -n 1 < /dev/tty
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                echo "Restoring database..."
                cat "$2" | docker compose exec -T postgres psql -U aivis aivis
                echo -e "${GREEN}✓ Database restored${NC}"
            fi
            ;;
        migrate)
            echo "Running Alembic migrations..."
            docker compose exec -T app python -m alembic upgrade head
            echo -e "${GREEN}✓ Migrations complete${NC}"
            ;;
        *)
            echo "Database commands:"
            echo "  aivis db connect          — Connect to PostgreSQL (psql)"
            echo "  aivis db dump             — Create SQL dump"
            echo "  aivis db restore <file>   — Restore from dump"
            echo "  aivis db migrate          — Run Alembic migrations"
            ;;
    esac
}

# ==============================================================================
# SEED
# ==============================================================================

case_seed() {
    cd_compose
    # R-2.3: seed_test_accounts refuses on APP_ENV=production unless
    # AIVIS_SEED_TEST_ACCOUNTS=1 is exported (well-known credentials).
    if [ "${1:-}" = "--reset" ]; then
        docker compose exec -T app python scripts/seed_platform.py --reset
        docker compose exec -T app python scripts/seed_documents.py
        docker compose exec -T app python -m scripts.seed_storefront --reset
        docker compose exec -T app python -m scripts.seed_test_accounts --reset ${AIVIS_SEED_TEST_ACCOUNTS:+--allow-production}
    else
        docker compose exec -T app python scripts/seed_platform.py
        docker compose exec -T app python scripts/seed_documents.py
        docker compose exec -T app python -m scripts.seed_storefront
        docker compose exec -T app python -m scripts.seed_test_accounts ${AIVIS_SEED_TEST_ACCOUNTS:+--allow-production}
    fi
}

# ==============================================================================
# SEED USER PORTFOLIO (dev)
# ==============================================================================

case_seed_portfolio() {
    cd_compose
    local EMAIL="${1:-}"
    if [ -z "$EMAIL" ]; then
        echo "Usage: aivis seed-portfolio <email> [--deposit CENTS] [--purchases N]"
        echo ""
        echo "Fills a user's dashboard with deposit + random purchases (dev only)."
        echo "Defaults: --deposit 10000000 (\$100k), --purchases 5"
        exit 1
    fi
    shift
    docker compose exec -T app python -m scripts.seed_user_portfolio \
        --email "$EMAIL" "$@"
}

# ==============================================================================
# SSL
# ==============================================================================

case_ssl() {
    case "${1:-status}" in
        renew)
            echo "Renewing SSL certificates..."
            certbot renew --quiet --post-hook "systemctl reload nginx"
            echo -e "${GREEN}✓ SSL renewed${NC}"
            ;;
        status)
            echo "SSL certificate status:"
            certbot certificates 2>/dev/null || echo "No certificates found"
            ;;
        *)
            echo "SSL commands:"
            echo "  aivis ssl renew   — Renew SSL certificates"
            echo "  aivis ssl status  — Show certificate info"
            ;;
    esac
}

# ==============================================================================
# NGINX
# ==============================================================================

# ==============================================================================
# NGINX TEMPLATES
# ==============================================================================
#
# One rendering path for the three site configs, used both by this command
# and by scripts/install_aivis.sh at install time -- so there is exactly one
# copy of the template text, not one baked into the installer and a second
# one here to drift out of sync with it. Placeholders are substituted with
# sed against a QUOTED heredoc, so nginx's own runtime variables ($host,
# $scheme, $remote_addr, ...) pass through untouched -- nothing here needs
# backslash-escaping to survive shell expansion, unlike the old installer
# heredoc these bodies were carried over from verbatim.
# ==============================================================================

render_nginx_api() {
    sed "s/__API_DOMAIN__/${API_DOMAIN}/g; s/__APP_PORT__/${APP_PORT}/g" << 'NGINX_API'
server {
    listen 80;
    server_name __API_DOMAIN__;

    client_max_body_size 100M;

    location / {
        proxy_pass http://127.0.0.1:__APP_PORT__;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
        proxy_connect_timeout 10s;
    }
}
NGINX_API
}

render_nginx_frontend() {
    sed "s/__FRONTEND_DOMAIN__/${FRONTEND_DOMAIN}/g; s/__FRONTEND_PORT__/${FRONTEND_PORT}/g" << 'NGINX_FRONTEND'
server {
    listen 80;
    server_name __FRONTEND_DOMAIN__;

    location / {
        proxy_pass http://127.0.0.1:__FRONTEND_PORT__;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
NGINX_FRONTEND
}

render_nginx_storage() {
    sed "s/__STORAGE_DOMAIN__/${STORAGE_DOMAIN}/g" << 'NGINX_STORAGE'
server {
    listen 80;
    server_name __STORAGE_DOMAIN__;

    client_max_body_size 100M;

    auth_basic "MinIO Console";
    auth_basic_user_file /etc/nginx/.htpasswd-storage-mc-admin;

    # Streaming -- required for large uploads/downloads and WebSocket.
    proxy_buffering off;
    proxy_request_buffering off;
    chunked_transfer_encoding off;

    location / {
        proxy_pass http://127.0.0.1:9001;

        # CRITICAL: strip Authorization after nginx basic-auth check, otherwise
        # the browser's basic-auth header is forwarded to MinIO Console and
        # MinIO tries to parse it as S3 signature v4 -> 401 on every request
        # (Object Browser appears as a blank page after a successful login).
        proxy_set_header Authorization "";

        # $http_host preserves the port; MinIO Console uses Host for cookie domain.
        proxy_set_header Host $http_host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket upgrade -- MinIO Console pushes real-time updates.
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        proxy_read_timeout 300s;
        proxy_connect_timeout 300s;
        proxy_send_timeout 300s;
    }
}
NGINX_STORAGE
}

# Writes the requested subset of the three site configs, ensures each has a
# sites-enabled symlink, then `nginx -t` gates the reload: on failure this
# refuses to reload, so a bad template never reaches the live config, even
# though the candidate file on disk in sites-available has already been
# overwritten by that point -- the on-disk write is not what "live" means
# here, nginx keeps serving whatever it last reloaded successfully until a
# reload actually happens, and that only happens below the `-t` check.
#
# `aivis update` never calls this on its own -- rendering new templates onto
# a running server is a deliberate, separate action the operator takes, not
# a side effect of pulling code.
case_nginx_render() {
    local targets=("$@")
    if [ ${#targets[@]} -eq 0 ]; then
        targets=(all)
    fi
    if [ "${targets[0]}" = "all" ]; then
        targets=(api frontend storage)
    fi

    local target
    for target in "${targets[@]}"; do
        case "$target" in
            api)
                render_nginx_api > /etc/nginx/sites-available/aivis-api
                ln -sf /etc/nginx/sites-available/aivis-api /etc/nginx/sites-enabled/aivis-api
                echo "Rendered: aivis-api ($API_DOMAIN)"
                ;;
            frontend)
                render_nginx_frontend > /etc/nginx/sites-available/aivis-frontend
                ln -sf /etc/nginx/sites-available/aivis-frontend /etc/nginx/sites-enabled/aivis-frontend
                echo "Rendered: aivis-frontend ($FRONTEND_DOMAIN)"
                ;;
            storage)
                render_nginx_storage > /etc/nginx/sites-available/aivis-storage-mc-admin
                ln -sf /etc/nginx/sites-available/aivis-storage-mc-admin /etc/nginx/sites-enabled/aivis-storage-mc-admin
                echo "Rendered: aivis-storage-mc-admin ($STORAGE_DOMAIN)"
                ;;
            *)
                echo -e "${RED}Unknown render target: $target${NC}"
                echo "Usage: aivis nginx render [api|frontend|storage|all]"
                return 1
                ;;
        esac
    done

    if nginx -t; then
        systemctl reload nginx
        echo -e "${GREEN}✓ Nginx reloaded${NC}"
    else
        echo -e "${RED}✗ nginx -t failed -- NOT reloading. The files above were written,${NC}"
        echo -e "${RED}  but the running config is untouched. Fix the template and re-run.${NC}"
        return 1
    fi
}

case_nginx() {
    case "${1:-reload}" in
        reload)
            nginx -t && systemctl reload nginx
            echo -e "${GREEN}✓ Nginx reloaded${NC}"
            ;;
        render)
            shift
            case_nginx_render "$@"
            ;;
        *)
            echo "Nginx commands:"
            echo "  aivis nginx reload             — Test config and reload Nginx"
            echo "  aivis nginx render [target...] — Render templates from the repo (api|frontend|storage|all, default: all)"
            ;;
    esac
}

# ==============================================================================
# STORAGE (MinIO)
# ==============================================================================
#
# Subcommands:
#   stats                            — bucket size + object count
#   console                          — print Web UI URL + credentials
#   reconcile <id>                   — sync inbox/ -> attachments/
#                                      (Refactor 2 iter 2.2)
#   reconcile-templates <id>         — sync templates-inbox/ -> templates/
#                                      (Refactor 2 iter 2.3)
#   reconcile-platform-templates     — sync _platform/templates-inbox/ ...
#                                      (Refactor 2 iter 2.3)
# ==============================================================================

case_storage() {
    cd_compose
    case "${1:-}" in
        stats)
            echo -e "${CYAN}=== MinIO Storage Stats ===${NC}"
            echo ""
            echo "Bucket size:"
            mc du local/aivis-attachments 2>/dev/null || {
                echo -e "${RED}✗ Cannot reach MinIO via mc alias 'local'${NC}"
                echo "  Check: mc alias list  |  aivis status"
                return 1
            }
            echo ""
            echo "Object count:"
            local COUNT
            COUNT=$(mc ls --recursive local/aivis-attachments 2>/dev/null | wc -l)
            echo "  $COUNT objects"
            ;;
        console)
            local CONSOLE_PASS ROOT_USER ROOT_PASS
            CONSOLE_PASS=$(grep "^MINIO_CONSOLE_BASIC_AUTH_PASSWORD=" "$COMPOSE_DIR/backend/.env" | cut -d= -f2-)
            ROOT_USER=$(grep "^MINIO_ROOT_USER=" "$COMPOSE_DIR/backend/.env" | cut -d= -f2-)
            ROOT_PASS=$(grep "^MINIO_ROOT_PASSWORD=" "$COMPOSE_DIR/backend/.env" | cut -d= -f2-)
            echo -e "${CYAN}=== MinIO Console Access ===${NC}"
            echo ""
            echo "URL:      https://${STORAGE_DOMAIN}"
            echo ""
            echo "Step 1 -- nginx basic-auth:"
            echo "  Login:    admin"
            echo "  Password: $CONSOLE_PASS"
            echo ""
            echo "Step 2 -- MinIO Console login (root credentials):"
            echo "  User:     $ROOT_USER"
            echo "  Password: $ROOT_PASS"
            ;;
        reconcile)
            shift
            if [ $# -eq 0 ]; then
                echo "Usage: aivis storage reconcile <company_id> [--dry-run|--orphans-only|--broken-only]"
                echo "       aivis storage reconcile --all          [--dry-run|--orphans-only|--broken-only]"
                exit 1
            fi
            # Refactor 2 iter 2.2: pass-through to the Python reconcile script.
            # Argument validation (company_id XOR --all, mutually exclusive
            # --orphans-only / --broken-only) happens inside argparse.
            docker compose exec -T app python -m scripts.reconcile_attachments "$@"
            ;;
        reconcile-templates)
            shift
            if [ $# -eq 0 ]; then
                echo "Usage: aivis storage reconcile-templates <company_id> [--dry-run]"
                exit 1
            fi
            # Refactor 2 iter 2.3: pass-through to the Python reconcile script.
            # No --all here -- per-company templates are uploaded one company
            # at a time, and a bulk pass would mask single-company errors
            # behind aggregate stats. See AIVIS-Refactor-Company-Docs.md §4.8.
            docker compose exec -T app python -m scripts.reconcile_templates "$@"
            ;;
        reconcile-platform-templates)
            shift
            # Refactor 2 iter 2.3: pass-through to the Python reconcile script.
            # No company_id argument -- there is exactly one platform default
            # series (company_id IS NULL). See AIVIS-Refactor-Company-Docs.md §4.9.
            docker compose exec -T app python -m scripts.reconcile_platform_templates "$@"
            ;;
        ""|help|*)
            echo "Storage commands:"
            echo "  aivis storage stats                              — Bucket size + object count"
            echo "  aivis storage console                            — Print MinIO Console URL + credentials"
            echo "  aivis storage reconcile <company_id>             — Sync inbox -> attachments"
            echo "  aivis storage reconcile --all                    — Sync inbox for every company"
            echo "  aivis storage reconcile-templates <company_id>   — Sync templates-inbox -> templates"
            echo "  aivis storage reconcile-platform-templates       — Sync _platform/templates-inbox -> platform default rows"
            ;;
    esac
}

# ==============================================================================
# VERSION
# ==============================================================================

case_version() {
    cd_compose
    echo "=== AIVIS.ONE Version ==="
    echo ""
    echo "Git log (last 5 commits):"
    git log --oneline -5
    echo ""
    echo "Branch: $(git branch --show-current)"
    echo "Commit: $(git rev-parse HEAD)"
    echo ""
    echo "Runtime:"
    docker compose exec -T app python --version 2>/dev/null || true
    docker --version
    docker compose version
    echo ""
    echo "Images:"
    docker images --filter "reference=repo-*" --format "  {{.Repository}}:{{.Tag}}  {{.Size}}  {{.CreatedSince}}"
    echo ""

    # This script only ever runs the code that is actually checked out, so
    # the one way the running command surface could differ from what git
    # HEAD says is a local hand-edit -- check for that directly instead of
    # trusting a version string someone has to remember to bump.
    echo -e "${CYAN}=== Management Script Drift ===${NC}"
    local SCRIPT_LAST_CHANGED
    SCRIPT_LAST_CHANGED=$(git --no-pager log -1 --format="%h (%ci)" -- scripts/aivis-manage.sh 2>/dev/null)
    echo "This script last changed: ${SCRIPT_LAST_CHANGED:-unknown}"
    if ! git diff --quiet HEAD -- scripts/aivis-manage.sh 2>/dev/null; then
        echo -e "${YELLOW}⚠ scripts/aivis-manage.sh has UNCOMMITTED local changes --${NC}"
        echo -e "${YELLOW}  the script actually running differs from git HEAD:${NC}"
        git diff --stat HEAD -- scripts/aivis-manage.sh 2>/dev/null | sed 's/^/  /'
    else
        echo -e "${GREEN}✓ Running script matches git HEAD exactly -- no local drift${NC}"
    fi
    # Sanity-check the shim itself: is $INSTALL_BASE/scripts/manage.sh still
    # the thin exec wrapper installed once, or has something replaced it?
    local SHIM="$INSTALL_BASE/scripts/manage.sh"
    if [ -f "$SHIM" ] && grep -q "exec .*aivis-manage\.sh" "$SHIM" 2>/dev/null; then
        echo -e "${GREEN}✓ Shim ($SHIM) delegates to the tracked script${NC}"
    else
        echo -e "${YELLOW}⚠ $SHIM does not look like the expected shim -- check it by hand${NC}"
    fi
}

# ==============================================================================
# TEST EMAIL
# ==============================================================================

case_test_email() {
    cd_compose
    local RECIPIENT="${1:-}"
    if [ -z "$RECIPIENT" ]; then
        echo "Usage: aivis test-email <recipient@example.com>"
        exit 1
    fi

    echo "=== Email Delivery Test ==="
    echo ""
    echo "Recipient: $RECIPIENT"
    echo ""

    # Test 1: Mailgun API (primary)
    echo -n "1. Mailgun API... "
    MAILGUN_RESULT=$(docker compose exec -T app python -c "
import asyncio
from app.core.email import send_email
result = asyncio.run(send_email(
    recipient='$RECIPIENT',
    subject='AIVIS.ONE — Mailgun Test',
    body='This test email was sent via Mailgun HTTP API (primary channel).',
))
print('OK' if result else 'FAIL')
" 2>/dev/null)
    if echo "$MAILGUN_RESULT" | grep -q "OK"; then
        echo -e "${GREEN}✓ Sent via Mailgun${NC}"
    else
        echo -e "${RED}✗ Mailgun failed${NC}"
    fi

    # Test 2: SMTP Postfix (fallback)
    echo -n "2. SMTP Postfix... "
    SMTP_RESULT=$(docker compose exec -T app python -c "
import asyncio
from app.core.email import send_email
result = asyncio.run(send_email(
    recipient='$RECIPIENT',
    subject='AIVIS.ONE — SMTP Test',
    body='This test email was sent via SMTP Postfix (fallback channel).',
    force_smtp=True,
))
print('OK' if result else 'FAIL')
" 2>/dev/null)
    if echo "$SMTP_RESULT" | grep -q "OK"; then
        echo -e "${GREEN}✓ Sent via SMTP${NC}"
    else
        echo -e "${YELLOW}⚠ SMTP failed (outbound port 25 may be blocked by hosting provider)${NC}"
    fi

    echo ""
    echo "Check $RECIPIENT inbox for test emails."
    echo "If SMTP failed, request port 25/587 unblock from your hosting provider."
}

# ==============================================================================
# MAIN
# ==============================================================================

CMD="${1:-help}"
shift 2>/dev/null || true

case "$CMD" in
    status)         case_status ;;
    logs)           case_logs "$@" ;;
    test)           case_test "$@" ;;
    lint)           case_lint ;;
    update|deploy)  case_update "$@" ;;
    gen-types)      case_gen_types ;;
    restart)        case_restart "$@" ;;
    backup)         case_backup ;;
    db)             case_db "$@" ;;
    seed)           case_seed "$@" ;;
    seed-portfolio) case_seed_portfolio "$@" ;;
    ssl)            case_ssl "$@" ;;
    nginx)          case_nginx "$@" ;;
    storage)        case_storage "$@" ;;
    version)        case_version ;;
    test-email)     case_test_email "$@" ;;
    help|*)
        echo -e "${CYAN}AIVIS.ONE Management Script${NC}"
        echo ""
        echo "Usage: aivis <command> [options]"
        echo ""
        echo "Monitoring:"
        echo "  status                                    — Docker + health + external access + MinIO"
        echo "  logs [app|db|redis|minio|frontend|all]    — View logs (default: app)"
        echo "  version                                   — Git log + runtime versions"
        echo ""
        echo "Testing:"
        echo "  test [backend|frontend|all]               — Run tests (default: all)"
        echo "  lint                                      — Run ruff + mypy + eslint"
        echo ""
        echo "Deployment:"
        echo "  update                                    — Pull, rebuild, migrate, test, regen-types, restart"
        echo "    --skip-tests                              Skip backend tests (everything else runs)"
        echo "    --frontend-only                           Skip whole backend cycle; refuses if backend/ changed"
        echo "  gen-types                                 — Regenerate frontend generated.ts from live OpenAPI"
        echo "  restart [service]                         — Restart all or specific service"
        echo ""
        echo "Database:"
        echo "  db connect                                — Open psql session"
        echo "  db dump                                   — Create SQL dump"
        echo "  db restore <file>                         — Restore from dump"
        echo "  db migrate                                — Run Alembic migrations"
        echo "  seed                                      — Seed Platform user + legal docs + storefront + test accounts"
        echo "  seed --reset                              — Reset everything seeded by 'seed' and re-seed"
        echo "  seed-portfolio <email>                    — Dev: fill user's dashboard with deposit + purchases"
        echo ""
        echo "Storage (MinIO):"
        echo "  storage stats                             — Bucket size + object count"
        echo "  storage console                           — Print MinIO Console URL + credentials"
        echo "  storage reconcile <id>                    — Sync inbox -> DB"
        echo "  storage reconcile-templates <id>          — Sync templates-inbox -> DB"
        echo "  storage reconcile-platform-templates      — Sync platform templates"
        echo ""
        echo "Maintenance:"
        echo "  backup                                    — Backup DB + .env + MinIO (7-day rotation)"
        echo "  ssl renew                                 — Renew SSL certificates"
        echo "  ssl status                                — Show certificate info"
        echo "  nginx reload                              — Test config and reload Nginx"
        echo "  nginx render [api|frontend|storage|all]   — Render nginx templates from the repo (default: all)"
        echo "  test-email <email>                        — Test Mailgun + SMTP delivery"
        ;;
esac
