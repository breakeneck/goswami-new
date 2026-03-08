#!/bin/bash
# Restore PostgreSQL database from dump file
# Usage: ./restore_db.sh [dump_file]

set -e

DUMP_FILE="$1"
CONTAINER_NAME="goswami-new-goswami-ru-db-1"
DB_NAME="goswami.ru"
DB_USER="postgres"

echo "Restoring database from: $DUMP_FILE"
echo "Container: $CONTAINER_NAME"
echo ""

# Check if container is running
if ! docker ps | grep -q "$CONTAINER_NAME"; then
    echo "Error: Container $CONTAINER_NAME is not running"
    echo "Start it first with: docker compose up -d"
    exit 1
fi

# Check if dump file exists
if [ ! -f "$DUMP_FILE" ]; then
    echo "Error: Dump file not found: $DUMP_FILE"
    exit 1
fi

echo "Dropping existing connections..."
docker exec -i "$CONTAINER_NAME" psql -U "$DB_USER" -d postgres -c \
    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$DB_NAME' AND pid <> pg_backend_pid();" || true

echo "Dropping database..."
docker exec -i "$CONTAINER_NAME" psql -U "$DB_USER" -d postgres -c \
    "DROP DATABASE IF EXISTS $DB_NAME;" || true

echo "Creating database..."
docker exec -i "$CONTAINER_NAME" psql -U "$DB_USER" -d postgres -c \
    "CREATE DATABASE $DB_NAME;"

echo "Restoring from dump..."
cat "$DUMP_FILE" | docker exec -i "$CONTAINER_NAME" psql -U "$DB_USER" -d "$DB_NAME"

echo ""
echo "Database restored successfully!"
echo ""
echo "Note: You may need to run migrations again:"
echo "  docker compose exec web python manage.py migrate --run-syncdb"
