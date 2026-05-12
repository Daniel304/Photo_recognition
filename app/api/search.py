"""Search by filename and by visual similarity to a given face."""
from fastapi import APIRouter, Depends, HTTPException, Query
import numpy as np
from sqlalchemy.orm import Session

from ..clustering import cluster_unassigned
from ..config import settings
from ..database import get_db
from ..face_engine import bytes_to_emb, cosine_matrix
from ..models import Face, Photo
from .deps import require_api_key

router = APIRouter(prefix="/api/search", tags=["search"], dependencies=[Depends(require_api_key)])


@router.get("/similar/{face_id}")
def similar_faces(
    face_id: int,
    limit: int = Query(40, ge=1, le=200),
    unassigned_only: bool = False,
    db: Session = Depends(get_db),
):
    base = db.query(Face).get(face_id)
    if not base:
        raise HTTPException(404)
    q = bytes_to_emb(base.embedding)

    rows = db.query(Face.id, Face.person_id, Face.photo_id, Face.embedding, Face.confirmed).filter(
        Face.hidden.is_(False), Face.id != face_id
    )
    if unassigned_only:
        rows = rows.filter(Face.person_id.is_(None))
    rows = rows.all()
    if not rows:
        return []
    embs = np.vstack([bytes_to_emb(r[3]) for r in rows]).astype(np.float32)
    sims = cosine_matrix(q, embs)
    order = np.argsort(-sims)[: limit]
    out = []
    for i in order:
        fid, pid, photo_id, _, confirmed = rows[int(i)]
        out.append({
            "face_id": int(fid),
            "person_id": pid,
            "photo_id": int(photo_id),
            "score": float(sims[int(i)]),
            "confirmed": bool(confirmed),
        })
    return out


@router.post("/cluster-unassigned")
def cluster(eps: float = 0.40, min_samples: int = 3, db: Session = Depends(get_db)):
    return cluster_unassigned(db, eps=eps, min_samples=min_samples)


@router.get("/photos")
def search_photos(
    q: str | None = None,
    limit: int = Query(40, ge=1, le=200),
    db: Session = Depends(get_db),
):
    query = db.query(Photo).filter(Photo.missing.is_(False))
    if q:
        for term in q.split():
            query = query.filter(Photo.path.like(f"%{term}%"))
    rows = query.order_by(Photo.taken_at.desc().nullslast()).limit(limit).all()
    return [
        {"id": p.id, "path": p.path, "taken_at": p.taken_at.isoformat() if p.taken_at else None}
        for p in rows
    ]
