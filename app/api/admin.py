from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..indexer import Indexer
from ..models import Face, Person, Photo, ScanState, Suggestion
from ..schemas import ScanStatus
from .deps import require_api_key

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_api_key)])


@router.get("/status", response_model=ScanStatus)
def status(db: Session = Depends(get_db)):
    st = db.query(ScanState).get(1)
    if st is None:
        st = ScanState(id=1, status="idle")

    photo_count = db.query(Photo).filter(Photo.missing.is_(False)).count()
    face_count = db.query(Face).filter(Face.hidden.is_(False)).count()
    person_count = db.query(Person).count()
    unassigned = db.query(Face).filter(Face.person_id.is_(None), Face.hidden.is_(False)).count()
    pending = db.query(Suggestion).filter(Suggestion.status == "pending").count()

    return ScanStatus(
        status="scanning" if Indexer.get().is_running else st.status,
        last_started=st.last_started,
        last_finished=st.last_finished,
        last_error=st.last_error,
        files_total=st.files_total or 0,
        files_done=st.files_done or 0,
        files_added=st.files_added or 0,
        files_failed=st.files_failed or 0,
        photo_count=photo_count,
        face_count=face_count,
        person_count=person_count,
        unassigned_face_count=unassigned,
        pending_suggestions=pending,
    )


@router.post("/scan")
def trigger_scan():
    started = Indexer.get().start()
    if not started:
        raise HTTPException(409, "Scan already running")
    return {"started": True, "at": datetime.utcnow().isoformat()}


@router.post("/scan/cancel")
def cancel_scan():
    Indexer.get().cancel()
    return {"cancelling": True}
