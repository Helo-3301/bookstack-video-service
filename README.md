# BookStack Video Service (BSVS)

Self-hosted video hosting service with BookStack integration.

## Features

- Video upload and HLS transcoding
- Multi-quality streaming (480p, 720p, 1080p)
- Thumbnail generation
- Celery-based async processing
- BookStack permission integration

## Quick Start

```bash
cd dev-env
docker compose up -d
```

Then access:
- BSVS API: http://localhost:8080
- BookStack: http://localhost:6875

