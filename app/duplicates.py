"""Group photos with similar perceptual hashes (near-duplicates)."""
from __future__ import annotations

from typing import Iterable

from sqlalchemy.orm import Session

from .models import Photo


def _popcount64(x: int) -> int:
    # Python 3.10+ supports int.bit_count(); fall back if needed.
    try:
        return x.bit_count()
    except AttributeError:
        return bin(x).count("1")


def find_duplicate_groups(db: Session, threshold: int = 8, limit: int = 5000) -> list[dict]:
    """Return groups of near-duplicate photos. Hamming distance <= threshold over 64-bit pHash."""
    rows = (
        db.query(Photo.id, Photo.phash, Photo.taken_at, Photo.path, Photo.width, Photo.height, Photo.size)
        .filter(Photo.phash.isnot(None), Photo.missing.is_(False))
        .limit(limit)
        .all()
    )
    n = len(rows)
    if n < 2:
        return []

    ids = [r[0] for r in rows]
    hashes = [int(r[1], 16) for r in rows]

    # Union-find on photo indices
    parent = list(range(n))
    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    # O(n^2) — fine for thousands. For 10k photos: ~50M xors; runs in seconds.
    for i in range(n):
        hi = hashes[i]
        for j in range(i + 1, n):
            if _popcount64(hi ^ hashes[j]) <= threshold:
                union(i, j)

    by_root: dict[int, list[int]] = {}
    for i in range(n):
        by_root.setdefault(find(i), []).append(i)

    out: list[dict] = []
    for members in by_root.values():
        if len(members) < 2:
            continue
        # Rank "primary" candidate by resolution then size, so the user knows which to keep.
        members.sort(key=lambda i: (
            -(rows[i][4] or 0) * (rows[i][5] or 0),
            -(rows[i][6] or 0),
        ))
        out.append({
            "primary_photo_id": ids[members[0]],
            "size": len(members),
            "photo_ids": [ids[i] for i in members],
        })
    out.sort(key=lambda g: -g["size"])
    return out
