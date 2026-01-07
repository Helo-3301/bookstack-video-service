# BookStack Video Service (BSVS)

Self-hosted video hosting service designed to integrate with BookStack.

## Features

- Video upload with drag-and-drop UI
- Automatic HLS transcoding (480p, 720p, 1080p)
- Adaptive bitrate streaming
- Thumbnail generation
- BookStack editor integration (insert videos directly)
- Header menu for quick access to video management
- Rate limiting and metrics endpoints
- S3-compatible storage support

## Installation

### Quick Install (Recommended)

Run the installer script to set up BSVS alongside your existing BookStack:

```bash
git clone https://github.com/Helo-3301/bookstack-video-service.git
cd bookstack-video-service
./install.sh
```

The installer will:
1. Prompt for your BookStack URL and BSVS settings
2. Create Docker Compose configuration
3. Start the BSVS services
4. Output the BookStack configuration needed

### Manual Installation

1. **Deploy BSVS Stack**

```bash
cd production
docker compose up -d
```

2. **Configure BookStack Environment**

Add to your BookStack `.env` file:

```bash
ALLOWED_IFRAME_HOSTS="http://your-bsvs-host:8080"
ALLOWED_IFRAME_SOURCES="http://your-bsvs-host:8080"
```

3. **Clear BookStack Cache**

```bash
# Docker
docker exec bookstack php /app/www/artisan config:clear
docker exec bookstack php /app/www/artisan cache:clear

# Native install
cd /path/to/bookstack && php artisan config:clear && php artisan cache:clear
```

4. **Add Plugin to BookStack**

Go to BookStack Admin → Settings → Customization → Custom HTML Head Content:

```html
<!-- BSVS Video Integration -->
<script>window.BSVS_URL = 'http://your-bsvs-host:8080';</script>
<script src="http://your-bsvs-host:8080/static/js/bookstack-plugin.js"></script>
```

## Usage

### Uploading Videos

1. Click "🎬 Videos" in the BookStack header
2. Select "Upload Video"
3. Drag and drop or browse for a video file
4. Wait for transcoding to complete

### Embedding in Pages

1. Edit a BookStack page
2. Click the 🎬 button in the editor toolbar
3. Select from Video Library or upload new
4. Click "Insert Video"

### Direct Access

- **Upload UI**: http://your-bsvs-host:8080/
- **Admin UI**: http://your-bsvs-host:8080/admin
- **API**: http://your-bsvs-host:8080/api/videos
- **Health Check**: http://your-bsvs-host:8080/health

## Development

### Initial Setup

```bash
# Clone and enter directory
git clone https://github.com/Helo-3301/bookstack-video-service.git
cd bookstack-video-service

# Install pre-commit hooks (recommended)
pip install pre-commit
pre-commit install

# Set up dev environment
cd dev-env
cp .env.example .env

# Generate secrets (edit .env with these values)
openssl rand -base64 32  # For BSVS_SECRET_KEY
docker compose run --rm bookstack php artisan key:generate --show  # For BOOKSTACK_APP_KEY

# Start services
docker compose up -d
```

### Access Points
- **BSVS**: http://localhost:8080
- **BookStack**: http://localhost:6875 (admin@admin.com / password)

### Pre-commit Hooks

This repo uses pre-commit hooks to prevent secrets from being committed:

```bash
# Run manually on all files
pre-commit run --all-files

# Skip hooks (not recommended)
git commit --no-verify
```

## Security

### Secret Management

- **Never commit secrets** - Use environment variables
- **Use `.env.example`** - Copy to `.env` and fill in values
- **Pre-commit hooks** - Gitleaks scans for secrets before commit
- **Rotate compromised secrets** - If a secret is exposed, rotate immediately

### Required Secrets

| Secret | Where | How to Generate |
|--------|-------|-----------------|
| `BOOKSTACK_APP_KEY` | BookStack | `php artisan key:generate --show` |
| `BSVS_SECRET_KEY` | BSVS | `openssl rand -base64 32` |
| API Tokens | BookStack UI | User Profile → API Tokens |

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `BSVS_PORT` | 8080 | API port |
| `BSVS_DATABASE_URL` | sqlite:///data/bsvs.db | Database connection |
| `BSVS_STORAGE_PATH` | /data/videos | Video storage path |
| `BSVS_REDIS_URL` | redis://localhost:6379/0 | Redis for Celery |
| `BSVS_TRANSCODE_PRESETS` | 1080p,720p,480p | Quality variants |
| `BSVS_MAX_UPLOAD_SIZE_MB` | 2048 | Max upload size |
| `BSVS_BOOKSTACK_URL` | - | BookStack base URL |
| `BSVS_SECRET_KEY` | - | Secret key for signing |

## Architecture

```
┌─────────────────┐     ┌──────────────────────────────────────────┐
│   BookStack     │     │           BSVS Stack                     │
│                 │     │  ┌─────────────────────────────────────┐ │
│  ┌───────────┐  │     │  │         BSVS API (FastAPI)          │ │
│  │   Page    │◄─┼─────┼──┤  - Upload, embed, stream endpoints  │ │
│  │  Editor   │  │     │  └──────────────┬──────────────────────┘ │
│  └───────────┘  │     │                 │                        │
│       +         │     │                 ▼                        │
│  🎬 Plugin JS   │     │  ┌─────────────────────────────────────┐ │
│                 │     │  │    Celery Worker (FFmpeg)           │ │
└─────────────────┘     │  │  - HLS transcoding                  │ │
                        │  │  - Multi-quality variants           │ │
                        │  └──────────────┬──────────────────────┘ │
                        │                 │                        │
                        │                 ▼                        │
                        │  ┌──────────┐  ┌──────────┐              │
                        │  │  Redis   │  │ Storage  │              │
                        │  │ (Queue)  │  │ (Videos) │              │
                        │  └──────────┘  └──────────┘              │
                        └──────────────────────────────────────────┘
```

## License

MIT
