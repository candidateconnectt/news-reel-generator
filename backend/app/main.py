"""FastAPI app entry point."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import campaigns, webhooks, social_posts
from app.config import settings
from app.core.logging import setup_logging
from app.database import Base, engine

setup_logging()


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Dev convenience: create tables on startup if they don't exist.
    # In production, run `alembic upgrade head` instead.
    Base.metadata.create_all(bind=engine)
    # Ensure the local storage dir exists so StaticFiles can mount it.
    Path(settings.local_storage_dir).mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(
    title="Autonomous News Reel Generator",
    version="0.1.0",
    description="Backend API for the autonomous news reel generation pipeline.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve rendered MP4s at /storage/{campaign_id}/final.mp4. The render worker
# points `video_url` here when running in mock mode (no Supabase upload).
storage_path = Path(settings.local_storage_dir).resolve()
app.mount(
    "/storage",
    StaticFiles(directory=str(storage_path), check_dir=False),
    name="storage",
)

app.include_router(campaigns.router, prefix="/api", tags=["campaigns"])
app.include_router(webhooks.router, prefix="/api", tags=["webhooks"])
app.include_router(social_posts.router, prefix="/api", tags=["social_posts"])


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
