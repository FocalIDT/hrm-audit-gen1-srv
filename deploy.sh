#!/bin/bash

set -e

echo "Stashing local changes (if any)..."
git stash || true

echo "Pulling latest changes from dev branch..."
git checkout dev
git pull origin dev

echo "Stopping running containers..."
docker compose down

echo "Cleaning old images..."
docker image prune -f

echo "Starting up with Docker Compose..."
docker compose up --build -d

echo "Deployment completed successfully!"
