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

DEPLOY_KEY="/root/.ssh/id_ed25519_aivis_deploy"
mkdir -p /root/.ssh
chmod 700 /root/.ssh

if ! grep -q "github.com" /root/.ssh/known_hosts 2>/dev/null; then
    ssh-keyscan -H github.com >> /root/.ssh/known_hosts 2>/dev/null
fi

if [ ! -f "$DEPLOY_KEY" ]; then
    ssh-keygen -t ed25519 -C "aivis-deploy@$(hostname)" \
        -f "$DEPLOY_KEY" -N "" > /dev/null 2>&1
    success "Deploy key generated"
fi

echo ""
echo -e "${YELLOW}${BOLD}ACTION REQUIRED:${NC}"
echo "Add this deploy key to GitHub -> $GITHUB_REPO -> Settings -> Deploy keys:"
echo ""
echo -e "${CYAN}"
cat "${DEPLOY_KEY}.pub"
echo -e "${NC}"
echo "Press ENTER after adding the deploy key to GitHub..."
read -r < /dev/tty

# Test SSH connection
if ssh -i "$DEPLOY_KEY" -o StrictHostKeyChecking=no \
    git@github.com 2>&1 | grep -q "successfully authenticated"; then
    success "GitHub SSH connection verified"
else
    warn "Could not verify GitHub SSH connection. Proceeding anyway."
fi

# Clone repository
mkdir -p "$INSTALL_BASE"
cd "$INSTALL_BASE"
GIT_SSH_COMMAND="ssh -i $DEPLOY_KEY" \
    git clone "git@github.com:${GITHUB_REPO}.git" repo
success "Repository cloned to $INSTALL_BASE/repo"
chown -R "$DEPLOY_USER:$DEPLOY_USER" "$INSTALL_BASE/repo"

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

prompt_secret "TELEGRAM_BOT_TOKEN" "Telegram Bot Token"
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

# Seed storefront (6 companies + 21 products + 19 installment plans) for dev/staging
log "Seeding storefront (dev/staging fixtures)..."
docker compose exec -T app python -m scripts.seed_storefront
success "Storefront seeded"

# Seed test accounts (investor / company / agent / staff for manual testing)
# R-2.3: on APP_ENV=production the seeder refuses the well-known
# seedpass123 accounts unless explicitly allowed -- opt in by exporting
# AIVIS_SEED_TEST_ACCOUNTS=1 before running.
log "Seeding test accounts (dev fixtures)..."
docker compose exec -T app python -m scripts.seed_test_accounts ${AIVIS_SEED_TEST_ACCOUNTS:+--allow-production}
success "Test accounts seeded"

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
# Runs after `aivis seed` (Platform user is already in the DB --
# seed_platform_templates.py needs it for system-actor audit attribution).
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
echo ""
