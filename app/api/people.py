from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Integer, func
from sqlalchemy.orm import Session

from ..database import get_db
from ..matcher import recompute_suggestions_for_person
from ..models import Face, Person, Suggestion
from ..schemas import PersonCreate, PersonUpdate, MergeRequest
from .deps import require_api_key

router = APIRouter(prefix="/api/people", tags=["people"], dependencies=[Depends(require_api_key)])


def _person_to_dict(p: Person, face_count: int, confirmed_count: int) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "cover_face_id": p.cover_face_id,
        "notes": p.notes,
        "face_count": face_count,
        "confirmed_count": confirmed_count,
    }


@router.get("")
def list_people(db: Session = Depends(get_db)):
    rows = (
        db.query(
            Person,
            func.count(Face.id).label("face_count"),
            func.sum(func.cast(Face.confirmed, type_=Integer)).label("confirmed_count"),
        )
        .outerjoin(Face, (Face.person_id == Person.id) & (Face.hidden.is_(False)))
        .group_by(Person.id)
        .order_by(Person.name.asc())
        .all()
    )
    return [_person_to_dict(p, fc or 0, cc or 0) for p, fc, cc in rows]


@router.post("")
def create_person(body: PersonCreate, db: Session = Depends(get_db)):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "name required")
    existing = db.query(Person).filter(Person.name == name).one_or_none()
    if existing:
        raise HTTPException(409, "Person already exists")
    p = Person(name=name)
    db.add(p)
    db.commit()
    return _person_to_dict(p, 0, 0)


@router.get("/{person_id}")
def get_person(person_id: int, db: Session = Depends(get_db)):
    p = db.query(Person).get(person_id)
    if not p:
        raise HTTPException(404)
    face_count = db.query(Face).filter(Face.person_id == person_id, Face.hidden.is_(False)).count()
    confirmed_count = db.query(Face).filter(
        Face.person_id == person_id, Face.hidden.is_(False), Face.confirmed.is_(True)
    ).count()
    return _person_to_dict(p, face_count, confirmed_count)


@router.patch("/{person_id}")
def update_person(person_id: int, body: PersonUpdate, db: Session = Depends(get_db)):
    p = db.query(Person).get(person_id)
    if not p:
        raise HTTPException(404)
    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(400, "name cannot be empty")
        clash = db.query(Person).filter(Person.name == name, Person.id != p.id).one_or_none()
        if clash:
            raise HTTPException(409, "Another person already has that name")
        p.name = name
    if body.cover_face_id is not None:
        # verify the face belongs to this person
        f = db.query(Face).get(body.cover_face_id)
        if not f or f.person_id != p.id:
            raise HTTPException(400, "cover face must belong to this person")
        p.cover_face_id = body.cover_face_id
    if body.notes is not None:
        p.notes = body.notes
    db.commit()
    face_count = db.query(Face).filter(Face.person_id == p.id, Face.hidden.is_(False)).count()
    confirmed = db.query(Face).filter(Face.person_id == p.id, Face.confirmed.is_(True)).count()
    return _person_to_dict(p, face_count, confirmed)


@router.delete("/{person_id}")
def delete_person(person_id: int, db: Session = Depends(get_db)):
    p = db.query(Person).get(person_id)
    if not p:
        raise HTTPException(404)
    # unassign their faces but keep face records
    db.query(Face).filter(Face.person_id == p.id).update(
        {Face.person_id: None, Face.confirmed: False}, synchronize_session=False
    )
    db.query(Suggestion).filter(Suggestion.person_id == p.id).delete(synchronize_session=False)
    # clear cover ref before deleting (FK)
    p.cover_face_id = None
    db.flush()
    db.delete(p)
    db.commit()
    return {"ok": True}


@router.post("/{person_id}/rescan-suggestions")
def rescan_suggestions(person_id: int, db: Session = Depends(get_db)):
    p = db.query(Person).get(person_id)
    if not p:
        raise HTTPException(404)
    added = recompute_suggestions_for_person(db, person_id)
    db.commit()
    return {"added": added}


@router.post("/merge")
def merge(body: MergeRequest, db: Session = Depends(get_db)):
    if body.source_person_id == body.target_person_id:
        raise HTTPException(400, "source and target are the same")
    src = db.query(Person).get(body.source_person_id)
    tgt = db.query(Person).get(body.target_person_id)
    if not src or not tgt:
        raise HTTPException(404)
    db.query(Face).filter(Face.person_id == src.id).update(
        {Face.person_id: tgt.id}, synchronize_session=False
    )
    db.query(Suggestion).filter(Suggestion.person_id == src.id).delete(synchronize_session=False)
    src.cover_face_id = None
    db.flush()
    db.delete(src)
    db.commit()
    return {"ok": True, "target_id": tgt.id}
