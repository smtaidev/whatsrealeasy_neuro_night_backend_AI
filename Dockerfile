# Multi-stage build for optimized image size
FROM python:3.11-slim as builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy and install requirements
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Production stage
FROM python:3.11-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user
RUN useradd --create-home --shell /bin/bash app

# Copy installed packages from builder
COPY --from=builder /root/.local /home/app/.local
ENV PATH=/home/app/.local/bin:$PATH

WORKDIR /app

# Copy application code
COPY --chown=app:app app/ ./app/
COPY --chown=app:app inbound_service/ ./inbound_service/
COPY --chown=app:app outbound_service/ ./outbound_service/

# Copy startup script
COPY --chown=app:app docker-entrypoint.sh ./
RUN chmod +x docker-entrypoint.sh

# Switch to non-root user
USER app

# Build argument to determine which service to run
ARG SERVICE_TYPE=inbound
ENV SERVICE_TYPE=${SERVICE_TYPE}

# Expose ports (both services use different ports)
EXPOSE 8000 8500

# Health check
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=2 \
    CMD curl -f http://localhost:8000/ || curl -f http://localhost:8500/ || exit 1

# Use entrypoint script
ENTRYPOINT ["./docker-entrypoint.sh"]
