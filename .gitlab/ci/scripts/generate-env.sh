#!/bin/bash

set -euo pipefail

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

ENV_FILE="${ENV_FILE:-.env}"
ENVIRONMENT="${ENVIRONMENT:-unknown}"

log_info "Generating .env file for environment: $ENVIRONMENT"

cat > "$ENV_FILE" << EOF
# =============================================================================
# Auto-generated .env file
# Environment: ${ENVIRONMENT}
# Generated at: $(date -u +"%Y-%m-%d %H:%M:%S UTC")
# =============================================================================

# Application Image
APP_IMAGE="$APP_IMAGE"

# Bot Configuration
BOT_TOKEN="$BOT_TOKEN"
VITE_BOT_USERNAME="$VITE_BOT_USERNAME"
SECRET_TOKEN="$SECRET_TOKEN"
WEBHOOK_URL="$WEBHOOK_URL"
WEBHOOK_PATH="$WEBHOOK_PATH"
PROXY_PORT="$PROXY_PORT"
TELEGRAM_BOT_API_URL="$TELEGRAM_BOT_API_URL"
WEBAPP_URL="$WEBAPP_URL"

# Moderation
MODERATION_CHANNEL_ID="$MODERATION_CHANNEL_ID"
BOT_ADMINS="$BOT_ADMINS"

# Database
POSTGRES_USER="$POSTGRES_USER"
POSTGRES_PASSWORD="$POSTGRES_PASSWORD"
POSTGRES_PUB_PORT="$POSTGRES_PUB_PORT"
MINIO_USER="$MINIO_USER"
MINIO_PASSWORD="$MINIO_PASSWORD"

# AI/LLM
OLLAMA_BASE_URL="$OLLAMA_BASE_URL"

# Router/Traefik
ROUTER_NAME="$ROUTER_NAME"

# Version
BOT_VERSION="$BOT_VERSION"
EOF

REQUIRED_VARS=(
    "APP_IMAGE"
    "BOT_TOKEN"
    "SECRET_TOKEN"
    "WEBHOOK_URL"
    "WEBHOOK_PATH"
    "POSTGRES_USER"
    "POSTGRES_PASSWORD"
    "MINIO_USER"
    "MINIO_PASSWORD"
)

MISSING_VARS=()

for var in "${REQUIRED_VARS[@]}"; do
    value=$(grep "^${var}=" "$ENV_FILE" | cut -d'=' -f2-)
    if [ -z "$value" ]; then
        MISSING_VARS+=("$var")
    fi
done

if [ ${#MISSING_VARS[@]} -gt 0 ]; then
    log_warning "The following required variables are empty:"
    for var in "${MISSING_VARS[@]}"; do
        echo "  - $var"
    done
fi

log_success ".env file generated successfully at: $ENV_FILE"
log_info "Total variables: $(grep -c "=" "$ENV_FILE" || echo 0)"
