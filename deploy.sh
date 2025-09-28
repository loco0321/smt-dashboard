#!/bin/bash
set -e  # stop on first error

APP_DIR="/home/smt/smt-dashboard"
COMPOSE="docker compose -f $APP_DIR/docker-compose.yml"

echo "=== Entering project directory ==="
cd $APP_DIR

echo "=== Pulling latest code from git ==="
git fetch --all
git reset --hard origin/main   # change 'main' if your branch is different

# Check if requirements.txt or Dockerfile changed
echo "=== Checking for changes in requirements.txt or Dockerfile ==="
if git diff --name-only HEAD@{1} HEAD | grep -E "(requirements.txt|Dockerfile)"; then
    echo "requirements.txt or Dockerfile changed, rebuilding image with no cache..."
    $COMPOSE build --no-cache django
else
    echo "No changes in requirements.txt or Dockerfile, skipping build..."
fi

echo "=== Applying database migrations ==="
$COMPOSE run --rm django python manage.py migrate --noinput

echo "=== Collecting static files ==="
$COMPOSE run --rm django python manage.py collectstatic --noinput

echo "=== Updating containers ==="
$COMPOSE down
$COMPOSE up -d

echo "=== Reloading Nginx ==="
sudo systemctl reload nginx

echo "=== Deployment finished successfully 🚀 ==="
