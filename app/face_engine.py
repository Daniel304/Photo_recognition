"""Wrapper around InsightFace for detection + 512-d embedding extraction."""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Optional

import numpy as np

from .config import settings

log = logging.getLogger(__name__)


class FaceEngine:
    _instance: Optional["FaceEngine"] = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._app = None
        self._load_lock = threading.Lock()

    @classmethod
    def get(cls) -> "FaceEngine":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _ensure_loaded(self):
        if self._app is not None:
            return
        with self._load_lock:
            if self._app is not None:
                return
            from insightface.app import FaceAnalysis

            log.info("Loading face model %s (this may download on first run)...", settings.face_model)
            app = FaceAnalysis(
                name=settings.face_model,
                root=str(settings.models_dir),
                allowed_modules=["detection", "recognition"],
                providers=["CPUExecutionProvider"],
            )
            app.prepare(ctx_id=-1, det_size=(640, 640))
            self._app = app
            log.info("Face model ready.")

    def detect(self, bgr: np.ndarray) -> list[dict]:
        """Return list of {bbox:(x,y,w,h), det_score, embedding(np.float32 512)} for one BGR image."""
        self._ensure_loaded()
        faces = self._app.get(bgr)
        out = []
        for f in faces:
            x1, y1, x2, y2 = [int(v) for v in f.bbox]
            x1 = max(0, x1); y1 = max(0, y1)
            w = max(0, x2 - x1); h = max(0, y2 - y1)
            if w < settings.min_face_size or h < settings.min_face_size:
                continue
            emb = f.normed_embedding.astype(np.float32)
            out.append({
                "bbox": (x1, y1, w, h),
                "det_score": float(f.det_score),
                "embedding": emb,
            })
        return out


def emb_to_bytes(emb: np.ndarray) -> bytes:
    return np.ascontiguousarray(emb, dtype=np.float32).tobytes()


def bytes_to_emb(b: bytes) -> np.ndarray:
    return np.frombuffer(b, dtype=np.float32)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    # Both are L2-normalized by insightface; dot is cosine.
    return float(np.dot(a, b))


def cosine_matrix(query: np.ndarray, refs: np.ndarray) -> np.ndarray:
    """query: (D,) or (N,D); refs: (M,D). Returns (N,M) or (M,)."""
    if query.ndim == 1:
        return refs @ query
    return query @ refs.T
