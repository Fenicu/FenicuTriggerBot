#!/bin/bash

# Usage: ./deploy.sh [options]
# Options:
#   --no-pull     Skip pulling images
#   --no-migrate  Skip migrator service
#   --rollback    Use previous image version


set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

NO_PULL=false
NO_MIGRATE=false
ROLLBACK=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --no-pull)
            NO_PULL=true
            shift
            ;;
        --no-migrate)
            NO_MIGRATE=true
            shift
            ;;
        --rollback)
            ROLLBACK=true
            shift
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

SERVICES="bot ai_worker migrator traefik rabbitmq"

if [ "$NO_MIGRATE" = true ]; then
    SERVICES="bot ai_worker traefik rabbitmq"
fi

log_info "Starting deployment process..."
log_info "Environment: ${ENVIRONMENT:-unknown}"
log_info "App Image: ${APP_IMAGE:-not set}"

if [ ! -f ".env" ]; then
    log_error ".env file not found! Run generate-env.sh first."
    exit 1
fi

if [ "$NO_PULL" = false ]; then
    log_info "Pulling latest images..."
    env -i PATH="$PATH" docker compose pull || {
        log_error "Failed to pull images"
        exit 1
    }
fi

log_info "Stopping services: $SERVICES"
env -i PATH="$PATH" docker compose down $SERVICES || {
    log_warning "Some services might not have been running"
}

log_info "Starting services..."
env -i PATH="$PATH" docker compose up -d --build || {
    log_error "Failed to start services"
    exit 1
}

log_info "Waiting for services to become healthy..."
sleep 10

log_info "Checking service status..."
env -i PATH="$PATH" docker compose ps

log_success "Deployment completed successfully!"
log_info "Version: ${BOT_VERSION:-unknown}"
