#!/bin/bash
# Deploy script for goswami-new project
# Usage: ./deploy.sh [--restore-db]

set -e

echo "=========================================="
echo "Deploying goswami-new project"
echo "=========================================="
echo ""

# Pull latest changes
echo "[1/6] Pulling latest changes..."
git pull origin main || git pull origin master || echo "Git pull skipped (not a git repo or no remote)"

# Stop existing containers
echo ""
echo "[2/6] Stopping existing containers..."
docker compose down || true

# Pull docker images (if using remote images)
echo ""
echo "[3/6] Pulling docker images..."
docker compose pull || true

# Build containers
echo ""
echo "[4/6] Building containers..."
docker compose build --no-cache

# Start containers
echo ""
echo "[5/6] Starting containers..."
docker compose up -d

# Wait for database to be ready
echo ""
echo "[6/6] Waiting for database..."
sleep 5
docker compose exec -T goswami-ru-db pg_isready -U postgres || {
    echo "Waiting more for database..."
    sleep 10
}

# Run migrations
echo ""
echo "Running migrations..."
docker compose exec -T web python manage.py migrate --run-syncdb || true

# Collect static files
echo ""
echo "Collecting static files..."
docker compose exec -T web python manage.py collectstatic --noinput || true

# Restore database if requested
if [ "$1" == "--restore-db" ]; then
    echo ""
    echo "Restoring database from dump..."
    ./restore_db.sh
fi

echo ""
echo "=========================================="
echo "Deploy completed!"
echo "=========================================="
echo ""
echo "Services:"
echo "  - Web: http://localhost:8000"
echo "  - DB:  localhost:5431"
echo ""
echo "Logs: docker compose logs -f"
echo "Stop:  docker compose down"
