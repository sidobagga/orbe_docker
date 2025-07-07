# Multi-stage build for LBO API service with all dependencies
# Build stage
FROM python:3.11-slim as builder

# Set build arguments
ARG BUILDPLATFORM
ARG TARGETPLATFORM

# Install system dependencies needed for building
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Set work directory
WORKDIR /app

# Copy requirements first to leverage Docker layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Production stage
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user for security
RUN groupadd -r lbouser && useradd -r -g lbouser lbouser

# Set work directory
WORKDIR /app

# Copy Python dependencies from builder stage
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application files in dependency order
# Core dependencies first
COPY defaults.py .
COPY models.py .
COPY schemas.py .
COPY sql_helpers.py .

# Services directory
COPY services/ services/

# Main application
COPY lbo_api.py .

# Change ownership of the app directory to the non-root user
RUN chown -R lbouser:lbouser /app

# Switch to non-root user
USER lbouser

# Expose port
EXPOSE 8000

# Health check endpoint (we'll need to add this to lbo_api.py)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Command to run the application
CMD ["uvicorn", "lbo_api:app", "--host", "0.0.0.0", "--port", "8000"]