#!/bin/bash
# Setup script for Whisper transcriber

set -e

cd "$(dirname "$0")"

# Create virtual environment if not exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Run database migration
echo "Running database migration..."
psql -h localhost -p 5431 -U postgres -d goswami.ru -f migrations/001_add_transcribe_fields.sql

echo ""
echo "Setup complete!"
echo ""
echo "Usage:"
echo "  source venv/bin/activate"
echo "  python transcribe.py list --lang=RUS     # List files for transcription"
echo "  python transcribe.py run --lang=RUS      # Run transcription"
echo "  python transcribe.py status              # Show status"
