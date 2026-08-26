#!/bin/bash

# ==============================================================================
# AIVIS.ONE Platform -- VPS Installation Script
# ==============================================================================
#
# WHAT THIS SCRIPT DOES:
#   1.  Pre-flight checks (OS, RAM, disk, DNS for 4 domains)
#   2.  Fix locale (en_US.UTF-8)
#   3.  Install system deps (Docker, Nginx, Certbot, UFW, git, dnsutils,
#       apache2-utils, mc binary)
#   4.  Configure firewall (22/80/443 only)
#   5.  Create deploy user `aivis` (non-root, docker group)
#   6.  Generate SSH deploy key -> add to GitHub -> clone repo
#   7.  Generate .env with random passwords (incl. MinIO secrets)
#   8.  Prompt for sensitive secrets (bot token, API keys)
#   9.  Configure Nginx reverse proxy (api.aivis.one, app.aivis.one)
#   10. Obtain SSL certificates (Let's Encrypt) + auto-renewal cron
#   11. Install and configure mail server (Postfix + OpenDKIM)
#   12. Set up MinIO Web UI proxy (storage-mc-admin.aivis.one + basic-auth)
#   13. Start Docker stack -> healthcheck -> mc alias on host -> migrations
#       -> seed Platform user
#   14. Create `aivis` management script -> symlink /usr/local/bin/aivis
#   15. Set up backup cron (4 AM daily, 7-day rotation)
#
# USAGE:
#   curl -fsSL https://raw.githubusercontent.com/aivis-one/aivis/main/scripts/install_aivis.sh | bash
#
# REQUIREMENTS:
#   - Ubuntu 22.04+ (fresh VPS, root access)
#   - Domain aivis.one already registered (the root/apex is a SEPARATE
#     landing page, NOT managed by this script)
#   - Subdomains (A records to server IP):
#       app.aivis.one
#       api.aivis.one
#       mail.aivis.one
#       storage-mc-admin.aivis.one
#   - GitHub repository aivis-one/aivis exists
# ==============================================================================

set -euo pipefail

# Ubuntu 22.04 runs `needrestart` after every apt transaction. Left at its
# interactive default, it opens two whiptail dialogs mid-install -- a
# "Pending kernel upgrade" msgbox and a "Which services should be restarted?"
# checklist -- and the install sits there waiting for a human until answered
# (measured: ~10 minutes lost on the live run). Mode 'a' = restart services
# automatically, no prompts. Must be set before the first `apt-get install`
# below, which is why it lives here rather than nearer the mail section.
export NEEDRESTART_MODE=a

# ==============================================================================
# CONFIGURATION
# ==============================================================================

INSTALL_BASE="/opt/aivis"
GITHUB_REPO="aivis-one/aivis"
DEPLOY_USER="aivis"
API_DOMAIN="api.aivis.one"
FRONTEND_DOMAIN="app.aivis.one"
MAIL_DOMAIN="mail.aivis.one"
STORAGE_DOMAIN="storage-mc-admin.aivis.one"
# Bug fix: certbot's --email must NOT derive from FRONTEND_DOMAIN. That
# domain is app.aivis.one (the app subdomain), which has no MX -- Let's
# Encrypt expiry warnings would go nowhere and the failure would only
# surface months later as an expired certificate. The apex aivis.one
# has real mail (owner-confirmed); this is a decoupled, dedicated value.
CERTBOT_EMAIL="admin@aivis.one"
APP_PORT="8000"
FRONTEND_PORT="3000"

# Let's Encrypt staging switch (decision 35). Unset/default -> production
# certificates, command line byte-identical to before this flag existed.
# AIVIS_CERTBOT_STAGING=1 -> both certbot calls below add --staging
# (untrusted test certs, no rate-limit exposure). Exists because retries
# are expected during a rehearsal and both worst install-abort points sit
# AFTER both certificates are already issued, against a cap of 5 real
# issuances per identical domain set per rolling 168 hours.
CERTBOT_STAGING_FLAG=""
if [ "${AIVIS_CERTBOT_STAGING:-0}" = "1" ]; then
    CERTBOT_STAGING_FLAG="--staging"
fi

# ==============================================================================
# COLORS & LOGGING
# ==============================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

log()     { echo -e "${GREEN}[$(date +'%H:%M:%S')]${NC} $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
error()   { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }
info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}✓${NC} $1"; }
section() { echo -e "\n${CYAN}${BOLD}=== $1 ===${NC}\n"; }

handle_error() {
    echo -e "\n${RED}[ERROR]${NC} Installation failed at line ${1}."
    echo "Check output above for details."
    exit 1
}
trap 'handle_error ${LINENO}' ERR

if [ "$EUID" -ne 0 ]; then
    error "Run as root: sudo bash install_aivis.sh"
fi

# ==============================================================================
# BANNER
# ==============================================================================

clear
echo -e "${CYAN}${BOLD}"
echo "╔══════════════════════════════════════════════════╗"
echo "║      AIVIS.ONE Platform -- VPS Installation      ║"
echo "╚══════════════════════════════════════════════════╝"
echo -e "${NC}"

# ==============================================================================
# PRE-FLIGHT CHECKS
# ==============================================================================

section "Pre-flight Checks"

preflight_checks() {
    # OS check
    if [ -f /etc/os-release ]; then
        source /etc/os-release
        if [ "$ID" = "ubuntu" ]; then
            success "OS: Ubuntu $VERSION_ID"
        else
            warn "OS: $ID $VERSION_ID (Ubuntu 22.04+ recommended)"
        fi
    else
        warn "Cannot detect OS. Proceeding anyway."
    fi

    # RAM check (>= 2GB)
    local MEM_MB
    MEM_MB=$(free -m | awk '/Mem:/ {print $2}')
    if [ "$MEM_MB" -lt 2000 ]; then
        warn "RAM: ${MEM_MB}MB (recommended: 2048MB+)"
    else
        success "RAM: ${MEM_MB}MB ✓"
    fi

    # Disk check (>= 10GB free)
    local FREE_GB
    FREE_GB=$(df -BG / | tail -1 | awk '{print $4}' | tr -d 'G')
    if [ "$FREE_GB" -lt 10 ]; then
        warn "Disk: ${FREE_GB}GB free (recommended: 10GB+)"
    else
        success "Disk: ${FREE_GB}GB free ✓"
    fi

    # DNS check for all 4 domains. We warn (not error) on mismatch / missing
    # so that an operator running the script on a fresh VPS without all DNS
    # records yet can still see what's missing and fix it before certbot
    # attempts HTTP-01 challenge.
    local SERVER_IP
    SERVER_IP=$(curl -s --max-time 5 ifconfig.me 2>/dev/null || true)
    if [ -z "$SERVER_IP" ]; then
        warn "Could not detect server's public IP via ifconfig.me"
    fi

    local DOMAIN
    for DOMAIN in "$API_DOMAIN" "$FRONTEND_DOMAIN" "$MAIL_DOMAIN" "$STORAGE_DOMAIN"; do
        local RESOLVED_IP
        RESOLVED_IP=$(dig +short "$DOMAIN" 2>/dev/null | head -1 || true)
        if [ -z "$RESOLVED_IP" ]; then
            warn "DNS: $DOMAIN does not resolve. Add A record -> $SERVER_IP. SSL setup will fail."
        elif [ -n "$SERVER_IP" ] && [ "$RESOLVED_IP" = "$SERVER_IP" ]; then
            success "DNS: $DOMAIN -> $RESOLVED_IP ✓"
        else
            warn "DNS: $DOMAIN -> $RESOLVED_IP (server IP: $SERVER_IP). SSL may fail."
        fi
    done

    success "Pre-flight checks complete"
}

preflight_checks

# ==============================================================================
# PREVIOUS INSTALLATION CHECK
# ==============================================================================

if [ -d "$INSTALL_BASE/repo" ]; then
    warn "Found existing installation at $INSTALL_BASE"
    echo ""
    read -rp "Remove existing installation and start fresh? (y/n): " -n 1 < /dev/tty
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log "Stopping existing services..."
        cd "$INSTALL_BASE/repo" 2>/dev/null && docker compose down -v 2>/dev/null || true
        log "Removing existing installation..."
        rm -rf "$INSTALL_BASE/repo"
        rm -f /usr/local/bin/aivis
        # Orphan from the pre-shim install scheme: the management script
        # used to be a physical file written here, outside the repo, and
        # this cleanup path never removed it because nothing here used to
        # know it was disposable. Left behind, it looks like a management
        # script to whoever finds it next -- remove it explicitly.
        rm -f "$INSTALL_BASE/aivis"
        success "Previous installation removed"
    else
        error "Cannot proceed with existing installation. Exiting."
    fi
fi

# ==============================================================================
# FIX LOCALE
# ==============================================================================

section "Locale"

apt-get update -qq
apt-get install -y -qq locales > /dev/null
locale-gen en_US.UTF-8 > /dev/null 2>&1
update-locale LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8
success "Locale: en_US.UTF-8"

# ==============================================================================
# SYSTEM DEPENDENCIES
# ==============================================================================

section "System Dependencies"

apt-get update -qq
apt-get install -y \
    apt-transport-https \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    git \
    ufw \
    dnsutils \
    software-properties-common \
    python3-certbot-nginx \
    apache2-utils \
    > /dev/null 2>&1

# apache2-utils provides htpasswd, used to create basic-auth file for the
# MinIO Console nginx proxy (storage-mc-admin.aivis.one).
success "Base packages installed (incl. apache2-utils for htpasswd)"

# Docker
if command -v docker &>/dev/null; then
    success "Docker already installed: $(docker --version)"
else
    log "Installing Docker..."
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
        -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
    echo \
        "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
        https://download.docker.com/linux/ubuntu \
        $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
        | tee /etc/apt/sources.list.d/docker.list > /dev/null
    apt-get update -qq
    apt-get install -y docker-ce docker-ce-cli containerd.io \
        docker-buildx-plugin docker-compose-plugin > /dev/null 2>&1
    systemctl enable docker
    systemctl start docker
    success "Docker installed: $(docker --version)"
fi

# Nginx
if command -v nginx &>/dev/null; then
    success "Nginx already installed"
else
    log "Installing Nginx..."
    apt-get install -y nginx > /dev/null 2>&1
    systemctl enable nginx
    systemctl start nginx
    success "Nginx installed"
fi

# Certbot
if command -v certbot &>/dev/null; then
    success "Certbot already installed"
else
    log "Installing Certbot..."
    apt-get install -y certbot python3-certbot-nginx > /dev/null 2>&1
    success "Certbot installed"
fi

# MinIO Client (mc) on host -- used by management script for backup,
# storage stats, and (in later iterations) reconcile commands. Installed
# host-side (not via docker compose run) so backup cron works even when
# the docker stack is degraded.
if command -v mc &>/dev/null; then
    success "mc already installed: $(mc --version 2>/dev/null | head -1)"
else
    log "Installing MinIO Client (mc)..."
    curl -fsSL https://dl.min.io/client/mc/release/linux-amd64/mc \
        -o /usr/local/bin/mc
    chmod +x /usr/local/bin/mc
    success "mc installed: $(mc --version 2>/dev/null | head -1)"
fi

# ==============================================================================
# FIREWALL
# ==============================================================================

section "Firewall"

ufw default deny incoming  > /dev/null 2>&1
ufw default allow outgoing > /dev/null 2>&1
ufw allow 22/tcp  > /dev/null 2>&1
ufw allow 80/tcp  > /dev/null 2>&1
ufw allow 443/tcp > /dev/null 2>&1
ufw allow from 172.16.0.0/12 to any port 25 proto tcp comment "Docker SMTP to Postfix" > /dev/null 2>&1
echo "y" | ufw enable > /dev/null 2>&1
success "UFW: 22 (SSH) + 80 (HTTP) + 443 (HTTPS) + Docker→SMTP"

# ==============================================================================
# DEPLOY USER
# ==============================================================================

section "Deploy User"

if id "$DEPLOY_USER" &>/dev/null; then
    success "User '$DEPLOY_USER' already exists"
else
    useradd -m -s /bin/bash "$DEPLOY_USER"
    success "User '$DEPLOY_USER' created"
fi
usermod -aG docker "$DEPLOY_USER"
success "User '$DEPLOY_USER' in docker group"

# ==============================================================================
# SSH DEPLOY KEY + GITHUB CLONE
# ==============================================================================

section "SSH Deploy Key & Repository"

# `ssh -T` against GitHub exits 1 even on SUCCESS ("does not provide shell
# access"), and this script runs under `set -o pipefail`, so the obvious
# `ssh | grep -q` form propagates that 1 through a MATCHING grep -- the
# test fails on a perfectly good key, every time. Capture the banner
# instead; `|| true` keeps the assignment from tripping the ERR trap.
github_probe() {
    # SUCCESS IS STILL DECIDED BY THE BANNER, not by the exit code, and
    # that has not changed: a working deploy key makes `ssh -T` exit 1,
    # because GitHub authenticates you and then refuses the shell. The
    # grep below is the same test it always was.
    #
    # WHAT CHANGED IS THE SILENCE. stderr went into the variable, so any
    # question ssh asked was captured instead of shown, and there was no
    # timeout -- the screen simply stopped, and the operator could not
    # tell a slow network from a prompt nobody would ever answer. With
    # twelve services in the registry that is twelve places to hang.
    #
    #   BatchMode=yes            -- an authentication question becomes a
    #                               refusal instead of an invisible wait.
    #   StrictHostKeyChecking=accept-new -- but NOT the host-key
    #                               question: on a fresh machine that one
    #                               is legitimate, and BatchMode alone
    #                               would turn a first install into a
    #                               refusal. provision_deploy_key seeds
    #                               known_hosts with ssh-keyscan before
    #                               this runs, and this is the belt for
    #                               the case where that seeding silently
    #                               failed.
    #   ConnectTimeout / timeout -- an unreachable GitHub answers in
    #                               seconds, not never. The outer
    #                               `timeout` covers the whole exchange,
    #                               the inner option only the TCP part.
    local alias="$1" banner status
    banner=$(timeout 25 ssh -T \
        -o BatchMode=yes \
        -o StrictHostKeyChecking=accept-new \
        -o ConnectTimeout=10 \
        "git@${alias}" 2>&1) && status=0 || status=$?

    if echo "$banner" | grep -q "successfully authenticated"; then
        return 0
    fi

    # Every failure path says something. `timeout` reports 124 when it
    # had to kill the command, which is the one case the operator most
    # needs named: it is indistinguishable from a hang otherwise.
    if [ "$status" -eq 124 ]; then
        warn "GitHub did not answer within 25s for ${alias} -- network or firewall, not the key"
    elif [ -n "$banner" ]; then
        warn "ssh to ${alias} said: ${banner}"
    else
        warn "ssh to ${alias} failed silently (exit ${status})"
    fi
    return 1
}

# Provision ONE GitHub deploy key: generate if absent, add the host alias
# if absent, then TEST -- and only interrupt the operator if the test
# fails.
#
# THE BLOCK IS UNCONDITIONAL, and there is exactly one of it per registry
# record. Every record prints its key and waits for ENTER, whether or not
# GitHub already holds that key: two records means two prompts, twelve
# means twelve. The operator counts them against the registry, so no
# branch may skip a prompt because the key exists or because the probe
# would have passed -- a run that silently skipped the keys already added
# is indistinguishable from a run that broke before reaching them.
#
# WHY A KEY PER REPOSITORY AT ALL: GitHub refuses the same public key as a
# deploy key on two repositories. One key cannot reach both aivis and
# comms, so each service gets its own, with its own `Host github.com-<name>`
# alias -- that alias is how git picks the right identity.
#
# WHY A REINSTALL USUALLY NEEDS NOTHING DONE ON GITHUB, even though it
# still asks: the wipe removes /opt/* and the docker state and does NOT
# touch /root/.ssh. The keys survive it and GitHub still holds the public
# halves, so the answer to every one of these prompts is a bare ENTER --
# the key on screen is the same one already added. Delete /root/.ssh as
# part of a wipe and each prompt becomes real work again.
#
#   $1 name    service id (key file and host alias are named after it)
#   $2 repo    owner/repo, for the URL printed to the operator
#   $3 access  "write" or "read" -- from the registry, never guessed: the
#              instruction differs materially and a claim about privilege
#              belongs where it can be reviewed.
provision_deploy_key() {
    local name="$1" repo="$2" access="$3"
    local key="/root/.ssh/id_ed25519_${name}_deploy"
    local host_alias="github.com-${name}"

    # An undeclared privilege is a stop, not a default. Guessing "read"
    # would print the wrong instruction to the operator and the failure
    # would surface days later, as a push that cannot. The check lives
    # HERE, where the key is created, so it covers the bootstrap's product
    # call as well as every service the loop passes in -- there is no
    # second pass to do it in.
    if [ "$access" != "read" ] && [ "$access" != "write" ]; then
        error "Service '$name' declares access='$access' -- expected 'read' or 'write'. Refusing to guess which instruction to give the operator."
    fi

    mkdir -p /root/.ssh
    chmod 700 /root/.ssh
    if ! grep -q "github.com" /root/.ssh/known_hosts 2>/dev/null; then
        ssh-keyscan -H github.com >> /root/.ssh/known_hosts 2>/dev/null
    fi

    if [ ! -f "$key" ]; then
        ssh-keygen -t ed25519 -C "${name}-deploy@$(hostname)" -f "$key" -N "" > /dev/null 2>&1
        success "Deploy key generated for $name"
    fi

    # The alias has to exist before the probe below runs, and the probe
    # runs after the prompt -- so the config block is written here, before
    # either.
    if ! grep -q "Host ${host_alias}\b" /root/.ssh/config 2>/dev/null; then
        cat >> /root/.ssh/config << SSH_CONFIG_EOF

# ${name} deploy key (${access})
Host ${host_alias}
    HostName github.com
    User git
    IdentityFile ${key}
    IdentitiesOnly yes
SSH_CONFIG_EOF
        chmod 600 /root/.ssh/config
    fi

    # ALWAYS PRINTED, ALWAYS ASKED, working key or not. One registry
    # record, one key block and one pause: two services means two keys,
    # nineteen means nineteen. That count is what the operator checks the
    # run against, so nothing about it may depend on whether GitHub
    # already knows the key -- a silent run and a broken run would look
    # identical, and the operator would have no way to tell them apart.
    echo ""
    echo -e "${CYAN}===============================================${NC}"
    echo -e "${CYAN}  GitHub Deploy Key -- ${name} repo${NC}"
    echo -e "${CYAN}===============================================${NC}"
    echo ""
    # The public half is what the operator is about to paste. Without
    # this guard a missing .pub -- half a key pair copied from another
    # box, or one file deleted by hand -- makes `cat` fail under set -e
    # and takes the whole install down on a line that says nothing about
    # what to do next.
    if [ ! -f "${key}.pub" ]; then
        error "Private key ${key} exists but its public half ${key}.pub is missing. Restore it with: ssh-keygen -y -f ${key} > ${key}.pub"
    fi
    cat "${key}.pub"
    echo ""
    echo -e "${YELLOW}Go to: https://github.com/${repo}/settings/keys${NC}"
    echo -e "${YELLOW}Click 'Add deploy key', paste the key above.${NC}"
    if [ "$access" = "write" ]; then
        echo -e "${RED}IMPORTANT: tick 'Allow write access'.${NC}"
        echo -e "${YELLOW}('aivis update' pushes regenerated API types back to this repo.)${NC}"
    else
        echo -e "${GREEN}READ-ONLY is enough: do NOT tick 'Allow write access'.${NC}"
        echo -e "${YELLOW}(nothing on this box ever pushes to ${repo}.)${NC}"
    fi
    echo -e "${YELLOW}Already added from an earlier install? Press ENTER, it is a no-op.${NC}"
    echo ""
    read -r -p "Press ENTER after adding the deploy key to GitHub..." < /dev/tty

    # The probe runs HERE and nowhere else: it verifies what the operator
    # just did. Testing before the prompt would let a key GitHub already
    # knows skip the block entirely, which is exactly the output that went
    # missing.
    if github_probe "$host_alias"; then
        success "GitHub connection OK ($name)"
        return 0
    fi

    error "Cannot connect to GitHub with the ${name} deploy key. Add it at https://github.com/${repo}/settings/keys"
}

# Provision a GitHub deploy key for every service the registry declares,
# except the product itself -- its key is the bootstrap below that made
# the registry readable in the first place, and a second pass over it
# would ask the operator twice about one key.
#
# This is what the registry buys: an N-th service is one record in
# services.conf and zero lines here. Eleven services plus the product is
# twelve records, twelve keys and twelve prompts.
#
# The privilege of EVERY record is checked here, including the product's,
# which this loop then skips. provision_deploy_key checks the value it is
# handed -- but the product's value reaches it from the bootstrap as a
# literal, so a services.conf whose product record lost its access field
# would otherwise be caught by nothing at all.
#
# DEFINED ABOVE ITS CALL ON PURPOSE: bash executes top to bottom, and a
# definition placed below the call site does not exist when the call runs.
provision_service_keys() {
    local record name repo access
    for record in "${AIVIS_SERVICES[@]}"; do
        name=$(svc_field "$record" 1)
        repo=$(svc_field "$record" 2)
        access=$(svc_field "$record" 7)

        if [ "$access" != "read" ] && [ "$access" != "write" ]; then
            error "Service '$name' declares access='$access' in services.conf -- expected 'read' or 'write'. Refusing to guess which instruction to give the operator."
        fi

        [ "$(svc_field "$record" 5)" = "internal" ] && continue

        provision_deploy_key "$name" "$repo" "$access"
    done
}

# BOOTSTRAP, and the one service that cannot come from the registry:
# services.conf lives INSIDE the aivis repo, so it cannot be read before
# aivis is cloned, and aivis cannot be cloned without this key. Every
# OTHER service is provisioned by the loop after the clone -- see
# provision_service_keys().
setup_ssh() {
    log "Setting up SSH for GitHub..."
    provision_deploy_key "aivis" "$GITHUB_REPO" "write" || return 1
    REPO_URL="git@github.com-aivis:$GITHUB_REPO.git"
}

setup_ssh

# Clone repository
mkdir -p "$INSTALL_BASE"
cd "$INSTALL_BASE"
git clone "$REPO_URL" repo
success "Repository cloned to $INSTALL_BASE/repo"
# root:root, NOT the deploy user. Everything that ever touches this
# checkout runs as root -- the installer, the `aivis` CLI (a root shim),
# every `docker compose` call -- and git 2.35+ refuses to operate on a
# repository owned by somebody other than the caller ("detected dubious
# ownership"), which is a HARD failure, not a warning: `aivis update`
# dies on its first fetch.
#
# The deploy user still exists and is still in the docker group; it is
# simply not the owner of the code. Nothing in either script runs as it
# -- checked by form: no sudo -u, no su -, no runuser, no systemd User=.
# Giving it the checkout bought nothing and cost the update cycle.
#
# The alternative -- teaching the CLI `git config --global --add
# safe.directory` -- was rejected: it is a plaster over an ownership
# mismatch that has no reason to exist, it has to be repeated in front
# of every git command anyone ever adds, and the donor installer does
# not have it precisely because it chowns to root here.
chown -R root:root "$INSTALL_BASE/repo"

# Only now can the registry be read -- it ships inside the checkout the
# clone above just made. Everything after this point is registry-driven:
# the same file scripts/aivis-manage.sh sources, so install and update can
# never disagree about a branch or a path.
SERVICES_CONF="$INSTALL_BASE/repo/scripts/services.conf"
if [ ! -f "$SERVICES_CONF" ]; then
    error "Service registry not found at $SERVICES_CONF -- this checkout cannot say which services this server runs."
fi
# shellcheck source=/dev/null
source "$SERVICES_CONF"

provision_service_keys

# ------------------------------------------------------------------------
# Install-specific config for the management script, and make the tracked
# script executable. Done here, right after the clone, rather than down
# with the rest of the management-command setup near the end of this file:
# the Nginx Configuration section below needs to invoke
# `aivis-manage.sh nginx render` as the one source of the three site
# templates, so both the config file and the +x bit must already exist by
# the time we get there.
# ------------------------------------------------------------------------
cat > "$INSTALL_BASE/aivis.conf" << AIVIS_CONF_EOF
API_DOMAIN=${API_DOMAIN}
FRONTEND_DOMAIN=${FRONTEND_DOMAIN}
STORAGE_DOMAIN=${STORAGE_DOMAIN}
APP_PORT=${APP_PORT}
FRONTEND_PORT=${FRONTEND_PORT}
AIVIS_CONF_EOF
success "Install config written: $INSTALL_BASE/aivis.conf"

chmod +x "$INSTALL_BASE/repo/scripts/aivis-manage.sh"

# ==============================================================================
# GENERATE .ENV
# ==============================================================================

section "Environment Configuration"

ENV_FILE="$INSTALL_BASE/repo/backend/.env"

gen_password() {
    openssl rand -base64 32 | tr -d "=+/" | cut -c1-32
}

gen_secret() {
    openssl rand -base64 64 | tr -d '\n'
}

# Short identifier (16 chars) for usernames / access keys -- MinIO root user
# and service account key, where 32-char random looks unwieldy in admin UIs.
gen_short_id() {
    openssl rand -base64 32 | tr -d "=+/" | cut -c1-16
}

log "Generating .env with random passwords..."

# Generate all secrets ONCE before writing -- ensures DATABASE_URL and
# POSTGRES_PASSWORD always contain the same password (no double gen_password calls).
DB_PASS=$(gen_password)
REDIS_PASS=$(gen_password)
SECRET=$(gen_secret)
KYC_SECRET=$(gen_password)
CRYPTO_SECRET=$(gen_password)

# MinIO secrets. Root credentials are used by MinIO server itself and by
# minio-init to bootstrap; service account (ACCESS/SECRET) is what backend
# actually uses at runtime. CONSOLE_BASIC_AUTH password gates nginx in
# front of the Web UI.
MINIO_ROOT_USER_VAL=$(gen_short_id)
MINIO_ROOT_PASS=$(gen_password)
MINIO_ACCESS_KEY_VAL=$(gen_short_id)
MINIO_SECRET_KEY_VAL=$(gen_password)
MINIO_CONSOLE_PASS=$(gen_password)

# Write atomically via temp file -- if interrupted, .env is never half-written.
cat > "${ENV_FILE}.tmp" << ENV_TEMPLATE
# =============================================================================
# AIVIS.ONE Backend -- Environment (generated by install_aivis.sh)
# Generated: $(date -u +"%Y-%m-%d %H:%M:%S UTC")
# =============================================================================

# -- Application --
APP_ENV=production
LOG_LEVEL=INFO
CORS_ORIGINS=https://${FRONTEND_DOMAIN}

# -- Database --
DATABASE_URL=postgresql+asyncpg://aivis:${DB_PASS}@postgres:5432/aivis
POSTGRES_DB=aivis
POSTGRES_USER=aivis
POSTGRES_PASSWORD=${DB_PASS}

# -- Redis --
REDIS_PASSWORD=${REDIS_PASS}
REDIS_URL=redis://:${REDIS_PASS}@redis:6379/0

# -- MinIO (S3-compatible object storage) --
# Root credentials -- consumed by MinIO server (docker-compose) and minio-init
# bootstrap only. Backend MUST use the service account below, never root.
MINIO_ROOT_USER=${MINIO_ROOT_USER_VAL}
MINIO_ROOT_PASSWORD=${MINIO_ROOT_PASS}
# Backend service account (created by minio-init).
MINIO_ACCESS_KEY=${MINIO_ACCESS_KEY_VAL}
MINIO_SECRET_KEY=${MINIO_SECRET_KEY_VAL}
# Endpoint as seen from inside the docker network.
MINIO_ENDPOINT=http://minio:9000
MINIO_BUCKET=aivis-attachments
MINIO_REGION=us-east-1
# Presigned URL TTL: 15 min for auth flow, 24h for public flow.
MINIO_PRESIGNED_TTL_AUTH=900
MINIO_PRESIGNED_TTL_PUBLIC=86400
# Hard limit on uploaded file size (MB). Mirrored in nginx client_max_body_size
# and in backend Pydantic validators (next iteration).
MINIO_MAX_FILE_SIZE_MB=100
# Password for nginx basic-auth in front of MinIO Web UI (login is fixed: admin).
MINIO_CONSOLE_BASIC_AUTH_PASSWORD=${MINIO_CONSOLE_PASS}

# -- Auth --
SECRET_KEY=${SECRET}
SESSION_TTL_DAYS=30
MAX_CONCURRENT_SESSIONS=5

# -- Telegram --
TELEGRAM_BOT_TOKEN=PLACEHOLDER
# Derived from the token by the installer (Telegram getMe), never typed.
# The backend does not read it -- Settings has no such field and drops it
# (extra="ignore"). It lives here because backend/.env is the SINGLE
# source the comms hand-over reads from: comms builds every deep-link
# button from it, and a value invented in two places is a value that can
# disagree with itself.
TELEGRAM_BOT_URL=PLACEHOLDER

# -- Telegram Auth Security --
AUTH_RATE_LIMIT_MAX_REQUESTS=5
AUTH_RATE_LIMIT_WINDOW_SECONDS=60
AUTH_INIT_DATA_TTL_SECONDS=300
AUTH_CLOCK_SKEW_SECONDS=60

# -- KYC (SumSub) --
SUMSUB_API_KEY=PLACEHOLDER
SUMSUB_SECRET_KEY=PLACEHOLDER
KYC_WEBHOOK_SECRET=${KYC_SECRET}

# -- Crypto Webhook --
CRYPTO_WEBHOOK_SECRET=${CRYPTO_SECRET}

# -- Email (SMTP primary, Mailgun fallback) --
SMTP_HOST=host.docker.internal
SMTP_PORT=25
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM_EMAIL=noreply@${MAIL_DOMAIN}
SMTP_USE_TLS=false
MAILGUN_API_KEY=PLACEHOLDER
MAILGUN_DOMAIN=${MAIL_DOMAIN}
MAILGUN_API_URL=https://api.eu.mailgun.net
HIGH_SECURED_DOMAINS=t-online.de,web.de,online.de,kabelmail.de,kabelbw.de,gmx.de,arcor.de

# -- Crypto --
CRYPTO_NETWORKS=TRC20,ERC20,BEP20,PoS
FREEZING_HOURS_CRYPTO=1

# -- Installments --
INSTALLMENT_DEFAULT_DAYS=7
INSTALLMENT_WORKER_HOUR=3

# -- Agent --
AGENT_APPLICATION_COOLDOWN_DAYS=30
ENV_TEMPLATE

mv "${ENV_FILE}.tmp" "$ENV_FILE"
success ".env generated with random passwords (incl. MinIO secrets)"

# Interactive secrets
echo ""
log "Enter secrets (press ENTER to keep PLACEHOLDER and configure later):"
echo ""

prompt_secret() {
    local VAR="$1"
    local LABEL="$2"
    local MIN_LEN="${3:-0}"
    local VALUE

    while true; do
        # Echo intentionally left ON: the operator wants to see what was
        # typed while typing it, not after. Trade-off accepted -- typed
        # values land in the terminal's own scrollback, and in any session
        # recording (script/asciinema/tmux capture) if one is running. No
        # explicit `echo` needed here: with echo on, the terminal itself
        # advances the cursor to a new line on Enter.
        read -rp "  $LABEL: " VALUE < /dev/tty
        if [ -z "$VALUE" ]; then
            warn "  $LABEL: keeping current value"
            return 0
        fi
        if [ "$MIN_LEN" -gt 0 ] && [ "${#VALUE}" -lt "$MIN_LEN" ]; then
            warn "  $LABEL: must be at least $MIN_LEN characters (got ${#VALUE}). Try again, or press ENTER to keep current."
            continue
        fi
        sed -i "s|${VAR}=.*|${VAR}=${VALUE}|" "$ENV_FILE"
        success "  $LABEL set"
        return 0
    done
}

# -- Telegram: ask for the token, DERIVE the URL ------------------------------
# The bot URL is not a second question. It is built from the username
# Telegram itself answers with FOR THIS TOKEN, so the two can never name
# different bots -- a hand-typed URL can, and the result is a comms stack
# in real mode sending working buttons that point at somebody else's bot.
# Both values are non-empty, so no validator downstream would catch it.
#
# The link domain is a constant here rather than a literal further down:
# domains live at the edge, in one named place, and comms refuses profile
# data that carries one at all.
TELEGRAM_LINK_DOMAIN="telegram.me"

prompt_telegram_bot() {
    local token username getme current
    current=$(grep -E '^TELEGRAM_BOT_TOKEN=' "$ENV_FILE" | tail -n 1 | cut -d= -f2-)

    while true; do
        read -rp "  Telegram Bot Token: " token < /dev/tty
        if [ -z "$token" ]; then
            # ENTER means "this run has nothing to say". If a real token is
            # already on file that is fine; if the placeholder is still
            # there, say what it costs rather than passing silently -- the
            # comms hand-over further down refuses to deliver a placeholder,
            # and the backend refuses to authenticate anyone with one.
            if [ "$current" = "PLACEHOLDER" ] || [ "$current" = "TEST" ] || [ -z "$current" ]; then
                warn "  Telegram Bot Token: still unset -- Telegram login will not work,"
                warn "  and comms will be left in stub mode (nothing gets delivered)."
            else
                warn "  Telegram Bot Token: keeping current value"
            fi
            return 0
        fi

        # Verify the token by using it. A typo, a revoked token or a
        # placeholder dies HERE, in front of the person who can fix it,
        # instead of as a silent auth failure on the first real login.
        # Parsed with grep/sed to avoid a jq dependency.
        log "  Verifying token with Telegram (getMe)..."
        getme=$(curl -s --max-time 15 "https://api.telegram.org/bot${token}/getMe" || true)
        if ! echo "$getme" | grep -q '"ok":true'; then
            warn "  Telegram rejected that token (getMe failed). Try again, or press ENTER to skip."
            warn "  Response: ${getme:-<empty>}"
            continue
        fi
        username=$(echo "$getme" | grep -o '"username":"[^"]*"' | head -1 | sed 's/"username":"//; s/"//' || true)
        if [ -z "$username" ]; then
            warn "  Could not read the bot username out of the getMe response. Try again."
            continue
        fi

        sed -i "s|^TELEGRAM_BOT_TOKEN=.*|TELEGRAM_BOT_TOKEN=${token}|" "$ENV_FILE"
        sed -i "s|^TELEGRAM_BOT_URL=.*|TELEGRAM_BOT_URL=https://${TELEGRAM_LINK_DOMAIN}/${username}|" "$ENV_FILE"
        success "  Telegram bot: @${username}"
        return 0
    done
}

prompt_telegram_bot
prompt_secret "SUMSUB_API_KEY"     "SumSub API Key (optional)"
prompt_secret "SUMSUB_SECRET_KEY"  "SumSub Secret Key (optional)"
prompt_secret "MAILGUN_API_KEY"    "Mailgun API Key (optional)"

# MinIO credentials -- user supplies memorable values OR ENTERs to keep the
# random defaults generated above by gen_short_id / gen_password. The three
# shell variables (MINIO_ROOT_USER_VAL, MINIO_ROOT_PASS, MINIO_CONSOLE_PASS)
# are consumed downstream by htpasswd (MinIO Storage section) and `mc alias
# set` (Docker Stack section), so they MUST be re-read from .env after the
# prompts in case the user replaced them.
echo ""
log "MinIO Console credentials (used to log in at https://${STORAGE_DOMAIN}):"
log "ENTER is RECOMMENDED on all three below -- unlike the PLACEHOLDER fields"
log "above, ENTER here keeps three INDEPENDENTLY GENERATED RANDOM values, not"
log "a placeholder. Only type a value to restore one specific known credential"
log "(e.g. re-installing with a password a script already depends on)."
prompt_secret "MINIO_ROOT_USER"                   "MinIO Root User (Console login, Step 2)" 3
prompt_secret "MINIO_ROOT_PASSWORD"               "MinIO Root Password (Console login, Step 2)" 8
prompt_secret "MINIO_CONSOLE_BASIC_AUTH_PASSWORD" "MinIO Console basic-auth password (nginx gate, Step 1)"

MINIO_ROOT_USER_VAL=$(grep "^MINIO_ROOT_USER=" "$ENV_FILE" | cut -d= -f2-)
MINIO_ROOT_PASS=$(grep "^MINIO_ROOT_PASSWORD=" "$ENV_FILE" | cut -d= -f2-)
MINIO_CONSOLE_PASS=$(grep "^MINIO_CONSOLE_BASIC_AUTH_PASSWORD=" "$ENV_FILE" | cut -d= -f2-)

chmod 600 "$ENV_FILE"
success ".env secured (chmod 600)"

# ==============================================================================
# NGINX CONFIGURATION
# ==============================================================================

section "Nginx Configuration"

# API (backend).
#
# client_max_body_size 100M -- mirrors MINIO_MAX_FILE_SIZE_MB hard limit
# (see Refactor 2 §1.6). Multipart attachment upload endpoint
# `POST /api/v1/staff/companies/{id}/attachments` arrives in a later
# iteration; setting the limit now means we don't have to come back and
# reload nginx when the endpoint goes live.
# Templates now live in scripts/aivis-manage.sh (`nginx render`) -- this
# call runs the exact same rendering code the operator uses later to push
# template changes, not a copy of it.
rm -f /etc/nginx/sites-enabled/default
"$INSTALL_BASE/repo/scripts/aivis-manage.sh" nginx render api frontend

# ==============================================================================
# SSL (Let's Encrypt)
# ==============================================================================

section "SSL Certificates"

certbot --nginx \
    -d "$API_DOMAIN" \
    -d "$FRONTEND_DOMAIN" \
    $CERTBOT_STAGING_FLAG \
    --non-interactive \
    --agree-tos \
    --email "$CERTBOT_EMAIL" \
    --redirect || warn "SSL setup failed. Run manually: certbot --nginx"

# Auto-renewal cron
RENEWAL_JOB="0 3 * * * certbot renew --quiet && systemctl reload nginx"
CURRENT_CRON=$(crontab -l 2>/dev/null || true)
if ! echo "$CURRENT_CRON" | grep -qF "$RENEWAL_JOB"; then
    (echo "$CURRENT_CRON"; echo "$RENEWAL_JOB") | crontab - || true
fi
success "SSL auto-renewal cron set (3 AM daily)"

# ==============================================================================
# MAIL SERVER (Postfix + OpenDKIM)
# ==============================================================================

section "Mail Server"

DKIM_SELECTOR="aivis"
DKIM_DIR="/etc/opendkim/keys/${MAIL_DOMAIN}"

# -- Postfix: send-only configuration --
log "Configuring Postfix..."

# Prevent interactive prompts from Postfix.
debconf-set-selections <<< "postfix postfix/mailname string ${MAIL_DOMAIN}"
debconf-set-selections <<< "postfix postfix/main_mailer_type string Internet Site"

# Install mail packages (after debconf preseeding to avoid interactive dialogs).
log "Installing Postfix + OpenDKIM..."
DEBIAN_FRONTEND=noninteractive apt-get install -y \
    postfix \
    opendkim \
    opendkim-tools \
    mailutils \
    > /dev/null 2>&1
success "Mail packages installed"

postconf -e "myhostname = ${MAIL_DOMAIN}"
postconf -e "myorigin = ${MAIL_DOMAIN}"
postconf -e "inet_interfaces = all"
postconf -e "mydestination = localhost"
postconf -e "mynetworks = 127.0.0.0/8 172.16.0.0/12 [::ffff:127.0.0.0]/104 [::1]/128"
postconf -e "relay_domains ="
postconf -e "default_transport = smtp"
postconf -e "smtp_tls_security_level = may"
postconf -e "smtp_tls_loglevel = 1"

# Connect Postfix to OpenDKIM milter.
postconf -e "milter_protocol = 6"
postconf -e "milter_default_action = accept"
postconf -e "smtpd_milters = unix:/run/opendkim/opendkim.sock"
postconf -e "non_smtpd_milters = unix:/run/opendkim/opendkim.sock"

success "Postfix configured (send-only via localhost)"

# -- OpenDKIM: generate key and configure --
log "Configuring OpenDKIM..."

mkdir -p "$DKIM_DIR"

# Generate DKIM key pair if not already present.
if [ ! -f "${DKIM_DIR}/${DKIM_SELECTOR}.private" ]; then
    opendkim-genkey -b 2048 -d "$MAIL_DOMAIN" -D "$DKIM_DIR" \
        -s "$DKIM_SELECTOR" -v > /dev/null 2>&1
    success "DKIM key pair generated (2048-bit)"
else
    success "DKIM key pair already exists"
fi

chown -R opendkim:opendkim /etc/opendkim
chmod 600 "${DKIM_DIR}/${DKIM_SELECTOR}.private"

# OpenDKIM main config.
cat > /etc/opendkim.conf << DKIM_CONF
Syslog          yes
SyslogSuccess   yes
LogWhy          yes

Mode            s
Canonicalization relaxed/simple
Domain          ${MAIL_DOMAIN}
Selector        ${DKIM_SELECTOR}
KeyFile         ${DKIM_DIR}/${DKIM_SELECTOR}.private

Socket          local:/run/opendkim/opendkim.sock
PidFile         /run/opendkim/opendkim.pid

UMask           007
UserID          opendkim

OversignHeaders From
DKIM_CONF

# Ensure socket directory exists with correct permissions.
mkdir -p /run/opendkim
chown opendkim:postfix /run/opendkim
chmod 750 /run/opendkim

# Add postfix to opendkim group so it can access the socket.
usermod -aG opendkim postfix

# Enable and start services.
systemctl enable opendkim > /dev/null 2>&1
systemctl enable postfix  > /dev/null 2>&1

# Validate before restarting, then WARN + CONTINUE on failure instead of
# aborting the install (decision 36). Mail is out of this migration's
# scope entirely (decision 30) -- a subsystem the owner explicitly
# excluded may not kill the run. Matches the precedent already set by
# both certbot calls above, which already end `|| warn` rather than abort.
if opendkim -n -x /etc/opendkim.conf; then
    if systemctl restart opendkim; then
        success "OpenDKIM restarted"
    else
        warn "OpenDKIM failed to restart. DKIM signing is NOT active. Check: systemctl status opendkim / journalctl -u opendkim / /etc/opendkim.conf"
    fi
else
    warn "OpenDKIM config check failed (opendkim -n -x /etc/opendkim.conf). NOT restarting -- DKIM signing is NOT active. Check: /etc/opendkim.conf"
fi

if postfix check; then
    if systemctl restart postfix; then
        success "Postfix restarted"
    else
        warn "Postfix failed to restart. Outbound mail is NOT active. Check: systemctl status postfix / journalctl -u postfix / /etc/postfix/main.cf"
    fi
else
    warn "Postfix config check failed (postfix check). NOT restarting -- outbound mail is NOT active. Check: /etc/postfix/main.cf"
fi

# -- Print DKIM DNS record for the user to add --
echo ""
echo -e "${YELLOW}${BOLD}ACTION REQUIRED -- Add DKIM DNS record:${NC}"
echo ""
echo "Type: TXT"
echo "Name: ${DKIM_SELECTOR}._domainkey.${MAIL_DOMAIN}"
echo "Value:"
echo ""
echo -e "${CYAN}"
# Extract the public key from the .txt file generated by opendkim-genkey.
cat "${DKIM_DIR}/${DKIM_SELECTOR}.txt"
echo -e "${NC}"
echo ""
echo "Add this TXT record in your DNS settings, then verify with:"
echo "  opendkim-testkey -d ${MAIL_DOMAIN} -s ${DKIM_SELECTOR} -vvv"
echo ""
echo "Press ENTER to continue..."
read -r < /dev/tty

success "Mail server setup complete"

# ==============================================================================
# MINIO STORAGE -- Web UI proxy (nginx + basic-auth + Let's Encrypt)
# ==============================================================================
#
# Sets up host-side infrastructure that lives in front of the MinIO Console.
# The MinIO server itself runs as a docker container (started below in the
# Docker Stack section), but its 9001 console port is bound to loopback only.
# Public access happens through nginx at https://storage-mc-admin.aivis.one
# with HTTP basic-auth (login: admin, password: MINIO_CONSOLE_BASIC_AUTH_PASSWORD).
#
# The mc host alias is configured later, once the docker stack is up and
# MinIO is healthy -- `mc alias set` validates the endpoint.
# ==============================================================================

section "MinIO Storage (Web UI proxy)"

# 1. Basic-auth file: login is the fixed string `admin`, password is the
#    generated MINIO_CONSOLE_BASIC_AUTH_PASSWORD from .env. -c creates /
#    truncates the file. Permissions: readable by www-data so nginx can use it.
log "Creating basic-auth file for MinIO Console..."
htpasswd -cb /etc/nginx/.htpasswd-storage-mc-admin admin "$MINIO_CONSOLE_PASS" > /dev/null 2>&1
chmod 640 /etc/nginx/.htpasswd-storage-mc-admin
chown root:www-data /etc/nginx/.htpasswd-storage-mc-admin
success "Basic-auth file: /etc/nginx/.htpasswd-storage-mc-admin"

# 2. Nginx site config for storage-mc-admin.aivis.one.
#    Rendered by scripts/aivis-manage.sh (`nginx render`) -- the same code
#    the operator uses later to push template changes, not a copy of it.
#    Must run AFTER the htpasswd file above: the template's
#    auth_basic_user_file line points at it, and `nginx -t` (inside the
#    render command) opens that file to validate the config -- rendering
#    this one earlier, alongside api/frontend, would fail here for a file
#    that does not exist yet.
"$INSTALL_BASE/repo/scripts/aivis-manage.sh" nginx render storage

# 3. SSL via Let's Encrypt for the new subdomain.
certbot --nginx \
    -d "$STORAGE_DOMAIN" \
    $CERTBOT_STAGING_FLAG \
    --non-interactive \
    --agree-tos \
    --email "$CERTBOT_EMAIL" \
    --redirect || warn "SSL setup for $STORAGE_DOMAIN failed. Run manually: certbot --nginx -d $STORAGE_DOMAIN"

success "SSL configured for $STORAGE_DOMAIN"

# ==============================================================================
# START DOCKER STACK
# ==============================================================================

# ==============================================================================
# NARROW ENV PROJECTIONS
# ==============================================================================
# postgres/redis read backend/.env.db and minio/minio-init read
# backend/.env.minio instead of the full backend/.env, so a compromise
# there no longer exposes the application's payment, telegram, session and
# comms-service secrets. Runs BEFORE any `docker compose` invocation --
# compose fails outright on a missing env_file, and it parses the whole
# file, so every compose command from here on depends on both existing.

# shellcheck source=/dev/null
source "$INSTALL_BASE/repo/scripts/env-render.sh"

if ! write_db_env "$INSTALL_BASE/repo/backend/.env" "$INSTALL_BASE/repo/backend/.env.db"; then
    error "Could not write backend/.env.db -- postgres/redis would start without their credentials."
fi
success "backend/.env.db written (narrow db env for postgres/redis)"

if ! write_minio_env "$INSTALL_BASE/repo/backend/.env" "$INSTALL_BASE/repo/backend/.env.minio"; then
    error "Could not write backend/.env.minio -- object storage would start on empty root credentials."
fi
success "backend/.env.minio written (narrow env for minio/minio-init)"

# ==============================================================================
# SHARED DOCKER NETWORK
# ==============================================================================
# aivis and comms are separate stacks joined by ONE external network;
# compose requires it to EXIST before either `up`. Idempotent, and
# comms-deploy.sh carries the same guard on its side -- either may win the
# race, the result is identical. Runs before setup_comms AND before the
# product stack: both join it.

SHARED_NETWORK="aivis-shared"

ensure_shared_network() {
    if docker network inspect "$SHARED_NETWORK" > /dev/null 2>&1; then
        success "Docker network '$SHARED_NETWORK' already exists"
        return 0
    fi
    if ! docker network create "$SHARED_NETWORK" > /dev/null; then
        error "Failed to create docker network '$SHARED_NETWORK'"
    fi
    success "Docker network '$SHARED_NETWORK' created"
}

ensure_shared_network

# ==============================================================================
# COMMS STACK (orchestration only)
# ==============================================================================
section "Comms Stack"

# This installer does NOT deploy comms itself: it clones the comms repo
# and calls the deploy CLI that ships INSIDE it. comms/deploy/ is the
# single source of the comms deploy mechanics -- nothing of it is
# duplicated here, and the path and branch come from the registry rather
# than from constants in this file.
#
# TOKEN SEAM -- the documented two-pass flow from comms/deploy/INTEGRATION.md:
#   pass 1:  mints comms secrets, seeds its generic smoke profile and
#            brings the comms stack up (PRODUCT_ENV_PATH is empty on a
#            fresh install, so the COMMS_* block is only printed);
#   knob:    PRODUCT_ENV_PATH=<aivis backend .env> is written into
#            /opt/comms/.env. Per-product CONFIG, not deploy logic;
#   pass 2:  install re-runs (idempotent: secrets and profile are
#            guarded, `up -d --build` is a cached no-op) and the hand-over
#            upserts COMMS_SERVICE_TOKEN / COMMS_API_URL / COMMS_REDIS_URL
#            into backend/.env.
# PRODUCT_ENV_PATH can NOT be passed as a process variable: the CLI
# SOURCES /opt/comms/.env, which overrides the environment. Hence two passes.
#
# Placed immediately before the product stack on purpose: aivis then
# starts with COMMS_* already in its env_file -- no backend restart -- and
# a comms failure stops the install before anything product-side is up.

# Read one KEY's value out of an env file. `grep`, deliberately not
# `source`: these files carry secrets and operator input, and sourcing
# executes whatever a value happens to look like.
read_env_value() {
    local file="$1" key="$2"
    [ -f "$file" ] || return 1
    # `tail -n 1`, not `grep -m1`: an env file resolves a repeated key to
    # the LAST assignment, exactly as a shell would. First-match would
    # hand the caller a stale value nothing else on the box agrees with.
    grep -E "^${key}=" "$file" 2>/dev/null | tail -n 1 | cut -d= -f2-
}

# Idempotent KEY=VALUE write into an env file: update in place when the
# key exists, append when it does not.
upsert_env_var() {
    local file="$1" key="$2" value="$3"
    if grep -q "^${key}=" "$file"; then
        if ! sed -i "s|^${key}=.*|${key}=${value}|" "$file"; then
            error "Failed to update ${key} in ${file}"
        fi
    else
        if ! printf '%s=%s\n' "$key" "$value" >> "$file"; then
            error "Failed to append ${key} to ${file}"
        fi
    fi
}

# Gate on every value we push into ANOTHER stack's env file.
#
# WHITELIST, not blacklist: we deliver exactly three shapes -- a bot
# token, a hostname-bearing URL and an absolute path -- and this set
# covers them with room to spare, so the guarantee is structural instead
# of a list of characters someone remembered to ban.
#
# What it actually catches: a NEWLINE in an operator-supplied value. The
# comms CLI *sources* its env file, so one newline in a delivered value
# writes an extra KEY=VALUE line into a file that is then executed as
# shell assignments. `[[ =~ ]]` and not `grep -Eq '^...$'` for exactly
# that reason -- grep anchors PER LINE and would pass a multi-line value
# whose every line is clean. Bash anchors the whole string. The '|' in
# the rejected set matters too: it is the sed delimiter in upsert_env_var
# above.
validate_deliverable() {
    local key="$1" value="$2"
    if [ -z "$value" ]; then
        error "Refusing to deliver an empty value for $key."
    fi
    if ! [[ "$value" =~ ^[A-Za-z0-9:._/-]+$ ]]; then
        error "Refusing to deliver $key: value contains characters outside the allowed set [A-Za-z0-9:._/-] (spaces, quotes, \$, backticks, '|' and newlines are rejected -- they would break the env file the comms CLI sources)."
    fi
}

# The product profile reaches comms by BIND, not by a copy: PROFILE_DIR
# points straight at comms-profile/ inside the checkout cloned above.
# Consequences, all wanted -- `aivis update` pulls the repo and the new
# dictionary is already on the path comms reads, with no second copy to
# keep in step.
#
# comms-deploy.sh needs no change for this: its own seed step only fills
# an EMPTY directory, and this one is never empty -- it carries the
# profile from git.
#
# NOTE, and this is where aivis differs from the donor: only types.yaml is
# required. The donor installer also demands a templates/ directory; that
# is the donor's rule, not the comms loader's. The loader treats a missing
# templates/ as an empty template set and starts normally -- verified in
# its body -- and aivis has no product notification types to write
# templates for until the emitters land.
deliver_comms_profile() {
    local comms_env="$1"
    local profile_dir="$INSTALL_BASE/repo/comms-profile"

    # Fail FAST and by name. Without this the failure still happens --
    # comms-app refuses to start without a valid profile -- but it arrives
    # as an opaque container health timeout minutes later, with the real
    # cause buried in another stack's logs.
    if [ ! -d "$profile_dir" ]; then
        error "Product profile not found at $profile_dir. The aivis checkout must carry comms-profile/types.yaml -- comms will not start without a valid profile."
    fi
    if [ ! -s "$profile_dir/types.yaml" ]; then
        error "Profile at $profile_dir has no (or an empty) types.yaml. comms validates the profile at startup and refuses to boot without the built-in chat types."
    fi

    validate_deliverable "PROFILE_DIR" "$profile_dir"
    upsert_env_var "$comms_env" "PROFILE_DIR" "$profile_dir"
    success "PROFILE_DIR=$profile_dir (bind: comms reads the profile from the aivis checkout)"
}

# The bot credentials and the channel mode reach comms from the ONE place
# they were ever entered: this installer's own prompt.
#
# Both values are read back OUT of backend/.env rather than rebuilt from
# shell variables, for two load-bearing reasons: byte-equality with what
# aivis itself uses becomes a property of the code rather than a
# coincidence of two formulas staying in step, and the .env generation
# above is a no-op when the file already exists, so on a re-run over a
# live box the prompt never happens and those shell variables do not exist.
#
# THE GUARD -- both or neither, and a PLACEHOLDER counts as neither. A
# re-run without the prompt would otherwise push a sentinel into comms and
# flip it to real mode, where every send fails and every button is built
# from a fake base. Note the sentinel set: this installer writes
# PLACEHOLDER, the committed .env.example carries TEST, and the backend's
# own config treats "" and TEST as absent. All three mean "nothing was
# said"; only a real value is a value.
deliver_comms_telegram() {
    local comms_env="$1" aivis_env="$2"
    local token url

    token=$(read_env_value "$aivis_env" "TELEGRAM_BOT_TOKEN" || true)
    url=$(read_env_value "$aivis_env" "TELEGRAM_BOT_URL" || true)

    case "${token:-}" in ""|PLACEHOLDER|TEST) token="" ;; esac
    case "${url:-}" in ""|PLACEHOLDER|TEST) url="" ;; esac

    if [ -z "$token" ] || [ -z "$url" ]; then
        warn "Telegram credentials NOT delivered to comms on this run."
        warn "backend/.env carries no real bot token, so pushing what is there"
        warn "would put comms into real mode with a placeholder -- where every"
        warn "delivery fails instead of being quietly stubbed."
        warn "CHANNELS_MODE in $comms_env is left as it is (stub, unless a"
        warn "previous run set it), and so are any existing credentials."
        warn "A clean delivery is a WIPE + fresh install -- never a hand edit"
        warn "of either .env (the installer is the deliverable; a server edited"
        warn "by hand is a server nobody can reproduce)."
        COMMS_TELEGRAM_DELIVERED=0
        return 0
    fi

    # Both or neither: the URL carries the username Telegram answered with
    # for THAT token, so moving one without the other is meaningless. And
    # real mode validates BOTH at startup -- comms refuses to boot on an
    # empty bot URL, because every deep-link button is built from it.
    validate_deliverable "TELEGRAM_BOT_TOKEN" "$token"
    validate_deliverable "TELEGRAM_BOT_URL" "$url"

    upsert_env_var "$comms_env" "TELEGRAM_BOT_TOKEN" "$token"
    upsert_env_var "$comms_env" "TELEGRAM_BOT_URL" "$url"
    # comms-deploy.sh writes CHANNELS_MODE=stub when it mints its env, and
    # in stub mode EVERY channel resolves to the stub -- nothing is ever
    # delivered. Flipping it is the point of delivering credentials at all.
    upsert_env_var "$comms_env" "CHANNELS_MODE" "real"
    COMMS_TELEGRAM_DELIVERED=1
    success "Telegram credentials delivered to comms; CHANNELS_MODE=real"
}

# Set by deliver_comms_telegram, read by the verification below.
COMMS_TELEGRAM_DELIVERED=0

setup_comms() {
    log "Setting up the comms stack (orchestrated)..."

    # Path, branch and repo slug all come from the registry -- the same
    # file `aivis update` reads, so the install and every later update can
    # never disagree about what this server tracks.
    local record comms_dir comms_branch comms_slug comms_lifecycle
    record=""
    local r
    for r in "${AIVIS_SERVICES[@]}"; do
        [ "$(svc_field "$r" 1)" = "comms" ] && record="$r" && break
    done
    if [ -z "$record" ]; then
        error "No 'comms' record in scripts/services.conf -- nothing to orchestrate."
    fi
    comms_slug=$(svc_field "$record" 2)
    comms_dir=$(svc_field "$record" 3)
    comms_branch=$(svc_branch "$(svc_field "$record" 4)" comms) || exit 1
    comms_lifecycle=$(svc_field "$record" 5)

    local comms_deploy="$comms_dir/$comms_lifecycle"
    local aivis_env="$INSTALL_BASE/repo/backend/.env"
    # A service's env sits NEXT TO its checkout, outside it, so that a
    # `git pull` in the checkout can never touch secrets. Derived from the
    # registry's path rather than written out again here -- the update
    # cycle derives it exactly the same way, and a second spelling of the
    # same location is a second thing to keep in step.
    local comms_env
    comms_env="$(dirname "$comms_dir")/.env"

    # -- 1. Clone the comms repo through its own read-only deploy key -----
    if [ -d "$comms_dir" ]; then
        warn "comms checkout already present at $comms_dir -- reusing it"
    else
        mkdir -p "$(dirname "$comms_dir")"
        if ! git clone -b "$comms_branch" "git@github.com-comms:${comms_slug}.git" "$comms_dir"; then
            error "Failed to clone $comms_slug (branch: $comms_branch)"
        fi
        success "comms cloned to $comms_dir (branch: $comms_branch)"
    fi

    if [ ! -f "$comms_deploy" ]; then
        error "comms deploy CLI not found at $comms_deploy -- does branch '$comms_branch' carry deploy/?"
    fi

    # -- 2. Pass 1: mint secrets, seed the smoke profile, bring the stack up
    # Every failure below is a HARD abort: a "successful" install that
    # brought up aivis without a linked comms would be hidden breakage.
    log "comms-deploy install, pass 1 (secrets + profile + bring-up)..."
    if ! bash "$comms_deploy" install; then
        error "comms-deploy.sh install (pass 1) FAILED. Logs: bash $comms_deploy logs"
    fi

    # -- 3. Point the token hand-over at the aivis backend .env -----------
    if [ ! -f "$comms_env" ]; then
        error "$comms_env not found after pass 1 -- the comms install did not mint its env, so there is nowhere to write the seam."
    fi
    validate_deliverable "PRODUCT_ENV_PATH" "$aivis_env"
    upsert_env_var "$comms_env" "PRODUCT_ENV_PATH" "$aivis_env"
    success "PRODUCT_ENV_PATH=$aivis_env written into $comms_env"

    # -- 3b. Deliver the product profile and the bot credentials ----------
    # Deliberately done from THIS side and not by teaching comms-deploy.sh
    # about products: comms is one deploy body for several products, and
    # everything product-specific -- which profile, which bot -- is ours to
    # supply. comms stays agnostic; this installer is the only artifact
    # that knows about aivis.
    deliver_comms_profile "$comms_env"
    deliver_comms_telegram "$comms_env" "$aivis_env"

    # -- 4. Pass 2: idempotent re-run -- executes the hand-over -----------
    log "comms-deploy install, pass 2 (COMMS_* hand-over into backend/.env)..."
    if ! bash "$comms_deploy" install; then
        error "comms-deploy.sh install (pass 2) FAILED."
    fi

    # -- 5. Verify the seam actually closed -------------------------------
    # The hand-over deliberately degrades to PRINTING the block when its
    # target is unusable, and returns SUCCESS while doing so. Fine for a
    # manual flow; for orchestration that is a silent failure -- aivis
    # would start unlinked while this installer reports success. So: every
    # key present AND non-empty, or the install dies here. `.+` is the
    # whole point of the pattern; `^KEY=` alone would pass an empty value.
    local key
    for key in COMMS_SERVICE_TOKEN COMMS_API_URL COMMS_REDIS_URL; do
        if ! grep -Eq "^${key}=.+" "$aivis_env"; then
            error "$key missing (or empty) in $aivis_env after the hand-over. The token seam did not close -- aivis would start unlinked."
        fi
    done
    success "COMMS_* variables verified in $aivis_env"

    if [ "$COMMS_TELEGRAM_DELIVERED" -eq 1 ]; then
        if ! grep -Eq "^CHANNELS_MODE=real$" "$comms_env"; then
            error "CHANNELS_MODE is not 'real' in $comms_env after delivering credentials -- comms would run in stub mode and deliver nothing."
        fi
        success "comms channels: real (bot credentials delivered by this installer)"
    else
        warn "comms channels: stub -- nothing will be delivered. See the note above."
    fi
    success "comms stack is up and linked (profile: $INSTALL_BASE/repo/comms-profile)"
}

setup_comms

section "Docker Stack"

cd "$INSTALL_BASE/repo"
log "Building Docker images (this may take a few minutes)..."
docker builder prune -f > /dev/null 2>&1 || true
docker compose build 2>&1 || { error "Docker build failed. Check output above."; }
docker compose up -d 2>&1 || { error "Docker compose up failed. Check output above."; }
log "Waiting for app to be healthy..."

HEALTH_URL="http://127.0.0.1:${APP_PORT}/ready"
for i in $(seq 1 24); do
    if curl -sf "$HEALTH_URL" > /dev/null 2>&1; then
        success "App is healthy"
        break
    fi
    if [ "$i" = "24" ]; then
        warn "App did not respond within 120s. Check: docker compose logs app"
    fi
    echo -n "."
    sleep 5
done
echo ""

# ------------------------------------------------------------------------------
# mc alias on host -- now that MinIO is healthy (app waited for it via
# depends_on chain), we can set up the host-side mc alias used by
# `aivis backup` and `aivis storage` commands. mc alias set validates
# the endpoint, so it only runs after the stack is up.
# ------------------------------------------------------------------------------
log "Configuring mc alias 'local' on host..."
mkdir -p /root/.mc
chmod 700 /root/.mc
mc alias set local http://127.0.0.1:9000 \
    "$MINIO_ROOT_USER_VAL" \
    "$MINIO_ROOT_PASS" > /dev/null 2>&1
chmod 600 /root/.mc/config.json
success "mc alias 'local' configured (config: /root/.mc/config.json)"

# Run Alembic migrations
log "Running database migrations..."
docker compose exec -T app python -m alembic upgrade head
success "Migrations applied"

# Seed Platform user
log "Seeding Platform user..."
docker compose exec -T app python scripts/seed_platform.py
success "Platform user seeded"

# Seed legal documents from frontend/public/legal/*.html (bind-mounted at /legal)
log "Seeding legal documents..."
docker compose exec -T app python scripts/seed_documents.py
success "Legal documents seeded"

# T-72: THE INSTALL NO LONGER SEEDS DEMO DATA. Two blocks stood here --
# the demo storefront and the four well-known test logins -- and both are
# gone along with the scripts behind them. An install now produces
# bootstrap and nothing else: the Platform user, the legal documents and
# (below) the platform default templates.
#
# Demo data is a deliberate act with its own command, `aivis seed`, which
# carries the contour guard that used to live inside one of the deleted
# scripts. See the NEXT STEPS at the end of this file.

# ------------------------------------------------------------------------------
# Refactor 2 iter 2.3: seed platform default templates (R2 §1.4 + §4.9).
#
# Two-step bootstrap:
#   1. mc cp -r backend/scripts/templates/_default/ -> _platform/templates/
#      copies 4 kinds x 4 languages = 16 folders (template.html + logo /
#      signature / stamp PNG placeholders) into MinIO.
#   2. seed_platform_templates.py inserts one active row per (kind, language)
#      into company_document_templates with company_id IS NULL. Idempotent --
#      a re-install with previously-seeded rows is a no-op.
#
# Order matters: (1) puts files in MinIO; (2) creates DB rows that point
# at those files. Reverse order would leave the DB pointing at empty
# storage and the renderer 500ing on the first render attempt.
#
# Runs after the Platform user is in the DB (seed_platform_templates.py
# needs it for system-actor audit attribution).
# ------------------------------------------------------------------------------

log "Seeding platform default templates to MinIO..."
mc cp -r "$INSTALL_BASE/repo/backend/scripts/templates/_default/" \
    local/aivis-attachments/_platform/templates/

log "Seeding platform default templates to DB..."
docker compose exec -T app python -m scripts.seed_platform_templates
success "Platform default templates seeded"

# ==============================================================================
# MANAGEMENT COMMAND
# ==============================================================================
#
# The management logic itself lives in scripts/aivis-manage.sh, tracked in
# the repo (chmod +x'd and configured right after the clone, above -- the
# Nginx Configuration section needed it runnable before we got here). What
# gets installed here is the entry point: a thin shim written once, and a
# symlink to it that is never rewritten again. Two files rather than one,
# so that /usr/local/bin/aivis itself never needs touching after this line
# -- a reinstall that fails partway through past this point still leaves a
# working command, because there is nothing left here to finish writing.

section "Management Command"

mkdir -p "$INSTALL_BASE/scripts"

cat > "$INSTALL_BASE/scripts/manage.sh" << SHIM_EOF
#!/bin/bash
# aivis management shim -- do not hand-edit the logic here.
# The real script is scripts/aivis-manage.sh, tracked in the repo; it
# updates with \`aivis update\` like any other file. This file only execs it.
exec "$INSTALL_BASE/repo/scripts/aivis-manage.sh" "\$@"
SHIM_EOF
chmod +x "$INSTALL_BASE/scripts/manage.sh"

ln -sf "$INSTALL_BASE/scripts/manage.sh" /usr/local/bin/aivis
success "Management command installed (use 'aivis' command)"

# ==============================================================================
# BACKUP CRON
# ==============================================================================

section "Backup Cron"

(crontab -l 2>/dev/null; echo "0 4 * * * /usr/local/bin/aivis backup >> /var/log/aivis-backup.log 2>&1") \
    | sort -u | crontab -
success "Backup cron: 4 AM daily, 7-day rotation"

# ==============================================================================
# DONE
# ==============================================================================

echo ""
echo -e "${GREEN}${BOLD}"
echo "╔══════════════════════════════════════════════════╗"
echo "║         AIVIS.ONE Installation Complete!         ║"
echo "╚══════════════════════════════════════════════════╝"
echo -e "${NC}"
echo -e "API:           ${CYAN}https://${API_DOMAIN}/health${NC}"
echo -e "Frontend:      ${CYAN}https://${FRONTEND_DOMAIN}${NC}"
echo -e "MinIO Console: ${CYAN}https://${STORAGE_DOMAIN}${NC}  (login: admin / see .env)"
echo ""
echo -e "Management: ${CYAN}aivis status | aivis logs | aivis update | aivis storage console${NC}"
echo ""
echo -e "${YELLOW}NEXT STEPS:${NC}"
echo "1. Edit $INSTALL_BASE/repo/backend/.env"
echo "   -- Set TELEGRAM_BOT_TOKEN (if not done)"
echo "   -- Set SUMSUB_API_KEY / SUMSUB_SECRET_KEY"
echo "   -- Set MAILGUN_API_KEY (if not done)"
echo "   -- Set MAILGUN_API_URL (default: EU endpoint, change to https://api.mailgun.net for US)"
echo "2. Add DKIM DNS record (printed above during mail setup)"
echo "3. Verify DKIM: opendkim-testkey -d ${MAIL_DOMAIN} -s ${DKIM_SELECTOR} -vvv"
echo "4. Run: aivis restart app"
echo "5. Test email: aivis test-email your@email.com"
echo "6. Open MinIO Console: aivis storage console  (prints URL + credentials)"
echo "7. Demo data, if this is a stand and not a real box:"
echo "   -- aivis seed                          (creates the first admin too)"
echo "   -- aivis seed --list                    (available profiles)"
echo "   The install seeds NO demo data at all; this is the only way in."
echo ""
