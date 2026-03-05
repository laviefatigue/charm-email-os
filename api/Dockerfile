# Charm Email OS API Dockerfile
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies for asyncpg and pg_dump (for admin db-export)
# PostgreSQL 18 client required to match production server version
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    gnupg \
    curl \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc | gpg --dearmor -o /usr/share/keyrings/postgresql-keyring.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/postgresql-keyring.gpg] http://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client-18 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies FROM requirements.txt
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy ALL application code
COPY . .

# Expose port
EXPOSE 8000

# Run uvicorn directly (avoid shell script CRLF issues)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
