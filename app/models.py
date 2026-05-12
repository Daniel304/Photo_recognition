from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey, LargeBinary, Index, Text, Boolean,
    UniqueConstraint,
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

    # User curation
    favorite = Column(Boolean, default=False, index=True)
    rating = Column(Integer, default=0, index=True)  # 0..5

    # Auto-extracted
    phash = Column(String(16), index=True)  # 64-bit perceptual hash, hex
    gps_lat = Column(Float)
    gps_lon = Column(Float)

    faces = relationship("Face", back_populates="photo", cascade="all, delete-orphan")
    album_links = relationship("PhotoAlbum", back_populates="photo", cascade="all, delete-orphan")
    event_links = relationship("PhotoEvent", back_populates="photo", cascade="all, delete-orphan")


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


class Album(Base):
    """User-curated collection: kind='album' for named albums (Vacation 2024),
    kind='tag' for free-form labels (kids, birthday). Same storage either way."""
    __tablename__ = "albums"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    kind = Column(String(16), default="album", index=True)  # album|tag
    color = Column(String(16))
    cover_photo_id = Column(Integer, ForeignKey("photos.id", ondelete="SET NULL"), nullable=True)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    photo_links = relationship("PhotoAlbum", back_populates="album", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("kind", "name", name="uq_album_kind_name"),
    )


class PhotoAlbum(Base):
    __tablename__ = "photo_albums"

    photo_id = Column(Integer, ForeignKey("photos.id", ondelete="CASCADE"), primary_key=True)
    album_id = Column(Integer, ForeignKey("albums.id", ondelete="CASCADE"), primary_key=True)
    added_at = Column(DateTime, default=datetime.utcnow)

    photo = relationship("Photo", back_populates="album_links")
    album = relationship("Album", back_populates="photo_links")


class Event(Base):
    """Auto-clustered group of photos taken close in time (and place, if GPS)."""
    __tablename__ = "events"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    start_at = Column(DateTime, index=True)
    end_at = Column(DateTime, index=True)
    gps_lat = Column(Float)
    gps_lon = Column(Float)
    cover_photo_id = Column(Integer, ForeignKey("photos.id", ondelete="SET NULL"))
    user_renamed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    photo_links = relationship("PhotoEvent", back_populates="event", cascade="all, delete-orphan")


class PhotoEvent(Base):
    __tablename__ = "photo_events"

    photo_id = Column(Integer, ForeignKey("photos.id", ondelete="CASCADE"), primary_key=True)
    event_id = Column(Integer, ForeignKey("events.id", ondelete="CASCADE"), primary_key=True)

    photo = relationship("Photo", back_populates="event_links")
    event = relationship("Event", back_populates="photo_links")


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
