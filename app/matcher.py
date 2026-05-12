"""Match a new face embedding against known people."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np
from sqlalchemy.orm import Session

from .config import settings
from .face_engine import bytes_to_emb, cosine_matrix
from .models import Face, Person, Suggestion

log = logging.getLogger(__name__)


@dataclass
class PersonIndex:
    person_ids: np.ndarray  # shape (N,), one per row of embeddings
    embeddings: np.ndarray  # shape (N, 512), L2-normalized


def build_person_index(db: Session) -> Optional[PersonIndex]:
    """All confirmed faces for all people, used as reference set."""
    rows = (
        db.query(Face.person_id, Face.embedding)
        .filter(Face.person_id.isnot(None), Face.confirmed.is_(True), Face.hidden.is_(False))
        .all()
    )
    if not rows:
        return None
    pids = np.array([r[0] for r in rows], dtype=np.int64)
    embs = np.vstack([bytes_to_emb(r[1]) for r in rows]).astype(np.float32)
    return PersonIndex(person_ids=pids, embeddings=embs)


def best_per_person(query: np.ndarray, index: PersonIndex) -> list[tuple[int, float]]:
    """Return [(person_id, best_sim), ...] sorted by similarity desc."""
    sims = cosine_matrix(query, index.embeddings)  # shape (N,)
    out: dict[int, float] = {}
    for pid, s in zip(index.person_ids.tolist(), sims.tolist()):
        if s > out.get(pid, -1.0):
            out[pid] = s
    return sorted(out.items(), key=lambda x: x[1], reverse=True)


def assign_or_suggest(db: Session, face: Face, index: Optional[PersonIndex]) -> None:
    """Decide what to do with a newly-detected face.

    - If best similarity >= AUTO_MATCH_THRESHOLD: auto-assign (unconfirmed, user can revoke).
    - Else if best >= SUGGEST_THRESHOLD: create Suggestion(s) for top candidates.
    - Else: leave unassigned (becomes an "unknown" face).
    """
    if index is None or index.embeddings.size == 0:
        return
    q = bytes_to_emb(face.embedding)
    ranked = best_per_person(q, index)
    if not ranked:
        return
    top_pid, top_score = ranked[0]
    if top_score >= settings.auto_match_threshold:
        face.person_id = top_pid
        face.confirmed = False
        return
    if top_score >= settings.suggest_threshold:
        for pid, score in ranked[:3]:
            if score < settings.suggest_threshold:
                break
            existing = (
                db.query(Suggestion)
                .filter(Suggestion.face_id == face.id, Suggestion.person_id == pid)
                .one_or_none()
            )
            if existing is None:
                db.add(Suggestion(face_id=face.id, person_id=pid, score=float(score), status="pending"))


def recompute_suggestions_for_person(db: Session, person_id: int) -> int:
    """When a new person is created (or new confirmed faces added), scan unassigned
    faces and queue suggestions for ones that look similar. Returns count added."""
    refs = (
        db.query(Face.embedding)
        .filter(Face.person_id == person_id, Face.confirmed.is_(True), Face.hidden.is_(False))
        .all()
    )
    if not refs:
        return 0
    ref_arr = np.vstack([bytes_to_emb(r[0]) for r in refs]).astype(np.float32)

    candidates = (
        db.query(Face.id, Face.embedding)
        .filter(Face.person_id.is_(None), Face.hidden.is_(False))
        .all()
    )
    added = 0
    for fid, emb_bytes in candidates:
        q = bytes_to_emb(emb_bytes)
        sims = cosine_matrix(q, ref_arr)
        s = float(sims.max())
        if s < settings.suggest_threshold:
            continue
        existing = (
            db.query(Suggestion)
            .filter(Suggestion.face_id == fid, Suggestion.person_id == person_id)
            .one_or_none()
        )
        if existing is None:
            db.add(Suggestion(face_id=fid, person_id=person_id, score=s, status="pending"))
            added += 1
        elif existing.status == "pending" and s > existing.score:
            existing.score = s
    return added
