"""BSVS FastAPI Application."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from bsvs.config import get_settings
from bsvs.db import init_db
from bsvs.api.routes import videos, embed, stream, metrics, auth
from bsvs.api.ratelimit import limiter

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if get_settings().debug else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    settings = get_settings()

    # Ensure storage directory exists
    settings.storage_path.mkdir(parents=True, exist_ok=True)

    # Ensure data directory for SQLite exists
    if "sqlite" in settings.database_url:
        db_path = Path(settings.database_url.split("///")[-1])
        db_path.parent.mkdir(parents=True, exist_ok=True)

    # Initialize database
    await init_db()

    logger.info(f"BSVS starting on port {settings.port}")
    logger.info(f"Storage path: {settings.storage_path}")
    logger.info(f"Transcode presets: {settings.presets_list}")

    yield

    logger.info("BSVS shutting down")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="BookStack Video Service",
        description="Self-hosted video hosting with BookStack integration",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Set up CORS for BookStack integration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Set up rate limiting
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # Mount static files
    static_path = Path(__file__).parent.parent / "web" / "static"
    if static_path.exists():
        app.mount("/static", StaticFiles(directory=static_path), name="static")

    # Include routers
    app.include_router(videos.router, prefix="/api/videos", tags=["videos"])
    app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
    app.include_router(embed.router, prefix="/embed", tags=["embed"])
    app.include_router(stream.router, prefix="/stream", tags=["stream"])
    app.include_router(metrics.router, prefix="/api", tags=["metrics"])

    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "healthy", "version": "0.1.0"}

    # Web UI routes
    templates_path = Path(__file__).parent.parent / "web" / "templates"
    if templates_path.exists():
        templates = Jinja2Templates(directory=templates_path)

        @app.get("/", response_class=HTMLResponse)
        async def upload_ui(request: Request):
            """Serve the upload UI."""
            return templates.TemplateResponse("upload.html", {"request": request})

        @app.get("/admin", response_class=HTMLResponse)
        async def admin_ui(request: Request):
            """Serve the admin UI for video management."""
            return templates.TemplateResponse("admin.html", {"request": request})

    return app


app = create_app()


def main():
    """Run the application with uvicorn."""
    import uvicorn
    settings = get_settings()
    uvicorn.run(
        "bsvs.main:app",
        host="0.0.0.0",
        port=settings.port,
        reload=settings.debug,
    )


if __name__ == "__main__":
    main()
