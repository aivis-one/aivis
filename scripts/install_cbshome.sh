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
#   11. Start Docker stack -> healthcheck -> migrations -> seed Platform user
#   12. Create `cbshome` management script -> symlink /usr/local/bin/cbshome
#   13. Set up backup cron (4 AM daily, 7-day rotation)
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
echo "y" | ufw enable > /dev/null 2>&1
success "UFW: 22 (SSH) + 80 (HTTP) + 443 (HTTPS) only"

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

cat > "$ENV_FILE" << ENV_TEMPLATE
# =============================================================================
# CBSHOME Backend -- Environment (generated by install_cbshome.sh)
# Generated: $(date -u +"%Y-%m-%d %H:%M:%S UTC")
# =============================================================================

# -- Application --
APP_ENV=production
LOG_LEVEL=INFO
CORS_ORIGINS=https://${FRONTEND_DOMAIN}

# -- Database --
DATABASE_URL=postgresql+asyncpg://cbshome:$(gen_password)@postgres:5432/cbshome
POSTGRES_DB=cbshome
POSTGRES_USER=cbshome
POSTGRES_PASSWORD=$(gen_password)

# -- Redis --
REDIS_PASSWORD=$(gen_password)
REDIS_URL=redis://:$(gen_password)@redis:6379/0

# -- Auth --
SECRET_KEY=$(gen_secret)
SESSION_TTL_DAYS=30
MAX_CONCURRENT_SESSIONS=5

# -- Telegram --
TELEGRAM_BOT_TOKEN=PLACEHOLDER

# -- KYC (SumSub) --
SUMSUB_API_KEY=PLACEHOLDER
SUMSUB_SECRET_KEY=PLACEHOLDER

# -- Email --
EMAP_API_KEY=PLACEHOLDER
MAILGUN_API_KEY=PLACEHOLDER
MAILGUN_DOMAIN=

# -- Crypto --
CRYPTO_NETWORKS=TRC20,ERC20,BEP20,PoS
FREEZING_HOURS_CRYPTO=1

# -- Installments --
INSTALLMENT_DEFAULT_DAYS=7
INSTALLMENT_WORKER_HOUR=3

# -- Agent --
AGENT_APPLICATION_COOLDOWN_DAYS=30
ENV_TEMPLATE

success ".env generated with random passwords"

# Note: REDIS_URL and POSTGRES_PASSWORD need to be consistent.
# Regenerate consistently:
DB_PASS=$(gen_password)
REDIS_PASS=$(gen_password)
SECRET=$(gen_secret)

sed -i "s|DATABASE_URL=.*|DATABASE_URL=postgresql+asyncpg://cbshome:${DB_PASS}@postgres:5432/cbshome|" "$ENV_FILE"
sed -i "s|POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=${DB_PASS}|" "$ENV_FILE"
sed -i "s|REDIS_PASSWORD=.*|REDIS_PASSWORD=${REDIS_PASS}|" "$ENV_FILE"
sed -i "s|REDIS_URL=.*|REDIS_URL=redis://:${REDIS_PASS}@redis:6379/0|" "$ENV_FILE"
sed -i "s|SECRET_KEY=.*|SECRET_KEY=${SECRET}|" "$ENV_FILE"

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
prompt_secret "EMAP_API_KEY"       "EMAP API Key (optional)"
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
# START DOCKER STACK
# ==============================================================================

section "Docker Stack"

cd "$INSTALL_BASE/repo"
log "Building Docker images (this may take a few minutes)..."
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
# cbshome -- CBSHOME Management Script
# ==============================================================================

INSTALL_BASE="/opt/cbshome"
COMPOSE_DIR="$INSTALL_BASE/repo"
API_DOMAIN="api.cbshome.org"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

cd_compose() {
    cd "$COMPOSE_DIR" || { echo -e "${RED}ERROR: $COMPOSE_DIR not found${NC}"; exit 1; }
}

cmd_status() {
    cd_compose
    echo -e "${CYAN}=== Docker Status ===${NC}"
    docker compose ps
    echo ""
    echo -e "${CYAN}=== Health ===${NC}"
    curl -s "http://127.0.0.1:8000/health" | python3 -m json.tool 2>/dev/null \
        || echo "App not responding"
    echo ""
    echo -e "${CYAN}=== External Access ===${NC}"
    curl -sf "https://${API_DOMAIN}/health" > /dev/null 2>&1 \
        && echo -e "${GREEN}✓ https://${API_DOMAIN}/health OK${NC}" \
        || echo -e "${RED}✗ https://${API_DOMAIN}/health unreachable${NC}"
}

cmd_logs() {
    cd_compose
    SERVICE="${1:-app}"
    docker compose logs -f "$SERVICE"
}

cmd_test() {
    cd_compose
    docker compose exec app python -m pytest tests/ -v --tb=short
}

cmd_lint() {
    cd_compose
    docker compose exec app python -m ruff check app/ tests/
    docker compose exec app python -m mypy app/
}

cmd_update() {
    cd_compose
    echo -e "${CYAN}=== Pulling latest code ===${NC}"
    GIT_SSH_COMMAND="ssh -i /root/.ssh/id_ed25519_cbshome_deploy" \
        git pull origin main

    echo -e "${CYAN}=== Building ===${NC}"
    docker compose build

    echo -e "${CYAN}=== Running migrations ===${NC}"
    docker compose exec -T app python -m alembic upgrade head

    echo -e "${CYAN}=== Seeding Platform user ===${NC}"
    docker compose exec -T app python scripts/seed_platform.py

    echo -e "${CYAN}=== Running tests ===${NC}"
    docker compose exec -T app python -m pytest tests/ -v --tb=short

    echo -e "${CYAN}=== Restarting ===${NC}"
    docker compose up -d

    echo -e "${GREEN}✓ Update complete${NC}"
}

cmd_restart() {
    cd_compose
    SERVICE="${1:-}"
    if [ -n "$SERVICE" ]; then
        docker compose restart "$SERVICE"
    else
        docker compose restart
    fi
}

cmd_backup() {
    cd_compose
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    BACKUP_DIR="/opt/cbshome/backups"
    BACKUP_FILE="$BACKUP_DIR/cbshome_backup_${TIMESTAMP}.tar.gz"
    mkdir -p "$BACKUP_DIR"

    # Dump database
    docker compose exec -T postgres pg_dump \
        -U cbshome cbshome > "/tmp/cbshome_db_${TIMESTAMP}.sql"

    # Archive DB dump + .env
    tar -czf "$BACKUP_FILE" \
        -C /tmp "cbshome_db_${TIMESTAMP}.sql" \
        -C /opt/cbshome/repo/backend ".env"

    rm -f "/tmp/cbshome_db_${TIMESTAMP}.sql"

    # Rotate: keep last 7 days
    find "$BACKUP_DIR" -name "cbshome_backup_*.tar.gz" \
        -mtime +7 -delete

    echo -e "${GREEN}✓ Backup: $BACKUP_FILE${NC}"
}

cmd_db_connect() {
    cd_compose
    docker compose exec postgres psql -U cbshome -d cbshome
}

cmd_db_migrate() {
    cd_compose
    docker compose exec -T app python -m alembic upgrade head
}

cmd_seed() {
    cd_compose
    if [ "${1:-}" = "--reset" ]; then
        docker compose exec -T app python scripts/seed.py --reset
    else
        docker compose exec -T app python scripts/seed.py
    fi
}

cmd_ssl_renew() {
    certbot renew --quiet
    systemctl reload nginx
    echo -e "${GREEN}✓ SSL renewed${NC}"
}

cmd_version() {
    cd_compose
    echo -e "${CYAN}=== CBSHOME Version ===${NC}"
    git log --oneline -5
    echo ""
    docker compose exec -T app python -c \
        "import subprocess; print(subprocess.check_output(['python','--version']).decode().strip())"
}

CMD="${1:-help}"
shift 2>/dev/null || true

case "$CMD" in
    status)     cmd_status ;;
    logs)       cmd_logs "$@" ;;
    test)       cmd_test ;;
    lint)       cmd_lint ;;
    update)     cmd_update ;;
    restart)    cmd_restart "$@" ;;
    backup)     cmd_backup ;;
    db)
        SUBCMD="${1:-connect}"
        shift 2>/dev/null || true
        case "$SUBCMD" in
            connect)  cmd_db_connect ;;
            migrate)  cmd_db_migrate ;;
            *)        echo "Usage: cbshome db [connect|migrate]" ;;
        esac
        ;;
    seed)       cmd_seed "$@" ;;
    ssl)
        SUBCMD="${1:-renew}"
        case "$SUBCMD" in
            renew)  cmd_ssl_renew ;;
            *)      echo "Usage: cbshome ssl renew" ;;
        esac
        ;;
    version)    cmd_version ;;
    help|*)
        echo -e "${CYAN}CBSHOME Management Script${NC}"
        echo ""
        echo "Usage: cbshome <command> [options]"
        echo ""
        echo "Commands:"
        echo "  status              Health check + Docker status"
        echo "  logs [app|db|redis] View logs (default: app)"
        echo "  test                Run all tests"
        echo "  lint                Run ruff + mypy"
        echo "  update              Pull, build, migrate, test, restart"
        echo "  restart [service]   Restart all or specific service"
        echo "  backup              Backup DB + .env (7-day rotation)"
        echo "  db connect          Open psql session"
        echo "  db migrate          Run Alembic migrations"
        echo "  seed                Populate DB with test data"
        echo "  seed --reset        Clean + re-seed"
        echo "  ssl renew           Renew SSL certificates"
        echo "  version             Show git log + Python version"
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
echo "   -- Set EMAP_API_KEY / MAILGUN_API_KEY"
echo "2. Run: cbshome restart app"
echo ""
