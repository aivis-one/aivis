#!/bin/bash

# ==============================================================================
# CBSHOME Platform -- VPS Installation Script
# ==============================================================================
#
# WHAT THIS SCRIPT DOES:
#   1.  Pre-flight checks (OS, RAM, disk, DNS for 4 domains)
#   2.  Fix locale (en_US.UTF-8)
#   3.  Install system deps (Docker, Nginx, Certbot, UFW, git, dnsutils,
#       apache2-utils, mc binary)
#   4.  Configure firewall (22/80/443 only)
#   5.  Create deploy user `cbshome` (non-root, docker group)
#   6.  Generate SSH deploy key -> add to GitHub -> clone repo
#   7.  Generate .env with random passwords (incl. MinIO secrets)
#   8.  Prompt for sensitive secrets (bot token, API keys)
#   9.  Configure Nginx reverse proxy (api.cbshome.org, cbshome.org)
#   10. Obtain SSL certificates (Let's Encrypt) + auto-renewal cron
#   11. Install and configure mail server (Postfix + OpenDKIM)
#   12. Set up MinIO Web UI proxy (storage-mc-admin.cbshome.org + basic-auth)
#   13. Start Docker stack -> healthcheck -> mc alias on host -> migrations
#       -> seed Platform user
#   14. Create `cbshome` management script -> symlink /usr/local/bin/cbshome
#   15. Set up backup cron (4 AM daily, 7-day rotation)
#
# USAGE:
#   curl -fsSL https://raw.githubusercontent.com/aivis-one/cbshome/main/scripts/install_cbshome.sh | bash
#
# REQUIREMENTS:
#   - Ubuntu 22.04+ (fresh VPS, root access)
#   - Domain cbshome.org pointing to this server
#   - Subdomains (A records to server IP):
#       api.cbshome.org
#       mail.cbshome.org
#       storage-mc-admin.cbshome.org
#   - GitHub repository aivis-one/cbshome exists
# ==============================================================================

set -euo pipefail

# ==============================================================================
# CONFIGURATION
# ==============================================================================

INSTALL_BASE="/opt/cbshome"
GITHUB_REPO="aivis-one/cbshome"
DEPLOY_USER="cbshome"
API_DOMAIN="api.cbshome.org"
FRONTEND_DOMAIN="cbshome.org"
MAIL_DOMAIN="mail.cbshome.org"
STORAGE_DOMAIN="storage-mc-admin.cbshome.org"
APP_PORT="8000"
FRONTEND_PORT="3000"

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
    error "Run as root: sudo bash install_cbshome.sh"
fi

# ==============================================================================
# BANNER
# ==============================================================================

clear
echo -e "${CYAN}${BOLD}"
echo "╔══════════════════════════════════════════════════╗"
echo "║        CBSHOME Platform -- VPS Installation      ║"
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
        rm -f /usr/local/bin/cbshome
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
# MinIO Console nginx proxy (storage-mc-admin.cbshome.org).
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

DEPLOY_KEY="/root/.ssh/id_ed25519_cbshome_deploy"
mkdir -p /root/.ssh
chmod 700 /root/.ssh

if ! grep -q "github.com" /root/.ssh/known_hosts 2>/dev/null; then
    ssh-keyscan -H github.com >> /root/.ssh/known_hosts 2>/dev/null
fi

if [ ! -f "$DEPLOY_KEY" ]; then
    ssh-keygen -t ed25519 -C "cbshome-deploy@$(hostname)" \
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
# CBSHOME Backend -- Environment (generated by install_cbshome.sh)
# Generated: $(date -u +"%Y-%m-%d %H:%M:%S UTC")
# =============================================================================

# -- Application --
APP_ENV=production
LOG_LEVEL=INFO
CORS_ORIGINS=https://${FRONTEND_DOMAIN}

# -- Database --
DATABASE_URL=postgresql+asyncpg://cbshome:${DB_PASS}@postgres:5432/cbshome
POSTGRES_DB=cbshome
POSTGRES_USER=cbshome
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
MINIO_BUCKET=cbshome-attachments
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
cat > /etc/nginx/sites-available/cbshome-api << NGINX_API
server {
    listen 80;
    server_name ${API_DOMAIN};

    client_max_body_size 100M;

    location / {
        proxy_pass http://127.0.0.1:${APP_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 60s;
        proxy_connect_timeout 10s;
    }
}
NGINX_API

# Frontend
cat > /etc/nginx/sites-available/cbshome-frontend << NGINX_FRONTEND
server {
    listen 80;
    server_name ${FRONTEND_DOMAIN};

    location / {
        proxy_pass http://127.0.0.1:${FRONTEND_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
NGINX_FRONTEND

ln -sf /etc/nginx/sites-available/cbshome-api \
    /etc/nginx/sites-enabled/cbshome-api
ln -sf /etc/nginx/sites-available/cbshome-frontend \
    /etc/nginx/sites-enabled/cbshome-frontend
rm -f /etc/nginx/sites-enabled/default

nginx -t && systemctl reload nginx
success "Nginx configured for $API_DOMAIN and $FRONTEND_DOMAIN"

# ==============================================================================
# SSL (Let's Encrypt)
# ==============================================================================

section "SSL Certificates"

certbot --nginx \
    -d "$API_DOMAIN" \
    -d "$FRONTEND_DOMAIN" \
    --non-interactive \
    --agree-tos \
    --email "admin@${FRONTEND_DOMAIN}" \
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

DKIM_SELECTOR="cbshome"
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
systemctl restart opendkim
systemctl restart postfix
success "OpenDKIM + Postfix running"

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
# Public access happens through nginx at https://storage-mc-admin.cbshome.org
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

# 2. Nginx site config for storage-mc-admin.cbshome.org.
#    - basic-auth gates everything before MinIO sees it.
#    - WebSocket upgrade headers are required: the MinIO Console uses WS
#      for real-time bucket updates.
#    - client_max_body_size 100M matches MINIO_MAX_FILE_SIZE_MB (Refactor 2 §1.6),
#      so Staff can upload files up to that size through the Web UI.
cat > /etc/nginx/sites-available/cbshome-storage-mc-admin << NGINX_STORAGE
server {
    listen 80;
    server_name ${STORAGE_DOMAIN};

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

        # \$http_host preserves the port; MinIO Console uses Host for cookie domain.
        proxy_set_header Host \$http_host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;

        # WebSocket upgrade -- MinIO Console pushes real-time updates.
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";

        proxy_read_timeout 300s;
        proxy_connect_timeout 300s;
        proxy_send_timeout 300s;
    }
}
NGINX_STORAGE

ln -sf /etc/nginx/sites-available/cbshome-storage-mc-admin \
    /etc/nginx/sites-enabled/cbshome-storage-mc-admin

nginx -t && systemctl reload nginx
success "Nginx configured for $STORAGE_DOMAIN"

# 3. SSL via Let's Encrypt for the new subdomain.
certbot --nginx \
    -d "$STORAGE_DOMAIN" \
    --non-interactive \
    --agree-tos \
    --email "admin@${FRONTEND_DOMAIN}" \
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
# `cbshome backup` and `cbshome storage` commands. mc alias set validates
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
# CBSHOME_SEED_TEST_ACCOUNTS=1 before running.
log "Seeding test accounts (dev fixtures)..."
docker compose exec -T app python -m scripts.seed_test_accounts ${CBSHOME_SEED_TEST_ACCOUNTS:+--allow-production}
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
# Runs after `cbshome seed` (Platform user is already in the DB --
# seed_platform_templates.py needs it for system-actor audit attribution).
# ------------------------------------------------------------------------------

log "Seeding platform default templates to MinIO..."
mc cp -r "$INSTALL_BASE/repo/backend/scripts/templates/_default/" \
    local/cbshome-attachments/_platform/templates/

log "Seeding platform default templates to DB..."
docker compose exec -T app python -m scripts.seed_platform_templates
success "Platform default templates seeded"

# ==============================================================================
# MANAGEMENT SCRIPT
# ==============================================================================

section "Management Script"

MANAGE_SCRIPT="$INSTALL_BASE/cbshome"

cat > "$MANAGE_SCRIPT" << 'MANAGE_EOF'
#!/bin/bash
# ==============================================================================
# cbshome -- CBSHOME Platform Management Script
# ==============================================================================

INSTALL_BASE="/opt/cbshome"
COMPOSE_DIR="$INSTALL_BASE/repo"
API_DOMAIN="api.cbshome.org"
FRONTEND_DOMAIN="cbshome.org"
STORAGE_DOMAIN="storage-mc-admin.cbshome.org"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

cd_compose() {
    cd "$COMPOSE_DIR" || { echo -e "${RED}ERROR: $COMPOSE_DIR not found${NC}"; exit 1; }
}

# ==============================================================================
# STATUS
# ==============================================================================

case_status() {
    cd_compose
    SERVER_IP=$(curl -s --max-time 3 ifconfig.me 2>/dev/null || echo "unknown")

    echo -e "${CYAN}=== CBSHOME Status ===${NC}"
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
        *)           echo "Usage: cbshome logs [app|db|redis|minio|frontend|all]" ;;
    esac
}

# ==============================================================================
# TEST DATABASE PROVISIONING (TD-068)
# ==============================================================================

# Provision an isolated test database so the suite never touches the live
# dev DB. Derives the test URL from the app's own DATABASE_URL (same
# creds/host, DB name -> cbshome_test), drops + recreates it, migrates via
# alembic, and seeds the minimum the suite needs (platform user + platform
# templates; tests build the rest through register_user). Exports
# TEST_DB_URL (global) for the caller to pass to pytest via -e.
prepare_test_db() {
    echo ""
    echo "Provisioning isolated test database (cbshome_test)..."

    local app_db_url
    app_db_url=$(docker compose exec -T app printenv DATABASE_URL | tr -d '\r\n')
    if [ -z "$app_db_url" ]; then
        echo -e "${RED}✗ Could not read DATABASE_URL from app container${NC}"
        return 1
    fi
    # Strip the trailing "/cbshome" DB name, append "/cbshome_test".
    # % removes the shortest matching suffix, so credentials/host are
    # untouched even if the password contained the substring "cbshome".
    TEST_DB_URL="${app_db_url%/cbshome}/cbshome_test"

    # Drop + recreate via the maintenance DB. FORCE terminates any
    # lingering connections left by a previous run (PG13+).
    docker compose exec -T postgres psql -U cbshome -d postgres \
        -c "DROP DATABASE IF EXISTS cbshome_test WITH (FORCE);" \
        -c "CREATE DATABASE cbshome_test OWNER cbshome;" >/dev/null || {
        echo -e "${RED}✗ Could not (re)create cbshome_test${NC}"
        return 1
    }

    # Schema via alembic -- faithful to migrations (NOT metadata.create_all,
    # which would miss functional indexes added in migration files).
    docker compose exec -T -e DATABASE_URL="$TEST_DB_URL" app \
        python -m alembic upgrade head || {
        echo -e "${RED}✗ Test DB migration failed${NC}"
        return 1
    }

    # Minimal seed. `import app.main` first so every model is registered in
    # Base.metadata before the Platform user is flushed -- otherwise the
    # users.referred_by_link_id -> referral_links FK cannot resolve on a
    # fresh DB (standalone seed scripts import only a subset of models).
    docker compose exec -T -e DATABASE_URL="$TEST_DB_URL" app \
        python -c "import app.main, runpy; runpy.run_path('scripts/seed_platform.py', run_name='__main__')" || {
        echo -e "${RED}✗ Test DB seed (platform user) failed${NC}"
        return 1
    }
    docker compose exec -T -e DATABASE_URL="$TEST_DB_URL" app \
        python -c "import app.main, runpy; runpy.run_module('scripts.seed_platform_templates', run_name='__main__')" || {
        echo -e "${RED}✗ Test DB seed (platform templates) failed${NC}"
        return 1
    }

    # Smoke check: 16 active platform-default templates (mirrors the dev-DB
    # check below -- template seeding is the historically fragile part).
    local tmpl_count
    tmpl_count=$(
        docker compose exec -T postgres psql -U cbshome -d cbshome_test \
            -tAc "SELECT COUNT(*) FROM company_document_templates WHERE company_id IS NULL AND status='active';" \
            2>/dev/null | tr -d '[:space:]'
    )
    if [ "$tmpl_count" != "16" ]; then
        echo -e "${RED}✗ Test DB platform-templates smoke check failed (found: '$tmpl_count', expected 16)${NC}"
        return 1
    fi

    echo -e "${GREEN}✓ cbshome_test ready (migrated + seeded, 16 templates)${NC}"
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
            echo "Usage: cbshome test [backend|frontend|all]"
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
                echo "Usage: cbshome update [--skip-tests] [--frontend-only]"
                return 1
                ;;
        esac
        shift
    done

    # --frontend-only implies --skip-tests (no backend cycle = no tests).
    if [ $FRONTEND_ONLY -eq 1 ]; then
        SKIP_TESTS=1
    fi

    echo "=== Updating CBSHOME ==="
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
    GIT_SSH_COMMAND="ssh -i /root/.ssh/id_ed25519_cbshome_deploy" git fetch origin
    if git diff --quiet HEAD "origin/$BRANCH" 2>/dev/null; then
        echo -e "${GREEN}✓ Already up to date${NC}"
        return 0
    fi

    # Pull changes.
    echo "Pulling updates..."
    if ! GIT_SSH_COMMAND="ssh -i /root/.ssh/id_ed25519_cbshome_deploy" git pull origin "$BRANCH"; then
        echo -e "${RED}✗ git pull failed. Local changes may conflict.${NC}"
        echo "  Inspect: git -C $COMPOSE_DIR status"
        echo "  To force: git -C $COMPOSE_DIR stash && cbshome update"
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
    # docker-compose.yml lives at the repo root in cbshome (unlike app
    # code which is under backend/), so we list it explicitly.
    if [ $FRONTEND_ONLY -eq 1 ]; then
        if ! git diff --quiet "$CURRENT_COMMIT" "$NEW_COMMIT" -- backend/ docker-compose.yml; then
            echo -e "${RED}✗ Detected backend-side changes between $CURRENT_COMMIT and $NEW_COMMIT${NC}"
            echo -e "${RED}  Refusing to run with --frontend-only.${NC}"
            echo ""
            echo "Changed files:"
            git diff --name-only "$CURRENT_COMMIT" "$NEW_COMMIT" -- backend/ docker-compose.yml | sed 's/^/  /'
            echo ""
            echo "Run: cbshome update              (full cycle)"
            echo "  or cbshome update --skip-tests (full cycle without tests)"
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
        echo "Check logs: cbshome logs app"
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
    # R-2.3: refuses on APP_ENV=production unless CBSHOME_SEED_TEST_ACCOUNTS=1.
    docker compose exec -T app python -m scripts.seed_test_accounts ${CBSHOME_SEED_TEST_ACCOUNTS:+--allow-production}
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
        docker compose exec -T postgres psql -U cbshome -d cbshome \
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
    # Run tests against an ISOLATED cbshome_test DB (TD-068), provisioned
    # fresh here -- so a run never accumulates cross-run residue and never
    # touches the live dev DB. Sequential -- xdist was an artefact of the
    # abandoned per-worker design and conftest refuses it. The dev-DB seed
    # above is for the running app; tests use cbshome_test via -e DATABASE_URL.
    # ----------------------------------------------------------------------
    pytest_status=0
    if [ $SKIP_TESTS -eq 0 ]; then
        if ! prepare_test_db; then
            echo -e "${RED}✗ Test DB provisioning failed${NC}"
            return 1
        fi
        echo ""
        echo "Running backend tests (against cbshome_test)..."
        docker compose exec -T -e DATABASE_URL="$TEST_DB_URL" app python -m pytest tests/ -v --tb=short \
            || pytest_status=$?

        if [ $pytest_status -eq 0 ]; then
            echo -e "${GREEN}✓ All tests passed${NC}"
        else
            echo -e "${RED}✗ Tests failed -- app is running, prod DB seeded${NC}"
            echo "Fix the code and run: cbshome update"
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
    # cbshome-bot commits and pushes it, so the next `cbshome update` on
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

        BOT_NAME="cbshome-bot"
        BOT_EMAIL="bot@cbshome.local"

        git add frontend/src/api/generated.ts
        git -c user.name="$BOT_NAME" -c user.email="$BOT_EMAIL" commit -m \
"chore(types): regenerate generated.ts

Triggered by cbshome update on commit $NEW_COMMIT" || {
            echo -e "${RED}✗ Bot commit failed${NC}"
            return 1
        }

        # Push with one retry: if a parallel push hits the same branch,
        # rebase on it once and try again. Anything beyond that is rare
        # and warrants manual investigation.
        PUSH_OK=0
        for attempt in 1 2; do
            if GIT_SSH_COMMAND="ssh -i /root/.ssh/id_ed25519_cbshome_deploy" \
                git push origin "$BRANCH"; then
                PUSH_OK=1
                break
            fi
            if [ "$attempt" = "1" ]; then
                echo "Push failed (likely a parallel push). Rebasing and retrying..."
                GIT_SSH_COMMAND="ssh -i /root/.ssh/id_ed25519_cbshome_deploy" \
                    git pull --rebase origin "$BRANCH" || break
            fi
        done

        if [ "$PUSH_OK" = "0" ]; then
            echo -e "${RED}✗ Failed to push regenerated types to GitHub${NC}"
            echo "  Bot commit exists locally on $COMPOSE_DIR but is not on origin."
            echo "  Resolve manually:"
            echo "    cd $COMPOSE_DIR && GIT_SSH_COMMAND=\"ssh -i /root/.ssh/id_ed25519_cbshome_deploy\" git push"
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
    # a test failure so the dev site stays usable, but `cbshome update`
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
# refresh types without running a full `cbshome update` (e.g. while
# iterating on a new Pydantic schema on the test VPS).
#
# This command does NOT commit or push -- it only writes the file.
# `cbshome update` is what handles the bot commit/push cycle.
# ==============================================================================

case_gen_types() {
    cd_compose

    if ! curl -sf "http://127.0.0.1:8000/openapi.json" -o /tmp/openapi.json; then
        echo -e "${RED}✗ Cannot fetch /openapi.json from backend${NC}"
        echo "  Is the app container running? Check with: cbshome status"
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
        echo "  Run 'cbshome update' to commit and push, or commit by hand."
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
#   - MinIO bucket snapshot (mc mirror local/cbshome-attachments)
#
# Rotation: 7 days. The MinIO mirror step is best-effort -- if mc fails
# (network blip, MinIO down), we proceed with DB-only backup and warn.
# ==============================================================================

case_backup() {
    cd_compose
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    BACKUP_DIR="$INSTALL_BASE/backups"
    BACKUP_FILE="$BACKUP_DIR/cbshome_backup_${TIMESTAMP}.tar.gz"
    DB_DUMP_FILE="/tmp/cbshome_db_${TIMESTAMP}.sql"
    MINIO_DUMP_DIR="/tmp/cbshome_minio_${TIMESTAMP}"
    mkdir -p "$BACKUP_DIR"

    echo "Creating backup..."

    # 1. Dump database.
    echo "  Dumping PostgreSQL..."
    docker compose exec -T postgres pg_dump \
        -U cbshome cbshome > "$DB_DUMP_FILE"

    # 2. Mirror MinIO bucket (best-effort).
    echo "  Mirroring MinIO bucket..."
    mkdir -p "$MINIO_DUMP_DIR"
    if mc mirror --quiet local/cbshome-attachments "$MINIO_DUMP_DIR/" 2>/dev/null; then
        MINIO_OBJECTS=$(find "$MINIO_DUMP_DIR" -type f 2>/dev/null | wc -l)
        echo "  MinIO: $MINIO_OBJECTS objects mirrored"
    else
        echo -e "${YELLOW}  ⚠ MinIO mirror failed -- proceeding with DB-only backup${NC}"
        # Keep the empty dir so tar doesn't choke on a missing path.
    fi

    # 3. Archive: DB dump + .env + MinIO snapshot.
    echo "  Creating archive..."
    tar -czf "$BACKUP_FILE" \
        -C /tmp "cbshome_db_${TIMESTAMP}.sql" \
        -C "$COMPOSE_DIR/backend" ".env" \
        -C /tmp "cbshome_minio_${TIMESTAMP}"

    # 4. Cleanup tmp.
    rm -f "$DB_DUMP_FILE"
    rm -rf "$MINIO_DUMP_DIR"

    # 5. Rotate: keep last 7 days.
    find "$BACKUP_DIR" -name "cbshome_backup_*.tar.gz" -mtime +7 -delete

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
            docker compose exec postgres psql -U cbshome -d cbshome
            ;;
        dump)
            TIMESTAMP=$(date +%Y%m%d_%H%M%S)
            DUMP_FILE="$INSTALL_BASE/backups/cbshome_db_${TIMESTAMP}.sql"
            mkdir -p "$INSTALL_BASE/backups"
            docker compose exec -T postgres pg_dump -U cbshome cbshome > "$DUMP_FILE"
            echo -e "${GREEN}✓ Dump: $DUMP_FILE${NC}"
            ;;
        restore)
            if [ -z "${2:-}" ]; then
                echo "Usage: cbshome db restore <file>"
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
                cat "$2" | docker compose exec -T postgres psql -U cbshome cbshome
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
            echo "  cbshome db connect          — Connect to PostgreSQL (psql)"
            echo "  cbshome db dump             — Create SQL dump"
            echo "  cbshome db restore <file>   — Restore from dump"
            echo "  cbshome db migrate          — Run Alembic migrations"
            ;;
    esac
}

# ==============================================================================
# SEED
# ==============================================================================

case_seed() {
    cd_compose
    # R-2.3: seed_test_accounts refuses on APP_ENV=production unless
    # CBSHOME_SEED_TEST_ACCOUNTS=1 is exported (well-known credentials).
    if [ "${1:-}" = "--reset" ]; then
        docker compose exec -T app python scripts/seed_platform.py --reset
        docker compose exec -T app python scripts/seed_documents.py
        docker compose exec -T app python -m scripts.seed_storefront --reset
        docker compose exec -T app python -m scripts.seed_test_accounts --reset ${CBSHOME_SEED_TEST_ACCOUNTS:+--allow-production}
    else
        docker compose exec -T app python scripts/seed_platform.py
        docker compose exec -T app python scripts/seed_documents.py
        docker compose exec -T app python -m scripts.seed_storefront
        docker compose exec -T app python -m scripts.seed_test_accounts ${CBSHOME_SEED_TEST_ACCOUNTS:+--allow-production}
    fi
}

# ==============================================================================
# SEED USER PORTFOLIO (dev)
# ==============================================================================

case_seed_portfolio() {
    cd_compose
    local EMAIL="${1:-}"
    if [ -z "$EMAIL" ]; then
        echo "Usage: cbshome seed-portfolio <email> [--deposit CENTS] [--purchases N]"
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
            echo "  cbshome ssl renew   — Renew SSL certificates"
            echo "  cbshome ssl status  — Show certificate info"
            ;;
    esac
}

# ==============================================================================
# NGINX
# ==============================================================================

case_nginx() {
    case "${1:-reload}" in
        reload)
            nginx -t && systemctl reload nginx
            echo -e "${GREEN}✓ Nginx reloaded${NC}"
            ;;
        *)
            echo "Nginx commands:"
            echo "  cbshome nginx reload — Test config and reload Nginx"
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
            mc du local/cbshome-attachments 2>/dev/null || {
                echo -e "${RED}✗ Cannot reach MinIO via mc alias 'local'${NC}"
                echo "  Check: mc alias list  |  cbshome status"
                return 1
            }
            echo ""
            echo "Object count:"
            local COUNT
            COUNT=$(mc ls --recursive local/cbshome-attachments 2>/dev/null | wc -l)
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
                echo "Usage: cbshome storage reconcile <company_id> [--dry-run|--orphans-only|--broken-only]"
                echo "       cbshome storage reconcile --all          [--dry-run|--orphans-only|--broken-only]"
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
                echo "Usage: cbshome storage reconcile-templates <company_id> [--dry-run]"
                exit 1
            fi
            # Refactor 2 iter 2.3: pass-through to the Python reconcile script.
            # No --all here -- per-company templates are uploaded one company
            # at a time, and a bulk pass would mask single-company errors
            # behind aggregate stats. See CBSHOME-Refactor-Company-Docs.md §4.8.
            docker compose exec -T app python -m scripts.reconcile_templates "$@"
            ;;
        reconcile-platform-templates)
            shift
            # Refactor 2 iter 2.3: pass-through to the Python reconcile script.
            # No company_id argument -- there is exactly one platform default
            # series (company_id IS NULL). See CBSHOME-Refactor-Company-Docs.md §4.9.
            docker compose exec -T app python -m scripts.reconcile_platform_templates "$@"
            ;;
        ""|help|*)
            echo "Storage commands:"
            echo "  cbshome storage stats                              — Bucket size + object count"
            echo "  cbshome storage console                            — Print MinIO Console URL + credentials"
            echo "  cbshome storage reconcile <company_id>             — Sync inbox -> attachments"
            echo "  cbshome storage reconcile --all                    — Sync inbox for every company"
            echo "  cbshome storage reconcile-templates <company_id>   — Sync templates-inbox -> templates"
            echo "  cbshome storage reconcile-platform-templates       — Sync _platform/templates-inbox -> platform default rows"
            ;;
    esac
}

# ==============================================================================
# VERSION
# ==============================================================================

case_version() {
    cd_compose
    echo "=== CBSHOME Version ==="
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
}

# ==============================================================================
# TEST EMAIL
# ==============================================================================

case_test_email() {
    cd_compose
    local RECIPIENT="${1:-}"
    if [ -z "$RECIPIENT" ]; then
        echo "Usage: cbshome test-email <recipient@example.com>"
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
    subject='CBS HOME — Mailgun Test',
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
    subject='CBS HOME — SMTP Test',
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
        echo -e "${CYAN}CBSHOME Management Script${NC}"
        echo ""
        echo "Usage: cbshome <command> [options]"
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
        echo "  test-email <email>                        — Test Mailgun + SMTP delivery"
        ;;
esac
MANAGE_EOF

chmod +x "$MANAGE_SCRIPT"
ln -sf "$MANAGE_SCRIPT" /usr/local/bin/cbshome
success "Management script: /usr/local/bin/cbshome"

# ==============================================================================
# BACKUP CRON
# ==============================================================================

section "Backup Cron"

(crontab -l 2>/dev/null; echo "0 4 * * * /usr/local/bin/cbshome backup >> /var/log/cbshome-backup.log 2>&1") \
    | sort -u | crontab -
success "Backup cron: 4 AM daily, 7-day rotation"

# ==============================================================================
# DONE
# ==============================================================================

echo ""
echo -e "${GREEN}${BOLD}"
echo "╔══════════════════════════════════════════════════╗"
echo "║           CBSHOME Installation Complete!         ║"
echo "╚══════════════════════════════════════════════════╝"
echo -e "${NC}"
echo -e "API:           ${CYAN}https://${API_DOMAIN}/health${NC}"
echo -e "Frontend:      ${CYAN}https://${FRONTEND_DOMAIN}${NC}"
echo -e "MinIO Console: ${CYAN}https://${STORAGE_DOMAIN}${NC}  (login: admin / see .env)"
echo ""
echo -e "Management: ${CYAN}cbshome status | cbshome logs | cbshome update | cbshome storage console${NC}"
echo ""
echo -e "${YELLOW}NEXT STEPS:${NC}"
echo "1. Edit $INSTALL_BASE/repo/backend/.env"
echo "   -- Set TELEGRAM_BOT_TOKEN (if not done)"
echo "   -- Set SUMSUB_API_KEY / SUMSUB_SECRET_KEY"
echo "   -- Set MAILGUN_API_KEY (if not done)"
echo "   -- Set MAILGUN_API_URL (default: EU endpoint, change to https://api.mailgun.net for US)"
echo "2. Add DKIM DNS record (printed above during mail setup)"
echo "3. Verify DKIM: opendkim-testkey -d ${MAIL_DOMAIN} -s cbshome -vvv"
echo "4. Run: cbshome restart app"
echo "5. Test email: cbshome test-email your@email.com"
echo "6. Open MinIO Console: cbshome storage console  (prints URL + credentials)"
echo ""
