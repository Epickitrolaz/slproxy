# SLProxy Dockerfile
# Lightweight Python 3.12 base image
FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SLPROXY_DATA_DIR=/data \
    SLPROXY_HOST=0.0.0.0 \
    SLPROXY_PORT=8080

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# Create persistent data volume for SQLite and user plugins
RUN mkdir -p /data
VOLUME ["/data"]

# Expose WebUI and API port
EXPOSE 8080

# Launch SLProxy server
CMD ["uvicorn", "slproxy.main:app", "--host", "0.0.0.0", "--port", "8080"]
