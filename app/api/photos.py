from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..image_utils import thumb_rel_path
from ..models import Face, Photo, PhotoAlbum, PhotoEvent
from .deps import require_api_key


class RatingBody(BaseModel):
    rating: int = Field(ge=0, le=5)


class FavoriteBody(BaseModel):
    favorite: bool

router = APIRouter(prefix="/api/photos", tags=["photos"], dependencies=[Depends(require_api_key)])


@router.get("")
def list_photos(
    q: str | None = None,
    person_id: int | None = None,
    album_id: int | None = None,
    event_id: int | None = None,
    favorite: bool | None = None,
    min_rating: int | None = Query(None, ge=0, le=5),
    limit: int = Query(60, ge=1, le=500),
    offset: int = Query(0, ge=0),
    order: str = Query("taken_desc"),
    db: Session = Depends(get_db),
):
    query = db.query(Photo).filter(Photo.missing.is_(False))
    if q:
        query = query.filter(Photo.path.like(f"%{q}%"))
    if person_id is not None:
        query = query.join(Face, Face.photo_id == Photo.id).filter(Face.person_id == person_id).distinct()
    if album_id is not None:
        query = query.join(PhotoAlbum, PhotoAlbum.photo_id == Photo.id).filter(PhotoAlbum.album_id == album_id)
    if event_id is not None:
        query = query.join(PhotoEvent, PhotoEvent.photo_id == Photo.id).filter(PhotoEvent.event_id == event_id)
    if favorite is True:
        query = query.filter(Photo.favorite.is_(True))
    if min_rating is not None:
        query = query.filter(Photo.rating >= min_rating)

    if order == "taken_asc":
        query = query.order_by(Photo.taken_at.asc().nullslast(), Photo.indexed_at.asc())
    elif order == "indexed_desc":
        query = query.order_by(Photo.indexed_at.desc())
    else:
        query = query.order_by(Photo.taken_at.desc().nullslast(), Photo.indexed_at.desc())

    total = query.with_entities(func.count(Photo.id)).order_by(None).scalar() or 0
    rows = query.offset(offset).limit(limit).all()

    items = []
    for p in rows:
        items.append({
            "id": p.id,
            "path": p.path,
            "filename": Path(p.path).name,
            "width": p.width,
            "height": p.height,
            "taken_at": p.taken_at.isoformat() if p.taken_at else None,
            "face_count": len(p.faces),
            "favorite": bool(p.favorite),
            "rating": p.rating or 0,
        })
    return {"total": total, "offset": offset, "limit": limit, "items": items}


@router.get("/{photo_id}")
def get_photo(photo_id: int, db: Session = Depends(get_db)):
    p = db.query(Photo).get(photo_id)
    if not p:
        raise HTTPException(404, "Photo not found")
    faces = []
    for f in p.faces:
        faces.append({
            "id": f.id,
            "person_id": f.person_id,
            "person_name": f.person.name if f.person else None,
            "bbox": [f.bbox_x, f.bbox_y, f.bbox_w, f.bbox_h],
            "det_score": f.det_score,
            "confirmed": f.confirmed,
            "hidden": f.hidden,
        })
    return {
        "id": p.id,
        "path": p.path,
        "filename": Path(p.path).name,
        "width": p.width,
        "height": p.height,
        "taken_at": p.taken_at.isoformat() if p.taken_at else None,
        "indexed_at": p.indexed_at.isoformat() if p.indexed_at else None,
        "favorite": bool(p.favorite),
        "rating": p.rating or 0,
        "gps_lat": p.gps_lat,
        "gps_lon": p.gps_lon,
        "faces": faces,
    }


@router.post("/{photo_id}/favorite")
def set_favorite(photo_id: int, body: FavoriteBody, db: Session = Depends(get_db)):
    p = db.query(Photo).get(photo_id)
    if not p:
        raise HTTPException(404)
    p.favorite = body.favorite
    db.commit()
    return {"ok": True, "favorite": p.favorite}


@router.post("/{photo_id}/rating")
def set_rating(photo_id: int, body: RatingBody, db: Session = Depends(get_db)):
    p = db.query(Photo).get(photo_id)
    if not p:
        raise HTTPException(404)
    p.rating = body.rating
    db.commit()
    return {"ok": True, "rating": p.rating}


@router.get("/{photo_id}/thumb")
def get_thumb(photo_id: int, db: Session = Depends(get_db)):
    p = db.query(Photo).get(photo_id)
    if not p:
        raise HTTPException(404)
    path = settings.thumbs_dir / thumb_rel_path(photo_id)
    if not path.exists():
        raise HTTPException(404, "Thumbnail not generated yet")
    return FileResponse(path, media_type="image/jpeg")


@router.get("/{photo_id}/original")
def get_original(photo_id: int, db: Session = Depends(get_db)):
    p = db.query(Photo).get(photo_id)
    if not p:
        raise HTTPException(404)
    src = Path(p.path)
    if not src.is_file():
        raise HTTPException(404, "Original file missing on disk")
    # Read-only serving; we never modify it.
    return FileResponse(src)
