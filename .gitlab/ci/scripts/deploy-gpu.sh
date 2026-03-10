#!/bin/bash
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

log_info "Starting GPU inference deployment..."
log_info "Inference Image: ${INFERENCE_IMAGE:-not set}"

if [ ! -f ".env" ]; then
    log_error ".env file not found!"
    exit 1
fi

log_info "Pulling images..."
env -i PATH="$PATH" docker compose -f compose.gpu.yml pull inference || {
    log_error "Failed to pull inference image"
    exit 1
}

log_info "Stopping services..."
env -i PATH="$PATH" docker compose -f compose.gpu.yml down || true

log_info "Starting services..."
env -i PATH="$PATH" docker compose -f compose.gpu.yml up -d || {
    log_error "Failed to start services"
    exit 1
}

log_info "Waiting for services..."
sleep 15

log_info "Service status:"
env -i PATH="$PATH" docker compose -f compose.gpu.yml ps

log_success "GPU deployment completed!"
