#!/usr/bin/env bash
set -e

echo "=== Casino Bot Setup ==="

# --- System dependencies (Homebrew) ---
if ! command -v brew &>/dev/null; then
  echo "Homebrew not found. Installing..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  # Add brew to PATH for the rest of this script
  eval "$(/opt/homebrew/bin/brew shellenv 2>/dev/null || /usr/local/bin/brew shellenv 2>/dev/null)"
fi

if ! command -v tesseract &>/dev/null; then
  echo "Installing Tesseract OCR..."
  brew install tesseract
else
  echo "Tesseract already installed: $(tesseract --version 2>&1 | head -1)"
fi

# --- Python dependencies ---
echo "Installing Python dependencies..."
pip3 install -r requirements.txt

echo ""
echo "=== Setup complete ==="
echo ""
echo "Remember to grant macOS permissions to your terminal app:"
echo "  1. Accessibility  — System Settings > Privacy & Security > Accessibility"
echo "  2. Screen Recording — System Settings > Privacy & Security > Screen Recording"
