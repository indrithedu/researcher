#!/usr/bin/env bash
# =============================================================================
# JewelScope Research — run.sh
# =============================================================================
# Single command to set up and run the app.
# Safe to run multiple times — skips steps that are already done.
# =============================================================================

set -e

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"

VENV="$APP_DIR/.venv"
BROWSERS="$APP_DIR/browsers"

echo "💎 JewelScope Research"
echo "─────────────────────"

# --- Virtual environment ---
if [ ! -f "$VENV/bin/activate" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv "$VENV"
    echo ""
fi

source "$VENV/bin/activate"

# --- Dependencies ---
echo "📥 Installing Python dependencies..."
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo ""

# --- Playwright browsers ---
if [ ! -d "$BROWSERS/chromium_headless_shell-"* ] && [ ! -d "$BROWSERS/chromium-"* ]; then
    echo "🌐 Installing Playwright browsers..."
    PLAYWRIGHT_BROWSERS_PATH="$BROWSERS" python -m playwright install chromium
    echo ""
else
    echo "🌐 Playwright browsers already installed"
fi

# --- Launch ---
echo "🚀 Launching JewelScope Research..."
echo "    Open: http://localhost:8501"
echo ""
PLAYWRIGHT_BROWSERS_PATH="$BROWSERS" streamlit run main.py
