from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class PersonOut(BaseModel):
    id: int
    name: str
    cover_face_id: Optional[int] = None
    face_count: int = 0
    confirmed_count: int = 0

    class Config:
        from_attributes = True


class PersonCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class PersonUpdate(BaseModel):
    name: Optional[str] = None
    cover_face_id: Optional[int] = None
    notes: Optional[str] = None


class FaceOut(BaseModel):
    id: int
    photo_id: int
    person_id: Optional[int]
    bbox: list[int]
    det_score: Optional[float]
    confirmed: bool
    hidden: bool

    class Config:
        from_attributes = True


class PhotoOut(BaseModel):
    id: int
    path: str
    width: Optional[int]
    height: Optional[int]
    taken_at: Optional[datetime]
    indexed_at: Optional[datetime]
    face_count: int = 0

    class Config:
        from_attributes = True


class SuggestionOut(BaseModel):
    id: int
    face_id: int
    person_id: int
    person_name: str
    score: float
    status: str


class ScanStatus(BaseModel):
    status: str
    last_started: Optional[datetime]
    last_finished: Optional[datetime]
    last_error: Optional[str]
    files_total: int
    files_done: int
    files_added: int
    files_failed: int
    photo_count: int
    face_count: int
    person_count: int
    unassigned_face_count: int
    pending_suggestions: int


class AssignRequest(BaseModel):
    person_id: Optional[int] = None
    person_name: Optional[str] = None
    confirmed: bool = True


class MergeRequest(BaseModel):
    source_person_id: int
    target_person_id: int
