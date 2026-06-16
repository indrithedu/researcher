# JewelScope Research - Dockerfile
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PLAYWRIGHT_BROWSERS_PATH=/app/browsers

# Set work directory
WORKDIR /app

# Install system dependencies
# These include dependencies for OpenCV, WeasyPrint, and basic build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libgl1 \
    libglib2.0-0 \
    libpango-1.0-0 \
    libharfbuzz0b \
    libpangoft2-1.0-0 \
    libpangocairo-1.0-0 \
    libxml2-dev \
    libxslt1-dev \
    shared-mime-info \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers and their system dependencies
RUN playwright install chromium
RUN playwright install-deps chromium

# Copy project files
COPY . .

# Ensure directories exist and have correct permissions
RUN mkdir -p databases reports scraper_sources static utils/temp_images

# Expose Streamlit port
EXPOSE 8501

# Default entrypoint is Streamlit
CMD ["streamlit", "run", "main.py", "--server.address=0.0.0.0"]
