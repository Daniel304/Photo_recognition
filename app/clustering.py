"""Cluster currently-unassigned faces so the user can name a group at once."""
from __future__ import annotations

from typing import Optional

import numpy as np
from sklearn.cluster import DBSCAN
from sqlalchemy.orm import Session

from .face_engine import bytes_to_emb
from .models import Face


def cluster_unassigned(db: Session, eps: float = 0.40, min_samples: int = 3, limit: int = 5000) -> list[dict]:
    """Run DBSCAN over unassigned faces (cosine distance ~= 1 - sim).

    Returns a list of clusters, each: {face_ids: [...], size: N, representative_face_id: int}.
    """
    rows = (
        db.query(Face.id, Face.embedding, Face.det_score)
        .filter(Face.person_id.is_(None), Face.hidden.is_(False))
        .order_by(Face.det_score.desc().nullslast())
        .limit(limit)
        .all()
    )
    if len(rows) < min_samples:
        return []

    ids = np.array([r[0] for r in rows], dtype=np.int64)
    embs = np.vstack([bytes_to_emb(r[1]) for r in rows]).astype(np.float32)
    scores = np.array([r[2] or 0.0 for r in rows], dtype=np.float32)

    db_clust = DBSCAN(eps=eps, min_samples=min_samples, metric="cosine", n_jobs=1)
    labels = db_clust.fit_predict(embs)

    clusters: dict[int, list[int]] = {}
    for idx, lab in enumerate(labels):
        if lab == -1:
            continue
        clusters.setdefault(int(lab), []).append(idx)

    out = []
    for lab, idxs in clusters.items():
        idxs.sort(key=lambda i: -scores[i])  # best-detected first
        rep = int(ids[idxs[0]])
        out.append({
            "cluster_id": lab,
            "size": len(idxs),
            "representative_face_id": rep,
            "face_ids": [int(ids[i]) for i in idxs],
        })
    out.sort(key=lambda c: -c["size"])
    return out
