#!/usr/bin/env bash
set -euo pipefail
echo "Building Docker image for webapp..."
docker build \
    --build-arg APP_VERSION="${APP_VERSION:-1.0.0}" \
    -t "${REGISTRY:-registry.example.com}/webapp:${APP_VERSION:-1.0.0}" \
    .
echo "Deploy image built successfully."
