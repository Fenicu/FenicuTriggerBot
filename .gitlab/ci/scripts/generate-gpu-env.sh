#!/bin/bash
set -euo pipefail

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }

ENV_FILE="${ENV_FILE:-.env}"
ENVIRONMENT="${ENVIRONMENT:-unknown}"

log_info "Generating GPU .env file for environment: $ENVIRONMENT"

cat > "$ENV_FILE" << EOF
# Auto-generated .env (GPU server)
# Environment: ${ENVIRONMENT}
# Generated at: $(date -u +"%Y-%m-%d %H:%M:%S UTC")

INFERENCE_IMAGE="$INFERENCE_IMAGE"
INFERENCE_PORT="$INFERENCE_PORT"
INFERENCE_API_KEY="$INFERENCE_API_KEY"
OLLAMA_MODEL="$OLLAMA_MODEL"
NSFW_THRESHOLD="${NSFW_THRESHOLD:-0.85}"
EOF

REQUIRED_VARS=("INFERENCE_IMAGE" "INFERENCE_API_KEY")

MISSING_VARS=()
for var in "${REQUIRED_VARS[@]}"; do
    value=$(grep "^${var}=" "$ENV_FILE" | cut -d'=' -f2-)
    if [ -z "$value" ]; then
        MISSING_VARS+=("$var")
    fi
done

if [ ${#MISSING_VARS[@]} -gt 0 ]; then
    log_warning "Missing required variables:"
    for var in "${MISSING_VARS[@]}"; do
        echo "  - $var"
    done
fi

log_success ".env file generated at: $ENV_FILE"
