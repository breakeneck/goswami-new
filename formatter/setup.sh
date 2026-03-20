#!/bin/bash
# Setup script for formatter environment

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"

echo "Creating Python virtual environment in $VENV_DIR..."
python3 -m venv "$VENV_DIR"

echo "Upgrading pip..."
"$VENV_DIR/bin/pip" install --upgrade pip

echo "Installing dependencies..."
"$VENV_DIR/bin/pip" install -r "$SCRIPT_DIR/requirements.txt"

echo "Setup complete!"
echo ""
echo "To activate the environment, run:"
echo "  source $VENV_DIR/bin/activate"
echo ""
echo "Or run the script directly with:"
echo "  $VENV_DIR/bin/python $SCRIPT_DIR/format.py [command]"
