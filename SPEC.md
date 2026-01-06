# BookStack Video Service (BSVS) - Architecture Spec

A self-hosted video hosting service designed to integrate with BookStack.

## Overview

**Goal**: Standalone video service that BookStack pages can embed, with permission-aware playback and automatic transcoding.

**Requirements**:
- Use case: Documentation/tutorials (screen recordings, how-to)
- Auth: Sync with BookStack permissions
- Transcoding: Full pipeline (multi-quality, thumbnails)
- Deployment: Docker containers

---

## Architecture

```
┌─────────────────┐     ┌──────────────────────────────────────────┐
│   BookStack     │     │           BSVS Stack                     │
│                 │     │  ┌─────────────────────────────────────┐ │
│  ┌───────────┐  │     │  │         BSVS API                    │ │
│  │   Page    │◄─┼─────┼──┤  - Upload endpoint                  │ │
│  │  Editor   │  │     │  │  - Embed player endpoint            │ │
│  └───────────┘  │     │  │  - Auth validation (BookStack API)  │ │
│                 │     │  └──────────────┬──────────────────────┘ │
│  ┌───────────┐  │     │                 │                        │
│  │  Webhook  │◄─┼─────┼─────────────────┤                        │
│  │ (optional)│  │     │                 ▼                        │
│  └───────────┘  │     │  ┌─────────────────────────────────────┐ │
│                 │     │  │       Transcode Worker              │ │
└─────────────────┘     │  │  - FFmpeg pipeline                  │ │
                        │  │  - HLS/DASH generation              │ │
                        │  │  - Thumbnail extraction             │ │
                        │  └──────────────┬──────────────────────┘ │
                        │                 │                        │
                        │                 ▼                        │
                        │  ┌─────────────────────────────────────┐ │
                        │  │          Storage                    │ │
                        │  │  - Original files                   │ │
                        │  │  - Transcoded variants              │ │
                        │  │  - Thumbnails                       │ │
                        │  └─────────────────────────────────────┘ │
                        │                                          │
                        │  ┌─────────────────────────────────────┐ │
                        │  │        PostgreSQL/SQLite            │ │
                        │  │  - Video metadata                   │ │
                        │  │  - Job queue                        │ │
                        │  │  - Access tokens                    │ │
                        │  └─────────────────────────────────────┘ │
                        └──────────────────────────────────────────┘
```

---

## Technology Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Language | **Python (FastAPI)** | Familiar, fast development, FFmpeg is the real bottleneck anyway |
| Player | **Video.js** | Industry standard, HLS support, well-documented |
| Upload UX | **Web UI first, BookStack plugin later** | Simpler MVP, plugin as Phase 3 enhancement |
| Database | **SQLite → PostgreSQL** | SQLite for dev/small deployments, Postgres for production |

---

## Components

### 1. BSVS API (Core Service)

**Tech**: Python 3.11+ with FastAPI

**Endpoints**:
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/videos` | POST | Upload new video |
| `/api/videos/{id}` | GET | Video metadata |
| `/api/videos/{id}` | DELETE | Remove video |
| `/api/videos/{id}/status` | GET | Transcode status |
| `/embed/{id}` | GET | Embeddable player HTML |
| `/stream/{id}/{quality}/playlist.m3u8` | GET | HLS stream |
| `/auth/validate` | POST | Validate BookStack token |

**Auth Flow**:
1. User embeds `<iframe src="https://bsvs.local/embed/{video_id}?token={signed_token}">`
2. BSVS validates token against BookStack API or checks signed JWT
3. If valid, serves player; if not, 403

### 2. Transcode Worker

**Tech**: FFmpeg wrapped in Celery worker

**Pipeline**:
```
Original Upload
     │
     ▼
┌─────────────┐
│  Probe      │  ← Get codec, resolution, duration
└──────┬──────┘
       ▼
┌─────────────┐
│  Transcode  │  ← Generate quality variants
│  - 1080p    │
│  - 720p     │
│  - 480p     │
└──────┬──────┘
       ▼
┌─────────────┐
│  HLS Split  │  ← Segment into .ts files + .m3u8 playlist
└──────┬──────┘
       ▼
┌─────────────┐
│  Thumbnail  │  ← Extract frames at 0%, 25%, 50%, 75%
└─────────────┘
```

**Quality Presets** (configurable):
```yaml
presets:
  - name: 1080p
    height: 1080
    bitrate: 5000k
    enabled: true
  - name: 720p
    height: 720
    bitrate: 2500k
    enabled: true
  - name: 480p
    height: 480
    bitrate: 1000k
    enabled: true
```

### 3. Storage Layer

**Options** (configurable):
- Local filesystem (default)
- S3-compatible (MinIO, AWS S3, Backblaze B2)

**Structure**:
```
/data/videos/
  /{video_id}/
    /original/
      video.mp4
    /transcoded/
      /1080p/
        playlist.m3u8
        segment_000.ts
        segment_001.ts
        ...
      /720p/
        ...
    /thumbnails/
      thumb_0.jpg
      thumb_25.jpg
      ...
```

### 4. Database Schema

```sql
CREATE TABLE videos (
    id UUID PRIMARY KEY,
    title VARCHAR(255),
    description TEXT,
    original_filename VARCHAR(255),
    duration_seconds INTEGER,
    status VARCHAR(50),  -- pending, processing, ready, failed
    created_at TIMESTAMP,
    updated_at TIMESTAMP,

    -- BookStack integration
    bookstack_page_id INTEGER,      -- optional: link to specific page
    bookstack_uploader_id INTEGER,  -- who uploaded
    visibility VARCHAR(50)          -- inherit, public, private
);

CREATE TABLE video_variants (
    id UUID PRIMARY KEY,
    video_id UUID REFERENCES videos(id),
    quality VARCHAR(50),    -- 1080p, 720p, 480p
    width INTEGER,
    height INTEGER,
    bitrate INTEGER,
    file_path VARCHAR(500),
    file_size_bytes BIGINT
);

CREATE TABLE transcode_jobs (
    id UUID PRIMARY KEY,
    video_id UUID REFERENCES videos(id),
    status VARCHAR(50),     -- queued, processing, completed, failed
    progress INTEGER,       -- 0-100
    error_message TEXT,
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);
```

---

## BookStack Integration

### Option A: Embed via Attachment Workaround (No BookStack Changes)
1. User uploads video to BSVS (separate UI or CLI)
2. BSVS returns embed code: `<iframe src="...">`
3. User pastes into BookStack page using HTML block

### Option B: BookStack Plugin/Webhook (Tighter Integration)
1. Custom JavaScript snippet added to BookStack
2. Adds "Insert Video" button to editor
3. Opens BSVS upload modal
4. On complete, inserts embed code automatically

### Auth Sync Strategy

```
BookStack                          BSVS
    │                                │
    │  User views page               │
    │         │                      │
    │         ▼                      │
    │  Embed iframe loads ───────────┼──► /embed/{id}?page_id=123
    │                                │         │
    │                                │         ▼
    │  ◄─────────────────────────────┼─── GET /api/pages/123
    │                                │    (BSVS calls BookStack API)
    │  Returns page permissions ─────┼──►      │
    │                                │         ▼
    │                                │    If user can view page,
    │                                │    serve video player
    │                                │         │
    │  ◄─────────────────────────────┼─── Player HTML + signed stream URLs
```

**Config** (BSVS side):
```yaml
bookstack:
  url: https://bookstack.example.com
  api_token_id: "xxx"
  api_token_secret: "yyy"
  auth_mode: "api"  # or "jwt" for signed tokens from BookStack
```

---

## Configuration

### Environment Variables

```bash
# Core
BSVS_PORT=8080
BSVS_DATABASE_URL=postgres://user:pass@db:5432/bsvs
BSVS_SECRET_KEY=generate-random-32-bytes

# Storage
BSVS_STORAGE_TYPE=local  # or s3
BSVS_STORAGE_PATH=/data/videos
# For S3:
# BSVS_S3_ENDPOINT=https://s3.amazonaws.com
# BSVS_S3_BUCKET=my-videos
# BSVS_S3_ACCESS_KEY=xxx
# BSVS_S3_SECRET_KEY=yyy

# Transcoding
BSVS_TRANSCODE_WORKERS=2
BSVS_TRANSCODE_PRESETS=1080p,720p,480p
BSVS_MAX_UPLOAD_SIZE_MB=2048

# BookStack Integration
BSVS_BOOKSTACK_URL=https://bookstack.example.com
BSVS_BOOKSTACK_TOKEN_ID=xxx
BSVS_BOOKSTACK_TOKEN_SECRET=yyy
```

---

## Docker Compose

```yaml
version: '3.8'

services:
  bsvs-api:
    image: bsvs:latest
    build: .
    ports:
      - "8080:8080"
    environment:
      - BSVS_DATABASE_URL=postgres://bsvs:bsvs@db:5432/bsvs
      - BSVS_STORAGE_PATH=/data/videos
      - BSVS_BOOKSTACK_URL=${BOOKSTACK_URL}
      - BSVS_BOOKSTACK_TOKEN_ID=${BOOKSTACK_TOKEN_ID}
      - BSVS_BOOKSTACK_TOKEN_SECRET=${BOOKSTACK_TOKEN_SECRET}
    volumes:
      - video-data:/data/videos
    depends_on:
      - db
      - redis

  bsvs-worker:
    image: bsvs:latest
    command: celery -A bsvs.worker worker --loglevel=info
    environment:
      - BSVS_DATABASE_URL=postgres://bsvs:bsvs@db:5432/bsvs
      - BSVS_STORAGE_PATH=/data/videos
      - BSVS_REDIS_URL=redis://redis:6379/0
    volumes:
      - video-data:/data/videos
    depends_on:
      - db
      - redis

  db:
    image: postgres:16-alpine
    environment:
      - POSTGRES_USER=bsvs
      - POSTGRES_PASSWORD=bsvs
      - POSTGRES_DB=bsvs
    volumes:
      - db-data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    volumes:
      - redis-data:/data

volumes:
  video-data:
  db-data:
  redis-data:
```

---

## Implementation Phases

### Phase 1: Core MVP
- [ ] Project scaffold (Python/FastAPI)
- [ ] Video upload endpoint
- [ ] Basic FFmpeg transcoding (single quality)
- [ ] HLS streaming endpoint
- [ ] Simple embedded player (Video.js)
- [ ] SQLite database
- [ ] Docker image

### Phase 2: Full Transcoding
- [ ] Multi-quality transcoding
- [ ] Celery job queue with progress tracking
- [ ] Thumbnail generation
- [ ] Transcode presets configuration

### Phase 3: BookStack Integration
- [ ] BookStack API client
- [ ] Permission validation on embed
- [ ] Signed URL generation
- [ ] Optional: BookStack editor plugin (JS snippet)

### Phase 4: Production Hardening
- [ ] S3 storage backend
- [ ] PostgreSQL support
- [ ] Rate limiting
- [ ] Upload resumption (tus protocol)
- [ ] Admin UI for video management
- [ ] Metrics/monitoring endpoints

---

## File Structure

```
bookstack-video-service/
├── bsvs/
│   ├── __init__.py
│   ├── main.py              # FastAPI app entrypoint
│   ├── config.py            # Pydantic settings
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes/
│   │   │   ├── videos.py    # Upload, list, delete
│   │   │   ├── embed.py     # Player embed endpoint
│   │   │   └── stream.py    # HLS streaming
│   │   └── deps.py          # Dependencies (auth, db)
│   ├── worker/
│   │   ├── __init__.py
│   │   ├── celery_app.py    # Celery configuration
│   │   └── tasks.py         # Transcode tasks
│   ├── transcode/
│   │   ├── __init__.py
│   │   ├── ffmpeg.py        # FFmpeg wrapper
│   │   └── presets.py       # Quality presets
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── base.py          # Abstract storage interface
│   │   ├── local.py         # Local filesystem
│   │   └── s3.py            # S3-compatible storage
│   ├── bookstack/
│   │   ├── __init__.py
│   │   └── client.py        # BookStack API client
│   └── db/
│       ├── __init__.py
│       ├── models.py        # SQLAlchemy models
│       └── crud.py          # Database operations
├── web/
│   ├── templates/
│   │   ├── player.html      # Video.js embed
│   │   └── upload.html      # Upload UI
│   └── static/
│       ├── css/
│       └── js/
├── tests/
│   ├── test_api.py
│   ├── test_transcode.py
│   └── conftest.py
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
├── pyproject.toml           # Dependencies (uv/poetry)
├── .env.example
└── README.md
```

## Dependencies

```toml
[project]
name = "bsvs"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.109.0",
    "uvicorn[standard]>=0.27.0",
    "python-multipart>=0.0.6",
    "sqlalchemy>=2.0.0",
    "alembic>=1.13.0",
    "celery[redis]>=5.3.0",
    "ffmpeg-python>=0.2.0",
    "boto3>=1.34.0",
    "httpx>=0.26.0",
    "pydantic-settings>=2.1.0",
    "python-jose>=3.3.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-asyncio>=0.23.0",
    "httpx>=0.26.0",
    "ruff>=0.1.0",
]
```
