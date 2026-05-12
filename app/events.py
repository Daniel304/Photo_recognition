"""Auto-cluster photos into events by date and (when available) GPS proximity."""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from .models import Event, Photo, PhotoEvent


EARTH_R_KM = 6371.0


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_R_KM * math.asin(math.sqrt(h))


def _format_event_name(start: datetime, end: datetime, has_gps: bool) -> str:
    days = (end.date() - start.date()).days
    if days == 0:
        d = start.strftime("%a %d %b %Y")
    elif start.month == end.month and start.year == end.year:
        d = f"{start.day}–{end.day} {start.strftime('%b %Y')}"
    elif start.year == end.year:
        d = f"{start.strftime('%d %b')} – {end.strftime('%d %b %Y')}"
    else:
        d = f"{start.strftime('%d %b %Y')} – {end.strftime('%d %b %Y')}"
    prefix = "Trip" if (days >= 1 and has_gps) else "Day"
    if days >= 2:
        prefix = "Trip"
    return f"{prefix}: {d}"


def rebuild_events(
    db: Session,
    max_gap_hours: float = 8.0,
    max_dist_km: float = 5.0,
    max_gap_no_gps_hours: float = 24.0,
    min_photos: int = 3,
) -> int:
    """Rebuild auto-events. Keeps user-renamed events' names; everything else is regenerated.

    Algorithm: walk photos in chronological order, start a new event when:
      - time gap > max_gap_no_gps_hours, OR
      - time gap > max_gap_hours AND last/current GPS differ by > max_dist_km.
    """
    photos = (
        db.query(Photo)
        .filter(Photo.taken_at.isnot(None), Photo.missing.is_(False))
        .order_by(Photo.taken_at.asc())
        .all()
    )
    if not photos:
        return 0

    # Remember user-renamed names keyed by start_at so we can restore them.
    renamed: dict[datetime, str] = {
        e.start_at: e.name for e in db.query(Event).filter(Event.user_renamed.is_(True)).all()
    }

    db.query(PhotoEvent).delete(synchronize_session=False)
    db.query(Event).delete(synchronize_session=False)
    db.flush()

    groups: list[list[Photo]] = []
    current: list[Photo] = []
    last_loc: Optional[tuple[float, float]] = None

    for p in photos:
        if current:
            prev = current[-1]
            gap_h = (p.taken_at - prev.taken_at).total_seconds() / 3600.0
            cur_loc = (p.gps_lat, p.gps_lon) if p.gps_lat is not None and p.gps_lon is not None else None
            far = False
            if cur_loc and last_loc:
                far = haversine_km(cur_loc, last_loc) > max_dist_km
            split = gap_h > max_gap_no_gps_hours or (gap_h > max_gap_hours and (far or not cur_loc and not last_loc))
            if split:
                groups.append(current)
                current = []
                last_loc = None
        current.append(p)
        if p.gps_lat is not None and p.gps_lon is not None:
            last_loc = (p.gps_lat, p.gps_lon)
    if current:
        groups.append(current)

    created = 0
    for grp in groups:
        if len(grp) < min_photos:
            continue
        gps_pts = [(g.gps_lat, g.gps_lon) for g in grp if g.gps_lat is not None and g.gps_lon is not None]
        avg_lat = sum(x for x, _ in gps_pts) / len(gps_pts) if gps_pts else None
        avg_lon = sum(y for _, y in gps_pts) / len(gps_pts) if gps_pts else None
        start = grp[0].taken_at
        end = grp[-1].taken_at
        cover = grp[len(grp) // 2].id  # middle-ish photo as cover
        name = renamed.get(start) or _format_event_name(start, end, bool(gps_pts))
        ev = Event(
            name=name,
            start_at=start,
            end_at=end,
            gps_lat=avg_lat,
            gps_lon=avg_lon,
            cover_photo_id=cover,
            user_renamed=(start in renamed),
        )
        db.add(ev)
        db.flush()
        for p in grp:
            db.add(PhotoEvent(event_id=ev.id, photo_id=p.id))
        created += 1
    db.commit()
    return created
