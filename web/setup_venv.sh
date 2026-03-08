#!/bin/bash
# Setup script for local development with virtual environment

set -e

echo "=== Setting up virtual environment for goswami.ru ==="

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 is not installed"
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip

# Install requirements
echo "Installing requirements..."
pip install -r requirements.txt

echo ""
echo "=== Setup complete! ==="
echo ""
echo "To activate environment, run:"
echo "  source venv/bin/activate"
echo ""
echo "To run Django development server:"
echo "  ./run_local.sh"
echo ""
