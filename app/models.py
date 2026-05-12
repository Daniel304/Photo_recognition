from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey, LargeBinary, Index, Text, Boolean
)
from sqlalchemy.orm import relationship

from .database import Base


class Photo(Base):
    __tablename__ = "photos"

    id = Column(Integer, primary_key=True)
    path = Column(Text, unique=True, nullable=False)
    sha256 = Column(String(64), index=True)
    size = Column(Integer)
    mtime = Column(Float, index=True)
    width = Column(Integer)
    height = Column(Integer)
    taken_at = Column(DateTime, index=True)
    indexed_at = Column(DateTime, default=datetime.utcnow, index=True)
    error = Column(Text)
    missing = Column(Boolean, default=False, index=True)

    faces = relationship("Face", back_populates="photo", cascade="all, delete-orphan")


class Person(Base):
    __tablename__ = "people"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True, nullable=False, index=True)
    cover_face_id = Column(Integer, ForeignKey("faces.id", use_alter=True, name="fk_person_cover"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    notes = Column(Text)

    faces = relationship("Face", back_populates="person", foreign_keys="Face.person_id")


class Face(Base):
    __tablename__ = "faces"

    id = Column(Integer, primary_key=True)
    photo_id = Column(Integer, ForeignKey("photos.id", ondelete="CASCADE"), nullable=False, index=True)
    person_id = Column(Integer, ForeignKey("people.id", ondelete="SET NULL"), nullable=True, index=True)

    # bbox in source image coordinates
    bbox_x = Column(Integer)
    bbox_y = Column(Integer)
    bbox_w = Column(Integer)
    bbox_h = Column(Integer)

    det_score = Column(Float)
    # normalized 512-d embedding as float32 bytes (2048 bytes)
    embedding = Column(LargeBinary, nullable=False)
    thumb_path = Column(Text)

    # confirmed=True means user-approved; False means auto-assigned (can be revoked)
    confirmed = Column(Boolean, default=False, index=True)
    # If user rejected this face entirely (not a real face / ignore)
    hidden = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    photo = relationship("Photo", back_populates="faces")
    person = relationship("Person", back_populates="faces", foreign_keys=[person_id])

    __table_args__ = (
        Index("ix_faces_person_confirmed", "person_id", "confirmed"),
    )


class Suggestion(Base):
    """Queue of low/medium-confidence matches awaiting user swipe."""
    __tablename__ = "suggestions"

    id = Column(Integer, primary_key=True)
    face_id = Column(Integer, ForeignKey("faces.id", ondelete="CASCADE"), nullable=False, index=True)
    person_id = Column(Integer, ForeignKey("people.id", ondelete="CASCADE"), nullable=False, index=True)
    score = Column(Float, nullable=False)
    status = Column(String(16), default="pending", index=True)  # pending|accepted|rejected
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_suggestions_face_person", "face_id", "person_id", unique=True),
    )


class ScanState(Base):
    __tablename__ = "scan_state"

    id = Column(Integer, primary_key=True)
    status = Column(String(32), default="idle")  # idle|scanning|error
    last_started = Column(DateTime)
    last_finished = Column(DateTime)
    last_error = Column(Text)
    files_total = Column(Integer, default=0)
    files_done = Column(Integer, default=0)
    files_added = Column(Integer, default=0)
    files_failed = Column(Integer, default=0)
