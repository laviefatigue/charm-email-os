# Charm Email OS API Dockerfile
# Includes Hypertide automation modules for inbox provisioning
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies for asyncpg and Playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    # Playwright dependencies
    wget \
    gnupg \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    libatspi2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy API requirements and install
COPY api/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Install Hypertide automation dependencies
RUN pip install --no-cache-dir \
    playwright>=1.40.0 \
    structlog>=23.0.0 \
    typer>=0.9.0 \
    rich>=13.0.0 \
    gspread>=6.0.0 \
    google-auth>=2.0.0

# Install Playwright browsers (Chromium only for smaller image)
RUN playwright install chromium
RUN playwright install-deps chromium

# Copy API application code
COPY api/ .

# Copy migrations directory for automatic migration runner
COPY migrations/ /migrations/

# Copy Hypertide automation to expected path
# The import code expects: Path(__file__).parent.parent.parent / "Hypertide" / "automation" / "src"
# In container: /app/routes/inbox_purchasing.py -> parent.parent.parent = /
# So Hypertide should be at /Hypertide/automation/src
COPY Hypertide/automation/src/hypertide_automation /Hypertide/automation/src/hypertide_automation

# Create __init__.py files for proper module resolution
RUN touch /Hypertide/__init__.py \
    && touch /Hypertide/automation/__init__.py \
    && touch /Hypertide/automation/src/__init__.py

# Expose port
EXPOSE 8000

# Run uvicorn directly
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
