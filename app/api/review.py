"""Swipe-left/right review queue: pending suggestions where AI isn't sure."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..matcher import recompute_suggestions_for_person
from ..models import Face, Person, Suggestion
from .deps import require_api_key

router = APIRouter(prefix="/api/review", tags=["review"], dependencies=[Depends(require_api_key)])


@router.get("/suggestions")
def list_suggestions(
    person_id: int | None = None,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    q = (
        db.query(Suggestion, Face, Person)
        .join(Face, Face.id == Suggestion.face_id)
        .join(Person, Person.id == Suggestion.person_id)
        .filter(Suggestion.status == "pending", Face.hidden.is_(False), Face.person_id.is_(None))
    )
    if person_id is not None:
        q = q.filter(Suggestion.person_id == person_id)
    q = q.order_by(Suggestion.score.desc())
    items = q.limit(limit).all()

    return [
        {
            "id": s.id,
            "face_id": f.id,
            "photo_id": f.photo_id,
            "person_id": p.id,
            "person_name": p.name,
            "person_cover_face_id": p.cover_face_id,
            "score": s.score,
            "bbox": [f.bbox_x, f.bbox_y, f.bbox_w, f.bbox_h],
        }
        for s, f, p in items
    ]


@router.post("/suggestions/{sugg_id}/accept")
def accept(sugg_id: int, db: Session = Depends(get_db)):
    s = db.query(Suggestion).get(sugg_id)
    if not s:
        raise HTTPException(404)
    f = db.query(Face).get(s.face_id)
    if not f:
        raise HTTPException(404)
    f.person_id = s.person_id
    f.confirmed = True
    f.hidden = False
    s.status = "accepted"
    # remove conflicting suggestions for the same face
    db.query(Suggestion).filter(
        Suggestion.face_id == s.face_id, Suggestion.id != s.id, Suggestion.status == "pending"
    ).delete(synchronize_session=False)

    p = db.query(Person).get(s.person_id)
    if p and p.cover_face_id is None:
        p.cover_face_id = f.id

    added = recompute_suggestions_for_person(db, s.person_id)
    db.commit()
    return {"ok": True, "new_suggestions": added}


@router.post("/suggestions/{sugg_id}/reject")
def reject(sugg_id: int, db: Session = Depends(get_db)):
    """Swipe-left: not this person. Face stays unassigned, other suggestions remain."""
    s = db.query(Suggestion).get(sugg_id)
    if not s:
        raise HTTPException(404)
    s.status = "rejected"
    db.commit()
    return {"ok": True}


@router.post("/suggestions/{sugg_id}/skip")
def skip(sugg_id: int, db: Session = Depends(get_db)):
    """User unsure — remove from queue but don't decide. Re-suggestion may re-create later."""
    s = db.query(Suggestion).get(sugg_id)
    if not s:
        raise HTTPException(404)
    db.delete(s)
    db.commit()
    return {"ok": True}
