#!/bin/bash
cd "$(dirname "$0")"
echo "============================================"
echo "  PACKTWIN — EV Battery Digital Twin"
echo "  Setting up and starting the app..."
echo "============================================"
echo ""

if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python was not found on this Mac."
    echo ""
    echo "Please install Python first:"
    echo "  1. Go to https://python.org/downloads"
    echo "  2. Download and run the macOS installer"
    echo "  3. Once installed, double-click this file again"
    echo ""
    read -p "Press Enter to close..."
    exit 1
fi

echo "Installing required packages — this can take a few minutes the first time..."
pip3 install -r requirements.txt
if [ $? -ne 0 ]; then
    echo ""
    echo "Something went wrong installing packages. Scroll up to see the error."
    read -p "Press Enter to close..."
    exit 1
fi

echo ""
echo "Starting PACKTWIN..."
python3 main.py

read -p "Press Enter to close..."
