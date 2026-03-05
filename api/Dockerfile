# Charm Email OS API Dockerfile
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies for asyncpg
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
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
