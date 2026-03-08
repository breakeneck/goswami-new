#!/bin/bash
# Create superuser for local development

set -e

# Activate virtual environment
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Load environment variables from .env file
if [ -f ".env" ]; then
    export $(grep -v '^#' .env | xargs)
fi

export DB_HOST=${DB_HOST:-localhost}
export DB_PORT=${DB_PORT:-5431}

echo "Creating superuser..."
python manage.py createsuperuser
