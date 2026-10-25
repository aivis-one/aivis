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

# The product commit that was last built and brought up healthy, written by
# `aivis update` at the end of a successful product cycle (H24 P-112). It
# lives OUTSIDE the checkout on purpose: the checkout is moved ahead of the
# running product before the services restart, so the checkout's HEAD says
# what is on disk, never what is running. See update_product.
DEPLOYED_COMMIT_FILE="$INSTALL_BASE/deployed-commit"

# The static company site (the apex, /): where nginx serves it from, and the
# generated include that carries its response headers. Constants of the
# product like INSTALL_BASE, not per-server facts. See "COMPANY SITE" below.
SITE_ROOT="/var/www/aivis-site"
SITE_HEADERS_SNIPPET="/etc/nginx/snippets/aivis-site-headers.conf"

CONF_FILE="$INSTALL_BASE/aivis.conf"
if [ ! -f "$CONF_FILE" ]; then
    echo "FATAL: $CONF_FILE not found." >&2
    echo "This looks like an incomplete install -- re-run scripts/install_aivis.sh," >&2
    echo "or create the file by hand with:" >&2
    echo "  API_DOMAIN=api.example.com" >&2
    echo "  FRONTEND_DOMAIN=example.com" >&2
    echo "  APP_PORT=8000" >&2
    echo "  FRONTEND_PORT=3000" >&2
    exit 1
fi
# shellcheck source=/dev/null
source "$CONF_FILE"

# -- Object storage helpers (H32 P-120) ---------------------------------------
# The public storage host is NOT a separate setting: it is the host of
# STORAGE_PUBLIC_URL in backend/.env, the address the backend signs
# download links for. One fact, one place -- the nginx site and the
# status probe both read it from there.
storage_public_host() {
    local url
    url=$(grep -E '^STORAGE_PUBLIC_URL=' "$COMPOSE_DIR/backend/.env" 2>/dev/null | tail -1 | cut -d= -f2-)
    url="${url#https://}"
    url="${url#http://}"
    echo "${url%%/*}"
}

# -- Frontend image build (H35 P-127) -----------------------------------------
# The frontend image carries two deployment addresses, both fixed when it is
# built: the API origin the cabinet calls (VITE_API_BASE_URL) and the API and
# files origins its Content-Security-Policy allows (frontend/nginx.conf,
# rendered by frontend/Dockerfile). They reach the build as build args
# (docker-compose.yml, frontend.build.args) from the two places this server
# already states them -- API_DOMAIN in aivis.conf, STORAGE_PUBLIC_URL in
# backend/.env -- and from nowhere else: the checkout carries no value. A
# missing or empty one stops the build with its name (frontend/Dockerfile,
# then vite.config.ts), never falls back to an address.
# The one way the image is built: `aivis update` and the installer
# (`aivis frontend build`) both come here.
build_frontend_image() {
    local files_origin
    files_origin=$(grep -E '^STORAGE_PUBLIC_URL=' "$COMPOSE_DIR/backend/.env" 2>/dev/null | tail -1 | cut -d= -f2- || true)
    (
        cd "$COMPOSE_DIR" || exit 1
        AIVIS_API_ORIGIN="https://${API_DOMAIN:-}" \
        AIVIS_FILES_ORIGIN="$files_origin" \
            docker compose build frontend
    )
}

case_frontend() {
    case "${1:-}" in
        build) build_frontend_image ;;
        *)
            echo "Frontend commands:"
            echo "  aivis frontend build  -- Build the frontend image with this server's addresses"
            ;;
    esac
}

# Run one rc command (RustFS's CLI, the replacement for mc) against the
# storage, inside the pinned storage-init image -- nothing is installed on
# the host. The alias is made fresh from the root keys in .env.storage on
# every call. RC_MOUNT, when set, is a host directory mounted at /backup.
storage_rc() {
    local mount=()
    if [ -n "${RC_MOUNT:-}" ]; then
        mount=(-v "$RC_MOUNT:/backup")
    fi
    docker compose run --rm --no-deps -T "${mount[@]}" --entrypoint /bin/sh storage-init -c \
        'export HOME=/tmp
         rc alias set local http://storage:9000 "$RUSTFS_ACCESS_KEY" "$RUSTFS_SECRET_KEY" > /dev/null &&
         rc "$@"' rc "$@"
}

# -- Service registry ---------------------------------------------------------
# What this box runs, and where each piece comes from. Tracked in the repo
# and read by the installer too, so the two can never disagree about a
# branch or a path. Sourced AFTER aivis.conf: a `conf:` branch expression
# resolves against the values that file just put in scope.
SERVICES_CONF="$COMPOSE_DIR/scripts/services.conf"
if [ ! -f "$SERVICES_CONF" ]; then
    echo "FATAL: $SERVICES_CONF not found." >&2
    echo "The service registry ships in this repo; a checkout without it" >&2
    echo "cannot say which services this server runs. Re-run the installer." >&2
    exit 1
fi
# shellcheck source=/dev/null
source "$SERVICES_CONF"

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
# update_all, below); the registry exists now, before a second consumer
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

# Make sure the shared external docker network exists before any `up`.
# docker-compose.yml declares `aivis-shared` as EXTERNAL (the comms stack
# joins the same network) -- compose never creates external networks, it
# requires them. Without this guard the update cycle runs `docker compose
# down` and then dies on the `up`, leaving the stand OFF rather than
# merely un-updated.
#
# Idempotent, and quiet on the happy path: it runs before every `up`, and
# a line printed on each of those would be noise that teaches people to
# skip the output. The same guard lives in the installer and in
# comms-deploy.sh -- any of the three may create it first, the result is
# identical. The network survives `docker compose down` (it is not this
# project's to remove) but not `docker network prune`, which is why the
# guard is a standing check and not a one-off install step.
ensure_shared_network() {
    docker network inspect aivis-shared > /dev/null 2>&1 && return 0
    docker network create aivis-shared > /dev/null
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

    echo -e "${CYAN}=== Storage (RustFS) ===${NC}"
    if docker compose ps --status running --services 2>/dev/null | grep -q "^storage$"; then
        if curl -sf --max-time 5 "http://127.0.0.1:9000/health" > /dev/null 2>&1; then
            echo -e "${GREEN}✓ Storage healthy (S3 API on 127.0.0.1:9000)${NC}"
        else
            echo -e "${RED}✗ Storage container running but /health not responding${NC}"
        fi
    else
        echo -e "${RED}✗ Storage container not running${NC}"
    fi
    echo ""

    echo -e "${CYAN}=== External Access ===${NC}"
    if curl -sf --max-time 5 "https://${API_DOMAIN}/health" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ https://${API_DOMAIN}/health OK${NC}"
    else
        echo -e "${RED}✗ https://${API_DOMAIN}/health unreachable${NC}"
    fi
    if curl -sf --max-time 5 "https://${FRONTEND_DOMAIN}/" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ https://${FRONTEND_DOMAIN}/ (company site) OK${NC}"
    else
        echo -e "${YELLOW}⚠ https://${FRONTEND_DOMAIN}/ not available (site not published yet)${NC}"
    fi
    if curl -sf --max-time 5 "https://${FRONTEND_DOMAIN}/app/" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ https://${FRONTEND_DOMAIN}/app/ (cabinet) OK${NC}"
    else
        echo -e "${YELLOW}⚠ https://${FRONTEND_DOMAIN}/app/ not available (frontend not deployed yet)${NC}"
    fi
    # The public storage site answers /health through nginx: 200 means the
    # site, its certificate and the proxy to 127.0.0.1:9000 all work.
    local files_host
    files_host=$(storage_public_host)
    if [ -z "$files_host" ]; then
        echo -e "${RED}✗ STORAGE_PUBLIC_URL is not set in backend/.env${NC}"
    elif curl -sf --max-time 5 "https://${files_host}/health" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ https://${files_host}/health OK${NC}"
    else
        echo -e "${RED}✗ https://${files_host}/health unreachable${NC}"
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
        storage)     docker compose logs -f --tail=100 storage ;;
        frontend)    docker compose logs -f --tail=100 frontend 2>/dev/null || echo "Frontend not running" ;;
        all|"")      docker compose logs -f --tail=100 ;;
        *)           echo "Usage: aivis logs [app|db|redis|storage|frontend|all]" ;;
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

    # The storage half, CHECKED AND NOT REPAIRED. `aivis test` may not
    # quietly supply what the run needs: a test command that fixes its own
    # environment on the way past proves only that it can fix it. The
    # repair lives in `aivis update`, where it is a stated step.
    #
    # Failing HERE rather than inside pytest is the point. Without the
    # objects the suite falls over anyway -- on 2026-09-01 it was
    # twenty-nine failures -- and the difference is what the reader gets:
    # twenty-nine StorageError tracebacks, or one line naming the count
    # and the command that restores it.
    #
    # The objects are read from the MAIN bucket even by the test run: only
    # test_storage.py redirects storage, and its fixture is local to that
    # file. Checking aivis-attachments-test here would pass precisely when
    # the agreement and certificate tests are failing.
    echo ""
    echo "Smoke check: platform template objects present..."
    check_platform_template_objects || return 1

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
            # --durations=25: the slowest tests at the end of the run -- see
            # the test step of update_product for why.
            if ! docker compose exec -T -e DATABASE_URL="$TEST_DB_URL" app python -m pytest tests/ -v --tb=short --durations=25; then
                FAILED=1
            fi
            ;;
        frontend)
            # THIS VERB CHECKED NOTHING AND SAID IT PASSED. It ran
            # `npx eslint` inside the `frontend` container, and that
            # container is nginx:alpine (frontend/Dockerfile, second
            # stage): no /app, no node, no npx. The `cd /app` failed, the
            # `|| true` swallowed it, and a green tick was printed for
            # work that never happened -- which is how "aivis test
            # frontend is green" ended up in delivery reports meaning
            # nothing at all.
            #
            # Rather than build a node container per run (an npm install
            # every time, minutes, for a check that already exists
            # elsewhere), the verb now says where the frontend IS
            # checked. A gate that prints green for an unperformed check
            # is worse than no gate: it is a lie the next reader has no
            # way to spot.
            echo "=== Frontend ==="
            echo "This box does not lint or type-check the frontend."
            echo "The serving container is nginx with a built bundle -- no"
            echo "sources and no node, so nothing here can run eslint."
            echo ""
            echo "Where the frontend IS checked:"
            echo "  aivis update  -- rebuilds it, and 'npm run build' is"
            echo "                   'vue-tsc --noEmit && vite build', so a"
            echo "                   type error stops the update."
            echo "  npm run lint  -- on a checkout with node_modules."
            exit 1
            ;;
        all)
            echo "=== Backend Tests ==="
            if ! prepare_test_db; then
                echo -e "${RED}✗ Test DB provisioning failed${NC}"
                exit 1
            fi
            # --durations=25: the slowest tests at the end of the run -- see
            # the test step of update_product for why.
            if ! docker compose exec -T -e DATABASE_URL="$TEST_DB_URL" app python -m pytest tests/ -v --tb=short --durations=25; then
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
    # No frontend section, deliberately -- see case_test. The line that
    # used to be here could not run and reported success regardless.
    echo "Frontend is not linted here: 'npm run lint' on a checkout, and"
    echo "'aivis update' type-checks it as part of the build."
}

# ==============================================================================
# UPDATE
# ==============================================================================

# -- Registry-driven update ---------------------------------------------------
# `aivis update` is no longer one function: the box runs more than one
# service now, and they are updated in registry order, top to bottom,
# with the product's BUILD last -- a service's code must be current
# before the product that calls it. The product's FILES arrive first,
# before any service (H24 P-112): services read data out of them.

# Bring one checkout to the branch the registry records for it, and
# report (through SVC_CHANGED) whether anything actually moved.
#
# The old cycle took the product branch from `git branch --show-current`,
# i.e. from whatever happened to be checked out. That is the drift this
# replaces: the recorded branch wins, and a checkout that wandered off it
# is realigned out loud.
SVC_CHANGED=0
svc_sync_checkout() {
    local dir="$1" want="$2" name="$3"
    SVC_CHANGED=0

    cd "$dir" || { echo -e "${RED}✗ $name: $dir is not reachable${NC}"; return 1; }

    if ! git fetch origin --quiet; then
        echo -e "${RED}✗ $name: git fetch failed -- nothing touched${NC}"
        return 1
    fi

    if ! git rev-parse --verify --quiet "origin/$want" > /dev/null; then
        echo -e "${RED}✗ $name: branch '$want' does not exist on origin${NC}"
        echo "  The registry says this service tracks '$want' (scripts/services.conf)."
        return 1
    fi

    local current ahead
    current=$(git branch --show-current)

    if [ "$current" = "$want" ]; then
        # Local commits that never reached origin. Realigning the branch
        # would erase them silently -- exactly what a failed types-push
        # leaves behind. Try to push them home; if that fails, STOP.
        # Losing a commit quietly is worse than a red update.
        ahead=$(git rev-list --count "origin/$want..HEAD" 2>/dev/null || echo 0)
        if [ "$ahead" -gt 0 ]; then
            echo -e "${YELLOW}⚠ $name: $ahead local commit(s) not on origin/$want -- pushing${NC}"
            if ! GIT_SSH_COMMAND="ssh -i /root/.ssh/id_ed25519_${name}_deploy" \
                 git push origin "$want"; then
                echo -e "${RED}✗ $name: cannot push local commits to origin/$want${NC}"
                echo "  Refusing to realign the checkout: that would destroy them."
                echo "  Inspect: cd $dir && git log origin/$want..HEAD"
                return 1
            fi
        fi
    else
        # The checkout drifted off its recorded branch. Local commits on a
        # FOREIGN branch are a double violation with no safe automatic
        # answer -- neither pushing them somewhere they do not belong nor
        # deleting them is ours to decide.
        if [ -n "$current" ] && git rev-parse --verify --quiet "origin/$current" > /dev/null; then
            ahead=$(git rev-list --count "origin/$current..HEAD" 2>/dev/null || echo 0)
            if [ "$ahead" -gt 0 ]; then
                echo -e "${RED}✗ $name: on branch '$current' (expected '$want') with $ahead unpushed commit(s)${NC}"
                echo "  Refusing to switch branches over them."
                echo "  Inspect: cd $dir && git log origin/$current..HEAD"
                return 1
            fi
        fi
        echo -e "${CYAN}↻ $name: checkout '${current:-detached}' -> '$want' (recorded branch wins)${NC}"
        if ! git checkout -B "$want" "origin/$want"; then
            echo -e "${RED}✗ $name: could not switch to '$want'${NC}"
            return 1
        fi
        # A branch switch replaces the code wholesale: always redeploy,
        # even though HEAD now equals origin (nothing left to pull).
        SVC_CHANGED=1
    fi

    # A service pinned to a non-main branch is allowed but never free:
    # warn (do not refuse) when main is not its ancestor -- that is the
    # moment a fix on main stops reaching this server.
    if [ "$want" != "main" ] && git rev-parse --verify --quiet origin/main > /dev/null; then
        if ! git merge-base --is-ancestor origin/main "origin/$want" 2>/dev/null; then
            echo -e "${YELLOW}⚠ $name: origin/$want is NOT a descendant of origin/main${NC}"
            echo "    Fixes landing on main do not reach this server until it is merged."
        fi
    fi

    if [ "$(git rev-parse HEAD)" != "$(git rev-parse "origin/$want")" ]; then
        SVC_CHANGED=1
    fi
    return 0
}

# Update ONE registry record.
update_service() {
    local record="$1"; shift
    local name dir branch_expr lifecycle updater want
    name=$(svc_field "$record" 1)
    dir=$(svc_field "$record" 3)
    branch_expr=$(svc_field "$record" 4)
    lifecycle=$(svc_field "$record" 5)
    updater=$(svc_field "$record" 6)

    # Presence: a service that is not on this box is a legitimate
    # configuration (a comms-less server exists -- that is every server
    # installed before comms orchestration did), not an error.
    if [ "$lifecycle" != "internal" ] && { [ ! -d "$dir/.git" ] || [ ! -f "$dir/$lifecycle" ]; }; then
        echo -e "${YELLOW}⊘ $name: not installed, skipped${NC}"
        echo ""
        return 0
    fi

    want=$(svc_branch "$branch_expr" "$name") || return 1
    echo -e "${CYAN}=== $name ($want) ===${NC}"

    if [ "$lifecycle" = "internal" ]; then
        # The product's checkout is NOT synced here: update_all already
        # brought it to origin before the first service ran (see
        # sync_product_checkout). Syncing it again here would be a second
        # way of getting the product's code, and there is one.
        #
        # The product runs its own full cycle (build, migrate, tests,
        # types, health) and decides for itself whether there is anything
        # to do -- from what was last deployed, not from the checkout. It
        # gets the branch the registry resolved, so it never has to ask
        # the checkout what it is.
        AIVIS_PRODUCT_BRANCH="$want" "$updater" "$@" || return 1
        return 0
    fi

    svc_sync_checkout "$dir" "$want" "$name" || return 1

    if [ "$SVC_CHANGED" -eq 0 ]; then
        echo -e "${GREEN}✓ $name: already up to date${NC}"
        echo ""
        return 0
    fi

    # Its own script, its own mechanics -- we only tell it to go.
    if ! bash "$dir/$lifecycle" "$updater"; then
        echo -e "${RED}✗ $name: update failed${NC}"
        return 1
    fi
    echo ""
    return 0
}

# Bring the PRODUCT's checkout to origin before any service is touched.
#
# WHY BEFORE (H24 P-112). Services read DATA out of this checkout -- comms
# bind-mounts comms-profile/ from it -- and a service's new code can refuse
# to start on the old data. When the pull came last, in update_product,
# the circle was closed: the new service would not come up on the old
# profile, the new profile only arrived with the product pull, and the
# product pull only ran once the service was up. Now the files land on
# disk first; the product's CODE is still built and restarted last, in
# update_product, because a service's code must be current before the
# product that calls it.
#
# This is the one path the product's code arrives by: the fetch in
# svc_sync_checkout, then a fast-forward. update_product does not fetch.
#
# Returns 0 when the checkout is at origin, 2 when the operator declined
# to discard local edits (nothing touched, not a failure), 1 otherwise.
# Every non-zero return happens before any service runs.
sync_product_checkout() {
    local record="$1"
    local name dir branch_expr want before after
    name=$(svc_field "$record" 1)
    dir=$(svc_field "$record" 3)
    branch_expr=$(svc_field "$record" 4)

    want=$(svc_branch "$branch_expr" "$name") || return 1
    echo -e "${CYAN}=== $name checkout ($want) -- files first, services next, build last ===${NC}"

    svc_sync_checkout "$dir" "$want" "$name" || return 1

    # Uncommitted edits. Asked HERE, before the services, because the
    # fast-forward below is what would carry them away. Use git status
    # --porcelain (same output git status reads) rather than git
    # diff-index, which fires false positives when file stat metadata
    # drifts (e.g. after chmod, touch, or filesystem restore) even when
    # the working tree is actually clean.
    if [ -n "$(git status --porcelain)" ]; then
        echo -e "${YELLOW}⚠ Uncommitted changes detected:${NC}"
        git status --short
        echo ""
        read -rp "Discard local changes and update? (y/n): " -n 1 < /dev/tty
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            return 2
        fi
        git checkout -- .
    fi

    before=$(git rev-parse --short HEAD)
    if [ "$(git rev-parse HEAD)" != "$(git rev-parse "origin/$want")" ]; then
        # Always a fast-forward here: svc_sync_checkout has already pushed
        # any local commits home or stopped the cycle -- including when
        # origin's history was rewritten, since that push is then refused
        # -- so HEAD is an ancestor of origin/$want. --ff-only says so in
        # the command, and a merge commit can never be made on the box.
        # What CAN still refuse is the working tree: an untracked file on
        # the box at a path the incoming commits add. git prints which.
        if ! git merge --ff-only --quiet "origin/$want"; then
            echo -e "${RED}✗ $name: the checkout could not be moved to origin/$want${NC}"
            echo "  git refused, and says why above -- most often an untracked file"
            echo "  on this box sits where the incoming commits add one."
            return 1
        fi
    fi
    after=$(git rev-parse --short HEAD)

    if [ "$before" = "$after" ]; then
        echo -e "${GREEN}✓ $name: checkout already at $after${NC}"
    else
        echo -e "${GREEN}✓ $name: $before -> $after on disk (before services)${NC}"
    fi
    echo ""
    return 0
}

# -- The deployed-commit record ----------------------------------------------
# What `aivis update` decides from, since H24 P-112: not "is the checkout
# behind origin" -- the checkout is moved ahead of the running product on
# purpose -- but "is what is running the checkout". See update_product.

# Sets DEPLOYED_COMMIT (full sha, or empty) and DEPLOYED_STATE, one of:
#   ok        a full sha that exists in this checkout's history
#   absent    no record -- a fresh install, or a box whose first run with
#             this logic has not finished yet
#   empty     the file exists and holds nothing
#   malformed not a full 40-character sha
#   unknown   a well-formed sha this checkout does not have
# Anything but "ok" means the running commit is not known. Must run inside
# the product checkout (the history check reads it).
read_deployed_commit() {
    DEPLOYED_COMMIT=""
    DEPLOYED_STATE=""
    if [ ! -f "$DEPLOYED_COMMIT_FILE" ]; then
        DEPLOYED_STATE="absent"
        return 0
    fi
    local raw
    raw=$(tr -d '[:space:]' < "$DEPLOYED_COMMIT_FILE" 2>/dev/null)
    if [ -z "$raw" ]; then
        DEPLOYED_STATE="empty"
    elif ! [[ "$raw" =~ ^[0-9a-f]{40}$ ]]; then
        DEPLOYED_STATE="malformed"
    elif ! git cat-file -e "${raw}^{commit}" 2>/dev/null; then
        DEPLOYED_STATE="unknown"
    else
        DEPLOYED_COMMIT="$raw"
        DEPLOYED_STATE="ok"
    fi
    return 0
}

# One line for the operator on why the running commit is not known.
deployed_state_text() {
    case "$DEPLOYED_STATE" in
        absent)    echo "no record yet" ;;
        empty)     echo "the record is empty" ;;
        malformed) echo "the record is not a commit id" ;;
        unknown)   echo "the recorded commit is not in this checkout's history" ;;
        *)         echo "$DEPLOYED_STATE" ;;
    esac
}

# Record the checkout's HEAD as deployed. Called once, after the final
# health check of a product cycle -- and after the bot's types commit, so
# the record is the commit the frontend was actually built from. Written
# to a temp file beside the record and moved over it: an interrupted
# write leaves the old record, never half a sha.
record_deployed_commit() {
    local sha tmp
    sha=$(git rev-parse HEAD) || return 1
    tmp=$(mktemp "$INSTALL_BASE/.deployed-commit.XXXXXX") || return 1
    if ! printf '%s\n' "$sha" > "$tmp" || ! mv -f "$tmp" "$DEPLOYED_COMMIT_FILE"; then
        rm -f "$tmp"
        return 1
    fi
    echo -e "${GREEN}✓ Recorded deployed commit $(git rev-parse --short HEAD)${NC}"
    return 0
}

# Restart one registry service whose PROFILE is bind-mounted out of this
# product's checkout, so that the dictionary and templates the product
# just pulled are the ones being served.
#
# UNCONDITIONAL -- deliberately not gated on "did comms-profile/ change in
# this pull". A diff gate would save one restart per update and lose the
# only thing that repairs a mismatch which did NOT arrive through a pull:
# a hand edit on the box, a half-finished previous run, a rollback. Those
# leave the running service on a profile nobody chose, and nothing else
# would ever notice.
#
# Everything is derived from the registry record. Silence is the correct
# answer in every "not applicable" case (no service env, profile kept
# elsewhere, comms-less box) -- this is an addition to `aivis update`, and
# an addition may not invent new ways for it to fail.
reload_bound_profile() {
    local record="$1"
    local name dir cli env_file profile_dir

    name=$(svc_field "$record" 1)
    dir=$(svc_field "$record" 3)
    cli=$(svc_field "$record" 5)

    # The service's own env sits next to its checkout, outside it -- the
    # layout every service CLI here uses, so that `update` never touches
    # secrets.
    env_file="$(dirname "$dir")/.env"
    [ -f "$env_file" ] || return 0

    # grep, not source: that file is full of secrets and this is a read
    # of exactly one key. `tail -n 1`, not `grep -m1`: the file is read
    # the way a shell reads assignments, so a repeated key resolves to
    # the LAST one -- first-match would act on a stale path while the
    # service used the current one.
    profile_dir=$(grep -E '^PROFILE_DIR=' "$env_file" 2>/dev/null | tail -n 1 | cut -d= -f2-)
    [ -n "$profile_dir" ] || return 0

    # Not bound into our checkout -> the pull changed nothing it reads.
    case "$profile_dir" in
        "$COMPOSE_DIR"/*) ;;
        *) return 0 ;;
    esac

    echo ""
    echo -e "${CYAN}Reloading $name -- its profile is bound to $profile_dir${NC}"
    if [ ! -f "$dir/$cli" ]; then
        echo -e "${YELLOW}⊘ $name: $dir/$cli not found -- skipping profile reload${NC}"
        return 0
    fi

    if bash "$dir/$cli" restart; then
        echo -e "${GREEN}✓ $name restarted on the profile from this checkout${NC}"
        return 0
    fi

    # The service validates its profile at startup and refuses to boot on
    # a bad one -- so by far the likeliest cause of a failure HERE is the
    # profile commit that just arrived, and the operator is looking at a
    # crash-looping service. Give them the way out, not just the verdict.
    echo -e "${RED}✗ $name did not come back after the profile reload${NC}"
    echo ""
    echo -e "${YELLOW}Most likely cause: the profile that just arrived in this pull.${NC}"
    echo "  $name refuses to start on a profile it cannot validate"
    echo "  (malformed types.yaml, one of the three msg.* chat types"
    echo "  declared without a category, ANY type declared with an empty"
    echo "  or over-long one, a broken template placeholder)."
    echo ""
    echo "  Inspect:  bash $dir/$cli logs"
    echo "  Recover:  revert the profile commit and roll out again --"
    echo "    cd $COMPOSE_DIR && git revert <commit touching comms-profile/>"
    echo "    git push && aivis update"
    echo ""
    return 1
}

# `aivis update` -- the whole box, in three steps:
#   1. the product's checkout is brought to origin (files only);
#   2. the services, in registry order;
#   3. the product is built and restarted, if what runs is not the checkout.
# Then services whose profile lives in the product's checkout restart once
# more. Step 1 comes first since H24 P-112 -- see sync_product_checkout.
update_all() {
    # Self-update guard -- this file is executed straight from the repo
    # checkout (via the shim at $INSTALL_BASE/scripts/manage.sh), and this
    # very call is about to fast-forward that same checkout below. Bash reads
    # a script incrementally by byte offset, so a mid-run rewrite of this
    # file can drop the interpreter into the middle of a different line.
    # Run the rest of the cycle from a snapshot instead: the copy is
    # immune to the pull that follows, and the next invocation of `aivis`
    # already picks up the new file on its own.
    #
    # CONSEQUENCE, and it is not a defect: logic arriving in THIS pull
    # does not run in THIS pass. On a box whose shared network does not
    # exist yet, the first `aivis update` after this lands still executes
    # the OLD script -- it will `down` and then fail on `up`. The second
    # `aivis update` runs the new one and comes back. One command, twice.
    if [ "${AIVIS_UPDATE_SNAPSHOT:-0}" != "1" ]; then
        local snapshot
        snapshot=$(mktemp /tmp/aivis-manage-snapshot.XXXXXX) || {
            echo -e "${RED}✗ Could not create the update snapshot${NC}"; exit 1; }
        cp "${BASH_SOURCE[0]}" "$snapshot" || {
            echo -e "${RED}✗ Could not snapshot ${BASH_SOURCE[0]}${NC}"; exit 1; }
        export AIVIS_UPDATE_SNAPSHOT=1 AIVIS_SNAPSHOT_PATH="$snapshot"
        # The dispatcher shifted "update"/"deploy" off $@ before calling
        # this function, so a bare "$@" here would re-launch the snapshot
        # with only the flags -- the command name is put back explicitly
        # so the re-exec lands in this branch again.
        exec bash "$snapshot" update "$@"
    fi
    # Running from the snapshot now: register its cleanup with the shared
    # trap at the top of this file instead of setting a trap of our own.
    aivis_cleanup_register "$AIVIS_SNAPSHOT_PATH"

    # Read-only pre-scan: --frontend-only is a deliberate narrow fast path
    # for iterating on the frontend, so it skips the service half
    # entirely. The flags themselves are parsed inside update_product.
    local frontend_only=0 arg
    for arg in "$@"; do
        [ "$arg" = "--frontend-only" ] && frontend_only=1
    done

    local registry_before=""
    [ -f "$SERVICES_CONF" ] && registry_before=$(md5sum "$SERVICES_CONF" 2>/dev/null)

    # -- The product's files first -------------------------------------------
    # Before any service restarts: a service may read data out of this
    # checkout (comms reads comms-profile/), and its new code may refuse
    # the old data. Only the FILES move here; the product is built and
    # restarted last, below, as before. Runs in frontend-only mode too --
    # that mode has always pulled the product.
    local record lifecycle sync_rc
    for record in "${AIVIS_SERVICES[@]}"; do
        [ "$(svc_field "$record" 5)" = "internal" ] || continue
        sync_rc=0
        sync_product_checkout "$record" || sync_rc=$?
        if [ "$sync_rc" -eq 2 ]; then
            echo "Update cancelled -- nothing was touched"
            exit 0
        fi
        if [ "$sync_rc" -ne 0 ]; then
            echo -e "${RED}✗ Update stopped at the '$(svc_field "$record" 1)' checkout, before any service -- nothing was restarted or built${NC}"
            exit 1
        fi
    done

    for record in "${AIVIS_SERVICES[@]}"; do
        lifecycle=$(svc_field "$record" 5)
        if [ "$lifecycle" != "internal" ] && [ "$frontend_only" -eq 1 ]; then
            echo -e "${YELLOW}⊘ $(svc_field "$record" 1): services skipped (--frontend-only)${NC}"
            echo ""
            continue
        fi
        if ! update_service "$record" "$@"; then
            echo -e "${RED}✗ Update stopped at '$(svc_field "$record" 1)' -- nothing after it was touched${NC}"
            exit 1
        fi
    done

    # -- Bound profiles: the SECOND restart ---------------------------------
    # The registry order is "services -> product" for CODE, and it stays
    # that way: a service's code must be current before the product that
    # calls it. A service whose PROFILE is bind-mounted out of the
    # product's checkout depends the other way round, on data -- and since
    # H24 that data is already on disk before the service loop (see
    # sync_product_checkout), so a service whose own code changed restarts
    # onto it. This pass is for the other case: the service's code did not
    # change, so the loop never restarted it, and it is still serving the
    # profile it read at its last start. Without this pass a profile-only
    # edit would sit on disk and reach the running service only when the
    # service itself next changed.
    #
    # Runs in frontend-only mode too. comms is a separate stack, its
    # profile is data rather than backend code, and the mode's guard does
    # not watch comms-profile/ -- so a commit touching only the profile
    # passes as frontend-only, and skipping the reload here would let it
    # silently never arrive.
    for record in "${AIVIS_SERVICES[@]}"; do
        [ "$(svc_field "$record" 5)" = "internal" ] && continue
        reload_bound_profile "$record" || exit 1
    done

    # A registry change arrives with the product's files, but the list was
    # read when this run started, before them -- so a newly declared
    # service starts being managed on the next run. Say so instead of
    # letting it look like a no-op.
    if [ -n "$registry_before" ] && [ -f "$SERVICES_CONF" ]; then
        if [ "$registry_before" != "$(md5sum "$SERVICES_CONF" 2>/dev/null)" ]; then
            echo ""
            echo -e "${CYAN}ℹ The service registry changed in this update.${NC}"
            echo "  Run 'aivis update' once more to apply it."
        fi
    fi
}

# ==============================================================================
# PLATFORM TEMPLATE OBJECTS -- the storage half of the template seam
# ==============================================================================
#
# A platform default template is TWO things that can be lost separately:
#   * a row in company_document_templates (company_id IS NULL, active),
#   * the objects under _platform/templates/<kind>/<lang>/ it points at.
#
# The existing smoke checks count the ROWS. On 2026-09-01 all sixteen rows
# were present and every object was gone -- the storage volume had been
# recreated empty -- so the check passed and the product answered NoSuchKey
# on every agreement and certificate. The row count was introduced after an
# earlier incident of exactly this shape ("purchase_agreement/en
# disappearing on update", per its own comment) and it still watched the
# wrong side of the seam.
#
# So: count the objects too. Sixteen template.html pairs the sixteen rows;
# sixty-four catches the logo / signature / stamp images, which render into
# the document and are just as gone when the volume is.
#
# THE COUNT RUNS THROUGH app, DELIBERATELY, in both callers: it then reads
# the same bucket, with the same credentials, through the same client the
# renderer uses. A count taken any other way could pass while the renderer
# still fails.
#
# NOTE ON THE BUCKET: templates live in the MAIN bucket for every caller,
# including the test suite. Only test_storage.py redirects storage to
# aivis-attachments-test, and it does so with a fixture local to that file.
# A check pointed at the test bucket would be green exactly when the tests
# are red.

# ONE COPY: backend/scripts/platform_template_objects.py, run inside app.
# This file used to carry its own python heredocs for the upload and the
# count, a second copy of that module -- and the installer a third. All
# three callers (this cycle, prepare_test_db, scripts/install_aivis.sh)
# now run the module, so the prefix, the source directory and the counts
# exist in one place.

# Upload backend/scripts/templates/_default/ into _platform/templates/.
# Idempotent -- an object that is already there is simply overwritten.
restore_platform_template_objects() {
    docker compose exec -T app python -m scripts.platform_template_objects upload
}

# Verify 64 objects and 16 template.html. The module prints what is wrong
# and how to restore it; a down container or a failed import is a
# non-zero exit too, never a silent pass.
check_platform_template_objects() {
    docker compose exec -T app python -m scripts.platform_template_objects check
}

# The product's own cycle. Reached through update_service (the "internal"
# record), which has already realigned this checkout to the recorded
# branch -- the fetch and pull below are what brings the commits in.
update_product() {
    # The snapshot guard that used to live here moved to update_all: the
    # whole cycle, services included, has to run from the copy.


    cd_compose

    # Parse optional flags (order-independent).
    #   --skip-tests      Skip the backend test suite (keep everything else,
    #                     incl. seeds and smoke check).
    #   --frontend-only   Skip the entire backend cycle: backend build,
    #                     full compose restart, migrations, seeds, smoke
    #                     check and backend tests. Only the OpenAPI types
    #                     regeneration + frontend rebuild run. Refuses to
    #                     proceed if backend/ or docker-compose.yml differ
    #                     between the deployed commit and the checkout, or
    #                     if the deployed commit is not known (fool-proof
    #                     guard).
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

    # NOTE: there is deliberately no `git config --global --add
    # safe.directory` here any more. It used to sit at exactly this spot
    # and it worked only by accident -- it happened to precede the first
    # git command by two lines, and stopped working the moment the fetch
    # moved into svc_sync_checkout, several hundred lines earlier. The
    # mismatch it papered over is gone: the installer now leaves the
    # checkout owned by root, which is who runs every git command here.
    # Re-adding a safe.directory call would document an ownership state
    # this product no longer produces.

    # The branch comes from AIVIS_PRODUCT_BRANCH, resolved from the
    # registry by update_service -- NOT from `git branch --show-current`,
    # which is what this used to read and which made "the branch this
    # server tracks" mean "whatever someone last checked out here".
    BRANCH="${AIVIS_PRODUCT_BRANCH:-$(git branch --show-current)}"

    # THE BOT'S WEBHOOK SECRET on a box installed before the webhook
    # existed: when backend/.env has no TELEGRAM_WEBHOOK_SECRET, make one,
    # write it (the backend reads it when it is restarted by this update)
    # and register the webhook once, the same setWebhook call the installer
    # makes. The bot token is read from the file and never printed. A
    # failure is a warning: the cabinet works without the /start welcome.
    if [ $FRONTEND_ONLY -eq 0 ]; then
        local wh_env="$COMPOSE_DIR/backend/.env" wh_secret wh_token wh_answer
        wh_secret=$(grep -E '^TELEGRAM_WEBHOOK_SECRET=' "$wh_env" 2>/dev/null | tail -n 1 | cut -d= -f2- || true)
        if [ -z "$wh_secret" ] && [ -f "$wh_env" ]; then
            wh_secret=$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-32)
            if grep -q '^TELEGRAM_WEBHOOK_SECRET=' "$wh_env"; then
                sed -i "s|^TELEGRAM_WEBHOOK_SECRET=.*|TELEGRAM_WEBHOOK_SECRET=${wh_secret}|" "$wh_env"
            else
                printf '%s\n' "TELEGRAM_WEBHOOK_SECRET=${wh_secret}" >> "$wh_env"
            fi
            wh_token=$(grep -E '^TELEGRAM_BOT_TOKEN=' "$wh_env" | tail -n 1 | cut -d= -f2- || true)
            wh_answer=$(curl -s --max-time 15 -X POST \
                "https://api.telegram.org/bot${wh_token}/setWebhook" \
                --data-urlencode "url=https://${API_DOMAIN}/api/v1/telegram/webhook" \
                --data-urlencode "secret_token=${wh_secret}" \
                --data-urlencode 'allowed_updates=["message"]' || true)
            if echo "$wh_answer" | grep -q '"ok":true'; then
                echo -e "${GREEN}✓ Bot webhook registered (new TELEGRAM_WEBHOOK_SECRET written)${NC}"
            else
                echo -e "${YELLOW}Telegram did not accept setWebhook; the /start welcome waits until it is set${NC}"
            fi
        fi
    fi

    # WHETHER THERE IS ANYTHING TO DO is decided from what was last
    # DEPLOYED, not from HEAD against origin (H24 P-112). The checkout was
    # already brought to origin before the services ran
    # (sync_product_checkout) -- this function no longer fetches or pulls
    # -- so HEAD == origin says only that the files are on disk. After a
    # run that stopped at a service, the checkout is new and the product
    # is not built; a HEAD-vs-origin check would call that "up to date"
    # on this run and every run after it, and the new backend would
    # never be built.
    read_deployed_commit
    NEW_COMMIT=$(git rev-parse --short HEAD)
    if [ "$DEPLOYED_STATE" = "ok" ]; then
        CURRENT_COMMIT=$(git rev-parse --short "$DEPLOYED_COMMIT")
        echo "Deployed: $CURRENT_COMMIT   checkout: $NEW_COMMIT ($BRANCH)"
        if [ "$DEPLOYED_COMMIT" = "$(git rev-parse HEAD)" ]; then
            echo -e "${GREEN}✓ Already up to date -- the checkout is what is running${NC}"
            return 0
        fi
    else
        CURRENT_COMMIT="unknown"
        echo "Deployed: unknown ($(deployed_state_text))   checkout: $NEW_COMMIT ($BRANCH)"
        # --frontend-only builds the frontend on top of the backend that is
        # already running, and its guard proves that safe by diffing that
        # backend's commit against the checkout. With no known commit there
        # is nothing to diff against, and "no difference found" would be a
        # guess.
        if [ $FRONTEND_ONLY -eq 1 ]; then
            echo -e "${RED}✗ The deployed commit is not known -- refusing to run with --frontend-only${NC}"
            echo "  frontend-only must prove the running backend matches this checkout,"
            echo "  and there is no deployed commit to compare it with."
            echo ""
            echo "Run: aivis update              (full cycle; records the deployed commit)"
            echo "  or aivis update --skip-tests (full cycle without tests)"
            return 1
        fi
        echo -e "${CYAN}The running commit is not known -- running the full cycle${NC}"
    fi
    echo ""

    # -- Narrow env projections, BEFORE any compose command ------------------
    # postgres/redis read backend/.env.db and storage/storage-init read
    # backend/.env.storage; both are generated from backend/.env and both
    # are gitignored, so no update of the checkout ever brings them. Compose fails
    # outright on a missing env_file -- and it parses the WHOLE file, so
    # even a frontend-only run dies on it. Regenerate here, before the
    # first compose invocation of this cycle.
    ENV_RENDER_LIB="$COMPOSE_DIR/scripts/env-render.sh"
    if [ ! -f "$ENV_RENDER_LIB" ]; then
        # Two very different states, and the compose file is the witness
        # that tells them apart. If it points at the projections and the
        # library that makes them is absent, this checkout is INCOMPLETE
        # -- the commit that brought the compose did not bring the
        # library -- and every compose command below would fail several
        # steps from the cause. If it does not point at them, this is
        # simply a checkout from before the projections existed, and
        # there is genuinely nothing to do.
        if grep -qE 'backend/\.env\.(db|storage)' "$COMPOSE_DIR/docker-compose.yml" 2>/dev/null; then
            echo -e "${RED}✗ Incomplete deployment: scripts/env-render.sh is missing${NC}"
            echo "  docker-compose.yml points postgres/redis/storage at backend/.env.db"
            echo "  and backend/.env.storage, and those files are generated by"
            echo "  scripts/env-render.sh -- which is not in this checkout."
            echo ""
            echo "  Expected at: $ENV_RENDER_LIB"
            echo "  Commit the missing file, then re-run: aivis update"
            echo ""
            echo "  The stack is untouched -- the containers still running are"
            echo "  the ones from before this update."
            return 1
        fi
        echo -e "${YELLOW}⊘ scripts/env-render.sh absent and not required by this compose -- skipping${NC}"
        echo ""
    else
        # shellcheck source=/dev/null
        source "$ENV_RENDER_LIB"
        if ! write_db_env "$COMPOSE_DIR/backend/.env" "$COMPOSE_DIR/backend/.env.db"; then
            echo -e "${RED}✗ Could not write backend/.env.db${NC}"
            echo "  postgres and redis read it as their env_file -- the stack"
            echo "  would come up without database credentials."
            return 1
        fi
        if ! write_storage_env "$COMPOSE_DIR/backend/.env" "$COMPOSE_DIR/backend/.env.storage"; then
            echo -e "${RED}✗ Could not write backend/.env.storage${NC}"
            echo "  storage and storage-init read it as their env_file -- object"
            echo "  storage would come up on empty root credentials."
            return 1
        fi
        echo -e "${GREEN}✓ backend/.env.db and backend/.env.storage projected from backend/.env${NC}"
        echo ""
    fi

    # Fool-proof guard for --frontend-only: if anything backend-side
    # differs between what is DEPLOYED and the checkout, refuse hard.
    # Deployed, not "HEAD before the pull": since H24 the checkout is
    # moved before this function runs, so HEAD-before and HEAD-after are
    # the same commit here and a diff between them would always be empty.
    # An unknown deployed commit never reaches this point (refused above).
    # Watched paths:
    #   backend/           -- app code + migrations + seed scripts
    #   docker-compose.yml -- service config, env wiring, mounts
    # docker-compose.yml lives at the repo root in aivis (unlike app
    # code which is under backend/), so we list it explicitly.
    if [ $FRONTEND_ONLY -eq 1 ]; then
        if ! git diff --quiet "$DEPLOYED_COMMIT" HEAD -- backend/ docker-compose.yml; then
            echo -e "${RED}✗ Detected backend-side changes between deployed $CURRENT_COMMIT and checkout $NEW_COMMIT${NC}"
            echo -e "${RED}  Refusing to run with --frontend-only.${NC}"
            echo ""
            echo "Changed files:"
            git diff --name-only "$DEPLOYED_COMMIT" HEAD -- backend/ docker-compose.yml | sed 's/^/  /'
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
    if ! docker compose build app; then
        echo -e "${RED}✗ Backend image build failed (see above)${NC}"
        echo "  Nothing has been stopped: the containers still running are the"
        echo "  ones from before this update. The deployed commit is not recorded."
        return 1
    fi

    # Restart stack: drop everything, bring up backend + infra first.
    # Frontend stays down until after gen-types so its build picks up the
    # freshly generated types.
    #
    # ensure_shared_network runs BEFORE the `down`, not between down and
    # up: `up` needs the external network, and if it is missing the stack
    # is already off by the time compose says so. Guarding first means the
    # worst case is "nothing happened", not "the stand is down".
    echo "Restarting backend + infra (frontend deferred)..."
    ensure_shared_network || {
        echo -e "${RED}✗ Cannot create docker network aivis-shared${NC}"
        echo "  compose needs it to exist -- it never creates an external"
        echo "  network. Nothing has been stopped."
        return 1
    }
    # --remove-orphans: a container of this project whose service is no
    # longer in the compose file is stopped and removed with the rest.
    # Without it, the move to RustFS (H32) left aivis-minio running on
    # 127.0.0.1:9000 and the new storage could not bind the port. Volumes
    # are never touched (no -v): aivis_minio_data stays as the rollback.
    if ! docker compose down --remove-orphans; then
        echo -e "${RED}✗ Stopping the stack failed (see above)${NC}"
        echo "  The stack may be partly stopped -- what runs now: docker compose ps"
        echo "  The deployed commit is not recorded."
        return 1
    fi
    if ! docker compose up -d app postgres redis storage; then
        echo -e "${RED}✗ Starting backend + infra failed (see above)${NC}"
        echo "  The stack was stopped above and is at most partly up; the"
        echo "  frontend is not running. What runs now: docker compose ps"
        echo "  The deployed commit is not recorded."
        return 1
    fi

    # storage-init IS PART OF EVERY UPDATE, not just of the install.
    # It creates the buckets and the backend service account, and both
    # live INSIDE the storage volume -- lose that volume and they are gone
    # while every other part of the stack still looks healthy. Until this
    # line existed they were created exactly once, at install, and an
    # update could not put them back: on 2026-09-01 that produced
    # InvalidAccessKeyId on 28 tests and a storage layer that answered
    # nothing.
    #
    # BLOCKING, NOT `up -d`. A one-shot container started detached
    # returns immediately and tells us nothing; the exit code below is
    # the only thing that distinguishes "buckets ready" from "refused to
    # create an account". Same lesson as an install reporting "App is
    # healthy" while the stack it just built never came up.
    echo ""
    echo "Ensuring storage buckets and service account (storage-init)..."
    docker compose up storage-init
    local init_code
    init_code=$(docker inspect -f '{{.State.ExitCode}}' aivis-storage-init 2>/dev/null || echo "missing")
    if [ "$init_code" != "0" ]; then
        echo -e "${RED}✗ storage-init did not complete (exit code: '$init_code')${NC}"
        echo "  Buckets and/or the backend service account may be missing."
        echo "  Check: aivis logs storage  |  docker compose logs storage-init"
        return 1
    fi
    echo -e "${GREEN}✓ Storage buckets and service account ready${NC}"

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
    # Re-run BOOTSTRAP after migrations. Bootstrap only -- the things the
    # product cannot run without, each idempotent:
    #   seed_platform            -- Platform user (singleton).
    #   seed_platform_templates  -- 16 active platform-default rows.
    #                               Self-healing: if a previous run left
    #                               only archived rows for a pair, the
    #                               new active version is max(v)+1 and
    #                               an audit row records the recovery.
    #   seed_documents           -- privacy_policy / terms / etc.
    #
    # T-72 REMOVED THE DEMO SEEDS FROM HERE, and this was the fourth
    # place they ran from -- the one nobody had counted. Every `aivis
    # update` re-seeded the demo storefront and the well-known test
    # logins; on a production contour only R-2.3 inside one of those two
    # scripts kept the logins out, and nothing at all kept the demo
    # storefront out. Updating a product is not a request for a demo.
    # Demo data now arrives one way: `aivis seed`, on purpose.
    # ----------------------------------------------------------------------
    # OBJECTS FIRST, ROWS SECOND -- the order the installer's own comment
    # already insists on ("Reverse order would leave the DB pointing at
    # empty storage and the renderer 500ing"). Restoring here rather than
    # merely checking is what makes a lost storage volume a non-event: the
    # sixty-four files ship inside the image, the upload is idempotent,
    # and it costs about two seconds.
    #
    # The check below still runs. A restore can be partial -- a half-read
    # source directory, a storage error mid-loop -- and "we uploaded
    # something" is not "the sixty-four objects are there". Replacing one
    # unbacked assurance with another was the whole failure of the row
    # count this pairs with.
    echo ""
    echo "Restoring platform template objects to storage..."
    restore_platform_template_objects || {
        echo -e "${RED}✗ Template object restore failed${NC}"
        return 1
    }

    echo ""
    echo "Seeding prod DB (bootstrap)..."
    local seed_step
    for seed_step in "scripts/seed_platform.py" "-m scripts.seed_platform_templates" "scripts/seed_documents.py"; do
        # Word splitting of $seed_step is intended: "-m module" is two args.
        # shellcheck disable=SC2086
        if ! docker compose exec -T app python $seed_step; then
            echo -e "${RED}✗ Bootstrap step failed: python $seed_step (see above)${NC}"
            echo "  The new backend is running on a database that is not fully"
            echo "  bootstrapped; the frontend is not running. The deployed commit"
            echo "  is not recorded."
            return 1
        fi
    done
    echo -e "${GREEN}✓ Prod DB bootstrapped${NC}"

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

    # The other side of the same seam. Sixteen rows above say the DB knows
    # about sixteen templates; this says the objects those rows point at
    # exist. Either half can be lost without the other.
    echo ""
    echo "Smoke check: platform template objects present..."
    check_platform_template_objects || return 1



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
        # --durations=25: pytest ends the run with the 25 slowest tests
        # (setup, call and teardown each). Output only -- what runs and its
        # outcome do not change. Here because the suite's time on the box
        # grew from 8 to 18 minutes while its test count grew by a quarter,
        # and the list says where the time goes. The same flag stands on
        # both runs of case_test.
        docker compose exec -T -e DATABASE_URL="$TEST_DB_URL" app python -m pytest tests/ -v --tb=short --durations=25 \
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

        # ...except the legal documents: their sources are frontend files
        # (frontend/public/legal, bind-mounted read-only into the running
        # app), and the seed archives every document whose file left that
        # folder. A frontend deploy that dropped a file without this step
        # would leave the database naming a document the site no longer has.
        echo ""
        echo "Seeding legal documents (sources are frontend files)..."
        docker compose exec -T app python scripts/seed_documents.py || {
            echo -e "${RED}✗ Legal document seed failed${NC}"
            return 1
        }
    fi

    # ----------------------------------------------------------------------
    # Regenerate frontend TypeScript types from the live OpenAPI schema and
    # commit them on drift -- generate_frontend_types + commit_generated_
    # types, the same two functions `aivis gen-types --commit` runs for the
    # installer (scripts/install_aivis.sh). One copy for both paths.
    # ----------------------------------------------------------------------
    echo ""
    echo "Regenerating frontend types from backend OpenAPI..."
    generate_frontend_types || return 1
    commit_generated_types "$BRANCH" "aivis update on commit $NEW_COMMIT" || return 1

    # ----------------------------------------------------------------------
    # Now build the frontend with the fresh generated.ts in place.
    # ----------------------------------------------------------------------
    echo ""
    echo "Building frontend with fresh types..."
    if ! build_frontend_image; then
        echo -e "${RED}✗ Frontend image build failed (see above)${NC}"
        if [ "$FRONTEND_ONLY" -eq 1 ]; then
            echo "  --frontend-only: the previous frontend keeps running."
        else
            echo "  The new backend is running; the frontend was stopped with the"
            echo "  stack above and is NOT running."
        fi
        echo "  The deployed commit is not recorded."
        return 1
    fi
    # Second `up` of this cycle, and the only one a --frontend-only run
    # reaches -- it needs the same guard as the first.
    ensure_shared_network || {
        echo -e "${RED}✗ Cannot create docker network aivis-shared${NC}"
        return 1
    }
    if ! docker compose up -d frontend; then
        echo -e "${RED}✗ Starting the frontend failed (see above)${NC}"
        echo "  The backend is running; what runs of the frontend now:"
        echo "  docker compose ps frontend. The deployed commit is not recorded."
        return 1
    fi

    # The company site (the apex, /) ships with the frontend and on a
    # --frontend-only run too: it is front-end content.
    echo ""
    case_site deploy || {
        echo -e "${RED}✗ Company site not deployed (see above)${NC}"
        return 1
    }

    # Final health check.
    echo ""
    sleep 3
    HEALTH=$(curl -s http://127.0.0.1:8000/health 2>/dev/null)
    if echo "$HEALTH" | grep -q '"status"'; then
        echo -e "${GREEN}✓ Update complete: $CURRENT_COMMIT -> $(git rev-parse --short HEAD)${NC}"
    else
        echo -e "${RED}✗ Health check failed after update${NC}"
        return 1
    fi

    # Built and running: record it. HERE, after the health check and
    # BEFORE the test verdict below, because the record says what runs,
    # and a red suite leaves the new code running (the cycle goes on past
    # it on purpose). Recording only on green would make every later
    # update rebuild -- a full outage each time -- for the same red tests.
    # HEAD, not NEW_COMMIT: the bot's types commit above moved HEAD, and
    # the frontend was built from it.
    if ! record_deployed_commit; then
        echo -e "${RED}✗ Could not record the deployed commit in $DEPLOYED_COMMIT_FILE${NC}"
        echo "  The product is running. The next aivis update will not know that"
        echo "  and will run the full cycle again."
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

# ==============================================================================
# FRONTEND TYPES -- the one copy (aivis update, aivis gen-types, installer)
# ==============================================================================
#
# frontend/src/api/generated.ts is written ONLY here, from the running
# backend's /openapi.json. Nobody edits it and no delivery carries it:
# the frontend is built AFTER this runs, so its bundle always has the
# types of the backend it talks to. Frontend-only types live in
# frontend/src/api/types.ts.
#
# Callers:
#   update_product                 -- generate + commit, then build frontend
#   aivis gen-types                -- generate and report, no commit
#   aivis gen-types --commit       -- generate + commit; what
#                                     scripts/install_aivis.sh runs before
#                                     it builds the frontend
#
# WHY THE INSTALLER COMMITS TOO. A drifted generated.ts left uncommitted on
# a fresh box makes the first `aivis update` stop on "Discard local
# changes and update?" (sync_product_checkout). Committing and pushing
# with the same code here leaves the checkout clean on both paths.

# Fetch /openapi.json from the running app and regenerate generated.ts.
generate_frontend_types() {
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
}

# On drift, commit generated.ts as aivis-bot and push it, so every box
# pulls the same types via plain git. $1 = branch, $2 = what triggered it
# (goes into the commit message).
commit_generated_types() {
    local branch="$1" trigger="$2"

    # --porcelain reports both a modified tracked file and an untracked
    # new one (first-ever run).
    if [ -z "$(git status --porcelain frontend/src/api/generated.ts)" ]; then
        echo -e "${GREEN}✓ Types are in sync, no commit needed${NC}"
        return 0
    fi

    echo "Schema drift detected -- committing regenerated generated.ts"
    git add frontend/src/api/generated.ts
    git -c user.name="aivis-bot" -c user.email="bot@aivis.local" commit -m \
"chore(types): regenerate generated.ts

Triggered by $trigger" || {
        echo -e "${RED}✗ Bot commit failed${NC}"
        return 1
    }

    # Push with one retry: if a parallel push hits the same branch,
    # rebase on it once and try again.
    local attempt push_ok=0
    for attempt in 1 2; do
        if GIT_SSH_COMMAND="ssh -i /root/.ssh/id_ed25519_aivis_deploy" \
            git push origin "$branch"; then
            push_ok=1
            break
        fi
        if [ "$attempt" = "1" ]; then
            echo "Push failed (likely a parallel push). Rebasing and retrying..."
            GIT_SSH_COMMAND="ssh -i /root/.ssh/id_ed25519_aivis_deploy" \
                git pull --rebase origin "$branch" || break
        fi
    done

    if [ "$push_ok" = "0" ]; then
        # The commit stays on this box. The next `aivis update` pushes
        # local commits home before anything else (svc_sync_checkout) --
        # so the remedy is that command, never a hand-typed git push.
        echo -e "${RED}✗ Failed to push regenerated types to GitHub${NC}"
        echo "  The commit is kept on this box; run 'aivis update' again --"
        echo "  it pushes local commits first."
        return 1
    fi
    echo -e "${GREEN}✓ Bot pushed regenerated types${NC}"
}

case_gen_types() {
    cd_compose
    case "${1:-}" in
        --commit)
            generate_frontend_types || return 1
            commit_generated_types "$(git branch --show-current)" \
                "aivis gen-types --commit on commit $(git rev-parse --short HEAD)"
            ;;
        "")
            generate_frontend_types || return 1
            if [ -n "$(git status --porcelain frontend/src/api/generated.ts)" ]; then
                echo -e "${YELLOW}⚠ generated.ts changed -- not committed${NC}"
                echo "  Run 'aivis update' (or 'aivis gen-types --commit') to commit and push."
            else
                echo -e "${GREEN}✓ generated.ts is already up to date${NC}"
            fi
            ;;
        *)
            echo "Usage: aivis gen-types [--commit]"
            return 1
            ;;
    esac
}

# ==============================================================================
# RESTART
# ==============================================================================

case_restart() {
    cd_compose
    SERVICE="${1:-}"
    if [ -n "$SERVICE" ]; then
        echo "Restarting $SERVICE..."
        docker compose restart "$SERVICE" || {
            echo -e "${RED}✗ Restart of $SERVICE failed (see above) -- what runs now: docker compose ps${NC}"
            return 1
        }
    else
        echo "Restarting all services..."
        docker compose restart || {
            echo -e "${RED}✗ Restart failed (see above) -- what runs now: docker compose ps${NC}"
            return 1
        }
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
#   - storage bucket snapshot (rc mirror local/aivis-attachments, run in
#     the pinned storage-init image -- see storage_rc)
#
# Rotation: 7 days. The storage mirror step is best-effort -- if it fails
# (storage down), we proceed with DB-only backup and warn.
#
# There is no storage RESTORE. Acknowledged debt, not built here (H32).
# ==============================================================================

case_backup() {
    cd_compose
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    BACKUP_DIR="$INSTALL_BASE/backups"
    BACKUP_FILE="$BACKUP_DIR/aivis_backup_${TIMESTAMP}.tar.gz"
    DB_DUMP_FILE="/tmp/aivis_db_${TIMESTAMP}.sql"
    STORAGE_DUMP_DIR="/tmp/aivis_storage_${TIMESTAMP}"
    mkdir -p "$BACKUP_DIR"

    echo "Creating backup..."

    # 1. Dump database.
    echo "  Dumping PostgreSQL..."
    if ! docker compose exec -T postgres pg_dump \
        -U aivis aivis > "$DB_DUMP_FILE"; then
        rm -f "$DB_DUMP_FILE"
        echo -e "${RED}✗ Database dump failed (see above) -- no backup was written${NC}"
        return 1
    fi

    # 2. Mirror the storage bucket (best-effort).
    echo "  Mirroring storage bucket..."
    mkdir -p "$STORAGE_DUMP_DIR"
    if RC_MOUNT="$STORAGE_DUMP_DIR" storage_rc mirror local/aivis-attachments /backup > /dev/null 2>&1; then
        STORAGE_OBJECTS=$(find "$STORAGE_DUMP_DIR" -type f 2>/dev/null | wc -l)
        echo "  Storage: $STORAGE_OBJECTS objects mirrored"
    else
        echo -e "${YELLOW}  ⚠ Storage mirror failed -- proceeding with DB-only backup${NC}"
        # Keep the empty dir so tar doesn't choke on a missing path.
    fi

    # 3. Archive: DB dump + .env + storage snapshot.
    echo "  Creating archive..."
    if ! tar -czf "$BACKUP_FILE" \
        -C /tmp "aivis_db_${TIMESTAMP}.sql" \
        -C "$COMPOSE_DIR/backend" ".env" \
        -C /tmp "aivis_storage_${TIMESTAMP}"; then
        rm -f "$BACKUP_FILE" "$DB_DUMP_FILE"
        rm -rf "$STORAGE_DUMP_DIR"
        echo -e "${RED}✗ Archive could not be written (see above) -- no backup was made${NC}"
        return 1
    fi

    # 4. Cleanup tmp.
    rm -f "$DB_DUMP_FILE"
    rm -rf "$STORAGE_DUMP_DIR"

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
            # Arguments after `connect` go through to psql. They used to
            # be dropped: the case branch read $1 and nothing else, so
            # `aivis db connect -c "SELECT ..."` opened an interactive
            # session and threw the query away -- the operator saw a
            # prompt where they expected a result, with nothing to say
            # the flag had been ignored.
            #
            # -T only in the non-interactive form: psql -c wants no
            # terminal, and an interactive session cannot live without
            # one.
            shift
            if [ "$#" -gt 0 ]; then
                docker compose exec -T postgres psql -U aivis -d aivis "$@"
            else
                docker compose exec postgres psql -U aivis -d aivis
            fi
            ;;
        dump)
            TIMESTAMP=$(date +%Y%m%d_%H%M%S)
            DUMP_FILE="$INSTALL_BASE/backups/aivis_db_${TIMESTAMP}.sql"
            mkdir -p "$INSTALL_BASE/backups"
            if ! docker compose exec -T postgres pg_dump -U aivis aivis > "$DUMP_FILE"; then
                rm -f "$DUMP_FILE"
                echo -e "${RED}✗ Dump failed (see above) -- no file was kept${NC}"
                return 1
            fi
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
                if ! docker compose exec -T postgres psql -U aivis aivis < "$2"; then
                    echo -e "${RED}✗ Restore failed (see above) -- the database may be partly restored${NC}"
                    return 1
                fi
                echo -e "${GREEN}✓ Database restored${NC}"
            fi
            ;;
        migrate)
            echo "Running Alembic migrations..."
            if ! docker compose exec -T app python -m alembic upgrade head; then
                echo -e "${RED}✗ Migration failed (see above)${NC}"
                return 1
            fi
            echo -e "${GREEN}✓ Migrations complete${NC}"
            ;;
        *)
            echo "Database commands:"
            echo "  aivis db connect [args]   — Open psql; any args go through to psql"
            echo "                              e.g. aivis db connect -c \"SELECT 1;\""
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

    # ----------------------------------------------------------------------
    # T-72: one verb, one script, one place the contour is checked.
    #
    # This used to run four seed scripts in a row and the production
    # guard lived inside ONE of them (R-2.3: seed_test_accounts refused
    # the well-known seedpass123 logins on APP_ENV=production). The
    # guard moves here, to the command, because the command is now the
    # only sanctioned way in -- and because a guard inside the script
    # protected nothing the moment a second script was added beside it.
    #
    # Bootstrap is NOT seeding and is not run from here: the platform
    # user, the platform templates and the legal documents are what the
    # product needs to exist, they are installed by install_aivis.sh,
    # and re-running them is not part of "make me a demo".
    #
    # AIVIS_SEED_DEMO=1 is the explicit opt-in on a production contour.
    # It is deliberately not a flag on the command line: a variable has
    # to be exported on purpose and does not end up in shell history as
    # part of an otherwise ordinary command.
    # ----------------------------------------------------------------------
    local app_env
    app_env=$(grep "^APP_ENV=" "$COMPOSE_DIR/backend/.env" 2>/dev/null | cut -d= -f2- | tr -d '"')

    if [ "$app_env" = "production" ] && [ -z "${AIVIS_SEED_DEMO:-}" ]; then
        echo -e "${RED}✗ Refusing to seed demo data on APP_ENV=production${NC}"
        echo ""
        echo "The seed creates demo people and demo projects on the"
        echo "storefront. On a production contour that is fake accounts and"
        echo "fake offers next to real ones."
        echo ""
        echo "If this box really is a stand that merely calls itself"
        echo "production, opt in explicitly:"
        echo "    AIVIS_SEED_DEMO=1 aivis seed"
        return 1
    fi

    docker compose exec -T app python scripts/seed.py "$@"
}

# ==============================================================================
# FIRST ADMIN (H30 P-118)
# ==============================================================================
#
# The production path to the first admin: promotes an ALREADY registered,
# verified user and creates nothing else. Refuses for good once the box
# has an admin -- from then on staff is appointed in the interface. Runs
# on any APP_ENV, production included; `aivis seed` is the test stands'
# path and refuses production. The decisions live in
# backend/app/modules/staff/bootstrap.py; the exit code is the script's
# (0 promoted, 1 refused with nothing written, 2 usage).
case_bootstrap_admin() {
    cd_compose
    if [ "$#" -ne 1 ] || [ -z "${1// /}" ]; then
        echo "Usage: aivis bootstrap-admin <email of a registered, verified user>"
        return 2
    fi
    docker compose exec -T app python -m scripts.bootstrap_admin "$1"
}

# ==============================================================================
# SEED USER PORTFOLIO (dev)
# ==============================================================================

case_seed_portfolio() {
    cd_compose

    # T-72: the verb survives, the script under it does not. Filling ONE
    # named person's dashboard is not something a profile can express --
    # the target already exists and is chosen by e-mail -- so it stays a
    # separate entry point into the same seed rather than a second
    # seeding mechanism that would drift away from the first.
    #
    # This path never writes users.seeded_profile: the target is a live
    # person, and topping up their dashboard must not make them
    # deletable by `aivis seed --reset`.
    local EMAIL="${1:-}"
    if [ -z "$EMAIL" ]; then
        echo "Usage: aivis seed-portfolio <email> [--deposit CENTS] [--purchases N]"
        echo ""
        echo "Fills an existing user's dashboard with a deposit + purchases."
        echo "Defaults: --deposit 10000000 (\$100k), --purchases 5"
        exit 1
    fi
    shift
    docker compose exec -T app python scripts/seed.py \
        --portfolio-for "$EMAIL" "$@"
}

# ==============================================================================
# SSL
# ==============================================================================

case_ssl() {
    case "${1:-status}" in
        renew)
            echo "Renewing SSL certificates..."
            if ! certbot renew --quiet --post-hook "systemctl reload nginx"; then
                echo -e "${RED}✗ certbot renew failed (see above) -- the current certificates stay in use${NC}"
                return 1
            fi
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

# The apex serves two things:
#   /app/   the cabinet -- proxied to the frontend container with the prefix
#           KEPT (frontend/nginx.conf serves it under /app/ itself);
#   /login  a redirect into the cabinet, the address the site's button uses;
#   /       the static company site, built from landing/ and copied to
#           SITE_ROOT by `aivis site publish`.
# The site's own Cloudflare Pages rules are reproduced here:
#   _headers  -> the generated include SITE_HEADERS_SNIPPET (every site
#                response; the cabinet sends its own CSP from the container);
#                the two other rules of that file are written out below;
#   _redirects -> `location = /ru`.
# An `add_header` inside a location drops every inherited one, so no header
# sits at server level: each site location includes the snippet itself.
# Cloudflare stays in front as a proxy (SSL mode "full"): this block is the
# origin, and certbot adds its TLS server block to the rendered file.
render_nginx_frontend() {
    sed "s/__FRONTEND_DOMAIN__/${FRONTEND_DOMAIN}/g; s/__FRONTEND_PORT__/${FRONTEND_PORT}/g; s#__SITE_ROOT__#${SITE_ROOT}#g; s#__SITE_HEADERS__#${SITE_HEADERS_SNIPPET}#g" << 'NGINX_FRONTEND'
server {
    listen 80;
    server_name __FRONTEND_DOMAIN__;

    root __SITE_ROOT__;
    index index.html;

    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml image/svg+xml;
    gzip_min_length 256;
    gzip_vary on;

    # -- The cabinet --
    location = /login {
        return 302 /app/login$is_args$args;
    }

    location = /app {
        return 301 /app/;
    }

    location ^~ /app/ {
        proxy_pass http://127.0.0.1:__FRONTEND_PORT__;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # -- The company site --
    location = /ru {
        include __SITE_HEADERS__;
        return 301 /ru/;
    }

    # _headers: /assets/*
    location ^~ /assets/ {
        include __SITE_HEADERS__;
        add_header Cache-Control "public, max-age=31536000, immutable" always;
        try_files $uri =404;
    }

    # _headers: /invest/* and /ru/invest/* -- never indexed, never followed
    location ~ ^(/ru)?/invest/ {
        include __SITE_HEADERS__;
        add_header X-Robots-Tag "noindex, nofollow" always;
        try_files $uri $uri/ =404;
    }

    location / {
        include __SITE_HEADERS__;
        try_files $uri $uri/ =404;
    }
}
NGINX_FRONTEND
}

# The public storage site (H32 P-121): browsers open the presigned links
# the backend signs for this host. HTTP only, like every template here --
# certbot adds the TLS server block to the rendered file afterwards, which
# is why a re-render of this target drops TLS until certbot runs again.
#
#   Host passes through UNCHANGED ($host): the SigV4 signature covers the
#     host the link was signed for; a rewritten Host makes the storage
#     answer 403 (checked against RustFS 1.0.1, H32 stand).
#   The path passes through unchanged too (no trailing slash on
#     proxy_pass, no rewrite): path-style links, <host>/<bucket>/<key>.
#   No Authorization stripping, no basic-auth: links carry their own
#     signature in the query string, and nothing else is served.
#   client_max_body_size mirrors STORAGE_MAX_FILE_SIZE_MB (100).
render_nginx_files() {
    local files_host
    files_host=$(storage_public_host)
    if [ -z "$files_host" ]; then
        echo "STORAGE_PUBLIC_URL is not set in backend/.env -- cannot render the files site" >&2
        return 1
    fi
    sed "s/__FILES_DOMAIN__/${files_host}/g" << 'NGINX_FILES'
server {
    listen 80;
    server_name __FILES_DOMAIN__;

    client_max_body_size 100M;

    # Streaming -- large downloads go straight through.
    proxy_buffering off;
    proxy_request_buffering off;

    location / {
        proxy_pass http://127.0.0.1:9000;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_http_version 1.1;
        proxy_read_timeout 300s;
        proxy_connect_timeout 60s;
        proxy_send_timeout 300s;
    }
}
NGINX_FILES
}

# ==============================================================================
# COMPANY SITE (the apex, /, row 32)
# ==============================================================================
#
# The static site is built from landing/ in the checkout and copied to
# SITE_ROOT, which the apex's nginx block serves. Two steps, so that the
# install can run them before nginx has any site block:
#   build    python3 only, standard library: the site, then the four courses
#            (landing/README.md "Build"). The legal pages are NOT written
#            into the checkout: landing/legal/out/ is tracked and the site
#            build reads it. They are rebuilt into a temporary folder and
#            compared with out/; a difference REFUSES the build.
#   publish  copies landing/site/dist to SITE_ROOT (without the Pages control
#            files, which are not content) into a release folder, writes
#            SITE_HEADERS_SNIPPET from dist/_headers, tests nginx, and flips
#            the SITE_ROOT symlink atomically.
# `aivis update` runs both on every cycle, --frontend-only included, then
# reloads nginx: the CSP lists a hash for every inline block, so a new page
# build needs the new snippet in the same moment.
site_build() {
    local landing="$COMPOSE_DIR/landing" legal_tmp
    if ! command -v python3 > /dev/null 2>&1; then
        echo -e "${RED}✗ python3 is not installed -- the site cannot be built${NC}" >&2
        return 1
    fi
    # The legal pages are not written into the checkout (landing/legal/out/ is
    # tracked), but a legal source committed without its out/ would ship old
    # pages silently: rebuild into a temporary folder and refuse on a difference.
    legal_tmp=$(mktemp -d) || return 1
    if ! (cd "$landing/legal" && python3 build.py --out "$legal_tmp" > /dev/null 2>&1); then
        rm -rf "$legal_tmp"
        echo -e "${RED}✗ The legal pages do not build from their sources (cd landing/legal && python3 build.py) -- nothing was published${NC}" >&2
        return 1
    fi
    if ! diff -r "$legal_tmp" "$landing/legal/out" > /dev/null 2>&1; then
        rm -rf "$legal_tmp"
        echo -e "${RED}✗ landing/legal/out is out of date against the legal sources -- rebuild it (cd landing/legal && python3 build.py), commit it, then update again. Nothing was published.${NC}" >&2
        return 1
    fi
    rm -rf "$legal_tmp"
    echo "Building the company site..."
    rm -rf "$landing/site/dist"
    (cd "$landing/site" && python3 scripts/build-site.py \
        --site content/site.json --content-dir content \
        --tokens tokens.tokens.json --assets-dir assets --out dist) || {
        echo -e "${RED}✗ Site build failed${NC}" >&2
        return 1
    }
    (cd "$landing" && python3 courses/build.py) || {
        echo -e "${RED}✗ Course pages build failed${NC}" >&2
        return 1
    }
    if [ ! -f "$landing/site/dist/index.html" ] || [ ! -f "$landing/site/dist/_headers" ]; then
        echo -e "${RED}✗ The site build left no index.html or _headers in landing/site/dist${NC}" >&2
        return 1
    fi
    echo -e "${GREEN}✓ Site built: landing/site/dist${NC}"
}

# dist/_headers -> nginx `add_header` lines, for the `/*` rule only. The other
# three rules of that file (/assets/*, /invest/*, /ru/invest/*) are written
# out in render_nginx_frontend; a rule this does not know is REFUSED, so a new
# path in _headers cannot be dropped silently. A header line it cannot quote
# safely, or a result without the Content-Security-Policy, is refused as well.
render_site_headers() {
    local src="$1" paths
    paths=$(tr -d '\r' < "$src" | grep -E '^[^[:space:]#]' | paste -sd ' ' -)
    if [ "$paths" != '/* /assets/* /invest/* /ru/invest/*' ]; then
        echo "_headers carries rules this script does not reproduce: ${paths}" >&2
        return 1
    fi
    tr -d '\r' < "$src" | awk '
        /^[^ \t#]/ { inblock = ($0 == "/*"); next }
        inblock && /^[ \t]+[A-Za-z-]+:/ {
            line = $0
            sub(/^[ \t]+/, "", line)
            name = line; sub(/:.*/, "", name)
            val = line;  sub(/^[^:]*:[ \t]*/, "", val); sub(/[ \t]+$/, "", val)
            if (index(val, "\"") || index(val, "$") || index(val, "\\")) bad = 1
            printf "add_header %s \"%s\" always;\n", name, val
        }
        END { exit bad }
    ' || { echo "a _headers value cannot be written as an nginx string" >&2; return 1; }
}

# The published tree is a RELEASE folder, and SITE_ROOT is a symlink to the
# live release (nginx's root points at the symlink). Order: write the new
# headers snippet and run `nginx -t` on it -- on failure the old snippet is
# put back and nothing is swapped; then the symlink is flipped atomically
# (`ln -sfn` to a temporary link, `mv -T` over SITE_ROOT). The previous
# release stays beside it for rollback; older ones are removed.
# Puts the headers snippet back as it was before a publish ($1: the saved copy,
# empty when there was none) and removes the staged release ($2).
site_publish_undo() {
    if [ -n "$1" ]; then
        mv "$1" "$SITE_HEADERS_SNIPPET"
    else
        rm -f "$SITE_HEADERS_SNIPPET"
    fi
    rm -rf "$2"
}

site_publish() {
    local src="$COMPOSE_DIR/landing/site/dist" snippet_tmp snippet_old="" releases rel stamp
    releases="${SITE_ROOT}-releases"
    if [ ! -f "$src/index.html" ]; then
        echo -e "${RED}✗ $src has no index.html -- run: aivis site build${NC}" >&2
        return 1
    fi
    snippet_tmp="${SITE_HEADERS_SNIPPET}.new"
    mkdir -p "$(dirname "$SITE_HEADERS_SNIPPET")" "$releases" || return 1
    render_site_headers "$src/_headers" > "$snippet_tmp" || { rm -f "$snippet_tmp"; return 1; }
    if ! grep -q '^add_header Content-Security-Policy ' "$snippet_tmp"; then
        rm -f "$snippet_tmp"
        echo -e "${RED}✗ _headers has no Content-Security-Policy -- refusing to publish a site without it${NC}" >&2
        return 1
    fi
    # 1. Stage the new release next to the old ones; nothing is live yet.
    #    mktemp -d gives a fresh name even for two publishes in one second, so
    #    the live release is never the one being staged.
    stamp=$(date +%Y%m%d%H%M%S)
    rel=$(mktemp -d "$releases/$stamp-XXXX") || { rm -f "$snippet_tmp"; return 1; }
    cp -a "$src/." "$rel/" || { rm -rf "$rel"; rm -f "$snippet_tmp"; return 1; }
    #    After the copy, never before it: cp -a carries dist's own mode onto
    #    $rel, and build-site.py makes dist with tempfile.mkdtemp (0700), so a
    #    chmod before the copy is undone and nginx (www-data) gets EACCES --
    #    403 on / and 404 on every file (the 2026-10-14 install).
    chmod -R a+rX "$rel" || { rm -rf "$rel"; rm -f "$snippet_tmp"; return 1; }
    rm -f "$rel/_headers" "$rel/_redirects" "$rel/cloudflare-redirect-rule.txt"
    # 2. New snippet in place, then nginx -t. Failure: the old snippet comes
    #    back and the swap does not happen -- the old release stays live.
    if [ -f "$SITE_HEADERS_SNIPPET" ]; then
        snippet_old="${SITE_HEADERS_SNIPPET}.old"
        cp -p "$SITE_HEADERS_SNIPPET" "$snippet_old" || { rm -rf "$rel"; rm -f "$snippet_tmp"; return 1; }
    fi
    mv "$snippet_tmp" "$SITE_HEADERS_SNIPPET" || { rm -rf "$rel"; return 1; }
    # Until a server block includes the snippet nginx -t cannot say anything
    # about it (the install publishes before it renders the block).
    if grep -RqsF "$SITE_HEADERS_SNIPPET" "${NGINX_ETC:-/etc/nginx}/sites-enabled" "${NGINX_ETC:-/etc/nginx}/conf.d" 2> /dev/null; then
        if ! nginx -t > /dev/null 2>&1; then
            if [ -n "$snippet_old" ]; then
                mv "$snippet_old" "$SITE_HEADERS_SNIPPET"
            else
                rm -f "$SITE_HEADERS_SNIPPET"
            fi
            rm -rf "$rel"
            echo -e "${RED}✗ nginx -t failed with the new headers -- old headers and old site left in place, nothing was swapped${NC}" >&2
            nginx -t 2>&1 | sed 's/^/    /' >&2
            return 1
        fi
    fi
    # 3. A SITE_ROOT that is still a real folder (the previous layout) becomes
    #    the first release; this is the only non-atomic moment, once.
    if [ -d "$SITE_ROOT" ] && [ ! -L "$SITE_ROOT" ]; then
        mv "$SITE_ROOT" "$releases/legacy-$stamp" || { site_publish_undo "$snippet_old" "$rel"; return 1; }
        ln -s "$releases/legacy-$stamp" "$SITE_ROOT" || {
            mv "$releases/legacy-$stamp" "$SITE_ROOT"
            site_publish_undo "$snippet_old" "$rel"
            return 1
        }
    fi
    # 4. The atomic flip. Failure: the old snippet comes back and the staged
    #    release goes, so the next reload and the next cleanup see the old state.
    ln -sfn "$rel" "${SITE_ROOT}.tmp-link" && mv -T "${SITE_ROOT}.tmp-link" "$SITE_ROOT" || {
        rm -f "${SITE_ROOT}.tmp-link"
        site_publish_undo "$snippet_old" "$rel"
        echo -e "${RED}✗ Could not switch $SITE_ROOT to the new release -- old headers and old site left in place${NC}" >&2
        return 1
    }
    rm -f "$snippet_old"
    # 5. Keep the live release and the one before it for rollback; drop older.
    # shellcheck disable=SC2012
    ls -1dt "$releases"/*/ 2> /dev/null | tail -n +3 | while read -r old; do rm -rf "$old"; done
    echo -e "${GREEN}✓ Site published: $SITE_ROOT -> $rel (headers: $SITE_HEADERS_SNIPPET)${NC}"
}

case_site() {
    case "${1:-}" in
        build)   site_build ;;
        publish) site_publish ;;
        deploy)
            site_build && site_publish || return 1
            nginx -t && systemctl reload nginx
            ;;
        *)
            echo "Site commands:"
            echo "  aivis site build     — Build the company site from landing/ (python3)"
            echo "  aivis site publish   — Copy the built site to ${SITE_ROOT} and write its nginx headers"
            echo "  aivis site deploy    — build + publish + nginx test and reload (what 'aivis update' runs)"
            ;;
    esac
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
        targets=(api frontend files)
    fi

    local target
    for target in "${targets[@]}"; do
        case "$target" in
            api)
                render_nginx_api > /etc/nginx/sites-available/aivis-api || {
                    echo -e "${RED}✗ Could not write the aivis-api site -- nginx not reloaded${NC}"
                    return 1
                }
                ln -sf /etc/nginx/sites-available/aivis-api /etc/nginx/sites-enabled/aivis-api
                echo "Rendered: aivis-api ($API_DOMAIN)"
                ;;
            frontend)
                if [ ! -f "$SITE_HEADERS_SNIPPET" ]; then
                    echo -e "${RED}✗ $SITE_HEADERS_SNIPPET is missing -- run: aivis site build && aivis site publish${NC}"
                    return 1
                fi
                render_nginx_frontend > /etc/nginx/sites-available/aivis-frontend || {
                    echo -e "${RED}✗ Could not write the aivis-frontend site -- nginx not reloaded${NC}"
                    return 1
                }
                ln -sf /etc/nginx/sites-available/aivis-frontend /etc/nginx/sites-enabled/aivis-frontend
                echo "Rendered: aivis-frontend ($FRONTEND_DOMAIN)"
                ;;
            files)
                local files_conf
                files_conf=$(render_nginx_files) || return 1
                printf '%s\n' "$files_conf" > /etc/nginx/sites-available/aivis-files || {
                    echo -e "${RED}✗ Could not write the aivis-files site -- nginx not reloaded${NC}"
                    return 1
                }
                ln -sf /etc/nginx/sites-available/aivis-files /etc/nginx/sites-enabled/aivis-files
                echo "Rendered: aivis-files ($(storage_public_host))"
                ;;
            *)
                echo -e "${RED}Unknown render target: $target${NC}"
                echo "Usage: aivis nginx render [api|frontend|files|all]"
                return 1
                ;;
        esac
    done

    if nginx -t; then
        if ! systemctl reload nginx; then
            echo -e "${RED}✗ nginx -t passed but the reload failed -- the running config is the old one${NC}"
            return 1
        fi
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
            if ! { nginx -t && systemctl reload nginx; }; then
                echo -e "${RED}✗ Nginx not reloaded (see above) -- the running config is the old one${NC}"
                return 1
            fi
            echo -e "${GREEN}✓ Nginx reloaded${NC}"
            ;;
        render)
            shift
            case_nginx_render "$@"
            ;;
        *)
            echo "Nginx commands:"
            echo "  aivis nginx reload             — Test config and reload Nginx"
            echo "  aivis nginx render [target...] — Render templates from the repo (api|frontend|files|all, default: all)"
            ;;
    esac
}

# ==============================================================================
# STORAGE (RustFS)
# ==============================================================================
#
# Subcommands:
#   stats                            — bucket size + object count
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
            echo -e "${CYAN}=== Storage Stats ===${NC}"
            echo ""
            echo "Bucket size:"
            storage_rc du local/aivis-attachments || {
                echo -e "${RED}✗ Cannot reach the storage${NC}"
                echo "  Check: aivis status  |  aivis logs storage"
                return 1
            }
            echo ""
            echo "Object count:"
            local listing
            listing=$(storage_rc ls --recursive local/aivis-attachments 2>/dev/null) || {
                echo -e "${RED}✗ Could not list the bucket -- no count${NC}"
                return 1
            }
            printf '%s\n' "$listing" | grep -c . || true
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
    echo "Commit: $(git rev-parse HEAD)   (the checkout)"
    # The checkout is not necessarily what runs (H24 P-112): `aivis update`
    # moves it before the services and builds the product last, so a run
    # that stopped at a service leaves it ahead of the running product.
    read_deployed_commit
    if [ "$DEPLOYED_STATE" != "ok" ]; then
        echo -e "${YELLOW}Deployed: unknown ($(deployed_state_text)) -- the next aivis update runs the full cycle${NC}"
    elif [ "$DEPLOYED_COMMIT" = "$(git rev-parse HEAD)" ]; then
        echo "Deployed: $DEPLOYED_COMMIT   (same as the checkout)"
    else
        echo -e "${YELLOW}Deployed: $DEPLOYED_COMMIT   -- the checkout is NOT what runs; the next aivis update builds it${NC}"
    fi
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
# EMAIL CHANNEL STATUS
# ==============================================================================
#
# WHY THIS IS NOT `test-email` ANY MORE. The old command sent two real
# letters -- one through Mailgun's HTTP API, one through the local
# Postfix -- and printed which arrived. Both paths are gone: this
# product no longer builds email at all, it asks the comms notification
# service for it, and comms holds the provider credentials.
#
# So the command cannot answer "did a letter go out" by sending one. It
# answers the question the owner actually asks -- "is mail working?" --
# by reading the state of the channel at the service that owns it. The
# name changed with the mechanism: a command called `test-email` that
# sends nothing would be the more confusing artifact.
#
# NO TEST NOTIFICATION TYPE, DELIBERATELY. Producing a letter would mean
# declaring a type in comms-profile/types.yaml that exists only so this
# command can fire it -- a permanent entry in the product's vocabulary
# earning its keep once a quarter. This asks about state instead.
#
# WHERE THE ANSWER LIVES. comms publishes its channel map in the body of
# its own GET /health, under `channels`: live / not_configured /
# not_implemented per channel. That endpoint is unauthenticated on
# purpose, so no token is needed -- but it is only reachable from the
# shared docker network, which is why the probe runs INSIDE the app
# container: that is also the exact path the product itself uses, so a
# green answer here means the product can reach comms, not just that
# something on the box can.
case_email_status() {
    cd_compose

    local comms_dir comms_env record r
    record=""
    for r in "${AIVIS_SERVICES[@]}"; do
        [ "$(svc_field "$r" 1)" = "comms" ] && record="$r" && break
    done
    comms_dir=$(svc_field "$record" 3)
    # A service's env sits NEXT TO its checkout -- same derivation the
    # installer uses, not a second spelling of the path.
    comms_env=""
    [ -n "$comms_dir" ] && comms_env="$(dirname "$comms_dir")/.env"

    echo "=== Email channel ==="
    echo ""

    # -- 1. Ask comms what it thinks its channels are -------------------
    local PROBE
    PROBE=$(docker compose exec -T app python -c "
import asyncio, json
import httpx
from app.core.config import settings

async def main():
    base = settings.comms_api_url
    if not base:
        print('NOLINK')
        return
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(base.rstrip('/') + '/health')
    body = resp.json()
    channels = body.get('channels') or {}
    print('STATE ' + str(channels.get('email', 'absent')))
    print('ALL ' + json.dumps(channels))

asyncio.run(main())
" 2>/dev/null) || true

    local EMAIL_STATE=""
    if echo "$PROBE" | grep -q "^NOLINK$"; then
        echo -e "${RED}✗ This box is not linked to comms at all${NC}"
        echo "  COMMS_API_URL is empty in backend/.env -- the product emits"
        echo "  nothing, so there is no mail and no in-app notification either."
        echo "  A missing link is an install-time failure: see setup_comms in"
        echo "  scripts/install_aivis.sh."
        return 0
    fi
    EMAIL_STATE=$(echo "$PROBE" | sed -n 's/^STATE //p')
    if [ -z "$EMAIL_STATE" ]; then
        echo -e "${RED}✗ comms did not answer${NC}"
        echo "  The probe ran inside the app container and could not read the"
        echo "  channel map from COMMS_API_URL/health."
        echo "  Check, in this order:"
        echo "    docker compose ps app                 (is the product up)"
        echo "    bash $comms_dir/deploy/comms-deploy.sh status"
        echo "    bash $comms_dir/deploy/comms-deploy.sh logs"
        return 0
    fi

    echo "Channel map reported by comms: $(echo "$PROBE" | sed -n 's/^ALL //p')"
    echo ""

    if [ "$EMAIL_STATE" = "live" ]; then
        echo -e "${GREEN}✓ email: live${NC}"
        echo "  comms has a full key set for the channel and will deliver."
        echo ""
        echo "  This says the channel EXISTS, not that the provider accepted"
        echo "  the last letter. A key that is well-formed but wrong shows up"
        echo "  only at delivery time, as email_channel_not_viable in the"
        echo "  comms log:"
        echo "    bash $comms_dir/deploy/comms-deploy.sh logs | grep email_channel_not_viable"
        return 0
    fi

    echo -e "${YELLOW}⚠ email: $EMAIL_STATE${NC}"
    echo "  comms reports no usable email channel, so no letter can leave"
    echo "  the product."
    echo ""

    # -- 2. Separate "never delivered" from "delivered, not picked up" --
    # Two very different states look identical from the channel map, and
    # sending the owner down the wrong one costs a day. The keys are in a
    # file THIS product writes (install_aivis.sh, deliver_comms_email), so
    # reading it back is not a new privilege.
    #
    # PRESENCE IS CHECKED AS `^KEY=.+`, NEVER `^KEY=`. An empty
    # assignment is exactly what comms treats as "no such channel", so a
    # name-only check would report the keys as delivered and send the
    # owner to recreate containers when the real answer is that nothing
    # was delivered. The VALUE never leaves this function -- grep decides,
    # and only yes/no is printed. Precedent and the same reasoning:
    # install_aivis.sh's COMMS_* hand-over verification, whose message
    # says "missing (or empty)".
    if [ -z "$comms_env" ] || [ ! -f "$comms_env" ]; then
        echo "  comms env not found${comms_env:+ at $comms_env} -- this box"
        echo "  may not have a comms stack installed at all."
        return 0
    fi

    local key missing=0
    for key in EMAIL_MAILGUN_API_KEY EMAIL_MAILGUN_DOMAIN EMAIL_FROM_ADDRESS; do
        if ! grep -Eq "^${key}=.+" "$comms_env"; then
            echo "  -- $key: not delivered (absent or empty) in $comms_env"
            missing=1
        fi
    done

    if [ "$missing" -eq 1 ]; then
        echo ""
        echo "  DIAGNOSIS: the credentials were never delivered."
        echo "  They travel from backend/.env to the comms env only during an"
        echo "  install (deliver_comms_email), and the current installer asks"
        echo "  for the Mailgun key and stops rather than install without it."
        echo "  A box in this state was not installed by it: the remedy is a"
        echo "  fresh install, not an edit of either .env."
    else
        echo "  All three deciding keys ARE present and non-empty in"
        echo "  $comms_env, yet comms reports the channel as $EMAIL_STATE."
        echo ""
        echo "  The region is the next suspect: EMAIL_MAILGUN_REGION must be"
        echo "  exactly eu or us,"
        echo "  and comms refuses to start on anything else."
    fi
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
    update|deploy)  update_all "$@" ;;
    gen-types)      case_gen_types "$@" ;;
    restart)        case_restart "$@" ;;
    backup)         case_backup ;;
    db)             case_db "$@" ;;
    seed)           case_seed "$@" ;;
    bootstrap-admin) case_bootstrap_admin "$@" ;;
    seed-portfolio) case_seed_portfolio "$@" ;;
    ssl)            case_ssl "$@" ;;
    nginx)          case_nginx "$@" ;;
    site)           case_site "$@" ;;
    frontend)       case_frontend "$@" ;;
    storage)        case_storage "$@" ;;
    version)        case_version ;;
    email-status)   case_email_status ;;
    help|*)
        echo -e "${CYAN}AIVIS.ONE Management Script${NC}"
        echo ""
        echo "Usage: aivis <command> [options]"
        echo ""
        echo "Monitoring:"
        echo "  status                                    — Docker + health + external access + storage"
        echo "  logs [app|db|redis|storage|frontend|all]  — View logs (default: app)"
        echo "  version                                   — Git log + runtime versions"
        echo ""
        echo "Testing:"
        echo "  test [backend|frontend|all]               — Backend tests only; 'frontend' explains why"
        echo "  lint                                      — Run ruff + mypy (backend only)"
        echo "    NOTE: nothing here checks the frontend. It is type-checked"
        echo "    by 'aivis update' (npm run build = vue-tsc --noEmit &&"
        echo "    vite build) and linted by 'npm run lint' on a checkout."
        echo ""
        echo "Deployment:"
        echo "  update                                    — Product files first, then services, then build, migrate, test, regen-types, restart"
        echo "                                              (builds when what runs is not the checkout)"
        echo "    --skip-tests                              Skip backend tests (everything else runs)"
        echo "    --frontend-only                           Skip services and the backend cycle; refuses if backend/"
        echo "                                              differs from what runs, or what runs is not known"
        echo "  frontend build                            -- Build the frontend image with this server's addresses"
        echo "  gen-types                                 — Regenerate frontend generated.ts from live OpenAPI"
        echo "  gen-types --commit                        — ...and commit + push it on drift (what update and install run)"
        echo "  restart [service]                         — Restart all or specific service"
        echo ""
        echo "Database:"
        echo "  db connect [psql args]                    — Open psql; args pass through (-c, -f, ...)"
        echo "  db dump                                   — Create SQL dump"
        echo "  db restore <file>                         — Restore from dump"
        echo "  db migrate                                — Run Alembic migrations"
        echo "  seed                                      — Seed demo data from the default profile"
        echo "  seed --list                               — List available seed profiles"
        echo "  seed --profile <name>                     — Seed from a named profile"
        echo "  seed --reset                              — Delete this profile's rows, then seed again"
        echo "  seed --dry-run                            — Print what would be seeded, write nothing"
        echo "  bootstrap-admin <email>                   — Make a registered, verified user the first admin (once per box)"
        echo "  seed-portfolio <email>                    — Fill an existing user's dashboard"
        echo ""
        echo "Storage (RustFS):"
        echo "  storage stats                             — Bucket size + object count"
        echo "  storage reconcile <id>                    — Sync inbox -> DB"
        echo "  storage reconcile-templates <id>          — Sync templates-inbox -> DB"
        echo "  storage reconcile-platform-templates      — Sync platform templates"
        echo ""
        echo "Maintenance:"
        echo "  backup                                    — Backup DB + .env + storage (7-day rotation)"
        echo "  ssl renew                                 — Renew SSL certificates"
        echo "  ssl status                                — Show certificate info"
        echo "  nginx reload                              — Test config and reload Nginx"
        echo "  nginx render [api|frontend|files|all]     — Render nginx templates from the repo (default: all)"
        echo "  site build|publish|deploy                 — Company site: build from landing/, copy to the nginx root, reload"
        echo "  email-status                              — Is the mail channel live at comms?"
        ;;
esac
