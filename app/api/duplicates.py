from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..duplicates import find_duplicate_groups
from .deps import require_api_key

router = APIRouter(prefix="/api/duplicates", tags=["duplicates"], dependencies=[Depends(require_api_key)])


@router.get("")
def list_duplicates(
    threshold: int = Query(8, ge=0, le=24),
    limit: int = Query(5000, ge=10, le=20000),
    db: Session = Depends(get_db),
):
    """Returns groups of near-duplicate photos. Files are NEVER deleted server-side."""
    groups = find_duplicate_groups(db, threshold=threshold, limit=limit)
    return {"threshold": threshold, "groups": groups}
