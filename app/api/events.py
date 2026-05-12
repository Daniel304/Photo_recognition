from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..events import rebuild_events
from ..models import Event, Photo, PhotoEvent
from .deps import require_api_key

router = APIRouter(prefix="/api/events", tags=["events"], dependencies=[Depends(require_api_key)])


class EventUpdate(BaseModel):
    name: str | None = None
    cover_photo_id: int | None = None


def _to_dict(e: Event, count: int) -> dict:
    return {
        "id": e.id,
        "name": e.name,
        "start_at": e.start_at.isoformat() if e.start_at else None,
        "end_at": e.end_at.isoformat() if e.end_at else None,
        "gps_lat": e.gps_lat,
        "gps_lon": e.gps_lon,
        "cover_photo_id": e.cover_photo_id,
        "photo_count": count,
        "user_renamed": e.user_renamed,
    }


@router.get("")
def list_events(db: Session = Depends(get_db)):
    rows = (
        db.query(Event, func.count(PhotoEvent.photo_id))
        .outerjoin(PhotoEvent, PhotoEvent.event_id == Event.id)
        .group_by(Event.id)
        .order_by(Event.start_at.desc())
        .all()
    )
    return [_to_dict(e, c or 0) for e, c in rows]


@router.get("/{event_id}")
def get_event(event_id: int, db: Session = Depends(get_db)):
    e = db.query(Event).get(event_id)
    if not e:
        raise HTTPException(404)
    count = db.query(PhotoEvent).filter(PhotoEvent.event_id == event_id).count()
    return _to_dict(e, count)


@router.patch("/{event_id}")
def update_event(event_id: int, body: EventUpdate, db: Session = Depends(get_db)):
    e = db.query(Event).get(event_id)
    if not e:
        raise HTTPException(404)
    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(400, "name cannot be empty")
        e.name = name
        e.user_renamed = True
    if body.cover_photo_id is not None:
        link = db.query(PhotoEvent).filter(
            PhotoEvent.event_id == event_id, PhotoEvent.photo_id == body.cover_photo_id
        ).one_or_none()
        if not link:
            raise HTTPException(400, "cover must be a photo in this event")
        e.cover_photo_id = body.cover_photo_id
    db.commit()
    count = db.query(PhotoEvent).filter(PhotoEvent.event_id == e.id).count()
    return _to_dict(e, count)


@router.delete("/{event_id}")
def delete_event(event_id: int, db: Session = Depends(get_db)):
    e = db.query(Event).get(event_id)
    if not e:
        raise HTTPException(404)
    db.delete(e); db.commit()
    return {"ok": True}


@router.post("/rebuild")
def rebuild(db: Session = Depends(get_db)):
    n = rebuild_events(db)
    return {"events": n}


@router.get("/{event_id}/gps")
def event_gps_points(event_id: int, db: Session = Depends(get_db)):
    rows = (
        db.query(Photo.id, Photo.gps_lat, Photo.gps_lon)
        .join(PhotoEvent, PhotoEvent.photo_id == Photo.id)
        .filter(PhotoEvent.event_id == event_id, Photo.gps_lat.isnot(None))
        .all()
    )
    return [{"photo_id": pid, "lat": lat, "lon": lon} for pid, lat, lon in rows]
