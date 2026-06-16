# =============================================================================
# JewelScope Research — Dockerfile
# =============================================================================
# Multi-stage build for a small, self-contained container.
# Usage:
#   docker build -t jewelscope-research .
#   docker run -p 8501:8501 jewelscope-research
#
# To persist data across restarts:
#   docker run -p 8501:8501 \
#     -v /path/to/databases:/app/databases \
#     -v /path/to/reports:/app/reports \
#     jewelscope-research
# =============================================================================

FROM python:3.12-slim AS base

# Install system deps needed for Playwright browsers
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libexpat1 \
    libxcb1 \
    libxkbcommon0 \
    libx11-6 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libatspi2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browser (chromium headless shell is enough)
RUN PLAYWRIGHT_BROWSERS_PATH=/app/browsers python -m playwright install chromium && \
    rm -rf /app/browsers/chromium_headless_shell-*/LOCAL_APPS \
           /app/browsers/chromium_headless_shell-*/locales

# Copy application code
COPY . .
RUN mkdir -p databases reports

# Don't ship the .venv or git artifacts
RUN rm -rf .venv .git

# Expose Streamlit port
EXPOSE 8501

# --- Health check ---
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501')" || exit 1

# Run the app
ENV PLAYWRIGHT_BROWSERS_PATH=/app/browsers
CMD ["streamlit", "run", "main.py", "--server.address=0.0.0.0", "--server.port=8501"]