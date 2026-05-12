from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import Face, Person, Suggestion
from ..schemas import AssignRequest
from ..matcher import recompute_suggestions_for_person
from .deps import require_api_key

router = APIRouter(prefix="/api/faces", tags=["faces"], dependencies=[Depends(require_api_key)])


@router.get("")
def list_faces(
    person_id: int | None = None,
    unassigned: bool = False,
    confirmed: bool | None = None,
    hidden: bool = False,
    limit: int = Query(60, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    q = db.query(Face).filter(Face.hidden.is_(hidden))
    if unassigned:
        q = q.filter(Face.person_id.is_(None))
    elif person_id is not None:
        q = q.filter(Face.person_id == person_id)
    if confirmed is not None:
        q = q.filter(Face.confirmed.is_(confirmed))
    q = q.order_by(Face.det_score.desc().nullslast(), Face.id.desc())
    total = q.count()
    items = q.offset(offset).limit(limit).all()
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": [
            {
                "id": f.id,
                "photo_id": f.photo_id,
                "person_id": f.person_id,
                "person_name": f.person.name if f.person else None,
                "bbox": [f.bbox_x, f.bbox_y, f.bbox_w, f.bbox_h],
                "det_score": f.det_score,
                "confirmed": f.confirmed,
            }
            for f in items
        ],
    }


@router.get("/{face_id}/thumb")
def face_thumb(face_id: int, db: Session = Depends(get_db)):
    f = db.query(Face).get(face_id)
    if not f or not f.thumb_path:
        raise HTTPException(404)
    path = settings.faces_dir / f.thumb_path
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path, media_type="image/jpeg")


@router.post("/{face_id}/assign")
def assign(face_id: int, body: AssignRequest, db: Session = Depends(get_db)):
    f = db.query(Face).get(face_id)
    if not f:
        raise HTTPException(404)

    person: Person | None = None
    if body.person_id is not None:
        person = db.query(Person).get(body.person_id)
    elif body.person_name:
        person = db.query(Person).filter(Person.name == body.person_name).one_or_none()
        if person is None:
            person = Person(name=body.person_name)
            db.add(person)
            db.flush()
    if person is None:
        raise HTTPException(400, "person_id or person_name required")

    f.person_id = person.id
    f.confirmed = body.confirmed
    f.hidden = False

    if person.cover_face_id is None:
        person.cover_face_id = f.id

    # remove pending suggestions for this face for OTHER people
    db.query(Suggestion).filter(Suggestion.face_id == f.id, Suggestion.person_id != person.id).delete(
        synchronize_session=False
    )
    # mark suggestion as accepted if it existed
    s = db.query(Suggestion).filter(Suggestion.face_id == f.id, Suggestion.person_id == person.id).one_or_none()
    if s:
        s.status = "accepted"

    added = recompute_suggestions_for_person(db, person.id)
    db.commit()
    return {"ok": True, "person_id": person.id, "new_suggestions": added}


@router.post("/{face_id}/unassign")
def unassign(face_id: int, db: Session = Depends(get_db)):
    f = db.query(Face).get(face_id)
    if not f:
        raise HTTPException(404)
    f.person_id = None
    f.confirmed = False
    db.commit()
    return {"ok": True}


@router.post("/{face_id}/hide")
def hide(face_id: int, db: Session = Depends(get_db)):
    """Mark a detection as not a real face (false positive) — kept in DB but ignored."""
    f = db.query(Face).get(face_id)
    if not f:
        raise HTTPException(404)
    f.hidden = True
    f.person_id = None
    db.query(Suggestion).filter(Suggestion.face_id == face_id).delete(synchronize_session=False)
    db.commit()
    return {"ok": True}


@router.post("/{face_id}/unhide")
def unhide(face_id: int, db: Session = Depends(get_db)):
    f = db.query(Face).get(face_id)
    if not f:
        raise HTTPException(404)
    f.hidden = False
    db.commit()
    return {"ok": True}
