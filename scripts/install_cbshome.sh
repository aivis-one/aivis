#!/bin/bash

# ==============================================================================
# CBSHOME Platform -- VPS Installation Script
# ==============================================================================
#
# WHAT THIS SCRIPT DOES:
#   1.  Pre-flight checks (OS, RAM, disk, DNS)
#   2.  Fix locale (en_US.UTF-8)
#   3.  Install system deps (Docker, Nginx, Certbot, UFW, git, dnsutils)
#   4.  Configure firewall (22/80/443 only)
#   5.  Create deploy user `cbshome` (non-root, docker group)
#   6.  Generate SSH deploy key -> add to GitHub -> clone repo
#   7.  Generate .env with random passwords
#   8.  Prompt for sensitive secrets (bot token, API keys)
#   9.  Configure Nginx reverse proxy (api.cbshome.org, cbshome.org)
#   10. Obtain SSL certificates (Let's Encrypt) + auto-renewal cron
#   11. Install and configure mail server (Postfix + OpenDKIM)
#   12. Start Docker stack -> healthcheck -> migrations -> seed Platform user
#   13. Create `cbshome` management script -> symlink /usr/local/bin/cbshome
#   14. Set up backup cron (4 AM daily, 7-day rotation)
#
# USAGE:
#   curl -fsSL https://raw.githubusercontent.com/aivis-one/cbshome/main/scripts/install_cbshome.sh | bash
#
# REQUIREMENTS:
#   - Ubuntu 22.04+ (fresh VPS, root access)
#   - Domain cbshome.org pointing to this server
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

    # DNS check
    local RESOLVED_IP
    RESOLVED_IP=$(dig +short "$API_DOMAIN" 2>/dev/null | head -1 || true)
    local SERVER_IP
    SERVER_IP=$(curl -s --max-time 5 ifconfig.me 2>/dev/null || true)

    if [ -z "$RESOLVED_IP" ]; then
        warn "DNS: $API_DOMAIN does not resolve. SSL setup may fail."
    elif [ "$RESOLVED_IP" = "$SERVER_IP" ]; then
        success "DNS: $API_DOMAIN -> $RESOLVED_IP ✓"
    else
        warn "DNS: $API_DOMAIN -> $RESOLVED_IP (server IP: $SERVER_IP). SSL may fail."
    fi

    success "Pre-flight checks complete"
}

preflight_checks

# ==============================================================================
# PREVIOUS INSTALLATION CHECK
# ==============================================================================

if [ -d "$INSTALL_BASE/repo" ]; then
    warn "Found existing installation at $INSTALL_BASE"
    echo ""
    read -rp "Remove existing installation and start fresh? (y/n): " -n 1
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
    > /dev/null 2>&1

success "Base packages installed"

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
read -r

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

log "Generating .env with random passwords..."

# Generate all secrets ONCE before writing -- ensures DATABASE_URL and
# POSTGRES_PASSWORD always contain the same password (no double gen_password calls).
DB_PASS=$(gen_password)
REDIS_PASS=$(gen_password)
SECRET=$(gen_secret)
KYC_SECRET=$(gen_password)
CRYPTO_SECRET=$(gen_password)

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

# -- Auth --
SECRET_KEY=${SECRET}
SESSION_TTL_DAYS=30
MAX_CONCURRENT_SESSIONS=5

# -- Telegram --
TELEGRAM_BOT_TOKEN=PLACEHOLDER

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
success ".env generated with random passwords"

# Interactive secrets
echo ""
log "Enter secrets (press ENTER to keep PLACEHOLDER and configure later):"
echo ""

prompt_secret() {
    local VAR="$1"
    local LABEL="$2"
    read -rp "  $LABEL: " VALUE
    if [ -n "$VALUE" ]; then
        sed -i "s|${VAR}=.*|${VAR}=${VALUE}|" "$ENV_FILE"
        success "  $LABEL set"
    else
        warn "  $LABEL: keeping PLACEHOLDER"
    fi
}

prompt_secret "TELEGRAM_BOT_TOKEN" "Telegram Bot Token"
prompt_secret "SUMSUB_API_KEY"     "SumSub API Key (optional)"
prompt_secret "SUMSUB_SECRET_KEY"  "SumSub Secret Key (optional)"
prompt_secret "MAILGUN_API_KEY"    "Mailgun API Key (optional)"

chmod 600 "$ENV_FILE"
success ".env secured (chmod 600)"

# ==============================================================================
# NGINX CONFIGURATION
# ==============================================================================

section "Nginx Configuration"

# API (backend)
cat > /etc/nginx/sites-available/cbshome-api << NGINX_API
server {
    listen 80;
    server_name ${API_DOMAIN};

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
read -r

success "Mail server setup complete"

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

# Run Alembic migrations
log "Running database migrations..."
docker compose exec -T app python -m alembic upgrade head
success "Migrations applied"

# Seed Platform user
log "Seeding Platform user..."
docker compose exec -T app python scripts/seed_platform.py
success "Platform user seeded"

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
}

# ==============================================================================
# LOGS
# ==============================================================================

case_logs() {
    cd_compose
    case "${1:-app}" in
        app)      docker compose logs -f --tail=100 app ;;
        db|postgres) docker compose logs -f --tail=100 postgres ;;
        redis)    docker compose logs -f --tail=100 redis ;;
        frontend) docker compose logs -f --tail=100 frontend 2>/dev/null || echo "Frontend not running" ;;
        all|"")   docker compose logs -f --tail=100 ;;
        *)        echo "Usage: cbshome logs [app|db|redis|frontend|all]" ;;
    esac
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
            if ! docker compose exec -T app python -m pytest tests/ -v --tb=short; then
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
            if ! docker compose exec -T app python -m pytest tests/ -v --tb=short; then
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

    echo "=== Updating CBSHOME ==="
    echo ""

    # Fix git safe directory (git 2.35+ security requirement).
    git config --global --add safe.directory "$COMPOSE_DIR" 2>/dev/null || true

    # Save current state.
    CURRENT_COMMIT=$(git rev-parse --short HEAD)
    BRANCH=$(git branch --show-current)
    echo "Current: $CURRENT_COMMIT ($BRANCH)"

    # Check for uncommitted local changes.
    if ! git diff-index --quiet HEAD -- 2>/dev/null; then
        echo -e "${YELLOW}⚠ Uncommitted changes detected:${NC}"
        git status --short
        echo ""
        read -rp "Discard local changes and update? (y/n): " -n 1
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

    # Rebuild all images (app + frontend).
    echo "Rebuilding Docker images..."
    docker compose build

    # Restart stack (down + up to ensure new image is used).
    echo "Restarting services..."
    docker compose down
    docker compose up -d

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

    # Seed Platform user (idempotent).
    echo ""
    echo "Seeding Platform user..."
    docker compose exec -T app python scripts/seed_platform.py

    # Run backend tests.
    echo ""
    echo "Running backend tests..."
    if docker compose exec -T app python -m pytest tests/ -v --tb=short; then
        echo -e "${GREEN}✓ All tests passed${NC}"
    else
        echo -e "${RED}✗ Tests failed -- app is running but code may be broken${NC}"
        echo "Fix the code and run: cbshome update"
        return 1
    fi

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

case_backup() {
    cd_compose
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    BACKUP_DIR="$INSTALL_BASE/backups"
    BACKUP_FILE="$BACKUP_DIR/cbshome_backup_${TIMESTAMP}.tar.gz"
    mkdir -p "$BACKUP_DIR"

    echo "Creating backup..."

    # Dump database.
    docker compose exec -T postgres pg_dump \
        -U cbshome cbshome > "/tmp/cbshome_db_${TIMESTAMP}.sql"

    # Archive DB dump + .env.
    tar -czf "$BACKUP_FILE" \
        -C /tmp "cbshome_db_${TIMESTAMP}.sql" \
        -C "$COMPOSE_DIR/backend" ".env"

    rm -f "/tmp/cbshome_db_${TIMESTAMP}.sql"

    # Rotate: keep last 7 days.
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
            read -rp "Are you sure? (y/n): " -n 1
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
    if [ "${1:-}" = "--reset" ]; then
        docker compose exec -T app python scripts/seed_platform.py --reset
    else
        docker compose exec -T app python scripts/seed_platform.py
    fi
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
    update|deploy)  case_update ;;
    restart)        case_restart "$@" ;;
    backup)         case_backup ;;
    db)             case_db "$@" ;;
    seed)           case_seed "$@" ;;
    ssl)            case_ssl "$@" ;;
    nginx)          case_nginx "$@" ;;
    version)        case_version ;;
    test-email)     case_test_email "$@" ;;
    help|*)
        echo -e "${CYAN}CBSHOME Management Script${NC}"
        echo ""
        echo "Usage: cbshome <command> [options]"
        echo ""
        echo "Monitoring:"
        echo "  status                    — Docker status + health + external access"
        echo "  logs [app|db|redis|all]   — View logs (default: app)"
        echo "  version                   — Git log + runtime versions"
        echo ""
        echo "Testing:"
        echo "  test [backend|frontend|all] — Run tests (default: all)"
        echo "  lint                      — Run ruff + mypy + eslint"
        echo ""
        echo "Deployment:"
        echo "  update                    — Pull, rebuild, migrate, test, restart"
        echo "  restart [service]         — Restart all or specific service"
        echo ""
        echo "Database:"
        echo "  db connect                — Open psql session"
        echo "  db dump                   — Create SQL dump"
        echo "  db restore <file>         — Restore from dump"
        echo "  db migrate                — Run Alembic migrations"
        echo "  seed                      — Seed Platform user"
        echo "  seed --reset              — Clean + re-seed"
        echo ""
        echo "Maintenance:"
        echo "  backup                    — Backup DB + .env (7-day rotation)"
        echo "  ssl renew                 — Renew SSL certificates"
        echo "  ssl status                — Show certificate info"
        echo "  nginx reload              — Test config and reload Nginx"
        echo "  test-email <email>        — Test Mailgun + SMTP delivery"
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
echo -e "API:      ${CYAN}https://${API_DOMAIN}/health${NC}"
echo -e "Frontend: ${CYAN}https://${FRONTEND_DOMAIN}${NC}"
echo ""
echo -e "Management: ${CYAN}cbshome status | cbshome logs | cbshome update${NC}"
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
echo ""
