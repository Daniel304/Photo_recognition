import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .api import admin, faces, people, photos, review, search
from .config import settings
from .database import init_db
from .indexer import Indexer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("photo-recognition")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    log.info("DB initialized at %s", settings.db_path)
    log.info("PHOTO_ROOT=%s DATA_DIR=%s", settings.photo_root, settings.data_dir)
    Indexer.get().start_auto_loop()
    yield
    Indexer.get().shutdown()


app = FastAPI(
    title="Photo Recognition",
    description="Recursive photo indexer with face recognition for Synology NAS.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(admin.router)
app.include_router(photos.router)
app.include_router(faces.router)
app.include_router(people.router)
app.include_router(review.router)
app.include_router(search.router)


WEB_DIR = Path(__file__).parent / "web"
if WEB_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


@app.get("/", include_in_schema=False)
def root_index():
    idx = WEB_DIR / "index.html"
    if idx.exists():
        return FileResponse(idx)
    return RedirectResponse("/docs")


@app.get("/healthz", include_in_schema=False)
def healthz():
    return {"ok": True}
