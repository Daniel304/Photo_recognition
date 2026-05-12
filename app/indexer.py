"""Background filesystem indexer. Walks PHOTO_ROOT recursively, detects faces, never modifies originals."""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from .config import settings
from .database import session_scope
from .face_engine import FaceEngine, emb_to_bytes
from .image_utils import (
    face_rel_path,
    load_pil,
    parse_exif_datetime,
    pil_to_bgr,
    save_face_crop,
    save_thumbnail,
    thumb_rel_path,
)
from .matcher import assign_or_suggest, build_person_index
from .models import Face, Photo, ScanState

log = logging.getLogger(__name__)


def _iter_files(root: Path, exts: set[str]) -> Iterable[Path]:
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d != "@eaDir"]
        for name in filenames:
            if name.startswith("."):
                continue
            p = Path(dirpath) / name
            if p.suffix.lower() in exts:
                yield p


def _get_or_create_state(db: Session) -> ScanState:
    st = db.query(ScanState).get(1)
    if st is None:
        st = ScanState(id=1, status="idle")
        db.add(st)
        db.flush()
    return st


def _process_photo(db: Session, path: Path, engine: FaceEngine, person_index) -> tuple[bool, int]:
    """Index a single photo. Returns (added, face_count)."""
    rel = str(path)
    stat = path.stat()
    existing = db.query(Photo).filter(Photo.path == rel).one_or_none()
    if existing is not None:
        # Already indexed: only re-process if mtime/size changed
        if existing.mtime == stat.st_mtime and existing.size == stat.st_size and not existing.error:
            if existing.missing:
                existing.missing = False
            return (False, len(existing.faces))
        # Changed: delete old faces and re-index
        for f in list(existing.faces):
            db.delete(f)
        db.flush()
        photo = existing
        photo.error = None
        photo.missing = False
    else:
        photo = Photo(path=rel)
        db.add(photo)

    try:
        pil = load_pil(path)
    except Exception as e:
        photo.error = f"open: {e}"
        photo.size = stat.st_size
        photo.mtime = stat.st_mtime
        photo.indexed_at = datetime.utcnow()
        db.flush()
        return (existing is None, 0)

    photo.size = stat.st_size
    photo.mtime = stat.st_mtime
    photo.width = pil.width
    photo.height = pil.height
    photo.taken_at = parse_exif_datetime(pil)
    photo.indexed_at = datetime.utcnow()
    db.flush()  # get photo.id

    # Thumbnail (stored in /data/thumbs)
    try:
        save_thumbnail(pil, settings.thumbs_dir / thumb_rel_path(photo.id), settings.thumb_size)
    except Exception as e:
        log.warning("thumbnail failed for %s: %s", path, e)

    # Faces
    try:
        bgr = pil_to_bgr(pil)
        detections = engine.detect(bgr)
    except Exception as e:
        photo.error = f"detect: {e}"
        db.flush()
        return (existing is None, 0)

    for det in detections:
        face = Face(
            photo_id=photo.id,
            bbox_x=det["bbox"][0],
            bbox_y=det["bbox"][1],
            bbox_w=det["bbox"][2],
            bbox_h=det["bbox"][3],
            det_score=det["det_score"],
            embedding=emb_to_bytes(det["embedding"]),
        )
        db.add(face)
        db.flush()  # face.id
        rel_face = face_rel_path(face.id)
        try:
            save_face_crop(pil, det["bbox"], settings.faces_dir / rel_face, settings.face_thumb_size)
            face.thumb_path = str(rel_face)
        except Exception as e:
            log.warning("face crop failed for %s: %s", path, e)
        assign_or_suggest(db, face, person_index)

    return (existing is None, len(detections))


class Indexer:
    _instance: Optional["Indexer"] = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._auto_thread: Optional[threading.Thread] = None
        self._cancel = threading.Event()

    @classmethod
    def get(cls) -> "Indexer":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> bool:
        if self.is_running:
            return False
        self._cancel.clear()
        self._thread = threading.Thread(target=self._run, name="indexer", daemon=True)
        self._thread.start()
        return True

    def cancel(self) -> None:
        self._cancel.set()

    def start_auto_loop(self) -> None:
        if settings.scan_interval <= 0:
            return
        if self._auto_thread and self._auto_thread.is_alive():
            return

        def loop():
            # initial delay so the API is responsive first
            time.sleep(5)
            while not self._stop.is_set():
                if not self.is_running:
                    log.info("Auto scan triggered.")
                    self.start()
                # wait for current scan + interval
                self._stop.wait(settings.scan_interval)

        self._auto_thread = threading.Thread(target=loop, name="indexer-auto", daemon=True)
        self._auto_thread.start()

    def shutdown(self) -> None:
        self._stop.set()
        self._cancel.set()

    def _run(self) -> None:
        log.info("Indexer started; root=%s", settings.photo_root)
        engine = FaceEngine.get()
        added = failed = done = 0
        with session_scope() as db:
            st = _get_or_create_state(db)
            st.status = "scanning"
            st.last_started = datetime.utcnow()
            st.last_error = None
            st.files_total = 0
            st.files_done = 0
            st.files_added = 0
            st.files_failed = 0
        try:
            if not settings.photo_root.exists():
                raise RuntimeError(f"PHOTO_ROOT does not exist: {settings.photo_root}")

            files = list(_iter_files(settings.photo_root, settings.extensions))
            total = len(files)
            with session_scope() as db:
                st = _get_or_create_state(db)
                st.files_total = total

            seen_paths: set[str] = set()
            # Refresh person_index occasionally so newly-confirmed faces feed back in.
            with session_scope() as db:
                person_index = build_person_index(db)

            BATCH = 25
            for i in range(0, total, BATCH):
                if self._cancel.is_set():
                    log.info("Indexer cancelled.")
                    break
                batch = files[i : i + BATCH]
                with session_scope() as db:
                    for p in batch:
                        seen_paths.add(str(p))
                        try:
                            was_added, _ = _process_photo(db, p, engine, person_index)
                            if was_added:
                                added += 1
                        except Exception as e:
                            log.exception("failed to index %s", p)
                            failed += 1
                        done += 1
                    st = _get_or_create_state(db)
                    st.files_done = done
                    st.files_added = added
                    st.files_failed = failed
                # Periodically rebuild the person index so newly-named faces start matching.
                if (i // BATCH) % 4 == 3:
                    with session_scope() as db:
                        person_index = build_person_index(db)

            # Mark photos no longer present on disk
            with session_scope() as db:
                if not self._cancel.is_set():
                    all_paths = {r[0] for r in db.query(Photo.path).all()}
                    missing = all_paths - seen_paths
                    if missing:
                        db.query(Photo).filter(Photo.path.in_(list(missing))).update(
                            {Photo.missing: True}, synchronize_session=False
                        )
                st = _get_or_create_state(db)
                st.status = "idle"
                st.last_finished = datetime.utcnow()
        except Exception as e:
            log.exception("Indexer crashed")
            with session_scope() as db:
                st = _get_or_create_state(db)
                st.status = "error"
                st.last_error = str(e)
                st.last_finished = datetime.utcnow()
        log.info("Indexer finished. added=%d failed=%d done=%d", added, failed, done)
