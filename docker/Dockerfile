# BSVS - BookStack Video Service

FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies (FFmpeg is required)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy application code and build files
COPY pyproject.toml README.md ./
COPY bsvs/ /app/bsvs/
COPY web/ /app/web/

# Install Python dependencies
RUN pip install --no-cache-dir .

# Create data directory
RUN mkdir -p /data/videos

# Set environment
ENV PYTHONUNBUFFERED=1
ENV BSVS_STORAGE_PATH=/data/videos
ENV BSVS_DATABASE_URL=sqlite+aiosqlite:///data/bsvs.db

EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8080/health')" || exit 1

# Run the application
CMD ["python", "-m", "bsvs.main"]
