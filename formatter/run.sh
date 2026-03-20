#!/bin/bash
# Run formatter script with optional language parameter
# Usage: ./run.sh [list|status|run] [--lang=RUS|ENG]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"

# Check if venv exists
if [ ! -d "$VENV_DIR" ]; then
    echo "Virtual environment not found. Running setup.sh first..."
    bash "$SCRIPT_DIR/setup.sh"
fi

# Pass all arguments to Python script
exec "$VENV_DIR/bin/python" "$SCRIPT_DIR/format.py" "$@"
