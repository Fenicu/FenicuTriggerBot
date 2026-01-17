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


# Debug: print all relevant env variables in base64 before generating .env
print_b64() {
    local var_name="$1"
    local var_value="${!var_name}"
    local b64_value=$(printf '%s' "$var_value" | base64)
    echo "[DEBUG-B64] $var_name: $b64_value"
}

print_b64 ENVIRONMENT
print_b64 APP_IMAGE
print_b64 BOT_TOKEN
print_b64 VITE_BOT_USERNAME
print_b64 SECRET_TOKEN
print_b64 WEBHOOK_URL
print_b64 WEBHOOK_PATH
print_b64 PROXY_PORT
print_b64 TELEGRAM_BOT_API_URL
print_b64 WEBAPP_URL
print_b64 MODERATION_CHANNEL_ID
print_b64 BOT_ADMINS
print_b64 POSTGRES_USER
print_b64 POSTGRES_PASSWORD
print_b64 POSTGRES_PUB_PORT
print_b64 OLLAMA_BASE_URL
print_b64 ROUTER_NAME
print_b64 BOT_VERSION

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

chmod 600 "$ENV_FILE"

log_success ".env file generated successfully at: $ENV_FILE"
log_info "Total variables: $(grep -c "=" "$ENV_FILE" || echo 0)"
