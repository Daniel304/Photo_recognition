"""Image loading, EXIF, thumbnail helpers. Originals are never modified."""
from __future__ import annotations

import hashlib
import io
from datetime import datetime
from pathlib import Path
from typing import Optional

import imagehash
import numpy as np
from PIL import Image, ImageOps

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except Exception:
    pass

EXIF_DATETIME_TAGS = (36867, 36868, 306)  # DateTimeOriginal, DateTimeDigitized, DateTime
EXIF_GPS_TAG = 34853


def load_pil(path: Path) -> Image.Image:
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)
    return img.convert("RGB")


def pil_to_bgr(img: Image.Image) -> np.ndarray:
    arr = np.asarray(img)  # RGB
    return arr[:, :, ::-1].copy()  # BGR for insightface


def sha256_of(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def parse_exif_datetime(img: Image.Image) -> Optional[datetime]:
    try:
        exif = img.getexif()
    except Exception:
        return None
    if not exif:
        return None
    for tag in EXIF_DATETIME_TAGS:
        v = exif.get(tag)
        if not v:
            continue
        try:
            return datetime.strptime(str(v).strip(), "%Y:%m:%d %H:%M:%S")
        except Exception:
            continue
    return None


def _to_float(val) -> Optional[float]:
    try:
        if hasattr(val, "numerator") and hasattr(val, "denominator"):
            return val.numerator / val.denominator if val.denominator else None
        return float(val)
    except Exception:
        return None


def _dms_to_decimal(dms, ref: Optional[str]) -> Optional[float]:
    """EXIF GPS values are ((d_num,d_den),(m_num,m_den),(s_num,s_den)) or list of Rationals."""
    try:
        d = _to_float(dms[0]) or 0.0
        m = _to_float(dms[1]) or 0.0
        s = _to_float(dms[2]) or 0.0
    except Exception:
        return None
    dec = d + m / 60.0 + s / 3600.0
    if ref and ref.upper() in ("S", "W"):
        dec = -dec
    return dec


def parse_exif_gps(img: Image.Image) -> tuple[Optional[float], Optional[float]]:
    try:
        exif = img.getexif()
        gps = exif.get_ifd(EXIF_GPS_TAG) if exif else None
    except Exception:
        return (None, None)
    if not gps:
        return (None, None)
    lat = _dms_to_decimal(gps.get(2), gps.get(1))
    lon = _dms_to_decimal(gps.get(4), gps.get(3))
    if lat is None or lon is None:
        return (None, None)
    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        return (None, None)
    return (lat, lon)


def compute_phash(img: Image.Image) -> str:
    """64-bit perceptual hash as 16-char hex string."""
    return str(imagehash.phash(img))


def phash_distance(a: str, b: str) -> int:
    return (int(a, 16) ^ int(b, 16)).bit_count()


def save_thumbnail(img: Image.Image, dest: Path, max_size: int) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    t = img.copy()
    t.thumbnail((max_size, max_size), Image.LANCZOS)
    t.save(dest, format="JPEG", quality=85, optimize=True)


def save_face_crop(img: Image.Image, bbox: tuple[int, int, int, int], dest: Path, size: int, pad: float = 0.25) -> None:
    x, y, w, h = bbox
    px = int(w * pad); py = int(h * pad)
    left = max(0, x - px); top = max(0, y - py)
    right = min(img.width, x + w + px); bottom = min(img.height, y + h + py)
    crop = img.crop((left, top, right, bottom))
    crop.thumbnail((size, size), Image.LANCZOS)
    dest.parent.mkdir(parents=True, exist_ok=True)
    crop.save(dest, format="JPEG", quality=88, optimize=True)


def thumb_rel_path(photo_id: int) -> Path:
    bucket = f"{photo_id // 1000:04d}"
    return Path(bucket) / f"{photo_id}.jpg"


def face_rel_path(face_id: int) -> Path:
    bucket = f"{face_id // 1000:04d}"
    return Path(bucket) / f"{face_id}.jpg"
