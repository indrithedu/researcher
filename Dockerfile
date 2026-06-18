# =============================================================================
# JewelScope Research — Dockerfile (v2.0 Unified)
# =============================================================================
FROM python:3.12-slim AS base

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PLAYWRIGHT_BROWSERS_PATH=/app/browsers

# Set work directory
WORKDIR /app

# Install system dependencies
# Unified list for Playwright, OpenCV, and WeasyPrint
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    # OpenCV deps
    libgl1 \
    libglib2.0-0 \
    # WeasyPrint / Cairo deps
    libpango-1.0-0 \
    libharfbuzz0b \
    libpangoft2-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    # Scrapy/Scrapers deps
    libxml2-dev \
    libxslt1-dev \
    shared-mime-info \
    # Playwright browser deps
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
    libasound2 \
    libatspi2.0-0 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browser (chromium)
RUN PLAYWRIGHT_BROWSERS_PATH=/app/browsers python -m playwright install chromium && \
    rm -rf /app/browsers/chromium_headless_shell-*/LOCAL_APPS \
           /app/browsers/chromium_headless_shell-*/locales

# Copy application code
COPY . .

# Ensure necessary directories exist
RUN mkdir -p databases reports scraper_sources static utils/temp_images

# Expose Streamlit port
EXPOSE 3000

# --- Health check ---
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:3000')" || exit 1

# Run the app
CMD ["streamlit", "run", "main.py", "--server.address=0.0.0.0", "--server.port=3000"]
