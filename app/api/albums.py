from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Album, Photo, PhotoAlbum
from .deps import require_api_key

router = APIRouter(prefix="/api/albums", tags=["albums"], dependencies=[Depends(require_api_key)])


class AlbumCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    kind: str = Field(default="album", pattern="^(album|tag)$")
    color: str | None = None
    notes: str | None = None


class AlbumUpdate(BaseModel):
    name: str | None = None
    color: str | None = None
    notes: str | None = None
    cover_photo_id: int | None = None


def _to_dict(a: Album, count: int) -> dict:
    return {
        "id": a.id,
        "name": a.name,
        "kind": a.kind,
        "color": a.color,
        "notes": a.notes,
        "cover_photo_id": a.cover_photo_id,
        "photo_count": count,
    }


@router.get("")
def list_albums(kind: str | None = None, db: Session = Depends(get_db)):
    q = (
        db.query(Album, func.count(PhotoAlbum.photo_id))
        .outerjoin(PhotoAlbum, PhotoAlbum.album_id == Album.id)
        .group_by(Album.id)
        .order_by(Album.kind.asc(), Album.name.asc())
    )
    if kind is not None:
        q = q.filter(Album.kind == kind)
    return [_to_dict(a, c or 0) for a, c in q.all()]


@router.post("")
def create_album(body: AlbumCreate, db: Session = Depends(get_db)):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "name required")
    existing = db.query(Album).filter(Album.kind == body.kind, Album.name == name).one_or_none()
    if existing:
        raise HTTPException(409, "Album/tag with that name already exists")
    a = Album(name=name, kind=body.kind, color=body.color, notes=body.notes)
    db.add(a); db.commit()
    return _to_dict(a, 0)


@router.get("/{album_id}")
def get_album(album_id: int, db: Session = Depends(get_db)):
    a = db.query(Album).get(album_id)
    if not a:
        raise HTTPException(404)
    count = db.query(PhotoAlbum).filter(PhotoAlbum.album_id == album_id).count()
    return _to_dict(a, count)


@router.patch("/{album_id}")
def update_album(album_id: int, body: AlbumUpdate, db: Session = Depends(get_db)):
    a = db.query(Album).get(album_id)
    if not a:
        raise HTTPException(404)
    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(400, "name cannot be empty")
        clash = db.query(Album).filter(
            Album.kind == a.kind, Album.name == name, Album.id != a.id
        ).one_or_none()
        if clash:
            raise HTTPException(409, "Another album/tag has that name")
        a.name = name
    if body.color is not None:
        a.color = body.color
    if body.notes is not None:
        a.notes = body.notes
    if body.cover_photo_id is not None:
        if not db.query(Photo).get(body.cover_photo_id):
            raise HTTPException(400, "cover photo not found")
        link = db.query(PhotoAlbum).filter(
            PhotoAlbum.album_id == a.id, PhotoAlbum.photo_id == body.cover_photo_id
        ).one_or_none()
        if not link:
            raise HTTPException(400, "cover must be a photo in this album")
        a.cover_photo_id = body.cover_photo_id
    db.commit()
    count = db.query(PhotoAlbum).filter(PhotoAlbum.album_id == a.id).count()
    return _to_dict(a, count)


@router.delete("/{album_id}")
def delete_album(album_id: int, db: Session = Depends(get_db)):
    a = db.query(Album).get(album_id)
    if not a:
        raise HTTPException(404)
    db.delete(a); db.commit()
    return {"ok": True}


@router.post("/{album_id}/photos")
def add_photos(album_id: int, photo_ids: list[int] = Body(..., embed=True), db: Session = Depends(get_db)):
    a = db.query(Album).get(album_id)
    if not a:
        raise HTTPException(404)
    existing = {
        pid for (pid,) in db.query(PhotoAlbum.photo_id)
        .filter(PhotoAlbum.album_id == album_id, PhotoAlbum.photo_id.in_(photo_ids)).all()
    }
    added = 0
    for pid in photo_ids:
        if pid in existing:
            continue
        if not db.query(Photo).get(pid):
            continue
        db.add(PhotoAlbum(album_id=album_id, photo_id=pid))
        added += 1
    if a.cover_photo_id is None and photo_ids:
        for pid in photo_ids:
            if db.query(Photo).get(pid):
                a.cover_photo_id = pid
                break
    db.commit()
    return {"added": added}


@router.delete("/{album_id}/photos/{photo_id}")
def remove_photo(album_id: int, photo_id: int, db: Session = Depends(get_db)):
    db.query(PhotoAlbum).filter(
        PhotoAlbum.album_id == album_id, PhotoAlbum.photo_id == photo_id
    ).delete(synchronize_session=False)
    a = db.query(Album).get(album_id)
    if a and a.cover_photo_id == photo_id:
        next_link = db.query(PhotoAlbum).filter(PhotoAlbum.album_id == album_id).first()
        a.cover_photo_id = next_link.photo_id if next_link else None
    db.commit()
    return {"ok": True}


@router.get("/photo/{photo_id}")
def albums_for_photo(photo_id: int, db: Session = Depends(get_db)):
    """Which albums/tags contain a given photo (used by the lightbox)."""
    rows = (
        db.query(Album)
        .join(PhotoAlbum, PhotoAlbum.album_id == Album.id)
        .filter(PhotoAlbum.photo_id == photo_id)
        .order_by(Album.kind, Album.name)
        .all()
    )
    return [{"id": a.id, "name": a.name, "kind": a.kind, "color": a.color} for a in rows]
