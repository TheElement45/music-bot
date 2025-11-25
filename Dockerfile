# Build stage
FROM python:3.13-slim as builder

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

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/deps

WORKDIR /app

# Install runtime dependencies (ffmpeg)
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Copy installed python dependencies from builder
COPY --from=builder /app/deps /app/deps

# Copy application code
COPY . .

# Run the Bot
CMD ["python", "main.py"]