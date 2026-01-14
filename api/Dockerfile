# Charm Email OS API Dockerfile - Ultra Minimal
FROM python:3.11-slim

WORKDIR /app

# Install only what we need
RUN pip install --no-cache-dir fastapi uvicorn

# Copy only main.py
COPY main.py .

# Expose port
EXPOSE 8000

# Run directly
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
