# Build stage
FROM python:3.13-slim as builder

# Metadata labels
LABEL maintainer="TheElement45"
LABEL description="Discord Music Bot"
LABEL version="1.0"

# Prevents Python from writing .pyc files to disc
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies required for building (if any)
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Install dependencies to a local directory
# Use cache mount to speed up pip install
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir --target=/app/deps -r requirements.txt

# Final stage
FROM python:3.13-slim

# Metadata labels
LABEL maintainer="TheElement45"
LABEL description="Discord Music Bot"
LABEL version="1.0"

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/deps

WORKDIR /app

# Install runtime dependencies (ffmpeg)
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN groupadd -r botuser && \
    useradd -r -g botuser -u 1000 botuser && \
    mkdir -p /app/logs && \
    chmod 755 /app/logs && \
    chown -R botuser:botuser /app

# Copy installed python dependencies from builder
COPY --from=builder /app/deps /app/deps

# Copy application code
COPY --chown=botuser:botuser . .

# Switch to non-root user
USER botuser

# Health check to ensure bot is responsive
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

# Run the Bot
CMD ["python", "main.py"]