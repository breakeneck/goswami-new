#!/bin/bash
# Run Django development server locally with virtual environment

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if venv exists
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}Virtual environment not found. Running setup...${NC}"
    ./setup_venv.sh
fi

# Activate virtual environment
echo -e "${GREEN}Activating virtual environment...${NC}"
source venv/bin/activate

# Check if .env file exists, if not - create from example
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}Creating .env file from example...${NC}"
    cp .env.example .env
    echo -e "${YELLOW}Please edit .env file with your settings if needed${NC}"
fi

# Export environment variables from .env file
if [ -f ".env" ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Default database host for local development (localhost instead of docker container)
export DB_HOST=${DB_HOST:-localhost}
export DB_PORT=${DB_PORT:-5431}

echo -e "${GREEN}Using database: ${DB_HOST}:${DB_PORT}${NC}"

# Run migrations if needed
echo -e "${GREEN}Running migrations...${NC}"
python manage.py migrate --run-syncdb

# Collect static files
echo -e "${GREEN}Collecting static files...${NC}"
python manage.py collectstatic --noinput 2>/dev/null || true

echo ""
echo -e "${GREEN}=== Starting Django development server ===${NC}"
echo -e "${GREEN}Site: http://localhost:8008${NC}"
echo -e "${GREEN}Admin: http://localhost:8008/admin${NC}"
echo ""

# Run server
python manage.py runserver 0.0.0.0:8008
